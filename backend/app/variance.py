"""
Step 4: Find and explain variances.

Detecting a variance (this month vs last month changed by X%) is pure
math -- no AI needed. Explaining WHY it changed in plain English, given
the exact categories and numbers involved, is a good use of AI: it's
summarizing facts we already computed, not inventing or calculating
anything itself.
"""
from app.database import Transaction
from app.pnl import compute_pnl, compute_category_breakdown
from app.ai_client import call_gemini

MATERIALITY_PCT_THRESHOLD = 0.10  # 10% change vs prior month is "material"
LINE_ITEMS = ["revenue", "cogs", "gross_profit", "payroll", "operating_expenses", "operating_profit"]


def _pct_change(old, new):
    if old == 0:
        return None
    return (new - old) / abs(old)


def compute_month_pairs(db):
    """Returns consecutive (month1, month2) pairs from the P&L, oldest first."""
    pnl = compute_pnl(db)
    months = [p["month"] for p in pnl]
    pnl_by_month = {p["month"]: p for p in pnl}
    pairs = list(zip(months, months[1:]))
    return pairs, pnl_by_month


def compute_category_drivers(db, month1, month2, top_n=3):
    """Which categories moved the most between two months, ranked by
    absolute dollar change."""
    b1 = {c["category"]: c["total"] for c in compute_category_breakdown(db, month1)["categories"]}
    b2 = {c["category"]: c["total"] for c in compute_category_breakdown(db, month2)["categories"]}

    all_categories = set(b1) | set(b2)
    deltas = []
    for cat in all_categories:
        v1 = b1.get(cat, 0)
        v2 = b2.get(cat, 0)
        deltas.append({
            "category": cat,
            "month1_total": round(v1, 2),
            "month2_total": round(v2, 2),
            "delta": round(v2 - v1, 2),
        })

    deltas.sort(key=lambda d: abs(d["delta"]), reverse=True)
    return deltas[:top_n]


def explain_variance(month1, month2, material_items, drivers) -> str:
    """Asks Gemini to narrate the ALREADY-COMPUTED numbers in plain
    English. The model is explicitly told not to calculate anything --
    only to reference the figures given, so it can't invent numbers."""
    items_text = "\n".join(
        f"- {i['line_item'].replace('_', ' ').title()}: {i['month1_value']} -> {i['month2_value']} "
        f"({'+' if i['delta'] >= 0 else ''}{i['delta']}, {'+' if i['pct_change'] >= 0 else ''}{i['pct_change']}%)"
        for i in material_items
    )
    drivers_text = "\n".join(
        f"- {d['category']}: {d['month1_total']} -> {d['month2_total']} "
        f"({'+' if d['delta'] >= 0 else ''}{d['delta']})"
        for d in drivers
    )

    prompt = f"""You are a financial analyst explaining a month-over-month change to a restaurant owner.

Comparing {month1} to {month2}:

MATERIAL P&L CHANGES (already calculated, do not recompute):
{items_text}

TOP CATEGORY DRIVERS OF THIS CHANGE (already calculated, do not recompute):
{drivers_text}

Write a 2-3 sentence plain-English explanation of what changed and why, referencing the
specific categories and numbers given above. Do not invent any numbers not listed above.
Do not perform any calculations. Just explain what these already-computed figures mean."""

    return call_gemini(prompt)


def compute_variances(db, explain: bool = True):
    """Full step-4 pipeline: for each consecutive month pair, find which
    top-level P&L line items moved materially, identify the categories
    driving that move, and (optionally) get an AI-written explanation."""
    pairs, pnl_by_month = compute_month_pairs(db)
    variances = []

    for month1, month2 in pairs:
        p1, p2 = pnl_by_month[month1], pnl_by_month[month2]

        material_items = []
        for item in LINE_ITEMS:
            old, new = p1[item], p2[item]
            pct = _pct_change(old, new)
            if pct is not None and abs(pct) >= MATERIALITY_PCT_THRESHOLD:
                material_items.append({
                    "line_item": item,
                    "month1_value": old,
                    "month2_value": new,
                    "delta": round(new - old, 2),
                    "pct_change": round(pct * 100, 1),
                })

        if not material_items:
            continue

        drivers = compute_category_drivers(db, month1, month2)

        variance_entry = {
            "month1": month1,
            "month2": month2,
            "material_line_items": material_items,
            "top_category_drivers": drivers,
        }

        if explain:
            variance_entry["explanation"] = explain_variance(month1, month2, material_items, drivers)

        variances.append(variance_entry)

    return variances


def get_variance_evidence(db, month1: str, month2: str, category: str) -> dict:
    """The actual transactions behind one category's change between two
    months -- this is what lets a user go from a variance straight down
    to the underlying evidence."""
    txns = (
        db.query(Transaction)
        .filter(Transaction.category == category, Transaction.is_pnl == True)  # noqa: E712
        .all()
    )

    def to_dict(t):
        return {
            "transaction_id": t.transaction_id,
            "date": t.date.isoformat(),
            "description": t.description,
            "counterparty": t.counterparty,
            "amount": t.amount,
        }

    month1_txns = [to_dict(t) for t in txns if t.date.strftime("%Y-%m") == month1]
    month2_txns = [to_dict(t) for t in txns if t.date.strftime("%Y-%m") == month2]

    return {
        "category": category,
        "month1": month1,
        "month1_transactions": month1_txns,
        "month1_total": round(sum(t["amount"] for t in month1_txns), 2),
        "month2": month2,
        "month2_transactions": month2_txns,
        "month2_total": round(sum(t["amount"] for t in month2_txns), 2),
    }
