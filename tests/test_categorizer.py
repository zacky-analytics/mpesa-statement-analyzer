"""
Tests for the categorizer. FAKE data only.
Run from the project folder:  py -m pytest
"""

from datetime import datetime
from decimal import Decimal

from analyzer.categorizer import (
    AIRTIME, BILLS, DEPOSITS, FEES, RECEIVED, REVERSALS, SENT, SHOPS, UNCATEGORIZED,
    WITHDRAWALS, RECEIVED_BUSINESS,
    categorize, category_totals, top_spending_categories,
    uncategorized_rows, uncategorized_share,
)
from analyzer.cleaner import Transaction


def tx(details, paid_in="0", paid_out="0"):
    return Transaction(
        receipt="AAAAAAAA01",
        time=datetime(2026, 10, 7, 11, 40, 51),
        details=details,
        status="Completed",
        paid_in=Decimal(paid_in),
        paid_out=Decimal(paid_out),
        balance=Decimal("0"),
    )


# ---------- each rule ----------

def test_sent_to_people():
    assert categorize(tx("Customer Transfer to - 0700***001 TEST PERSON", paid_out="300")) == SENT


def test_received_from_people():
    assert categorize(tx("Funds received from - 254700***002 Test Person", paid_in="50")) == RECEIVED


def test_bills():
    assert categorize(tx("Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", paid_out="5000")) == BILLS


def test_shops():
    assert categorize(tx("Merchant Payment to 111 - TEST SHOP", paid_out="300")) == SHOPS


def test_bundles_by_prefix():
    row = tx("Customer Bundle Purchase to 826915Safaricom Offers by - 254700***003 TEST", paid_out="20")
    assert categorize(row) == AIRTIME


def test_airtime_by_keyword():
    assert categorize(tx("Airtime Purchase for 0700***004", paid_out="50")) == AIRTIME


def test_cash_deposit():
    assert categorize(tx("Deposit of Funds at Agent Till 111 - TEST SHOP", paid_in="2600")) == DEPOSITS


def test_agent_cash_withdrawal():
    row = tx("Customer Withdrawal At Agent Till 606808 - Test Connection Test Town", paid_out="140")
    assert categorize(row) == WITHDRAWALS


def test_withdrawal_is_matched_ignoring_case_and_counts_as_spending():
    row = tx("CUSTOMER WITHDRAWAL AT AGENT TILL 1 - X", paid_out="500")
    assert categorize(row) == WITHDRAWALS
    top = top_spending_categories([row])
    assert [c.category for c in top] == [WITHDRAWALS]


def test_withdrawal_charge_is_still_a_fee():
    assert categorize(tx("Customer Withdrawal Charge", paid_out="28")) == FEES


def test_an_unknown_withdrawal_wording_stays_uncategorized():
    assert categorize(tx("Withdrawal from somewhere else", paid_out="50")) == UNCATEGORIZED


# ---------- order and safety ----------

def test_matching_ignores_capital_letters_and_extra_spaces():
    assert categorize(tx("CUSTOMER   TRANSFER  TO - 0700***001 TEST", paid_out="10")) == SENT


def test_fee_wins_over_every_other_rule():
    assert categorize(tx("Pay Bill Charge", paid_out="34")) == FEES
    assert categorize(tx("Customer Transfer of Funds Charge", paid_out="7")) == FEES


def test_reversal_gets_its_own_category_not_uncategorized():
    assert categorize(tx("Reversal of Pay Bill Charge", paid_in="34")) == REVERSALS


def test_keyword_rule_does_not_beat_a_prefix_rule():
    # A cash deposit at a shop that has 'airtime' in its name is still a deposit
    row = tx("Deposit of Funds at Agent Till 111 - TEST AIRTIME SHOP", paid_in="100")
    assert categorize(row) == DEPOSITS


def test_a_prefix_must_be_at_the_start_not_just_inside():
    # 'pay bill to' appears inside the text but not at the start
    assert categorize(tx("Something odd - pay bill to 123", paid_out="10")) == UNCATEGORIZED


def test_unseen_transaction_types_are_uncategorized_not_guessed():
    assert categorize(tx("Withdrawal from Agent 123 - TEST SHOP", paid_out="500")) == UNCATEGORIZED


# ---------- totals ----------

SAMPLE = [
    tx("Funds received from - 254700***002 Test Person", paid_in="1000"),
    tx("Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", paid_out="500"),
    tx("Pay Bill Charge", paid_out="34"),
    tx("Customer Transfer to - 0700***001 TEST PERSON", paid_out="300"),
    tx("Customer Transfer to - 0700***005 OTHER PERSON", paid_out="100"),
    tx("Withdrawal from Agent 123 - TEST SHOP", paid_out="200"),
]


def test_category_totals_add_up_to_everything():
    totals = category_totals(SAMPLE)
    assert sum(c.count for c in totals) == len(SAMPLE)
    assert sum(c.money_out for c in totals) == Decimal("1134")
    assert sum(c.money_in for c in totals) == Decimal("1000")


def test_category_totals_per_category():
    by_name = {c.category: c for c in category_totals(SAMPLE)}
    assert by_name[SENT].count == 2
    assert by_name[SENT].money_out == Decimal("400")
    assert by_name[FEES].money_out == Decimal("34")


def test_empty_categories_are_not_listed():
    names = [c.category for c in category_totals(SAMPLE)]
    assert REVERSALS not in names


def test_top_spending_categories_skip_fees_and_incoming():
    top = top_spending_categories(SAMPLE, count=10)
    names = [c.category for c in top]
    assert FEES not in names
    assert RECEIVED not in names
    assert names[0] == BILLS          # 500 is the largest
    assert top[0].money_out == Decimal("500")


# ---------- uncertainty ----------

def test_uncategorized_rows_are_listed_for_review():
    rows = uncategorized_rows(SAMPLE)
    assert len(rows) == 1
    assert rows[0].details.startswith("Withdrawal")


def test_uncategorized_share_is_a_fraction_of_all_money_moved():
    # money moved = 1000 in + 1134 out = 2134; uncategorized = 200
    share = uncategorized_share(SAMPLE)
    assert share == Decimal("200") / Decimal("2134")


def test_share_is_zero_for_empty_list():
    assert uncategorized_share([]) == Decimal("0")


# ---------- Fuliza ----------

from analyzer.categorizer import FULIZA_BORROWED, FULIZA_REPAID  # noqa: E402


def test_fuliza_money_borrowed_is_not_income():
    assert categorize(tx("OverDraft of Credit Party", paid_in="500")) == FULIZA_BORROWED


def test_fuliza_repayment_is_not_spending():
    row = tx("OD Loan Repayment to 1000 - M-PESA Overdraw", paid_out="400")
    assert categorize(row) == FULIZA_REPAID
    assert top_spending_categories([row]) == []


def test_only_exact_loan_wording_counts_as_a_loan_row():
    # Unknown Fuliza wording is NOT guessed: it stays Uncategorized.
    assert categorize(tx("Fuliza top up", paid_in="100")) == UNCATEGORIZED
    assert categorize(tx("Fuliza payment", paid_out="100")) == UNCATEGORIZED


def test_payments_made_with_fuliza_money_are_spending_by_what_they_were_for():
    cases = [
        ("Customer Withdrawal at Agent Till with Fuliza to 369713 - Test Station", WITHDRAWALS),
        ("Customer Transfer Fuliza MPesa to - 254700***001 TEST PERSON", SENT),
        ("Pay Bill Online Fuliza M-Pesa to 244441 - TEST BUNDLES Acc. X", BILLS),
        ("Pay Bill Fuliza M-Pesa to 4104151 - TEST LIMITED PB Acc. 1", BILLS),
        ("Merchant Payment Fuliza M-Pesa to 6071807 - TEST PETROLEUM", SHOPS),
        ("Customer Bundle Purchase with Fuliza to 244441TEST BUNDLES by - 254700***001 X", AIRTIME),
        ("Airtime Purchase with Fuliza", AIRTIME),
    ]
    for details, expected in cases:
        assert categorize(tx(details, paid_out="100")) == expected, details


def test_a_fuliza_charge_is_a_fee_not_a_loan_row():
    assert categorize(tx("Fuliza Charge", paid_out="5")) == FEES


def test_a_payment_made_with_fuliza_money_is_categorized_normally():
    assert categorize(tx("Pay Bill to 123 - TEST SCHOOL Acc. X", paid_out="500")) == BILLS


def test_money_paid_in_by_banks_and_businesses():
    row = tx("Business Payment from 501901 - TEST BANK 1 via API. Original conversation ID is X", paid_in="10200")
    assert categorize(row) == RECEIVED_BUSINESS


def test_health_insurance_paybill_and_small_business_payments():
    assert categorize(tx("SHA Customer Insurance Payment to 200222 - SHA Acc. 12345", paid_out="2600")) == BILLS
    assert categorize(tx("Customer Payment to Small Business to - 254700***001 TEST PERSON", paid_out="60")) == SHOPS
