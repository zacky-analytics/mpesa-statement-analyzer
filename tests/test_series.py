"""Tests for the chart numbers. FAKE data only. Run: py -m pytest"""

from datetime import date, datetime
from decimal import Decimal

from analyzer.cleaner import Transaction
from analyzer.series import closing_balances, daily_flow


def tx(receipt, when, details, paid_in="0", paid_out="0", balance="0"):
    return Transaction(receipt, datetime.fromisoformat(when), details, "Completed",
                       Decimal(paid_in), Decimal(paid_out), Decimal(balance))


def test_daily_flow_sums_each_day_and_skips_quiet_days():
    rows = [
        tx("A1", "2026-09-05 10:00:00", "x", paid_in="500", balance="500"),
        tx("A2", "2026-09-05 11:00:00", "x", paid_out="100", balance="400"),
        tx("A3", "2026-09-09 11:00:00", "x", paid_out="50", balance="350"),
    ]
    flows = daily_flow(rows)
    assert [f.day for f in flows] == [date(2026, 9, 5), date(2026, 9, 9)]
    assert flows[0].money_in == Decimal("500") and flows[0].money_out == Decimal("100")
    assert flows[1].money_in == Decimal("0") and flows[1].money_out == Decimal("50")


def test_closing_balance_is_the_last_transaction_of_the_day():
    rows = [
        tx("A1", "2026-09-05 10:00:00", "x", paid_in="500", balance="500"),
        tx("A2", "2026-09-05 11:00:00", "x", paid_out="100", balance="400"),
    ]
    [day] = closing_balances(rows)
    assert day.balance == Decimal("400") and day.certain


def test_a_payment_and_its_fee_at_the_same_second_are_ordered_by_the_balances():
    # Payment 1000 then its fee 10, same timestamp. Fee is the LAST row: balance 990.
    pay = tx("B1", "2026-09-06 10:00:00", "Pay Bill to 1", paid_out="1000", balance="1000")
    fee = tx("B1", "2026-09-06 10:00:00", "Pay Bill Charge", paid_out="10", balance="990")
    for order in ([pay, fee], [fee, pay]):          # statement order must not matter
        [day] = closing_balances(order)
        assert day.balance == Decimal("990") and day.certain


def test_an_undecidable_tie_is_flagged_not_hidden():
    a = tx("C1", "2026-09-06 10:00:00", "x", paid_out="10", balance="500")
    b = tx("C2", "2026-09-06 10:00:00", "x", paid_out="20", balance="700")   # unrelated balances
    [day] = closing_balances([a, b])
    assert not day.certain


def test_no_transactions_gives_empty_lists():
    assert daily_flow([]) == [] and closing_balances([]) == []
