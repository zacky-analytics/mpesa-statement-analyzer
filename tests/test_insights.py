"""Tests for the spending facts. FAKE data only. Run: py -m pytest"""

from datetime import datetime
from decimal import Decimal

from analyzer.cleaner import Transaction
from analyzer.insights import average_per_day, biggest_day, busiest_weekday, top_payees


def tx(when, details, paid_out="0", paid_in="0"):
    return Transaction("R", datetime.fromisoformat(when), details, "Completed",
                       Decimal(paid_in), Decimal(paid_out), Decimal("0"))


ROWS = [
    tx("2026-09-07 10:00:00", "Merchant Payment to 1 - Shop A", "300"),       # Monday
    tx("2026-09-07 12:00:00", "merchant  payment to 1 - shop a", "200"),      # Monday, same text
    tx("2026-09-08 10:00:00", "Pay Bill to 2 - Water Co", "400"),             # Tuesday
    tx("2026-09-08 10:00:00", "Pay Bill Charge", "10"),                       # fee: not spending
    tx("2026-09-09 10:00:00", "OD Loan Repayment to 1000 - M-PESA Overdraw", "900"),  # not spending
    tx("2026-09-09 11:00:00", "Funds received from - Test Person", paid_in="5000"),   # not spending
]


def test_average_per_day_uses_spending_only():
    assert average_per_day(ROWS, 10) == Decimal("90")          # (300 + 200 + 400) / 10


def test_average_per_day_is_none_without_known_days():
    assert average_per_day(ROWS, 0) is None


def test_biggest_day_and_busiest_weekday():
    assert biggest_day(ROWS)[1] == Decimal("500") and str(biggest_day(ROWS)[0]) == "2026-09-07"
    assert busiest_weekday(ROWS) == ("Monday", Decimal("500"))


def test_top_payees_group_only_identical_text():
    top = top_payees(ROWS)
    assert top[0].count == 2 and top[0].total == Decimal("500")
    assert top[0].name == "Merchant Payment to 1 - Shop A"
    assert len(top) == 2


def test_nothing_to_report_gives_none_or_empty():
    only_in = [tx("2026-09-09 11:00:00", "Funds received from - X", paid_in="5")]
    assert biggest_day(only_in) is None and busiest_weekday(only_in) is None and top_payees(only_in) == []
