"""
FINZ AI-Native Financial Review — API entry point.

Run with:
    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000/docs for interactive API docs.
"""
import shutil
import tempfile

from dotenv import load_dotenv
load_dotenv()  # reads .env into environment variables BEFORE anything reads os.environ

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.database import init_db, get_db, Transaction
from app.ingestion import parse_file, load_into_db, ingestion_summary
from app.categorization import categorize_all
from app.chart_of_accounts import CATEGORY_NAMES, IS_PNL_BY_CATEGORY
from app.pnl import compute_pnl, compute_category_breakdown
from app.variance import compute_variances, get_variance_evidence
from app.quality_checks import run_quality_checks
from app.analyst import ask_analyst
app = FastAPI(title="FINZ AI-Native Financial Review")


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a bank transaction .xlsx file. Safe to call multiple times."""
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx or .xls file")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        df = parse_file(tmp_path)
        result = load_into_db(df, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result["summary"] = ingestion_summary(db)
    return result


@app.get("/api/transactions")
def list_transactions(db: Session = Depends(get_db)):
    """List all ingested transactions (raw + any derived fields set so far)."""
    txns = db.query(Transaction).order_by(Transaction.date).all()
    return [
        {
            "transaction_id": t.transaction_id,
            "date": t.date.isoformat(),
            "description": t.description,
            "counterparty": t.counterparty,
            "amount": t.amount,
            "method": t.method,
            "category": t.category,
            "category_confidence": t.category_confidence,
            "is_pnl": t.is_pnl,
            "needs_review": t.needs_review,
        }
        for t in txns
    ]


@app.get("/api/summary")
def summary(db: Session = Depends(get_db)):
    """Quick sanity-check numbers for the ingested data."""
    return ingestion_summary(db)


@app.post("/api/categorize")
def categorize(db: Session = Depends(get_db)):
    """Classify every uncategorized transaction using Gemini, against the
    fixed chart of accounts. Safe to call repeatedly — already-categorized
    transactions are skipped."""
    try:
        return categorize_all(db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")


@app.get("/api/transactions/needs-review")
def transactions_needing_review(db: Session = Depends(get_db)):
    """Transactions flagged as low-confidence, unclassified, or a data-quality concern."""
    txns = db.query(Transaction).filter(Transaction.needs_review == True).all()  # noqa: E712
    return [
        {
            "transaction_id": t.transaction_id,
            "date": t.date.isoformat(),
            "description": t.description,
            "counterparty": t.counterparty,
            "amount": t.amount,
            "category": t.category,
            "category_confidence": t.category_confidence,
            "review_reason": t.review_reason,
        }
        for t in txns
    ]


class CategoryCorrection(BaseModel):
    category: str

class AnalystQuestion(BaseModel):
    question: str


@app.patch("/api/transactions/{transaction_id}/category")
def correct_category(transaction_id: str, body: CategoryCorrection, db: Session = Depends(get_db)):
    """User correction of a transaction's category (requirement: 'correct
    an incorrect classification and save the correction')."""
    if body.category not in CATEGORY_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown category. Must be one of: {CATEGORY_NAMES}")

    txn = db.query(Transaction).filter_by(transaction_id=transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.corrected_category = body.category
    txn.category = body.category
    txn.is_pnl = IS_PNL_BY_CATEGORY[body.category]
    txn.needs_review = False
    txn.reviewed = True
    db.commit()

    return {"transaction_id": transaction_id, "category": txn.category, "reviewed": True}
@app.get("/api/pnl")
def pnl(db: Session = Depends(get_db)):
    """Monthly Profit & Loss, computed deterministically from categorized
    transactions. No AI involved in this calculation."""
    return compute_pnl(db)


@app.get("/api/pnl/{month}/breakdown")
def pnl_breakdown(month: str, db: Session = Depends(get_db)):
    """Category-level detail for one month, e.g. /api/pnl/2026-02/breakdown"""
    return compute_category_breakdown(db, month)
@app.get("/api/variances")
def variances(db: Session = Depends(get_db)):
    """Month-over-month P&L variances that exceed a materiality threshold,
    with AI-written plain-English explanations of already-computed numbers."""
    try:
        return compute_variances(db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")
@app.get("/api/variances/evidence")
def variance_evidence(month1: str, month2: str, category: str, db: Session = Depends(get_db)):
    """The underlying transactions behind one category's change between
    two months, e.g. /api/variances/evidence?month1=2026-01&month2=2026-02&category=Payroll"""
    return get_variance_evidence(db, month1, month2, category)
@app.post("/api/quality-checks")
def quality_checks(db: Session = Depends(get_db)):
    """Runs deterministic data-quality checks (amount outliers, possible
    duplicates) and flags matching transactions for review."""
    return run_quality_checks(db)
@app.post("/api/ask")
def ask(body: AnalystQuestion, db: Session = Depends(get_db)):
    """Ask the AI financial analyst a question. It answers using only
    real data fetched via tool calls -- never invented numbers."""
    try:
        return ask_analyst(db, body.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")