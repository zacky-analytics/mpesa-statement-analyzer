"""
comparison.py - month-by-month view, built on the days the statement(s)
actually cover.

Why coverage matters: a statement for 13 Sep to 13 Oct covers only PART of
September and PART of October. Comparing those two totals as if they were
full months would be misleading.

Rules
-----
- Coverage comes ONLY from each statement's STATED period, combined. It is
  never guessed from the first and last transaction dates, because quiet days
  and gaps would make a guess wrong. With no stated period, no months are built.
- A month is "full" only if the combined coverage spans the whole calendar month.
- A change or percentage exists ONLY when both months are full AND next to each
  other. Otherwise `change` and `change_pct` are None on every line, so the
  page, the PDF and the AI summary all read the same result and cannot invent
  a figure of their own. The two amounts (and per-day averages) are still given
  side by side, for reference.
- A percentage of a zero starting value is also None.

All money is Decimal. Nothing here matches transaction text; fee and
category decisions come from cleaner.py and categorizer.py.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from analyzer.categorizer import CATEGORY_ORDER, category_totals
from analyzer.metrics import ZERO, Totals, calculate_totals
from analyzer.parser import StatementPeriod

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _short(day):
    return f"{day.day} {MONTH_ABBR[day.month - 1]}"


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def merge_periods(periods):
    """Joins overlapping or back-to-back periods. Gaps stay as separate periods."""
    ranges = sorted((p.start, p.end) for p in periods)
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + timedelta(days=1):
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return [StatementPeriod(s, e) for s, e in merged]


def transactions_outside_coverage(transactions, coverage):
    outside = []
    for t in transactions:
        day = t.time.date()
        if not any(p.start <= day <= p.end for p in coverage):
            outside.append(t)
    return outside


def _month_range(first, last):
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def _covered_days(coverage, month_first, month_last):
    days = 0
    first = None
    last = None
    for p in coverage:
        start = max(p.start, month_first)
        end = min(p.end, month_last)
        if start <= end:
            days += (end - start).days + 1
            first = start if first is None else min(first, start)
            last = end if last is None else max(last, end)
    return days, first, last


# ---------------------------------------------------------------------------
# Month summaries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonthSummary:
    year: int
    month: int
    first_covered: date      # first day of this month that the statement(s) cover
    last_covered: date       # last day of this month that the statement(s) cover
    days_covered: int
    days_in_month: int
    totals: Totals
    categories: list         # list of CategoryTotal

    @property
    def key(self):
        return f"{self.year}-{self.month:02d}"

    @property
    def name(self):
        return f"{MONTH_ABBR[self.month - 1]} {self.year}"

    @property
    def is_full(self):
        return self.days_covered == self.days_in_month

    @property
    def has_gaps(self):
        """True if some days between the first and last covered day are not covered."""
        return self.days_covered != (self.last_covered - self.first_covered).days + 1

    @property
    def description(self):
        if self.is_full:
            return f"{self.name} (full month)"
        kind = "partial, with gaps" if self.has_gaps else "partial"
        return (
            f"{self.name} ({kind}: {_short(self.first_covered)} to "
            f"{_short(self.last_covered)}, {self.days_covered} of "
            f"{self.days_in_month} days)"
        )


@dataclass(frozen=True)
class MonthlyReport:
    months: list              # list of MonthSummary, oldest first
    coverage: list            # list of StatementPeriod
    outside_coverage: list    # transactions not inside any covered day
    period_missing: bool = False   # transactions exist but no statement period was given


def build_monthly_report(transactions, periods):
    """
    transactions: cleaned transactions (already de-duplicated across files).
    periods: the STATED period of each statement. None entries are ignored.
    """
    known = [p for p in (periods or []) if p is not None]
    if not known:
        return MonthlyReport(
            months=[],
            coverage=[],
            outside_coverage=[],
            period_missing=bool(transactions),
        )

    coverage = merge_periods(known)

    by_month = defaultdict(list)
    for t in transactions:
        by_month[(t.time.year, t.time.month)].append(t)

    months = []
    for year, month in _month_range(coverage[0].start, coverage[-1].end):
        days_in_month = calendar.monthrange(year, month)[1]
        days, first, last = _covered_days(
            coverage, date(year, month, 1), date(year, month, days_in_month)
        )
        if days == 0:
            continue  # a month entirely inside a gap between statements
        rows = by_month.get((year, month), [])
        months.append(MonthSummary(
            year=year,
            month=month,
            first_covered=first,
            last_covered=last,
            days_covered=days,
            days_in_month=days_in_month,
            totals=calculate_totals(rows),
            categories=category_totals(rows),
        ))

    return MonthlyReport(
        months=months,
        coverage=coverage,
        outside_coverage=transactions_outside_coverage(transactions, coverage),
    )


def report_notes(report):
    """Plain-English warnings about the report as a whole."""
    notes = []
    if report.period_missing:
        notes.append(
            "No statement period was found, so the days covered cannot be "
            "confirmed and no months are shown."
        )
    if report.outside_coverage:
        notes.append(
            f"{len(report.outside_coverage)} transaction(s) fall outside the days "
            f"covered by the statement(s). Please check the files you uploaded."
        )
    return notes


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComparisonLine:
    label: str
    previous: Decimal
    current: Decimal
    # Both are None when the comparison is not fair (see the rules at the top).
    # change_pct is also None when the previous value is zero.
    # Never compute a change or percentage anywhere else.
    change: Optional[Decimal]
    change_pct: Optional[Decimal]


@dataclass(frozen=True)
class MonthComparison:
    previous: MonthSummary
    current: MonthSummary
    like_for_like: bool      # True only when both months are full AND consecutive
    totals: list             # lines: money in, money out, fees, spending
    per_day: list            # the same lines divided by the days each month covers
    out_categories: list     # lines on money OUT, per category
    in_categories: list      # lines on money IN, per category
    notes: list              # plain-English warnings about this comparison


def _line(label, previous, current, fair):
    if not fair:
        return ComparisonLine(label, previous, current, None, None)
    change = current - previous
    change_pct = (change / previous) * 100 if previous != 0 else None
    return ComparisonLine(label, previous, current, change, change_pct)


def _total_lines(previous, current, fair, suffix="", prev_days=1, cur_days=1):
    p, c = previous.totals, current.totals
    return [
        _line("Money in" + suffix, p.money_in / prev_days, c.money_in / cur_days, fair),
        _line("Money out" + suffix, p.money_out / prev_days, c.money_out / cur_days, fair),
        _line("Fees paid" + suffix, p.fees_paid / prev_days, c.fees_paid / cur_days, fair),
        _line("Spending" + suffix, p.spending / prev_days, c.spending / cur_days, fair),
    ]


def _category_lines(previous, current, side, fair):
    """side is 'out' or 'in'. Only categories with money on that side are listed."""
    def amounts(month):
        return {
            c.category: (c.money_out if side == "out" else c.money_in)
            for c in month.categories
        }

    prev_amounts = amounts(previous)
    cur_amounts = amounts(current)

    lines = []
    for category in CATEGORY_ORDER:
        prev_value = prev_amounts.get(category, ZERO)
        cur_value = cur_amounts.get(category, ZERO)
        if prev_value == 0 and cur_value == 0:
            continue
        lines.append(_line(category, prev_value, cur_value, fair))
    return lines


def compare_months(previous, current):
    notes = []

    both_full = previous.is_full and current.is_full
    consecutive = (
        (current.year * 12 + current.month) - (previous.year * 12 + previous.month) == 1
    )
    like_for_like = both_full and consecutive

    if not both_full:
        partial = [m.name for m in (previous, current) if not m.is_full]
        verb = "is" if len(partial) == 1 else "are"
        notes.append(
            f"Not like-for-like: {' and '.join(partial)} {verb} only partly covered "
            f"by the statement(s), so no change or percentage is shown. The amounts "
            f"are side by side for reference only."
        )

    if not consecutive:
        notes.append(
            f"{previous.name} and {current.name} are not consecutive months, "
            f"so no change or percentage is shown."
        )

    return MonthComparison(
        previous=previous,
        current=current,
        like_for_like=like_for_like,
        totals=_total_lines(previous, current, like_for_like),
        per_day=_total_lines(
            previous, current, like_for_like, suffix=" per day",
            prev_days=previous.days_covered, cur_days=current.days_covered,
        ),
        out_categories=_category_lines(previous, current, "out", like_for_like),
        in_categories=_category_lines(previous, current, "in", like_for_like),
        notes=notes,
    )


def latest_comparison(report):
    """Compares the last two months. None if there is only one."""
    if len(report.months) < 2:
        return None
    return compare_months(report.months[-2], report.months[-1])
