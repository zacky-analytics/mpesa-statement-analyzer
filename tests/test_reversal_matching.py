"""
A reversal is tied to its payment ONLY on exact evidence. FAKE data only.
The wording copies a real statement; the names and numbers are made up.
Run: py -m pytest
"""

import io
from datetime import date

import pdfplumber

from analyzer.categorizer import RECEIVED, REVERSALS, SENT, category_totals
from analyzer.cleaner import clean_rows, parse_amount
from analyzer.metrics import calculate_totals, monthly_totals
from analyzer.parser import ParsedStatement, StatementPeriod
from analyzer.pipeline import combine, process_parsed
from analyzer.report import build_report
from analyzer.reversals import mark_reversal_pairs, other_party
from analyzer.summary import build_summary, reversal_note


def raw(receipt, when, details, paid_in="", withdrawn="", balance="0.00"):
    return {"receipt": receipt, "time": when, "details": details, "status": "Completed",
            "paid_in": paid_in, "withdrawn": withdrawn, "balance": balance}


PERSON = "254700***111 TEST PERSON"
OTHER = "254700***222 OTHER PERSON"

# A mistaken payment arrives and Safaricom sends it back (same shape as the real case).
RECEIVED_THEN_BACK = [
    raw("AAAAAAAA01", "2026-10-30 19:07:43", f"Funds received from - {PERSON}", paid_in="3,100.00"),
    raw("AAAAAAAA02", "2026-10-31 10:08:09", f"Send Money Reversal via API to - {PERSON}", withdrawn="-3,100.00"),
]
# We paid 80 and it came back.
PAID_THEN_BACK = [
    raw("BBBBBBBB01", "2026-10-27 09:00:00", f"Customer Transfer to - {PERSON}", withdrawn="-80.00"),
    raw("BBBBBBBB02", "2026-10-28 12:11:00", f"Send Money Reversal via API from - {PERSON}", paid_in="80.00"),
]
ORDINARY = [
    raw("CCCCCCCC01", "2026-10-02 08:00:00", f"Funds received from - {OTHER}", paid_in="1,000.00"),
    raw("CCCCCCCC02", "2026-10-03 08:00:00", "Merchant Payment to 5 - Some Shop", withdrawn="-250.00"),
]


def combined_for(rows, start=date(2026, 10, 1), end=date(2026, 10, 31)):
    paid_in = sum((parse_amount(r["paid_in"]) for r in rows), parse_amount("0"))
    paid_out = sum((abs(parse_amount(r["withdrawn"])) for r in rows), parse_amount("0"))
    parsed = ParsedStatement(
        rows=rows,
        summary={"TOTAL": {"paid_in": f"{paid_in:,.2f}", "paid_out": f"{paid_out:,.2f}"}},
        warnings=[], skipped_rows=0, period=StatementPeriod(start, end),
    )
    return combine([process_parsed("oct.pdf", parsed)])


def category(combined, name):
    return next((c for c in category_totals(list(combined.transactions)) if c.category == name), None)


# ---------------------------------------------------------------- the wording

def test_other_party_is_the_text_after_the_first_dash():
    assert other_party("Send Money Reversal via API to - 254700***111 TEST PERSON") == "254700***111 test person"
    assert other_party("Funds received from -   254700***111   Test  Person ") == "254700***111 test person"
    assert other_party("Send Money Reversal via API to -\n254700***111 TEST PERSON") == "254700***111 test person"


def test_no_dash_means_no_party():
    assert other_party("Reversal of Merchant Payment") is None
    assert other_party("Customer Transfer to -") is None


# ---------------------------------------------------------------- matches that are proven

def test_money_received_then_sent_back_is_matched():
    combined = combined_for(ORDINARY + RECEIVED_THEN_BACK)
    marked = [t for t in combined.transactions if t.matched_reversal]
    assert sorted(t.receipt for t in marked) == ["AAAAAAAA01", "AAAAAAAA02"]
    totals = calculate_totals(list(combined.transactions))
    assert totals.cancelled_in == parse_amount("3,100.00")
    assert totals.cancelled_out == 0
    assert totals.reversals_matched == 1 and totals.reversals_unmatched == 0


def test_a_matched_receipt_leaves_received_from_people_and_goes_to_reversals():
    combined = combined_for(ORDINARY + RECEIVED_THEN_BACK)
    assert category(combined, RECEIVED).money_in == parse_amount("1,000.00")   # only the ordinary one
    reversals = category(combined, REVERSALS)
    assert reversals.money_in == parse_amount("3,100.00")                      # the mistaken payment
    assert reversals.money_out == parse_amount("3,100.00")                     # and its reversal: nets to zero


def test_money_in_and_money_out_stay_the_statements_own_totals():
    combined = combined_for(ORDINARY + RECEIVED_THEN_BACK)
    totals = calculate_totals(list(combined.transactions))
    assert totals.money_in == parse_amount("4,100.00")
    assert totals.money_out == parse_amount("3,350.00")
    assert totals.net == parse_amount("750.00")
    assert totals.spending == parse_amount("250.00")        # the shop payment only


def test_a_payment_that_came_back_is_taken_out_of_spending():
    combined = combined_for(ORDINARY + PAID_THEN_BACK)
    totals = calculate_totals(list(combined.transactions))
    assert totals.cancelled_out == parse_amount("80.00")
    assert totals.spending == parse_amount("250.00")        # the 80 is no longer spending
    assert totals.money_out == parse_amount("330.00")       # still the statement's total
    assert category(combined, SENT) is None                 # the only 'sent' row was cancelled


def test_two_proven_pairs_in_one_statement():
    combined = combined_for(RECEIVED_THEN_BACK + PAID_THEN_BACK)
    totals = calculate_totals(list(combined.transactions))
    assert totals.reversals_matched == 2 and totals.reversals_unmatched == 0
    assert totals.cancelled_in == parse_amount("3,100.00")
    assert totals.cancelled_out == parse_amount("80.00")


def test_a_pair_split_across_two_months_is_still_matched():
    rows = [
        raw("DDDDDDDD01", "2026-10-31 22:00:00", f"Customer Transfer to - {PERSON}", withdrawn="-500.00"),
        raw("DDDDDDDD02", "2026-11-01 08:00:00", f"Send Money Reversal via API from - {PERSON}", paid_in="500.00"),
    ]
    combined = combined_for(rows, end=date(2026, 11, 30))
    assert all(t.matched_reversal for t in combined.transactions)
    october, november = [m.totals for m in monthly_totals(list(combined.transactions))]
    assert october.spending == 0 and october.cancelled_out == parse_amount("500.00")
    assert november.reversals_matched == 1


# ---------------------------------------------------------------- everything short of proof stays unmatched

def test_two_identical_payments_means_nothing_is_matched():
    rows = [
        raw("EEEEEEEE01", "2026-10-28 08:00:00", f"Funds received from - {PERSON}", paid_in="3,100.00"),
        raw("EEEEEEEE02", "2026-10-29 08:00:00", f"Funds received from - {PERSON}", paid_in="3,100.00"),
        raw("EEEEEEEE03", "2026-10-31 10:00:00", f"Send Money Reversal via API to - {PERSON}", withdrawn="-3,100.00"),
    ]
    combined = combined_for(rows)
    assert not any(t.matched_reversal for t in combined.transactions)
    totals = calculate_totals(list(combined.transactions))
    assert totals.reversals_unmatched == 1 and totals.cancelled_in == 0
    assert category(combined, RECEIVED).money_in == parse_amount("6,200.00")     # untouched


def test_a_different_person_is_not_matched():
    rows = [
        raw("FFFFFFFF01", "2026-10-30 08:00:00", f"Funds received from - {OTHER}", paid_in="3,100.00"),
        raw("FFFFFFFF02", "2026-10-31 08:00:00", f"Send Money Reversal via API to - {PERSON}", withdrawn="-3,100.00"),
    ]
    assert not any(t.matched_reversal for t in combined_for(rows).transactions)


def test_a_different_amount_is_not_matched():
    rows = [
        raw("GGGGGGGG01", "2026-10-30 08:00:00", f"Funds received from - {PERSON}", paid_in="3,100.00"),
        raw("GGGGGGGG02", "2026-10-31 08:00:00", f"Send Money Reversal via API to - {PERSON}", withdrawn="-3,000.00"),
    ]
    assert not any(t.matched_reversal for t in combined_for(rows).transactions)


def test_a_payment_after_the_reversal_is_not_matched():
    rows = [
        raw("HHHHHHHH01", "2026-10-30 08:00:00", f"Send Money Reversal via API to - {PERSON}", withdrawn="-3,100.00"),
        raw("HHHHHHHH02", "2026-10-31 08:00:00", f"Funds received from - {PERSON}", paid_in="3,100.00"),
    ]
    assert not any(t.matched_reversal for t in combined_for(rows).transactions)


def test_wrong_direction_is_not_matched():
    # Money came in, and a reversal ALSO brought money in: it cannot be cancelling that receipt.
    rows = [
        raw("IIIIIIII01", "2026-10-30 08:00:00", f"Funds received from - {PERSON}", paid_in="80.00"),
        raw("IIIIIIII02", "2026-10-31 08:00:00", f"Send Money Reversal via API from - {PERSON}", paid_in="80.00"),
    ]
    assert not any(t.matched_reversal for t in combined_for(rows).transactions)


def test_no_payment_in_the_statement_means_the_reversal_stays_unmatched():
    combined = combined_for(ORDINARY + RECEIVED_THEN_BACK[1:])       # the receipt is outside the file
    assert not any(t.matched_reversal for t in combined.transactions)
    assert calculate_totals(list(combined.transactions)).reversals_unmatched == 1


def test_a_reversal_without_a_named_person_is_never_matched():
    rows = [
        raw("JJJJJJJJ01", "2026-10-05 08:00:00", "Merchant Payment to 5 - Some Shop", withdrawn="-2,000.00"),
        raw("JJJJJJJJ02", "2026-10-06 08:00:00", "Reversal of Merchant Payment", paid_in="2,000.00"),
    ]
    assert not any(t.matched_reversal for t in combined_for(rows).transactions)


def test_two_reversals_cannot_claim_the_same_payment():
    rows = RECEIVED_THEN_BACK + [
        raw("KKKKKKKK01", "2026-10-31 11:00:00", f"Send Money Reversal via API to - {PERSON}", withdrawn="-3,100.00"),
    ]
    combined = combined_for(rows)
    assert not any(t.matched_reversal for t in combined.transactions)
    assert calculate_totals(list(combined.transactions)).reversals_unmatched == 2


def test_a_reversal_is_never_the_payment_cancelled_by_another_reversal():
    rows = RECEIVED_THEN_BACK + [
        raw("LLLLLLLL01", "2026-11-01 08:00:00", f"Send Money Reversal via API from - {PERSON}", paid_in="3,100.00"),
    ]
    combined = combined_for(rows, end=date(2026, 11, 30))
    flagged = {t.receipt for t in combined.transactions if t.matched_reversal}
    assert "LLLLLLLL01" not in flagged                      # nothing for it to cancel except a reversal
    assert flagged == {"AAAAAAAA01", "AAAAAAAA02"}


def test_marking_does_not_change_the_rows_otherwise():
    rows = clean_rows(ORDINARY + RECEIVED_THEN_BACK)
    marked = mark_reversal_pairs(rows)
    assert len(marked) == len(rows)
    for before, after in zip(rows, marked):
        assert before.duplicate_key == after.duplicate_key


# ---------------------------------------------------------------- what the person reads

def test_the_note_for_a_clean_match_is_information_not_a_warning():
    totals = calculate_totals(list(combined_for(RECEIVED_THEN_BACK).transactions))
    note = reversal_note(totals)
    assert "Reversals matched" in note and "3,100.00 was received and then sent back" in note
    assert "not matched" not in note
    assert totals.reversals_unmatched == 0                  # app.py shows st.info when this is 0


def test_the_note_for_a_paid_then_returned_match():
    totals = calculate_totals(list(combined_for(PAID_THEN_BACK).transactions))
    assert "80.00 was paid and then came back" in reversal_note(totals)


def test_matched_and_unmatched_reversals_are_both_explained():
    rows = RECEIVED_THEN_BACK + [
        raw("MMMMMMMM01", "2026-10-05 08:00:00", "Merchant Payment to 5 - Some Shop", withdrawn="-2,000.00"),
        raw("MMMMMMMM02", "2026-10-06 08:00:00", "Reversal of Merchant Payment", paid_in="2,000.00"),
    ]
    totals = calculate_totals(list(combined_for(rows).transactions))
    note = reversal_note(totals)
    assert "Reversals matched" in note
    assert "Reversals found: KES 2,000.00 came back" in note and "not matched to the payment they cancel" in note
    assert totals.reversals_unmatched == 1


def test_the_unmatched_note_no_longer_claims_the_payment_is_always_spending():
    totals = calculate_totals(clean_rows([
        raw("NNNNNNNN01", "2026-10-06 08:00:00", "Reversal of Merchant Payment", paid_in="2,000.00")]))
    note = reversal_note(totals)
    assert "if it was money you paid" in note


def test_the_summary_and_the_pdf_use_the_matched_note():
    combined = combined_for(ORDINARY + RECEIVED_THEN_BACK)
    assert "Reversals matched" in " ".join(build_summary(combined))
    with pdfplumber.open(io.BytesIO(build_report(combined))) as document:
        text = " ".join((page.extract_text() or "") for page in document.pages)
    assert "Reversals matched" in " ".join(text.split())


def test_no_reversals_still_means_no_note():
    totals = calculate_totals(list(combined_for(ORDINARY).transactions))
    assert reversal_note(totals) is None
    assert totals.reversals_matched == 0 and totals.cancelled_in == 0
