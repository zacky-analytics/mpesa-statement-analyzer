"""
sample.py - FAKE statements for the "Try with sample data" button.

Everything here is invented: names, numbers and amounts. No real person or
account is used. The rows go through the same cleaning, checking and
categorizing as a real statement, so the demo shows the real behavior.
The balance column is calculated from the rows, so each file adds up exactly.
"""

from datetime import date
from decimal import Decimal

from analyzer.parser import ParsedStatement, StatementPeriod
from analyzer.pipeline import combine, process_parsed

# (day, hour, kind, who, base amount, fee)
_PLAN = [
    (1, 8, "biz_in", "100100 - Sample Employer Ltd", 42000, 0),
    (2, 9, "bill", "400200 - Sample Landlord Acc. RENT", 12000, 25),
    (3, 12, "shop", "500300 - Sample Supermarket", 2150, 0),
    (4, 18, "airtime", "Safaricom Data Bundles", 500, 0),
    (5, 10, "send", "254700***101 Test Person A", 3000, 22),
    (7, 14, "withdraw", "123456 - Sample Agent", 4000, 59),
    (8, 11, "shop", "500301 - Sample Fuel Station", 3200, 0),
    (9, 9, "person_in", "254700***102 Test Person B", 6000, 0),
    (10, 19, "bill", "400201 - Sample Power Co Acc. 5566", 1800, 5),
    (11, 13, "shop", "500302 - Sample Pharmacy", 950, 0),
    (12, 8, "fuliza_in", "", 1500, 0),
    (12, 8, "shop", "500303 - Sample Restaurant", 1500, 0),
    (14, 17, "send", "254700***103 Test Person C", 1500, 22),
    (15, 10, "shop", "500300 - Sample Supermarket", 2800, 0),
    (16, 12, "fuliza_out", "", 1500, 0),
    (17, 15, "airtime", "Safaricom Data Bundles", 250, 0),
    (18, 11, "deposit", "123456 - Sample Agent", 5000, 0),
    (19, 20, "bill", "400202 - Sample Internet Co Acc. 7788", 3000, 5),
    (21, 9, "shop", "500304 - Sample Hardware", 4100, 0),
    (22, 16, "person_in", "254700***104 Test Person D", 2500, 0),
    (23, 12, "send", "254700***101 Test Person A", 2000, 22),
    (24, 18, "shop", "500300 - Sample Supermarket", 1900, 0),
    (26, 10, "withdraw", "123456 - Sample Agent", 3000, 59),
    (27, 13, "shop", "500301 - Sample Fuel Station", 2700, 0),
    (28, 9, "airtime", "Safaricom Data Bundles", 300, 0),
    (29, 19, "bill", "400201 - Sample Power Co Acc. 5566", 1200, 5),
]

_DETAILS = {
    "biz_in": "Business Payment from {who}",
    "person_in": "Funds received from - {who}",
    "send": "Customer Transfer to - {who}",
    "bill": "Pay Bill to {who}",
    "shop": "Merchant Payment to {who}",
    "airtime": "Customer Bundle Purchase - {who}",
    "withdraw": "Customer Withdrawal At Agent Till {who}",
    "deposit": "Deposit of Funds at Agent {who}",
    "fuliza_in": "OverDraft of Credit Party",
    "fuliza_out": "OD Loan Repayment to 1000 - M-PESA Overdraw",
}
_FEE_DETAILS = {
    "send": "Customer Transfer of Funds Charge",
    "bill": "Pay Bill Charge",
    "withdraw": "Withdrawal Charge",
}
_MONEY_IN = {"biz_in", "person_in", "deposit", "fuliza_in"}

_STATEMENTS = [
    # (file name, year, month, last day, scale in percent, code)
    ("Sample statement (fake) - Aug 2026", 2026, 8, 31, 100, "A"),
    ("Sample statement (fake) - Sep 2026", 2026, 9, 30, 108, "B"),
]


def _scaled(amount, percent):
    return Decimal(round(amount * percent / 100))


def _money(value):
    return f"{value:,.2f}"


def _build_rows(year, month, percent, code):
    rows = []
    balance = Decimal("3000")
    receipt_no = 0
    for day, hour, kind, who, base, fee in _PLAN:
        amount = _scaled(base, percent)
        receipt_no += 1
        receipt = f"SMP{code}{receipt_no:07d}"
        when = f"{year}-{month:02d}-{day:02d} {hour:02d}:00:00"
        details = _DETAILS[kind].format(who=who)
        if kind in _MONEY_IN:
            balance += amount
            rows.append({"receipt": receipt, "time": when, "details": details, "status": "Completed",
                         "paid_in": _money(amount), "withdrawn": "", "balance": _money(balance)})
        else:
            balance -= amount
            rows.append({"receipt": receipt, "time": when, "details": details, "status": "Completed",
                         "paid_in": "", "withdrawn": "-" + _money(amount), "balance": _money(balance)})
        if fee and kind in _FEE_DETAILS:
            balance -= Decimal(fee)
            rows.append({"receipt": receipt, "time": when, "details": _FEE_DETAILS[kind],
                         "status": "Completed", "paid_in": "", "withdrawn": "-" + _money(Decimal(fee)),
                         "balance": _money(balance)})
    return rows


def _total(rows, column):
    total = Decimal("0")
    for row in rows:
        text = row[column].replace(",", "").replace("-", "")
        if text:
            total += Decimal(text)
    return total


def sample_results():
    """The fake statements, already read and checked like real ones."""
    results = []
    for name, year, month, last_day, percent, code in _STATEMENTS:
        rows = _build_rows(year, month, percent, code)
        parsed = ParsedStatement(
            rows=rows,
            summary={"TOTAL": {"paid_in": _money(_total(rows, "paid_in")),
                               "paid_out": _money(_total(rows, "withdrawn"))}},
            warnings=[],
            skipped_rows=0,
            period=StatementPeriod(date(year, month, 1), date(year, month, last_day)),
        )
        results.append(process_parsed(name, parsed))
    return results


def sample_combined():
    return combine(sample_results())
