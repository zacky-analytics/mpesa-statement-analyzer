"""
series.py - the numbers behind the time charts (daily flow, closing balance).

Rules
-----
- Only days that have at least one transaction get a point. We never invent
  values for quiet days.
- Daily flow is plain sums of paid_in and paid_out (fees included in out,
  the same as everywhere else).
- Closing balance of a day = the balance printed on that day's LAST
  transaction. When several rows share the latest timestamp (a payment and its
  fee often do), the row order is worked out from the balances themselves:
  the last row is the one that no other row follows. If that cannot be decided
  exactly, the day is marked `certain=False` and the page says so.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class DayFlow:
    day: date
    money_in: Decimal
    money_out: Decimal


@dataclass(frozen=True)
class DayBalance:
    day: date
    balance: Decimal
    certain: bool


def _by_day(transactions):
    groups = defaultdict(list)
    for t in transactions:
        groups[t.time.date()].append(t)
    return groups


def daily_flow(transactions):
    """One DayFlow per day that has transactions, oldest first."""
    flows = []
    for day, rows in sorted(_by_day(transactions).items()):
        flows.append(DayFlow(
            day=day,
            money_in=sum((t.paid_in for t in rows), ZERO),
            money_out=sum((t.paid_out for t in rows), ZERO),
        ))
    return flows


def _last_row(rows):
    """Returns (row, certain) for the last transaction among rows sharing one timestamp."""
    if len(rows) == 1:
        return rows[0], True

    def follows(later, earlier):
        return later.balance == earlier.balance + later.paid_in - later.paid_out

    last = [
        r for r in rows
        if not any(s is not r and follows(s, r) for s in rows)
    ]
    if len(last) == 1:
        return last[0], True
    return (last or rows)[0], False


def closing_balances(transactions):
    """One DayBalance per day that has transactions, oldest first."""
    result = []
    for day, rows in sorted(_by_day(transactions).items()):
        latest = max(t.time for t in rows)
        row, certain = _last_row([t for t in rows if t.time == latest])
        result.append(DayBalance(day=day, balance=row.balance, certain=certain))
    return result
