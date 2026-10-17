"""
Tests for the statement period reader and the month comparison. FAKE data only.
Run from the project folder:  py -m pytest
"""

from datetime import date, datetime
from decimal import Decimal

from analyzer.categorizer import BILLS, FEES, RECEIVED, SENT
from analyzer.cleaner import Transaction
from analyzer.comparison import (
    build_monthly_report,
    latest_comparison,
    merge_periods,
    report_notes,
)
from analyzer.parser import StatementPeriod, parse_statement_period


def tx(details, paid_in="0", paid_out="0", when="2026-09-18 10:00:00"):
    return Transaction(
        receipt="AAAAAAAA01",
        time=datetime.strptime(when, "%Y-%m-%d %H:%M:%S"),
        details=details,
        status="Completed",
        paid_in=Decimal(paid_in),
        paid_out=Decimal(paid_out),
        balance=Decimal("0"),
    )


def period(start, end):
    return StatementPeriod(date.fromisoformat(start), date.fromisoformat(end))


def line(lines, label):
    return next(l for l in lines if l.label == label)


# ---------- reading the statement period ----------

def test_reads_period_from_statement_text():
    text = (
        "Page 1 of 3\nM-PESA STATEMENT\nCustomer Name: TEST PERSON\n"
        "Statement Period: 13 Sep 2026 - 13 Oct 2026\nRequest Date: 13 Oct 2026\n"
    )
    assert parse_statement_period(text) == period("2026-09-13", "2026-10-13")


def test_period_with_a_long_dash_is_read():
    text = "Statement Period: 1 Jan 2026 – 31 Jan 2026"
    assert parse_statement_period(text) == period("2026-01-01", "2026-01-31")


def test_missing_period_gives_none():
    assert parse_statement_period("M-PESA STATEMENT\nNo period here") is None
    assert parse_statement_period("") is None
    assert parse_statement_period(None) is None


def test_impossible_date_gives_none():
    assert parse_statement_period("Statement Period: 31 Feb 2026 - 5 Mar 2026") is None


def test_period_ending_before_it_starts_gives_none():
    assert parse_statement_period("Statement Period: 13 Oct 2026 - 13 Sep 2026") is None


# ---------- merging coverage ----------

def test_overlapping_periods_are_joined():
    merged = merge_periods([period("2026-09-01", "2026-09-15"), period("2026-09-10", "2026-09-30")])
    assert merged == [period("2026-09-01", "2026-09-30")]


def test_back_to_back_periods_are_joined():
    merged = merge_periods([period("2026-09-01", "2026-09-15"), period("2026-09-16", "2026-09-30")])
    assert merged == [period("2026-09-01", "2026-09-30")]


def test_a_gap_keeps_periods_separate():
    merged = merge_periods([period("2026-09-20", "2026-09-30"), period("2026-09-01", "2026-09-10")])
    assert merged == [period("2026-09-01", "2026-09-10"), period("2026-09-20", "2026-09-30")]


# ---------- months and coverage labels ----------

# The real situation: a statement for 13 Sep to 13 Oct covers PART of two months.
PARTIAL_PERIOD = period("2026-09-13", "2026-10-13")
PARTIAL_TXS = [
    tx("Pay Bill to 1 - X", paid_out="100", when="2026-09-18 10:00:00"),
    tx("Funds received from - 254700***002 Test", paid_in="500", when="2026-09-25 10:00:00"),
    tx("Pay Bill to 1 - X", paid_out="300", when="2026-10-02 10:00:00"),
    tx("Customer Transfer to - 0700***001 TEST", paid_out="50", when="2026-10-12 10:00:00"),
]


def test_a_mid_month_statement_makes_both_months_partial():
    report = build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD])
    sep, oct_ = report.months
    assert [m.key for m in report.months] == ["2026-09", "2026-10"]

    assert sep.days_covered == 18 and sep.days_in_month == 30 and not sep.is_full
    assert sep.first_covered == date(2026, 9, 13) and sep.last_covered == date(2026, 9, 30)

    assert oct_.days_covered == 13 and oct_.days_in_month == 31 and not oct_.is_full
    assert oct_.first_covered == date(2026, 10, 1) and oct_.last_covered == date(2026, 10, 13)


def test_month_descriptions_say_what_is_covered():
    report = build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD])
    assert report.months[0].description == "Sep 2026 (partial: 13 Sep to 30 Sep, 18 of 30 days)"
    assert report.months[1].description == "Oct 2026 (partial: 1 Oct to 13 Oct, 13 of 31 days)"


def test_full_months_are_labelled_full():
    report = build_monthly_report([], [period("2026-09-01", "2026-10-31")])
    assert all(m.is_full for m in report.months)
    assert report.months[0].description == "Sep 2026 (full month)"


def test_a_covered_month_with_no_transactions_still_appears_with_zeros():
    txs = [tx("Pay Bill to 1 - X", paid_out="100", when="2026-08-10 10:00:00")]
    report = build_monthly_report(txs, [period("2026-08-01", "2026-09-30")])
    assert [m.key for m in report.months] == ["2026-08", "2026-09"]
    assert report.months[1].totals.transaction_count == 0
    assert report.months[1].is_full


def test_a_month_entirely_inside_a_gap_is_left_out():
    txs = [
        tx("Pay Bill to 1 - X", paid_out="100", when="2026-08-10 10:00:00"),
        tx("Pay Bill to 1 - X", paid_out="100", when="2026-10-10 10:00:00"),
    ]
    report = build_monthly_report(txs, [period("2026-08-01", "2026-08-31"), period("2026-10-01", "2026-10-31")])
    assert [m.key for m in report.months] == ["2026-08", "2026-10"]
    comparison = latest_comparison(report)
    assert any("not consecutive" in n for n in comparison.notes)
    assert not comparison.like_for_like


# ---------- coverage comes from the STATED periods ----------

def test_quiet_days_do_not_make_a_month_partial():
    # Only two transactions, but the statement says it covers the whole month.
    txs = [
        tx("Pay Bill to 1 - X", paid_out="10", when="2026-09-05 10:00:00"),
        tx("Pay Bill to 1 - X", paid_out="10", when="2026-09-10 10:00:00"),
    ]
    report = build_monthly_report(txs, [period("2026-09-01", "2026-09-30")])
    assert report.months[0].is_full
    assert report.months[0].days_covered == 30


def test_two_statements_together_can_make_a_month_full():
    report = build_monthly_report([], [period("2026-09-01", "2026-09-15"), period("2026-09-16", "2026-09-30")])
    assert report.months[0].is_full


def test_a_gap_between_two_statements_is_labelled():
    report = build_monthly_report([], [period("2026-09-01", "2026-09-10"), period("2026-09-20", "2026-09-30")])
    sep = report.months[0]
    assert not sep.is_full and sep.has_gaps
    assert sep.days_covered == 21
    assert sep.description == "Sep 2026 (partial, with gaps: 1 Sep to 30 Sep, 21 of 30 days)"


def test_no_stated_period_means_no_months_and_nothing_is_guessed():
    report = build_monthly_report(PARTIAL_TXS, [])
    assert report.months == []
    assert report.coverage == []
    assert any("statement period" in n for n in report_notes(report))


def test_none_entries_in_the_period_list_are_ignored():
    report = build_monthly_report(PARTIAL_TXS, [None, PARTIAL_PERIOD])
    assert [m.key for m in report.months] == ["2026-09", "2026-10"]


# ---------- comparison ----------

FULL_PERIOD = period("2026-09-01", "2026-10-31")
FULL_TXS = [
    tx("Funds received from - 254700***002 Test", paid_in="3000", when="2026-09-05 10:00:00"),
    tx("Pay Bill to 1 - X", paid_out="1000", when="2026-09-10 10:00:00"),
    tx("Pay Bill Charge", paid_out="10", when="2026-09-10 10:00:00"),
    tx("Funds received from - 254700***002 Test", paid_in="3000", when="2026-10-05 10:00:00"),
    tx("Pay Bill to 1 - X", paid_out="1200", when="2026-10-10 10:00:00"),
    tx("Pay Bill Charge", paid_out="20", when="2026-10-10 10:00:00"),
]


def test_full_months_are_like_for_like_and_have_no_warning():
    comparison = latest_comparison(build_monthly_report(FULL_TXS, [FULL_PERIOD]))
    assert comparison.like_for_like
    assert comparison.notes == []


def test_changes_and_percentages_are_exact_for_full_months():
    comparison = latest_comparison(build_monthly_report(FULL_TXS, [FULL_PERIOD]))

    out = line(comparison.totals, "Money out")
    assert (out.previous, out.current, out.change) == (Decimal("1010"), Decimal("1220"), Decimal("210"))
    assert out.change_pct == Decimal("210") / Decimal("1010") * 100

    fees = line(comparison.totals, "Fees paid")
    assert fees.change_pct == Decimal("100")

    spending = line(comparison.totals, "Spending")
    assert (spending.previous, spending.current) == (Decimal("1000"), Decimal("1200"))


def test_full_month_category_changes_and_percentages():
    comparison = latest_comparison(build_monthly_report(FULL_TXS, [FULL_PERIOD]))

    out = {l.label: l for l in comparison.out_categories}
    assert out[BILLS].change == Decimal("200") and out[BILLS].change_pct == Decimal("20")
    assert out[FEES].change == Decimal("10") and out[FEES].change_pct == Decimal("100")

    incoming = {l.label: l for l in comparison.in_categories}
    assert incoming[RECEIVED].change == Decimal("0") and incoming[RECEIVED].change_pct == Decimal("0")


def test_no_percentage_when_the_previous_value_is_zero():
    txs = [
        tx("Pay Bill to 1 - X", paid_out="100", when="2026-09-10 10:00:00"),
        tx("Pay Bill to 1 - X", paid_out="100", when="2026-10-10 10:00:00"),
        tx("Pay Bill Charge", paid_out="20", when="2026-10-10 10:00:00"),
    ]
    comparison = latest_comparison(build_monthly_report(txs, [FULL_PERIOD]))
    fees = line(comparison.totals, "Fees paid")
    assert fees.previous == 0 and fees.current == 20
    assert fees.change == Decimal("20")      # the plain difference is still shown
    assert fees.change_pct is None           # but no percentage of zero


def test_partial_months_are_flagged_not_like_for_like():
    comparison = latest_comparison(build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD]))
    assert not comparison.like_for_like
    assert len(comparison.notes) == 1
    assert "Not like-for-like" in comparison.notes[0]
    assert "Sep 2026" in comparison.notes[0] and "Oct 2026" in comparison.notes[0]


def test_partial_months_return_no_changes_and_no_percentages_anywhere():
    comparison = latest_comparison(build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD]))
    every_line = (
        comparison.totals + comparison.per_day
        + comparison.out_categories + comparison.in_categories
    )
    assert every_line  # there is something to check
    for l in every_line:
        assert l.change is None and l.change_pct is None


def test_partial_months_still_show_the_amounts_side_by_side():
    comparison = latest_comparison(build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD]))

    out = line(comparison.totals, "Money out")
    assert (out.previous, out.current) == (Decimal("100"), Decimal("350"))

    cats = {l.label: l for l in comparison.out_categories}
    assert set(cats) == {SENT, BILLS}
    assert (cats[BILLS].previous, cats[BILLS].current) == (Decimal("100"), Decimal("300"))
    assert (cats[SENT].previous, cats[SENT].current) == (Decimal("0"), Decimal("50"))

    incoming = {l.label: l for l in comparison.in_categories}
    assert set(incoming) == {RECEIVED}


def test_per_day_figures_divide_by_days_covered_not_days_with_transactions():
    comparison = latest_comparison(build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD]))
    out = line(comparison.per_day, "Money out per day")
    assert out.previous == Decimal("100") / 18      # Sep covers 18 days
    assert out.current == Decimal("350") / 13       # Oct covers 13 days


def test_one_partial_month_is_enough_to_withhold_percentages():
    # Sep is full, Oct is only half covered.
    report = build_monthly_report(FULL_TXS, [period("2026-09-01", "2026-10-15")])
    comparison = latest_comparison(report)
    assert not comparison.like_for_like
    assert all(l.change is None and l.change_pct is None for l in comparison.totals)


def test_only_one_month_means_no_comparison():
    report = build_monthly_report([], [period("2026-09-01", "2026-09-30")])
    assert latest_comparison(report) is None


# ---------- trust warnings ----------

def test_transactions_outside_the_statement_period_are_reported():
    txs = [
        tx("Pay Bill to 1 - X", paid_out="10", when="2026-09-01 10:00:00"),   # same month, before the period
        tx("Pay Bill to 1 - X", paid_out="10", when="2026-08-20 10:00:00"),   # a month nobody covers
        tx("Pay Bill to 1 - X", paid_out="10", when="2026-09-20 10:00:00"),   # fine
    ]
    report = build_monthly_report(txs, [PARTIAL_PERIOD])
    assert len(report.outside_coverage) == 2
    assert any("outside" in n for n in report_notes(report))
    assert [m.key for m in report.months] == ["2026-09", "2026-10"]  # no August


def test_a_clean_report_has_no_notes():
    report = build_monthly_report(PARTIAL_TXS, [PARTIAL_PERIOD])
    assert report_notes(report) == []
