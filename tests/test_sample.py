"""Tests for the fake sample data. Run: py -m pytest"""

from analyzer.categorizer import uncategorized_rows
from analyzer.metrics import calculate_totals
from analyzer.report import build_report
from analyzer.sample import sample_combined
from analyzer.summary import build_summary


def test_both_sample_files_pass_every_check():
    combined = sample_combined()
    assert all(f.ok for f in combined.files), [f.problems for f in combined.files]
    assert combined.excluded == () and combined.has_results


def test_every_sample_row_is_categorized():
    assert uncategorized_rows(list(sample_combined().transactions)) == []


def test_the_sample_compares_two_full_months():
    comparison = sample_combined().comparison
    assert comparison is not None and comparison.like_for_like


def test_the_sample_numbers_add_up():
    totals = calculate_totals(list(sample_combined().transactions))
    assert totals.money_out == totals.spending + totals.fees_paid + totals.loans_repaid
    assert totals.loans_in == totals.loans_repaid


def test_sample_names_are_clearly_fake():
    text = " ".join(t.details for t in sample_combined().transactions)
    assert "Sample" in text and "Test Person" in text


def test_summary_and_report_work_on_the_sample():
    combined = sample_combined()
    assert build_summary(combined)
    assert build_report(combined)[:4] == b"%PDF"
