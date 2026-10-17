"""Tests for the plain-English summary. FAKE data only. Run: py -m pytest"""

from datetime import date
from decimal import Decimal

from analyzer.cleaner import parse_amount
from analyzer.parser import ParsedStatement, StatementPeriod
from analyzer.pipeline import combine, process_parsed
from analyzer.summary import build_summary


def raw(receipt, when, details, paid_in="", withdrawn="", balance="0.00"):
    return {"receipt": receipt, "time": when, "details": details, "status": "Completed",
            "paid_in": paid_in, "withdrawn": withdrawn, "balance": balance}


def result(name, rows, start, end, summary=None):
    money_in = sum((parse_amount(r["paid_in"]) for r in rows), Decimal("0"))
    money_out = sum((abs(parse_amount(r["withdrawn"])) for r in rows), Decimal("0"))
    totals = summary or {"TOTAL": {"paid_in": f"{money_in:,.2f}", "paid_out": f"{money_out:,.2f}"}}
    parsed = ParsedStatement(
        rows=rows, summary=totals, warnings=[], skipped_rows=0,
        period=StatementPeriod(date.fromisoformat(start), date.fromisoformat(end)),
    )
    return process_parsed(name, parsed)


SEP = [
    raw("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - 254700***002 Jane Secret", paid_in="3,000.00"),
    raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", withdrawn="-1,000.00"),
    raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill Charge", withdrawn="-10.00"),
]
OCT = [
    raw("BBBBBBBB01", "2026-10-05 10:00:00", "Funds received from - 254700***002 Jane Secret", paid_in="3,000.00"),
    raw("BBBBBBBB02", "2026-10-10 10:00:00", "Pay Bill to 1234567 - TEST SCHOOL Acc. X/1", withdrawn="-1,200.00"),
    raw("BBBBBBBB02", "2026-10-10 10:00:00", "Pay Bill Charge", withdrawn="-20.00"),
]


def text(combined):
    return " ".join(build_summary(combined))


def test_one_month_summary_states_the_checked_numbers():
    combined = combine([result("sep.pdf", SEP, "2026-09-01", "2026-09-30")])
    out = text(combined)
    assert "01 Sep 2026 to 30 Sep 2026 (30 days)" in out and "3 transactions" in out
    assert "Money in was KES 3,000.00 and money out was KES 1,010.00" in out
    assert "your balance went up by KES 1,990.00" in out
    assert "Bills (Pay Bill) (KES 1,000.00, 100.0%)" in out
    assert "largest single payment was KES 1,000.00, on 10 Sep 2026" in out
    assert "Most money in came from Received from people: KES 3,000.00 (100.0% of money in)" in out
    assert "You paid KES 10.00 in fees across 1 charge, which is 1.0% of money out." in out
    assert "Every transaction was placed in a category." in out


def test_no_names_or_descriptions_appear():
    out = text(combine([result("sep.pdf", SEP, "2026-09-01", "2026-09-30")]))
    for secret in ("Jane", "Secret", "TEST SCHOOL", "254700", "1234567"):
        assert secret not in out


def test_two_full_months_state_the_change_from_the_comparison():
    combined = combine([
        result("sep.pdf", SEP, "2026-09-01", "2026-09-30"),
        result("oct.pdf", OCT, "2026-10-01", "2026-10-31"),
    ])
    out = text(combined)
    # 1,010 -> 1,220 is +210, which is 20.8% of 1,010
    assert "Money out in Oct 2026 was 20.8% higher than in Sep 2026 (KES 1,010.00 to KES 1,220.00)." in out


def test_partial_months_state_no_change():
    combined = combine([result("both.pdf", SEP + OCT, "2026-09-13", "2026-10-13",
                               summary={"TOTAL": {"paid_in": "6,000.00", "paid_out": "2,230.00"}})])
    out = text(combined)
    assert "only partly covered" in out and "no month-to-month change is stated" in out
    assert "higher" not in out and "lower" not in out


def test_uncategorized_rows_are_reported():
    rows = SEP + [raw("AAAAAAAA09", "2026-09-11 10:00:00", "Something Unknown", withdrawn="-50.00")]
    out = text(combine([result("sep.pdf", rows, "2026-09-01", "2026-09-30")]))
    assert "1 transaction could not be categorized" in out


def test_no_fees_gives_a_plain_sentence():
    rows = [SEP[0], SEP[1]]
    out = text(combine([result("sep.pdf", rows, "2026-09-01", "2026-09-30")]))
    assert "No transaction fees were charged." in out


def test_a_balance_that_went_down_says_so():
    rows = [
        raw("AAAAAAAA01", "2026-09-05 10:00:00", "Funds received from - X", paid_in="100.00"),
        raw("AAAAAAAA02", "2026-09-10 10:00:00", "Pay Bill to 1 - X", withdrawn="-300.00"),
    ]
    out = text(combine([result("sep.pdf", rows, "2026-09-01", "2026-09-30")]))
    assert "your balance went down by KES 200.00" in out


def test_a_left_out_file_is_mentioned_without_its_name():
    good = result("good.pdf", SEP, "2026-09-01", "2026-09-30")
    bad = result("secret_name.pdf", OCT, "2026-10-01", "2026-10-31",
                 summary={"TOTAL": {"paid_in": "1.00", "paid_out": "1.00"}})
    out = text(combine([good, bad]))
    assert "1 file left out because it did not pass the checks" in out
    assert "secret_name" not in out


def test_no_results_gives_no_summary():
    bad = result("bad.pdf", SEP, "2026-09-01", "2026-09-30",
                 summary={"TOTAL": {"paid_in": "1.00", "paid_out": "1.00"}})
    assert build_summary(combine([bad])) == []


def test_the_summary_gives_no_advice():
    out = text(combine([result("sep.pdf", SEP, "2026-09-01", "2026-09-30")])).lower()
    for word in ("should", "recommend", "you ought", "try to", "consider"):
        assert word not in out


def test_fuliza_is_explained_and_is_not_counted_as_income():
    rows = [
        raw("CCCCCCCC01", "2026-09-05 10:00:00", "OverDraft of Credit Party", paid_in="500.00"),
        raw("CCCCCCCC02", "2026-09-05 10:01:00", "Pay Bill to 1 - TEST", withdrawn="-500.00"),
        raw("CCCCCCCC03", "2026-09-08 10:00:00", "Funds received from - Test Person", paid_in="400.00"),
        raw("CCCCCCCC04", "2026-09-08 10:00:30", "OD Loan Repayment to 1000 - M-PESA Overdraw", withdrawn="-400.00"),
    ]
    out = text(combine([result("sep.pdf", rows, "2026-09-01", "2026-09-30")]))
    assert "Fuliza: you borrowed KES 500.00 and repaid KES 400.00." in out
    assert "Most money in came from Received from people: KES 400.00 (100.0% of money in, not counting Fuliza)" in out
    assert "Biggest spending categories: Bills (Pay Bill) (KES 500.00, 100.0%)" in out


def test_repaying_more_than_borrowed_is_explained_not_hidden():
    rows = [
        raw("DDDDDDDD01", "2026-09-05 10:00:00", "Funds received from - Test Person", paid_in="900.00"),
        raw("DDDDDDDD02", "2026-09-05 10:00:30", "OD Loan Repayment to 1000 - M-PESA Overdraw", withdrawn="-900.00"),
    ]
    out = text(combine([result("sep.pdf", rows, "2026-09-01", "2026-09-30")]))
    assert "borrowed KES 0.00 and repaid KES 900.00" in out
    assert "may have owed Fuliza before the statement began" in out


def test_when_borrowing_comes_first_no_owed_before_claim_is_made():
    rows = [
        raw("EEEEEEEE01", "2026-09-01 10:00:00", "OverDraft of Credit Party", paid_in="100.00"),
        raw("EEEEEEEE02", "2026-09-01 10:00:30", "Pay Bill to 1 - TEST", withdrawn="-100.00"),
        raw("EEEEEEEE03", "2026-09-04 10:00:00", "Funds received from - Test Person", paid_in="500.00"),
        raw("EEEEEEEE04", "2026-09-04 10:00:30", "OD Loan Repayment to 1000 - M-PESA Overdraw", withdrawn="-500.00"),
    ]
    out = text(combine([result("sep.pdf", rows, "2026-09-01", "2026-09-30")]))
    assert "Repayments are higher than the amount borrowed in this period" in out
    assert "owed Fuliza before" not in out
