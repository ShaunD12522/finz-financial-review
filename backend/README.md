# FINZ AI-Native Financial Review

An AI-native financial review application that turns raw bank transactions into
an explainable monthly P&L, with AI-assisted categorization, automatic variance
detection, data-quality review flagging, and a conversational financial analyst.

Built for the FINZ Software Engineering Internship take-home challenge.

## Live app
https://finz-financial-review-l4zs.onrender.com/docs

## Architecture
backend/
├── app/
│ ├── main.py # FastAPI entry point, all API endpoints
│ ├── database.py # SQLAlchemy models (SQLite)
│ ├── ingestion.py # Step 1: parse & validate the raw transaction file
│ ├── chart_of_accounts.py # Fixed category list (Revenue/COGS/Payroll/OpEx/Non-P&L)
│ ├── categorization.py # Step 2: AI categorization + confidence flagging
│ ├── pnl.py # Step 3: deterministic P&L calculation (pandas)
│ ├── variance.py # Step 4: variance detection + AI explanation + evidence
│ ├── quality_checks.py # Step 5: statistical outlier / duplicate detection
│ ├── analyst.py # Step 6: AI analyst with tool-calling
│ └── ai_client.py # Shared Gemini-calling helper (retry/backoff)
├── data/raw_transactions.xlsx
└── requirements.txt
