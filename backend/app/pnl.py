"""
Step 3: Build the P&L.

Pure deterministic computation — no AI involved. Pandas aggregates
transactions already categorized in step 2 into a monthly Profit & Loss.
This is the "single source of truth" for every dollar figure the rest
of the app (variance detection, the AI analyst) will ever display.
"""
import pandas as pd
from sqlalchemy.orm import Session

from app.database import Transaction
from app.chart_of_accounts import CATEGORIES

# Map each category name to its higher-level P&L group, e.g.
# "Food Sales" -> "Revenue", "Rent" -> "Operating Expenses"
GROUP_BY_CATEGORY = {c["name"]: c["group"] for c in CATEGORIES}


def _transactions_to_dataframe(db: Session) -> pd.DataFrame:
    """Pull only P&L-relevant transactions into a DataFrame, with a
    'month' and 'group' column ready for aggregation."""
    txns = db.query(Transaction).filter(Transaction.is_pnl == True).all()  # noqa: E712

    rows = [
        {
            "month": t.date.strftime("%Y-%m"),
            "category": t.category,
            "group": GROUP_BY_CATEGORY.get(t.category, "Unknown"),
            "amount": t.amount,
        }
        for t in txns
    ]
    return pd.DataFrame(rows)


def compute_pnl(db: Session) -> list[dict]:
    """Returns one P&L object per month, sorted chronologically."""
    df = _transactions_to_dataframe(db)
    if df.empty:
        return []

    # Sum amounts by month + group. Revenue lines are positive in the
    # bank data, expense lines are negative — we take absolute value for
    # display so "Payroll: 45000" reads naturally, not "-45000".
    grouped = df.groupby(["month", "group"])["amount"].sum().unstack(fill_value=0)

    months = sorted(grouped.index.tolist())
    result = []

    for month in months:
        revenue = grouped.loc[month].get("Revenue", 0)
        cogs = abs(grouped.loc[month].get("COGS", 0))
        payroll = abs(grouped.loc[month].get("Payroll", 0))
        opex = abs(grouped.loc[month].get("Operating Expenses", 0))

        gross_profit = revenue - cogs
        operating_profit = gross_profit - payroll - opex

        result.append({
            "month": month,
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "payroll": round(payroll, 2),
            "operating_expenses": round(opex, 2),
            "operating_profit": round(operating_profit, 2),
        })

    return result


def compute_category_breakdown(db: Session, month: str) -> dict:
    """Detail view: every category's total for one month (YYYY-MM),
    used later so the AI analyst / variance step can drill from a
    P&L line down to which categories drove it."""
    df = _transactions_to_dataframe(db)
    if df.empty:
        return {"month": month, "categories": []}

    month_df = df[df["month"] == month]
    by_category = month_df.groupby("category")["amount"].sum().round(2)

    return {
        "month": month,
        "categories": [
            {"category": cat, "total": amt}
            for cat, amt in by_category.items()
        ],
    }
