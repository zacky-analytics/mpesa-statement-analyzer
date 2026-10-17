"""
Tests for the per-file checks and the merging of several files. FAKE data only.
No PDF and no Streamlit are needed: a stand-in "reader" returns ready-made rows.

Run from the project folder:  py -m pytest
"""

from datetime import date
from decimal import Decimal

from analyzer.cleaner import parse_amount
from analyzer.parser import (
    ParsedStatement,
    StatementPeriod,
    WrongPasswordError,
    extract_rows,
)
from analyzer.pipeline import combine, merge_transactions, process_file

HEADER = ["Receipt No.", "Completion Time", "Details", "Transaction Status",
          "Paid In", "Withdrawn", "Balance"]


def raw(receipt, when, details, paid_in="", withdrawn="", balance="0.00", status="Completed"):
    return {"receipt": receipt, "time": when, "details": details, "status": status,
            "paid_in": paid_in, "withdrawn": withdrawn, "balance": balance}


def summary_for(rows):
    """The totals a statement would print for these rows."""
    money_in = sum((parse_amount(r["paid_in"]) for r in rows), Decimal("0"))
    money_out = sum((abs(parse_amount(r["withdrawn"])) for r in rows), Decimal("0"))
    return {"TOTAL": {"paid_in": f"{money_in:,.2f}", "paid_out": f"{money_out:,.2f}"}}


def period(start, end):
    return StatementPeriod(date.fromisoformat(start), date.fromisoformat(end))


def reader_for(rows, start="2026-09-01", end="2026-09-30", summary=None,
               warnings=(), skipped=0, with_period=True):
    parsed = ParsedStatement(
        rows=list(rows),
        summary=summary if summary is not None else summary_for(rows),
        warnings=list(warnings),
        period=period(start, end) if with_period else None,
        skipped_rows=skipped,
    )

    def reader(file, password):
        return parsed
    return reader


def run(name, rows, **kwargs):
    return process_file(name, "unused.pdf", "unused", reader=reader_for(rows, **kwargs))


SEP_ROWS = [
    raw("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - 254700***002 Test Person", paid_in="3,000.00"),
    raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", withdrawn="-1,000.00"),
    raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill Charge", withdrawn="-10.00"),
]
OCT_ROWS = [
    raw("BBBBBBBB01", "2026-10-05 10:00:00", "Funds received from - 254700***002 Test Person", paid_in="3,000.00"),
    raw("BBBBBBBB02", "2026-10-10 10:00:00", "Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", withdrawn="-1,200.00"),
    raw("BBBBBBBB02", "2026-10-10 10:00:00", "Pay Bill Charge", withdrawn="-20.00"),
]


# ---------- checking one file ----------

def test_a_good_file_passes():
    result = run("sep.pdf", SEP_ROWS)
    assert result.ok
    assert result.problems == ()
    assert result.rows_read == 3 and result.rows_skipped == 0
    assert len(result.transactions) == 3
    assert result.period == period("2026-09-01", "2026-09-30")


def test_totals_that_do_not_match_the_statement_exclude_the_file():
    wrong = {"TOTAL": {"paid_in": "3,000.00", "paid_out": "9,999.00"}}
    result = run("sep.pdf", SEP_ROWS, summary=wrong)
    assert not result.ok
    assert any("Money out" in p for p in result.problems)
    assert result.transactions == ()          # a failed file contributes nothing


def test_a_missing_statement_period_excludes_the_file():
    result = run("sep.pdf", SEP_ROWS, with_period=False)
    assert not result.ok
    assert any("statement period" in p.lower() for p in result.problems)


def test_a_missing_statement_summary_excludes_the_file():
    result = run("sep.pdf", SEP_ROWS, summary={})
    assert not result.ok
    assert any("summary" in p.lower() for p in result.problems)


def test_an_unreadable_file_reports_the_reason_and_never_raises():
    def bad_reader(file, password):
        raise WrongPasswordError("Wrong PDF password. Please check it and try again.")

    result = process_file("sep.pdf", "unused.pdf", "wrong", reader=bad_reader)
    assert not result.ok
    assert result.problems == ("Wrong PDF password. Please check it and try again.",)
    assert result.rows_read == 0


def test_an_unreadable_amount_excludes_the_file():
    rows = [raw("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - X", paid_in="12abc")]
    totals = {"TOTAL": {"paid_in": "12.00", "paid_out": "0.00"}}
    result = run("sep.pdf", rows, summary=totals)
    assert not result.ok
    assert any("12abc" in p for p in result.problems)


def test_skipped_rows_are_counted_and_the_warnings_are_kept():
    result = run("sep.pdf", SEP_ROWS, warnings=["Page 1: skipped a row that did not match the expected layout."], skipped=1)
    assert result.rows_skipped == 1
    assert "Page 1" in result.warnings[0]
    assert result.ok      # the totals still match, so the file passes, with the warning shown


def test_a_status_other_than_completed_is_a_warning_not_a_failure():
    rows = SEP_ROWS + [raw("AAAAAAAA03", "2026-09-11 10:00:00", "Pay Bill to 7654321 - X", withdrawn="-5.00", status="Failed")]
    result = run("sep.pdf", rows)
    assert result.ok
    assert any("other than 'Completed'" in w for w in result.warnings)


def test_the_parser_counts_skipped_rows_as_a_number():
    bad = ["???", "not a date", "x", "Completed", "", "-1.00", "1.00"]
    rows, summary, warnings, skipped = extract_rows([[[HEADER, bad]]])
    assert rows == []
    assert skipped == 1
    assert len(warnings) == 1


# ---------- merging ----------

def test_overlapping_rows_are_kept_once_across_files():
    a = run("a.pdf", SEP_ROWS + OCT_ROWS, start="2026-09-01", end="2026-10-31")
    b = run("b.pdf", OCT_ROWS, start="2026-10-01", end="2026-10-31")
    merged, removed = merge_transactions([a.transactions, b.transactions])
    assert removed == 3
    assert len(merged) == 6


def test_identical_rows_inside_one_file_are_all_kept():
    twice = [raw("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - X", paid_in="100.00", balance="500.00")] * 2
    result = run("a.pdf", twice)
    assert result.ok
    merged, removed = merge_transactions([result.transactions])
    assert removed == 0
    assert len(merged) == 2


def test_a_payment_and_its_charge_with_one_receipt_are_not_duplicates():
    result = run("a.pdf", SEP_ROWS)
    merged, removed = merge_transactions([result.transactions])
    assert removed == 0 and len(merged) == 3


# ---------- combining files ----------

def test_two_full_months_in_two_files_allow_a_fair_comparison():
    sep = run("sep.pdf", SEP_ROWS, start="2026-09-01", end="2026-09-30")
    octo = run("oct.pdf", OCT_ROWS, start="2026-10-01", end="2026-10-31")
    combined = combine([sep, octo])

    assert combined.has_results
    assert [m.key for m in combined.report.months] == ["2026-09", "2026-10"]
    assert combined.comparison.like_for_like

    out = next(l for l in combined.comparison.totals if l.label == "Money out")
    assert out.change_pct == Decimal("210") / Decimal("1010") * 100
    assert combined.notes == ()


def test_each_file_is_checked_before_overlaps_are_removed():
    # b.pdf is entirely inside a.pdf. It must still PASS its own check.
    a = run("a.pdf", SEP_ROWS + OCT_ROWS, start="2026-09-01", end="2026-10-31")
    b = run("b.pdf", OCT_ROWS, start="2026-10-01", end="2026-10-31")
    assert a.ok and b.ok

    combined = combine([a, b])
    assert combined.cross_file_duplicates_removed == 3
    assert len(combined.transactions) == 6
    assert any("counted once" in n for n in combined.notes)
    assert combined.excluded == ()


def test_a_failed_file_is_excluded_and_the_others_still_give_results():
    good = run("good.pdf", SEP_ROWS, start="2026-09-01", end="2026-09-30")
    bad = run("bad.pdf", OCT_ROWS, start="2026-10-01", end="2026-10-31",
              summary={"TOTAL": {"paid_in": "1.00", "paid_out": "1.00"}})
    combined = combine([good, bad])

    assert combined.has_results
    assert [f.name for f in combined.included] == ["good.pdf"]
    assert [f.name for f in combined.excluded] == ["bad.pdf"]
    assert any("exclude" in n and "bad.pdf" in n for n in combined.notes)
    # coverage is built only from the file that passed
    assert [m.key for m in combined.report.months] == ["2026-09"]


def test_when_no_file_passes_there_are_no_results():
    bad = run("bad.pdf", SEP_ROWS, summary={"TOTAL": {"paid_in": "1.00", "paid_out": "1.00"}})
    combined = combine([bad])
    assert not combined.has_results
    assert combined.report.months == []
    assert combined.comparison is None
    assert any("None of the uploaded files" in n for n in combined.notes)


def test_no_files_gives_an_empty_result_without_errors():
    combined = combine([])
    assert not combined.has_results
    assert combined.notes == ()


def test_coverage_is_the_stated_period_even_when_the_days_are_quiet():
    # Two transactions in a 30-day statement: the month is still FULL.
    result = run("sep.pdf", SEP_ROWS[:2], start="2026-09-01", end="2026-09-30")
    combined = combine([result])
    assert combined.report.months[0].is_full


def test_two_files_with_a_gap_between_them_label_the_month_with_gaps():
    a = run("a.pdf", [SEP_ROWS[0]], start="2026-09-01", end="2026-09-10")
    b = run("b.pdf", [raw("CCCCCCCC01", "2026-09-25 10:00:00", "Funds received from - X", paid_in="10.00")],
            start="2026-09-20", end="2026-09-30")
    combined = combine([a, b])
    sep = combined.report.months[0]
    assert not sep.is_full and sep.has_gaps
    assert "with gaps" in sep.description


def test_a_transaction_outside_its_own_statement_period_is_flagged():
    stray = SEP_ROWS + [raw("AAAAAAAA09", "2026-10-02 10:00:00", "Pay Bill to 1 - X", withdrawn="-5.00")]
    result = run("sep.pdf", stray, start="2026-09-01", end="2026-09-30")
    combined = combine([result])
    assert any("outside" in n for n in combined.notes)
