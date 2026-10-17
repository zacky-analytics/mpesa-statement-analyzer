"""
metrics.py - calculates the numbers shown on the dashboard.

Rules:
- All money is Decimal.
- Fees are counted separately, but they stay INSIDE total money out.
  money_out = spending + fees + reversals_out + loans_repaid
- Reversal rows are never counted as fees or spending. They get their own line.
- Fuliza rows are loans: money borrowed (loans_in) and money repaid (loans_repaid)
  have their own lines. Repayments are not spending.
- Fee and reversal detection lives in cleaner.py (Transaction.is_fee and
  Transaction.is_reversal; Fuliza: is_loan_draw and is_loan_repayment).
  This file never matches text itself.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class Totals:
    money_in: Decimal
    money_out: Decimal       # everything that left, fees included
    fees_paid: Decimal       # part of money_out
    fee_count: int
    spending: Decimal        # money_out without fees and reversals
    reversals_in: Decimal
    reversals_out: Decimal
    net: Decimal             # money_in - money_out
    transaction_count: int
    loans_in: Decimal = ZERO        # Fuliza money borrowed (part of money_in)
    loans_repaid: Decimal = ZERO    # Fuliza repayments (part of money_out)


@dataclass(frozen=True)
class MonthTotals:
    month: str               # "2026-10"
    first_day: date          # first transaction we actually have in this month
    last_day: date          # last transaction we actually have in this month
    totals: Totals


def calculate_totals(transactions):
    money_in = sum((t.paid_in for t in transactions), ZERO)
    money_out = sum((t.paid_out for t in transactions), ZERO)

    fee_rows = [t for t in transactions if t.is_fee]
    reversal_rows = [t for t in transactions if t.is_reversal]
    loans_in = sum((t.paid_in for t in transactions if t.is_loan_draw), ZERO)
    loans_repaid = sum((t.paid_out for t in transactions if t.is_loan_repayment), ZERO)

    fees_paid = sum((t.paid_out for t in fee_rows), ZERO)
    reversals_in = sum((t.paid_in for t in reversal_rows), ZERO)
    reversals_out = sum((t.paid_out for t in reversal_rows), ZERO)

    return Totals(
        money_in=money_in,
        money_out=money_out,
        fees_paid=fees_paid,
        fee_count=len(fee_rows),
        spending=money_out - fees_paid - reversals_out - loans_repaid,
        reversals_in=reversals_in,
        reversals_out=reversals_out,
        net=money_in - money_out,
        transaction_count=len(transactions),
        loans_in=loans_in,
        loans_repaid=loans_repaid,
    )


def top_transactions(transactions, count=5):
    """
    The biggest SINGLE payments. Fees and reversals are excluded.
    This is not the same as top categories, which come after the categorizer.
    """
    candidates = [
        t for t in transactions
        if t.paid_out > 0 and not t.is_fee and not t.is_reversal
    ]
    candidates.sort(key=lambda t: (-t.paid_out, t.time))
    return candidates[:count]


def monthly_totals(transactions):
    """Groups by calendar month, oldest month first."""
    groups = defaultdict(list)
    for t in transactions:
        groups[t.time.strftime("%Y-%m")].append(t)

    months = []
    for month in sorted(groups):
        rows = groups[month]
        months.append(MonthTotals(
            month=month,
            first_day=min(t.time for t in rows).date(),
            last_day=max(t.time for t in rows).date(),
            totals=calculate_totals(rows),
        ))
    return months


def fee_review_list(transactions):
    """
    Rows that mention 'charge' or 'fee' but were NOT counted as fees.
    Shown to the user so nothing is misclassified silently.
    """
    review = []
    for t in transactions:
        text = t.details.lower()
        if t.is_fee or t.is_reversal:
            continue
        if "charge" in text or "fee" in text:
            review.append(t)
    return review
