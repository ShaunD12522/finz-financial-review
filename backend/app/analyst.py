"""
Step 6: Build an AI financial analyst.

Instead of asking Gemini to answer financial questions directly (which
risks it inventing plausible-sounding but wrong numbers), we give it a
small set of Python functions it can call to fetch REAL data computed
by the deterministic code from steps 3-5. Gemini decides which
function(s) a question needs, the SDK runs them automatically, and only
then does it write a natural-language answer -- grounded in real numbers
it just fetched, not numbers it guessed.
"""
import os

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app.pnl import compute_pnl, compute_category_breakdown
from app.variance import compute_variances, get_variance_evidence
from app.database import Transaction

MODEL = "gemini-3.1-flash-lite"

SYSTEM_INSTRUCTION = """You are a financial analyst assistant for a restaurant.
Answer questions using ONLY the data returned by the tools available to you.
Never invent, estimate, or calculate a number yourself -- always call a tool
to get real figures. If a question needs data you don't have a tool for,
say so honestly instead of guessing. Cite specific numbers, months, and
categories from the tool results in your answer. Keep answers concise
(2-4 sentences) unless the question needs a list."""


def _make_tools(db: Session):
    """Builds the tool functions for one request, bound to this request's
    database session via closure. The LLM only ever sees the parameters
    in each function's signature -- it never sees or controls `db`."""

    def get_pnl() -> list[dict]:
        """Returns the monthly Profit & Loss statement: revenue, COGS,
        gross profit, payroll, operating expenses, and operating profit
        for every month in the data. Use this for any question about
        revenue, profit, or overall financial performance for a month."""
        return compute_pnl(db)

    def get_category_breakdown(month: str) -> dict:
        """Returns the total amount for every category in one month
        (format: YYYY-MM, e.g. "2026-02"). Use this to see what made up
        revenue or expenses in a specific month."""
        return compute_category_breakdown(db, month)

    def get_variances() -> list[dict]:
        """Returns month-over-month P&L changes that were material
        (10% or more), with the top categories that drove each change.
        Use this for any question about why something changed between
        months, or what changed most significantly."""
        return compute_variances(db, explain=False)

    def get_transactions_needing_review() -> list[dict]:
        """Returns transactions currently flagged for human review
        (low-confidence classification, ambiguous accounting treatment,
        or statistically unusual amounts). Use this for questions like
        'which transactions need my attention'."""
        txns = db.query(Transaction).filter(Transaction.needs_review == True).all()  # noqa: E712
        return [
            {
                "transaction_id": t.transaction_id,
                "date": t.date.isoformat(),
                "description": t.description,
                "amount": t.amount,
                "category": t.category,
                "review_reason": t.review_reason,
            }
            for t in txns
        ]

    def get_transactions(category: str = "", month: str = "") -> list[dict]:
        """Returns individual P&L transactions, optionally filtered by
        exact category name and/or month (format YYYY-MM). Pass an empty
        string for a filter you don't need. Use this to show the specific
        transactions behind a category total or a variance."""
        query = db.query(Transaction).filter(Transaction.is_pnl == True)  # noqa: E712
        if category:
            query = query.filter(Transaction.category == category)
        txns = query.all()
        if month:
            txns = [t for t in txns if t.date.strftime("%Y-%m") == month]
        return [
            {
                "transaction_id": t.transaction_id,
                "date": t.date.isoformat(),
                "description": t.description,
                "counterparty": t.counterparty,
                "amount": t.amount,
                "category": t.category,
            }
            for t in txns
        ]

    def get_variance_transactions(month1: str, month2: str, category: str) -> dict:
        """Returns the actual transactions behind one category's change
        between two months (format YYYY-MM), to trace a variance back to
        its underlying evidence."""
        return get_variance_evidence(db, month1, month2, category)

    return [
        get_pnl,
        get_category_breakdown,
        get_variances,
        get_transactions_needing_review,
        get_transactions,
        get_variance_transactions,
    ]


def ask_analyst(db: Session, question: str) -> dict:
    """Sends the user's question to Gemini with tool access, and returns
    the answer plus which tools were actually called -- for transparency
    and traceability, so we can show an answer wasn't hallucinated."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    tools = _make_tools(db)

    response = client.models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tools,
        ),
    )

    tools_called = []
    if response.automatic_function_calling_history:
        for content in response.automatic_function_calling_history:
            if not content.parts:
                continue
            for part in content.parts:
                if part.function_call:
                    tools_called.append({
                        "tool": part.function_call.name,
                        "arguments": dict(part.function_call.args or {}),
                    })

    return {
        "question": question,
        "answer": response.text,
        "tools_called": tools_called,
    }
