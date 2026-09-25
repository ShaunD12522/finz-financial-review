"""
Step 5 (remaining piece): flag transactions with unusual or inconsistent
data -- statistical outliers within a category, and exact-duplicate-looking
transactions. This is deterministic pattern detection, not AI: an amount
being 2.5 standard deviations from its category's average is a fact you
can compute, not something that benefits from an AI's judgment.
"""
import statistics
from collections import defaultdict

from sqlalchemy.orm import Session
from app.database import Transaction

Z_SCORE_THRESHOLD = 2.5
MIN_CATEGORY_SIZE = 4  # need at least this many transactions in a category
                        # before "average" is statistically meaningful


def detect_amount_outliers(db: Session) -> list[dict]:
    """Flags transactions whose amount is a statistical outlier relative
    to other transactions in the same category."""
    txns = db.query(Transaction).filter(Transaction.category.isnot(None)).all()

    by_category = defaultdict(list)
    for t in txns:
        by_category[t.category].append(t)

    flags = []
    for category, items in by_category.items():
        if len(items) < MIN_CATEGORY_SIZE:
            continue

        amounts = [abs(t.amount) for t in items]
        mean = statistics.mean(amounts)
        stdev = statistics.pstdev(amounts)
        if stdev == 0:
            continue

        for t in items:
            z = (abs(t.amount) - mean) / stdev
            if abs(z) >= Z_SCORE_THRESHOLD:
                flags.append({
                    "transaction_id": t.transaction_id,
                    "reason": (
                        f"Unusually {'large' if z > 0 else 'small'} amount for category "
                        f"'{category}': ${abs(t.amount):,.2f} vs. category average ${mean:,.2f} "
                        f"(z-score {z:.2f})"
                    ),
                })

    return flags


def detect_duplicate_transactions(db: Session) -> list[dict]:
    """Flags transactions that share the same date, counterparty, and
    amount as another transaction -- a common sign of an accidental
    double entry or double charge."""
    txns = db.query(Transaction).all()

    groups = defaultdict(list)
    for t in txns:
        groups[(t.date, t.counterparty, t.amount)].append(t)

    flags = []
    for (date, counterparty, amount), items in groups.items():
        if len(items) > 1:
            ids = [t.transaction_id for t in items]
            for t in items:
                others = [i for i in ids if i != t.transaction_id]
                flags.append({
                    "transaction_id": t.transaction_id,
                    "reason": (
                        f"Possible duplicate: same date ({date}), counterparty "
                        f"('{counterparty}'), and amount (${amount:,.2f}) as {', '.join(others)}"
                    ),
                })

    return flags


def run_quality_checks(db: Session) -> dict:
    """Runs all data-quality checks and flags matching transactions for
    review. Skips transactions a human has already explicitly reviewed
    (reviewed=True), since those were already looked at."""
    all_flags = detect_amount_outliers(db) + detect_duplicate_transactions(db)

    flagged_count = 0
    for flag in all_flags:
        txn = db.query(Transaction).filter_by(transaction_id=flag["transaction_id"]).first()
        if txn is None or txn.reviewed:
            continue
        txn.needs_review = True
        txn.review_reason = flag["reason"]
        flagged_count += 1

    db.commit()
    return {"quality_flags_found": len(all_flags), "transactions_flagged": flagged_count}
