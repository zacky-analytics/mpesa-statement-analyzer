"""Tests for the PDF report. FAKE data only. Run: py -m pytest"""

from datetime import date
from decimal import Decimal

from analyzer.cleaner import parse_amount
from analyzer.parser import ParsedStatement, StatementPeriod
from analyzer.pipeline import combine, process_parsed
from analyzer.report import build_report


def raw(receipt, when, details, paid_in="", withdrawn="", balance="0.00"):
    return {"receipt": receipt, "time": when, "details": details, "status": "Completed",
            "paid_in": paid_in, "withdrawn": withdrawn, "balance": balance}


ROWS = [
    raw("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - Test Person", paid_in="3,000.00", balance="3,000.00"),
    raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill to 1 - TEST", withdrawn="-1,000.00", balance="2,000.00"),
    raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill Charge", withdrawn="-10.00", balance="1,990.00"),
]


def make(name="sep.pdf"):
    money_in = sum((parse_amount(r["paid_in"]) for r in ROWS), Decimal("0"))
    money_out = sum((abs(parse_amount(r["withdrawn"])) for r in ROWS), Decimal("0"))
    parsed = ParsedStatement(
        rows=ROWS,
        summary={"TOTAL": {"paid_in": f"{money_in:,.2f}", "paid_out": f"{money_out:,.2f}"}},
        warnings=[], skipped_rows=0,
        period=StatementPeriod(date(2026, 9, 1), date(2026, 9, 30)),
    )
    return combine([process_parsed(name, parsed)])


def test_report_is_a_real_pdf():
    pdf = build_report(make())
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000


def test_a_file_name_with_markup_characters_does_not_break_the_report():
    pdf = build_report(make("a<b>&c.pdf"))
    assert pdf.startswith(b"%PDF")


def test_a_single_month_report_has_no_comparison_and_still_builds():
    combined = make()
    assert combined.comparison is None
    assert build_report(combined).startswith(b"%PDF")
