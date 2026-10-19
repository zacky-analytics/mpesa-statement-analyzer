"""Reversals are shown clearly and never matched by guessing. FAKE data only. Run: py -m pytest"""

import io
from datetime import date

import pdfplumber

from analyzer.categorizer import REVERSALS, SHOPS, category_totals
from analyzer.cleaner import clean_rows, parse_amount
from analyzer.metrics import calculate_totals
from analyzer.parser import ParsedStatement, StatementPeriod
from analyzer.pipeline import combine, process_parsed
from analyzer.report import build_report
from analyzer.summary import build_summary, reversal_note


def raw(receipt, when, details, paid_in="", withdrawn="", balance="0.00"):
    return {"receipt": receipt, "time": when, "details": details, "status": "Completed",
            "paid_in": paid_in, "withdrawn": withdrawn, "balance": balance}


# Two payments of the SAME amount, then 2,000 comes back. Which one was reversed? Nobody can tell.
TWO_SAME = [
    raw("RRRRRRRR01", "2026-09-05 10:00:00", "Merchant Payment to 1 - Shop A", withdrawn="-2,000.00"),
    raw("RRRRRRRR02", "2026-09-06 10:00:00", "Merchant Payment to 2 - Shop B", withdrawn="-2,000.00"),
    raw("RRRRRRRR03", "2026-09-07 10:00:00", "Reversal of Merchant Payment", paid_in="2,000.00"),
]


def combined_for(rows):
    paid_in = sum((parse_amount(r["paid_in"]) for r in rows), parse_amount("0"))
    paid_out = sum((abs(parse_amount(r["withdrawn"])) for r in rows), parse_amount("0"))
    parsed = ParsedStatement(
        rows=rows,
        summary={"TOTAL": {"paid_in": f"{paid_in:,.2f}", "paid_out": f"{paid_out:,.2f}"}},
        warnings=[], skipped_rows=0,
        period=StatementPeriod(date(2026, 9, 1), date(2026, 9, 30)),
    )
    return combine([process_parsed("sep.pdf", parsed)])


def test_an_unmatched_reversal_does_not_change_any_other_row():
    before = category_totals(clean_rows(TWO_SAME[:2]))
    after = category_totals(clean_rows(TWO_SAME))
    shops_before = next(c for c in before if c.category == SHOPS)
    shops_after = next(c for c in after if c.category == SHOPS)
    assert shops_before == shops_after                       # both payments still counted, untouched
    reversal = next(c for c in after if c.category == REVERSALS)
    assert reversal.money_in == parse_amount("2,000.00")


def test_the_original_payment_stays_in_spending_and_the_reversal_is_not_spending():
    totals = calculate_totals(clean_rows(TWO_SAME))
    assert totals.spending == parse_amount("4,000.00")       # both payments
    assert totals.reversals_in == parse_amount("2,000.00")
    assert totals.net == parse_amount("-2,000.00")            # money really is only 2,000 down


def test_the_warning_says_what_is_and_is_not_matched():
    note = reversal_note(calculate_totals(clean_rows(TWO_SAME)))
    assert "2,000.00 came back" in note
    assert "not matched" in note and "still counted" in note


def test_the_summary_contains_the_warning():
    text = " ".join(build_summary(combined_for(TWO_SAME)))
    assert "not matched to the payment they cancel" in text


def test_no_reversals_means_no_warning():
    rows = TWO_SAME[:2]
    assert reversal_note(calculate_totals(clean_rows(rows))) is None
    assert "Reversals found" not in " ".join(build_summary(combined_for(rows)))


def test_an_ordinary_incoming_payment_of_the_same_amount_is_not_a_reversal():
    rows = TWO_SAME[:2] + [raw("RRRRRRRR04", "2026-09-07 10:00:00",
                               "Funds received from - Test Person", paid_in="2,000.00")]
    totals = calculate_totals(clean_rows(rows))
    assert totals.reversals_in == 0 and reversal_note(totals) is None


def test_several_reversals_are_added_together():
    rows = TWO_SAME + [raw("RRRRRRRR05", "2026-09-08 10:00:00", "Reversal of Pay Bill Charge", paid_in="34.00")]
    totals = calculate_totals(clean_rows(rows))
    assert totals.reversals_in == parse_amount("2,034.00")


def test_the_pdf_report_also_shows_the_warning():
    pdf = build_report(combined_for(TWO_SAME))
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        text = " ".join((page.extract_text() or "") for page in document.pages)
    assert "Reversals found" in " ".join(text.split())
