"""
Tests use FAKE data in the same layout as a real M-Pesa statement.
Never put a real statement or real names in this folder.

Run from the project folder:  py -m pytest
"""

from decimal import Decimal

import pytest

from analyzer.cleaner import (
    CleaningError,
    clean_rows,
    parse_amount,
    reconcile,
    remove_duplicates,
)
from analyzer.parser import extract_from_tables

HEADER = ["Receipt No.", "Completion Time", "Details", "Transaction Status",
          "Paid In", "Withdrawn", "Balance"]

SUMMARY_TABLE = [
    ["TRANSACTION TYPE", "PAID IN", "PAID OUT"],
    ["SEND MONEY:", "0.00", "28.00"],
    ["RECEIVED MONEY:", "50.00", "0.00"],
    ["AGENT DEPOSIT:", "2,600.00", "0.00"],
    ["LIPA NA M-PESA (PAYBILL):", "0.00", "5,000.00"],
    ["OTHERS:", "0.00", "34.00"],
    ["TOTAL:", "2,650.00", "5,062.00"],
]

VERIFICATION_TABLE = [
    ["Statement Verification Code", "To verify the validity of this statement dial ..."],
    ["", None],
    ["TESTCODE", None],
]

PAGE_1_TRANSACTIONS = [
    HEADER,
    ["AAAAAAAA01", "2026-10-12 19:02:04",
     "Customer Transfer to -\n0700***001 TEST PERSON ONE", "Completed", "", "-28.00", "0.94"],
    ["AAAAAAAA02", "2026-10-07 12:52:42",
     "Funds received from -\n254700***002 Test\nPerson Two", "Completed", "50.00", "", "78.94"],
    ["AAAAAAAA03", "2026-10-07 11:40:51",
     "Pay Bill Charge", "Completed", "", "-34.00", "5,578.94"],
    ["AAAAAAAA03", "2026-10-07 11:40:51",
     "Pay Bill to 1234567 - TEST\nSCHOOL Acc.\nX/1", "Completed", "", "-5,000.00", "578.94"],
]

PAGE_2_TRANSACTIONS = [
    HEADER,  # the header repeats on every page
    ["AAAAAAAA04", "2026-10-07 11:14:20",
     "Deposit of Funds at Agent Till\n111111 - TEST SHOP", "Completed", "2,600.00", "", "5,612.94"],
]

PAGES = [
    [SUMMARY_TABLE, PAGE_1_TRANSACTIONS, VERIFICATION_TABLE],
    [PAGE_2_TRANSACTIONS, VERIFICATION_TABLE],
]


def _clean_all():
    rows, summary, warnings = extract_from_tables(PAGES)
    return clean_rows(rows), summary, warnings


# ---------- parser ----------

def test_reads_all_transaction_rows_across_pages():
    rows, _, warnings = extract_from_tables(PAGES)
    assert len(rows) == 5
    assert warnings == []


def test_header_summary_and_verification_tables_are_not_rows():
    rows, _, _ = extract_from_tables(PAGES)
    assert all(r["receipt"].startswith("AAAAAAAA") for r in rows)


def test_line_breaks_inside_details_become_spaces():
    rows, _, _ = extract_from_tables(PAGES)
    assert rows[1]["details"] == "Funds received from - 254700***002 Test Person Two"


def test_reads_summary_totals():
    _, summary, _ = extract_from_tables(PAGES)
    assert summary["TOTAL"] == {"paid_in": "2,650.00", "paid_out": "5,062.00"}


def test_row_with_wrong_layout_is_reported_not_dropped_silently():
    bad = [["???", "not a date", "x", "Completed", "", "-1.00", "1.00"]]
    _, _, warnings = extract_from_tables([[bad]])
    assert len(warnings) == 1


# ---------- cleaner ----------

def test_amounts_with_commas_and_blanks():
    assert parse_amount("1,069.94") == Decimal("1069.94")
    assert parse_amount("") == Decimal("0")
    assert parse_amount(None) == Decimal("0")


def test_bad_amount_raises_clear_error():
    with pytest.raises(CleaningError):
        parse_amount("12abc")


def test_withdrawn_becomes_a_positive_paid_out():
    transactions, _, _ = _clean_all()
    assert transactions[0].paid_out == Decimal("28.00")
    assert transactions[0].paid_in == Decimal("0")


def test_money_is_decimal_not_float():
    transactions, _, _ = _clean_all()
    assert isinstance(transactions[0].balance, Decimal)


def test_payment_and_its_charge_share_a_receipt_and_both_are_kept():
    transactions, _, _ = _clean_all()
    unique, removed = remove_duplicates(transactions)
    assert removed == 0
    assert len(unique) == 5


def test_true_duplicates_are_removed():
    transactions, _, _ = _clean_all()
    unique, removed = remove_duplicates(transactions + transactions)
    assert removed == 5
    assert len(unique) == 5


# ---------- reconcile ----------

def test_totals_match_the_statement_summary():
    transactions, summary, _ = _clean_all()
    assert reconcile(transactions, summary) == []


def test_missing_row_is_caught():
    transactions, summary, _ = _clean_all()
    problems = reconcile(transactions[:-1], summary)  # lose the deposit
    assert len(problems) == 1
    assert "Money in" in problems[0]


def test_missing_summary_is_reported():
    transactions, _, _ = _clean_all()
    assert len(reconcile(transactions, {})) == 1
