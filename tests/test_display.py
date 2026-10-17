"""Tests for the display helpers. FAKE data only. Run: py -m pytest"""

from datetime import date, datetime
from decimal import Decimal

from analyzer.cleaner import Transaction
from analyzer.comparison import ComparisonLine
from analyzer.display import (
    change_text,
    comparison_rows,
    file_status_lines,
    filter_rows,
    money,
    transaction_rows,
)
from analyzer.parser import StatementPeriod
from analyzer.pipeline import FileResult


def tx(receipt, when, details, paid_in="0", paid_out="0"):
    return Transaction(receipt, datetime.fromisoformat(when), details, "Completed",
                       Decimal(paid_in), Decimal(paid_out), Decimal("100"))


ROWS = [
    tx("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - Test Person", paid_in="500"),
    tx("AAAAAAAA02", "2026-09-06 10:00:00", "Pay Bill to 123 - TEST SCHOOL", paid_out="200"),
    tx("AAAAAAAA02", "2026-09-06 10:00:00", "Pay Bill Charge", paid_out="10"),
]


def test_money_has_commas_and_two_decimals():
    assert money(Decimal("1234.5")) == "KES 1,234.50"


def test_change_text_is_dashes_when_not_fair():
    line = ComparisonLine("Money in", Decimal("10"), Decimal("20"), None, None)
    assert change_text(line) == ("-", "-")


def test_change_text_shows_numbers_when_fair():
    line = ComparisonLine("Money in", Decimal("100"), Decimal("110"), Decimal("10"), Decimal("10"))
    assert change_text(line) == ("+10.00", "+10.0%")


def test_percentage_is_na_when_before_is_zero():
    line = ComparisonLine("Shops", Decimal("0"), Decimal("50"), Decimal("50"), None)
    assert change_text(line) == ("+50.00", "n/a")


def test_comparison_rows_keep_the_amounts_even_when_change_is_hidden():
    line = ComparisonLine("Money in", Decimal("10"), Decimal("20"), None, None)
    row = comparison_rows([line])[0]
    assert row["Before"] == "10.00" and row["After"] == "20.00" and row["Change %"] == "-"


def test_transactions_are_newest_first_with_categories():
    rows = transaction_rows(ROWS)
    assert rows[0]["Date"].startswith("2026-09-06")
    assert {r["Category"] for r in rows} == {"Received from people", "Bills (Pay Bill)", "Fees"}


def test_search_and_category_filter():
    rows = transaction_rows(ROWS)
    assert len(filter_rows(rows, "school")) == 1
    assert len(filter_rows(rows, "", "Fees")) == 1
    assert len(filter_rows(rows, "school", "Fees")) == 0
    assert len(filter_rows(rows, "")) == 3


def test_file_status_lines_report_the_failure_plainly():
    result = FileResult(name="a.pdf", ok=False, rows_read=5, rows_skipped=1,
                        period=StatementPeriod(date(2026, 9, 1), date(2026, 9, 30)))
    lines = file_status_lines(result)
    assert "Totals match the statement summary: NO" in lines
    assert "Rows skipped: 1" in lines
