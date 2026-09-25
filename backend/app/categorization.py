"""
Step 2: Categorize & label transactions.

Strategy: instead of asking the AI to classify all 181 individual rows
(slow, expensive, and repeats the same judgment call many times), we
first reduce the data to its UNIQUE (description pattern, counterparty)
combinations — there are only ~35 of these, because things like weekly
POS deposits repeat every week with just the week number changing.

We classify those ~35 patterns once, then apply the result to every
matching transaction. This is a deterministic "fan-out" step, not an
AI step — the AI never sees or touches the actual dollar amounts.
"""
import json
import os
import re
import time

from google import genai
from sqlalchemy.orm import Session

from app.database import Transaction
from app.chart_of_accounts import chart_of_accounts_text, CATEGORY_NAMES, IS_PNL_BY_CATEGORY

CONFIDENCE_REVIEW_THRESHOLD = 0.8  # below this, a transaction is flagged needs_review


def normalize_description(description: str) -> str:
    """
    Collapse recurring weekly line items to one pattern.
    e.g. "POS batch deposit - food sales week 1" and "...week 7"
    both become "POS batch deposit - food sales week N".
    """
    return re.sub(r"week \d+", "week N", description, flags=re.IGNORECASE)


def get_unique_patterns(db: Session) -> list[dict]:
    """Find distinct (normalized description, counterparty) pairs that
    haven't been categorized yet."""
    uncategorized = db.query(Transaction).filter(Transaction.category.is_(None)).all()

    seen = {}
    for t in uncategorized:
        key = (normalize_description(t.description), t.counterparty)
        if key not in seen:
            seen[key] = {"desc_norm": key[0], "counterparty": key[1], "example_description": t.description}
    return list(seen.values())


def build_prompt(patterns: list[dict]) -> str:
    items = "\n".join(
        f'{i+1}. Description: "{p["example_description"]}" | Counterparty: "{p["counterparty"]}"'
        for i, p in enumerate(patterns)
    )
    return f"""You are classifying bank transaction line items for a restaurant's books into a fixed chart of accounts.

CHART OF ACCOUNTS (you must use EXACTLY one of these category names):
{chart_of_accounts_text()}

TRANSACTION PATTERNS TO CLASSIFY:
{items}

For EACH numbered pattern, return an object with:
- "index": the number from the list
- "category": ONLY the bare category name from the list above (e.g. "Rent", "Capital Expenditure") — do NOT include the group in parentheses, do NOT include "[NOT part of P&L]", do NOT include the description. Just the name itself, exactly as it appears before the first "(" character.
- "confidence": your confidence this category is correct, from 0.0 to 1.0
- "reasoning": one short sentence explaining why

Respond with ONLY a JSON array, no other text, no markdown code fences. Example format:
[{{"index": 1, "category": "Rent", "confidence": 0.98, "reasoning": "Description explicitly says Rent, paid to Landlord"}}]
"""


def normalize_category(raw_category: str) -> str | None:
    """
    Recover a valid category name even if the model added extra text
    (group names, annotations, etc.) around it. Tries, in order:
    1. Exact match against our chart of accounts.
    2. The raw text starts with a known category name (handles
       "Capital Expenditure (Non-P&L) [NOT part of P&L]" -> "Capital Expenditure").
    Returns None if nothing matches — caller must treat that as "needs review".
    """
    cleaned = raw_category.strip()

    if cleaned in CATEGORY_NAMES:
        return cleaned

    # Sort longest-first so a category name that is a prefix of a longer
    # one (not the case here, but a safe habit) doesn't match too eagerly.
    for name in sorted(CATEGORY_NAMES, key=len, reverse=True):
        if cleaned.startswith(name):
            return name

    return None


def classify_patterns_with_claude(patterns: list[dict]) -> dict:
    """Calls Gemini once with all patterns, returns a lookup keyed by
    (desc_norm, counterparty). Retries with exponential backoff on
    transient errors (e.g. 503 UNAVAILABLE under high demand)."""
    if not patterns:
        return {}

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    max_attempts = 4
    response = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=build_prompt(patterns),
            )
            break
        except Exception as e:
            if attempt == max_attempts:
                raise
            wait = 2 ** attempt  # 2s, 4s, 8s
            print(f"Gemini call failed (attempt {attempt}/{max_attempts}): {e}. Retrying in {wait}s...")
            time.sleep(wait)

    raw_text = response.text.strip()
    # Defensive: strip markdown fences if the model adds them anyway
    raw_text = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()

    try:
        results = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini did not return valid JSON: {e}\nRaw response: {raw_text[:500]}")

    lookup = {}
    for r in results:
        pattern = patterns[r["index"] - 1]
        key = (pattern["desc_norm"], pattern["counterparty"])
        category = normalize_category(r["category"])
        if category is None:
            print(f"REJECTED CATEGORY: Gemini said '{r['category']}' for '{pattern['example_description']}' "
                  f"— could not be matched to our chart of accounts even after normalization.")
        lookup[key] = {
            "category": category,
            "confidence": r.get("confidence", 0.0) if category else 0.0,
            "reasoning": r.get("reasoning", ""),
        }
    return lookup


def apply_categorization(db: Session, lookup: dict) -> dict:
    """Writes category/confidence/is_pnl/needs_review onto every matching
    uncategorized transaction."""
    uncategorized = db.query(Transaction).filter(Transaction.category.is_(None)).all()

    updated, unmatched = 0, 0
    for t in uncategorized:
        key = (normalize_description(t.description), t.counterparty)
        result = lookup.get(key)
        if not result or not result["category"]:
            t.needs_review = True
            unmatched += 1
            continue

        t.category = result["category"]
        t.category_confidence = result["confidence"]
        t.is_pnl = IS_PNL_BY_CATEGORY[result["category"]]
        t.needs_review = result["confidence"] < CONFIDENCE_REVIEW_THRESHOLD
        updated += 1

    db.commit()
    return {"categorized": updated, "flagged_for_review": unmatched}


def categorize_all(db: Session) -> dict:
    """Full step-2 pipeline: find patterns -> classify -> apply."""
    patterns = get_unique_patterns(db)
    lookup = classify_patterns_with_claude(patterns)
    result = apply_categorization(db, lookup)
    result["unique_patterns_classified"] = len(patterns)
    return result
