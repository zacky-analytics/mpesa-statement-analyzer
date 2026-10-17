"""
insights.py - a few extra facts about SPENDING, all calculated from the rows.

"Spending" here means money paid to people, bills, shops, airtime and cash
withdrawals (the categories in SPENDING_CATEGORIES). Fees, reversals and Fuliza
repayments are not spending, so they are not counted here.
No advice is given: these are plain facts.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from analyzer.categorizer import SPENDING_CATEGORIES, categorize

ZERO = Decimal("0")
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class PayeeTotal:
    name: str        # the description exactly as the statement shows it (first one seen)
    count: int
    total: Decimal


def spending_rows(transactions):
    return [t for t in transactions if t.paid_out > 0 and categorize(t) in SPENDING_CATEGORIES]


def average_per_day(transactions, days_covered):
    """Spending divided by the days the statements cover. None if no days are known."""
    if days_covered <= 0:
        return None
    total = sum((t.paid_out for t in spending_rows(transactions)), ZERO)
    return total / days_covered


def biggest_day(transactions):
    """(date, amount) of the day with the most spending, or None."""
    by_day = defaultdict(lambda: ZERO)
    for t in spending_rows(transactions):
        by_day[t.time.date()] += t.paid_out
    if not by_day:
        return None
    day = max(by_day, key=lambda d: (by_day[d], d))
    return day, by_day[day]


def busiest_weekday(transactions):
    """(weekday name, amount) of the weekday with the most spending, or None."""
    by_weekday = defaultdict(lambda: ZERO)
    for t in spending_rows(transactions):
        by_weekday[t.time.weekday()] += t.paid_out
    if not by_weekday:
        return None
    number = max(by_weekday, key=lambda w: (by_weekday[w], -w))
    return WEEKDAYS[number], by_weekday[number]


def top_payees(transactions, count=5):
    """
    Where the most spending went, grouped by the SAME description text.
    Nothing is guessed: two rows are grouped only if their text is identical
    (ignoring capital letters and extra spaces).
    """
    groups = {}
    for t in sorted(spending_rows(transactions), key=lambda x: x.time):
        key = " ".join(t.details.lower().split())
        if key not in groups:
            groups[key] = [" ".join(t.details.split()), 0, ZERO]
        groups[key][1] += 1
        groups[key][2] += t.paid_out
    ranked = sorted(groups.values(), key=lambda g: (-g[2], -g[1], g[0]))
    return [PayeeTotal(name, n, total) for name, n, total in ranked[:count]]
