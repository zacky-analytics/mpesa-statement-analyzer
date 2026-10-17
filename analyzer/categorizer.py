"""
categorizer.py - puts every transaction into exactly one category.

Rules (not case sensitive, first match wins):
  1. Fees                  - decided by Transaction.is_fee (cleaner.py)
  2. Reversals             - decided by Transaction.is_reversal (cleaner.py)
  3. Fuliza loans          - decided by Transaction.is_loan_draw / is_loan_repayment
  4. Exact PREFIX rules    - the Details text must START with the phrase
  5. Keyword rule          - 'airtime' anywhere in the text (only after the
                             prefix rules, because 'contains' is the weakest match)
  6. Uncategorized         - everything else. Never guessed, always shown.

Fee, reversal and Fuliza detection is NOT repeated here.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")

FEES = "Fees"
REVERSALS = "Reversals"
SENT = "Sent to people"
RECEIVED = "Received from people"
RECEIVED_BUSINESS = "Received from businesses"
BILLS = "Bills (Pay Bill)"
SHOPS = "Shops (Buy Goods)"
AIRTIME = "Airtime & bundles"
DEPOSITS = "Cash deposits"
WITHDRAWALS = "Cash withdrawals"
FULIZA_BORROWED = "Fuliza borrowed"
FULIZA_REPAID = "Fuliza repayments"
UNCATEGORIZED = "Uncategorized"

# Display order on the dashboard
CATEGORY_ORDER = [
    FEES, REVERSALS, SENT, RECEIVED, RECEIVED_BUSINESS, BILLS, SHOPS, AIRTIME, DEPOSITS, WITHDRAWALS,
    FULIZA_BORROWED, FULIZA_REPAID, UNCATEGORIZED,
]

# (prefix, category). Prefixes are lower case because matching ignores case.
PREFIX_RULES = [
    ("customer transfer to", SENT),
    ("customer transfer fuliza", SENT),            # sent using Fuliza money
    ("funds received from", RECEIVED),
    ("business payment from", RECEIVED_BUSINESS),   # banks and businesses paying in
    ("pay bill to", BILLS),
    ("sha customer insurance payment", BILLS),     # health insurance paybill
    ("pay bill fuliza", BILLS),                     # paid using Fuliza money
    ("pay bill online fuliza", BILLS),
    ("merchant payment to", SHOPS),
    ("merchant payment fuliza", SHOPS),
    ("customer payment to small business", SHOPS),
    ("customer bundle purchase", AIRTIME),
    ("deposit of funds at agent", DEPOSITS),
    ("customer withdrawal at agent", WITHDRAWALS),
]

AIRTIME_KEYWORD = "airtime"

# Categories that count as "spending" when ranking top categories.
# Fees are shown separately. Money coming in is not spending.
SPENDING_CATEGORIES = {SENT, BILLS, SHOPS, AIRTIME, WITHDRAWALS, UNCATEGORIZED}


@dataclass(frozen=True)
class CategoryTotal:
    category: str
    count: int
    money_in: Decimal
    money_out: Decimal


def categorize(transaction):
    if transaction.is_fee:
        return FEES
    if transaction.is_reversal:
        return REVERSALS
    if transaction.is_loan_draw:
        return FULIZA_BORROWED
    if transaction.is_loan_repayment:
        return FULIZA_REPAID

    text = " ".join(transaction.details.lower().split())

    for prefix, category in PREFIX_RULES:
        if text.startswith(prefix):
            return category

    if AIRTIME_KEYWORD in text:
        return AIRTIME

    return UNCATEGORIZED


def category_totals(transactions):
    """One entry per category that has at least one transaction, in display order."""
    counts = defaultdict(int)
    money_in = defaultdict(lambda: ZERO)
    money_out = defaultdict(lambda: ZERO)

    for t in transactions:
        category = categorize(t)
        counts[category] += 1
        money_in[category] += t.paid_in
        money_out[category] += t.paid_out

    return [
        CategoryTotal(c, counts[c], money_in[c], money_out[c])
        for c in CATEGORY_ORDER
        if counts[c] > 0
    ]


def top_spending_categories(transactions, count=5):
    """Biggest categories by money out. Fees, reversals and incoming money are excluded."""
    spending = [
        ct for ct in category_totals(transactions)
        if ct.category in SPENDING_CATEGORIES and ct.money_out > 0
    ]
    spending.sort(key=lambda ct: (-ct.money_out, ct.category))
    return spending[:count]


def uncategorized_rows(transactions):
    """Rows no rule matched. Shown to the user for review."""
    return [t for t in transactions if categorize(t) == UNCATEGORIZED]


def uncategorized_share(transactions):
    """
    Share of all money moved (in + out) that is uncategorized, from 0 to 1.
    Tells the user how much to trust the category charts.
    """
    total = sum((t.paid_in + t.paid_out for t in transactions), ZERO)
    if total == 0:
        return ZERO
    unknown = sum(
        (t.paid_in + t.paid_out for t in uncategorized_rows(transactions)), ZERO
    )
    return unknown / total
