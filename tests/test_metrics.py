"""
Tests for fee detection and metrics. FAKE data only.
Run from the project folder:  py -m pytest
"""

from datetime import datetime
from decimal import Decimal

from analyzer.cleaner import Transaction
from analyzer.metrics import (
    calculate_totals,
    fee_review_list,
    monthly_totals,
    top_transactions,
)


def tx(details, paid_in="0", paid_out="0", when="2026-10-07 11:40:51", receipt="AAAAAAAA01"):
    return Transaction(
        receipt=receipt,
        time=datetime.strptime(when, "%Y-%m-%d %H:%M:%S"),
        details=details,
        status="Completed",
        paid_in=Decimal(paid_in),
        paid_out=Decimal(paid_out),
        balance=Decimal("0"),
    )


# ---------- fee detection ----------

def test_known_fee_descriptions_are_fees():
    assert tx("Pay Bill Charge", paid_out="34").is_fee
    assert tx("Customer Transfer of Funds Charge", paid_out="7").is_fee


def test_fee_matching_ignores_capital_letters():
    assert tx("PAY BILL CHARGE", paid_out="34").is_fee
    assert tx("pay bill charge", paid_out="34").is_fee


def test_normal_payments_are_not_fees():
    assert not tx("Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", paid_out="5000").is_fee
    assert not tx("Customer Transfer to - 0700***001 TEST PERSON", paid_out="300").is_fee


def test_shop_with_charge_in_its_name_is_not_a_fee():
    assert not tx("Merchant Payment to 111 - CHARGE POINT LTD", paid_out="500").is_fee


def test_reversal_is_not_a_fee_even_if_it_mentions_charge():
    row = tx("Reversal of Pay Bill Charge", paid_in="34")
    assert row.is_reversal
    assert not row.is_fee


# ---------- totals ----------

SAMPLE = [
    tx("Funds received from - 254700***002 Test Person", paid_in="1000"),
    tx("Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", paid_out="500"),
    tx("Pay Bill Charge", paid_out="34"),
    tx("Customer Transfer to - 0700***001 TEST PERSON", paid_out="300"),
    tx("Customer Transfer of Funds Charge", paid_out="7"),
]


def test_fees_are_inside_total_money_out():
    t = calculate_totals(SAMPLE)
    assert t.money_out == Decimal("841")          # 500 + 34 + 300 + 7
    assert t.fees_paid == Decimal("41")           # 34 + 7
    assert t.fee_count == 2


def test_spending_excludes_fees_and_adds_up():
    t = calculate_totals(SAMPLE)
    assert t.spending == Decimal("800")           # 500 + 300
    assert t.spending + t.fees_paid + t.reversals_out == t.money_out


def test_money_in_and_net():
    t = calculate_totals(SAMPLE)
    assert t.money_in == Decimal("1000")
    assert t.net == Decimal("159")                # 1000 - 841


def test_reversals_are_kept_out_of_fees_and_spending():
    rows = SAMPLE + [tx("Reversal of Pay Bill Charge", paid_in="34")]
    t = calculate_totals(rows)
    assert t.reversals_in == Decimal("34")
    assert t.fees_paid == Decimal("41")
    assert t.money_in == Decimal("1034")          # still inside total money in


def test_empty_list_gives_zeros():
    t = calculate_totals([])
    assert t.money_in == t.money_out == t.fees_paid == t.spending == Decimal("0")
    assert t.transaction_count == 0


def test_money_stays_exact_decimal():
    rows = [tx("Pay Bill Charge", paid_out="0.10"), tx("Pay Bill Charge", paid_out="0.20")]
    assert calculate_totals(rows).fees_paid == Decimal("0.30")


# ---------- top transactions ----------

def test_top_transactions_skip_fees_and_are_sorted():
    top = top_transactions(SAMPLE, count=2)
    assert [t.paid_out for t in top] == [Decimal("500"), Decimal("300")]


# ---------- months ----------

def test_months_are_grouped_by_calendar_month_oldest_first():
    rows = [
        tx("Pay Bill to X", paid_out="10", when="2026-10-02 10:00:00"),
        tx("Pay Bill to X", paid_out="20", when="2026-09-18 10:00:00"),
        tx("Pay Bill to X", paid_out="30", when="2026-09-25 10:00:00"),
    ]
    months = monthly_totals(rows)
    assert [m.month for m in months] == ["2026-09", "2026-10"]
    assert months[0].totals.money_out == Decimal("50")
    assert months[0].first_day.isoformat() == "2026-09-18"
    assert months[0].last_day.isoformat() == "2026-09-25"


# ---------- review list ----------

def test_unclear_rows_are_listed_for_review_not_hidden():
    rows = SAMPLE + [tx("Merchant Payment to 111 - CHARGE POINT LTD", paid_out="500")]
    review = fee_review_list(rows)
    assert len(review) == 1
    assert "CHARGE POINT" in review[0].details


def test_fuliza_borrowed_and_repaid_are_not_income_or_spending():
    from datetime import datetime
    from decimal import Decimal
    from analyzer.cleaner import Transaction
    from analyzer.metrics import calculate_totals

    def row(details, paid_in="0", paid_out="0"):
        return Transaction("AAAAAAAA01", datetime(2026, 9, 1, 10, 0, 0), details, "Completed",
                           Decimal(paid_in), Decimal(paid_out), Decimal("0"))

    rows = [
        row("OverDraft of Credit Party", paid_in="500"),
        row("Pay Bill to 1 - X", paid_out="500"),
        row("OD Loan Repayment to 1000 - M-PESA Overdraw", paid_out="300"),
        row("Funds received from - X", paid_in="300"),
    ]
    t = calculate_totals(rows)
    assert t.loans_in == Decimal("500") and t.loans_repaid == Decimal("300")
    assert t.money_out == Decimal("800") and t.spending == Decimal("500")
    assert t.money_in == Decimal("800")
