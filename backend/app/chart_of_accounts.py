CATEGORIES = [
    # --- Revenue ---
    {"name": "Food Sales", "group": "Revenue", "is_pnl": True,
     "description": "Food sales rung through the POS system"},
    {"name": "Beverage Sales", "group": "Revenue", "is_pnl": True,
     "description": "Beverage/alcohol sales rung through the POS system"},
    {"name": "Catering Revenue", "group": "Revenue", "is_pnl": True,
     "description": "Payments from catering clients for catering events"},
    {"name": "Delivery Platform Revenue", "group": "Revenue", "is_pnl": True,
     "description": "Payouts from delivery marketplaces (DoorDash, Uber Eats) for orders"},
    {"name": "Gift Card Sales", "group": "Revenue", "is_pnl": True,
     "description": "Gift card sales deposits"},
    {"name": "Revenue Adjustments", "group": "Revenue", "is_pnl": True,
     "description": "Refunds and discounts that reduce revenue (contra-revenue, will be negative)"},

    # --- Cost of Goods Sold ---
    {"name": "Food COGS", "group": "COGS", "is_pnl": True,
     "description": "Food inventory purchases from suppliers"},
    {"name": "Beverage COGS", "group": "COGS", "is_pnl": True,
     "description": "Beverage/alcohol inventory purchases from suppliers"},

    # --- Payroll ---
    {"name": "Payroll", "group": "Payroll", "is_pnl": True,
     "description": "Wages, salaries, payroll taxes, and employee benefits"},

    # --- Operating Expenses ---
    {"name": "Rent", "group": "Operating Expenses", "is_pnl": True,
     "description": "Rent paid to landlord"},
    {"name": "Insurance", "group": "Operating Expenses", "is_pnl": True,
     "description": "Business insurance premiums"},
    {"name": "Software & Subscriptions", "group": "Operating Expenses", "is_pnl": True,
     "description": "POS system, software subscriptions"},
    {"name": "Utilities", "group": "Operating Expenses", "is_pnl": True,
     "description": "Electric, gas, water, internet, phone"},
    {"name": "Marketing", "group": "Operating Expenses", "is_pnl": True,
     "description": "Advertising and marketing spend"},
    {"name": "Repairs & Maintenance", "group": "Operating Expenses", "is_pnl": True,
     "description": "Equipment repairs, facility maintenance"},
    {"name": "Professional Services", "group": "Operating Expenses", "is_pnl": True,
     "description": "Accounting, bookkeeping, legal, consulting fees"},
    {"name": "Supplies", "group": "Operating Expenses", "is_pnl": True,
     "description": "Packaging, disposables, cleaning/linen service, office/admin supplies"},
    {"name": "Delivery Platform Fees", "group": "Operating Expenses", "is_pnl": True,
     "description": "Commission charged by delivery marketplaces"},
    {"name": "Licenses & Permits", "group": "Operating Expenses", "is_pnl": True,
     "description": "Business licenses, permit renewals"},

    # --- Non-P&L (real money, but not operating income/expense) ---
    {"name": "Capital Expenditure", "group": "Non-P&L", "is_pnl": False,
     "description": "Purchases of equipment/fixed assets (belongs on the balance sheet, depreciated over time, not expensed immediately)"},
    {"name": "Debt Financing", "group": "Non-P&L", "is_pnl": False,
     "description": "Loan principal repayments (paying down debt, not an operating expense)"},
    {"name": "Owner's Equity", "group": "Non-P&L", "is_pnl": False,
     "description": "Owner draws/distributions (not a business expense)"},
    {"name": "Tax Remittance", "group": "Non-P&L", "is_pnl": False,
     "description": "Sales tax collected from customers and remitted to the government (a liability pass-through, not the business's own expense)"},
]

CATEGORY_NAMES = [c["name"] for c in CATEGORIES]
IS_PNL_BY_CATEGORY = {c["name"]: c["is_pnl"] for c in CATEGORIES}


def chart_of_accounts_text() -> str:
    """Render the chart of accounts as text for the AI prompt."""
    lines = []
    for c in CATEGORIES:
        pnl_note = "" if c["is_pnl"] else " [NOT part of P&L]"
        lines.append(f"- {c['name']} ({c['group']}){pnl_note}: {c['description']}")
    return "\n".join(lines)
