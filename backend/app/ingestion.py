import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import Transaction

REQUIRED_COLUMNS = ["Transaction ID", "Date", "Description", "Counterparty", "Amount", "Method"]


def parse_file(file_path: str) -> pd.DataFrame:
    df = pd.read_excel(file_path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Uploaded file is missing required columns: {missing}")

    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df["Transaction ID"] = df["Transaction ID"].astype(str).str.strip()
    df["Description"] = df["Description"].astype(str).str.strip()
    df["Counterparty"] = df["Counterparty"].astype(str).str.strip()
    df["Method"] = df["Method"].astype(str).str.strip()

    bad_rows = df[df["Amount"].isna() | df["Date"].isna()]
    if not bad_rows.empty:
        raise ValueError(
            f"{len(bad_rows)} row(s) have an unparseable Date or Amount. "
            f"Transaction IDs: {bad_rows['Transaction ID'].tolist()}"
        )

    dupes = df[df["Transaction ID"].duplicated()]
    if not dupes.empty:
        raise ValueError(f"Duplicate Transaction IDs in file: {dupes['Transaction ID'].tolist()}")

    return df


def load_into_db(df: pd.DataFrame, db: Session) -> dict:
    inserted, skipped = 0, 0

    for _, row in df.iterrows():
        exists = db.query(Transaction).filter_by(transaction_id=row["Transaction ID"]).first()
        if exists:
            skipped += 1
            continue

        txn = Transaction(
            transaction_id=row["Transaction ID"],
            date=row["Date"],
            description=row["Description"],
            counterparty=row["Counterparty"],
            amount=float(row["Amount"]),
            method=row["Method"],
        )
        db.add(txn)
        inserted += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise

    return {"inserted": inserted, "skipped_duplicates": skipped, "total_in_file": len(df)}


def ingestion_summary(db: Session) -> dict:
    txns = db.query(Transaction).all()
    if not txns:
        return {"row_count": 0}

    dates = [t.date for t in txns]
    inflow = sum(t.amount for t in txns if t.amount > 0)
    outflow = sum(t.amount for t in txns if t.amount < 0)

    return {
        "row_count": len(txns),
        "date_range": [min(dates).isoformat(), max(dates).isoformat()],
        "total_inflow": round(inflow, 2),
        "total_outflow": round(outflow, 2),
        "net": round(inflow + outflow, 2),
    }
