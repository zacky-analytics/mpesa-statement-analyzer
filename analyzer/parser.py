"""
parser.py - reads an M-Pesa statement PDF and returns the RAW rows as text.

It does not fix or calculate anything. That is cleaner.py's job.
It works on the file in memory only. Nothing is written to disk.

Personal details at the top of the statement (name, phone, email) are
never kept or returned. The only thing read from that area is the
'Statement Period' dates.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect

RECEIPT_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
TIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
TRANSACTION_COLUMNS = 7  # Receipt, Time, Details, Status, Paid In, Withdrawn, Balance

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches: "Statement Period: 13 Sep 2026 - 13 Oct 2026"
PERIOD_PATTERN = re.compile(
    r"Statement Period:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*[-–—]\s*"
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)


class StatementError(Exception):
    """Something is wrong with the file. The message is safe to show the user."""


class WrongPasswordError(StatementError):
    pass


@dataclass(frozen=True)
class StatementPeriod:
    """The days a statement covers. Both dates are included."""
    start: date
    end: date


@dataclass(frozen=True)
class ParsedStatement:
    """Everything read from ONE statement PDF, still as raw text."""
    rows: list                        # list of dicts of text values
    summary: dict                     # the statement's own summary table
    warnings: list                    # plain-English notes
    period: Optional[StatementPeriod]
    skipped_rows: int                 # rows that looked like transactions but were not read


def parse_statement_period(text):
    """Finds the 'Statement Period' line in page text. Returns None if not found or unclear."""
    match = PERIOD_PATTERN.search(text or "")
    if not match:
        return None

    day1, month1, year1, day2, month2, year2 = match.groups()
    m1 = MONTHS.get(month1[:3].lower())
    m2 = MONTHS.get(month2[:3].lower())
    if m1 is None or m2 is None:
        return None

    try:
        start = date(int(year1), m1, int(day1))
        end = date(int(year2), m2, int(day2))
    except ValueError:
        return None

    if end < start:
        return None
    return StatementPeriod(start, end)


def _clean_cell(cell):
    """Turn a table cell into plain text. Line breaks inside a cell become spaces."""
    if cell is None:
        return ""
    return " ".join(str(cell).split())


def _is_transaction_row(cells):
    return (
        len(cells) == TRANSACTION_COLUMNS
        and RECEIPT_PATTERN.match(cells[0]) is not None
        and TIME_PATTERN.match(cells[1]) is not None
    )


def _is_header_row(cells):
    return len(cells) == TRANSACTION_COLUMNS and cells[0].lower().startswith("receipt")


def _is_summary_table(table):
    return bool(table) and _clean_cell(table[0][0]).upper() == "TRANSACTION TYPE"


def extract_rows(tables_per_page):
    """
    tables_per_page: a list with one entry per page, each entry is the list of
    tables that pdfplumber found on that page.

    Returns (rows, summary, warnings, skipped_rows):
      rows         - list of dicts of text values, in statement order
      summary      - dict like {"SEND MONEY": {"paid_in": "0.00", "paid_out": "4,243.00"}, ...}
      warnings     - list of plain-English notes about anything we skipped
      skipped_rows - how many rows looked like transactions but could not be read

    A row is counted as skipped when it sits in a transaction table and either
      - has the right number of columns but does not match the layout, or
      - starts like a receipt number but has the wrong number of columns.
    Blank rows and the verification-code table are not counted.
    """
    rows = []
    summary = {}
    warnings = []
    skipped = 0

    for page_number, tables in enumerate(tables_per_page, start=1):
        for table in tables:
            if _is_summary_table(table):
                for raw in table[1:]:
                    cells = [_clean_cell(c) for c in raw]
                    if len(cells) >= 3 and cells[0]:
                        label = cells[0].rstrip(":").strip().upper()
                        summary[label] = {"paid_in": cells[1], "paid_out": cells[2]}
                continue

            cleaned = [[_clean_cell(c) for c in raw] for raw in table]
            is_transaction_table = any(
                _is_header_row(cells) or _is_transaction_row(cells) for cells in cleaned
            )

            for cells in cleaned:
                if _is_transaction_row(cells):
                    rows.append({
                        "receipt": cells[0],
                        "time": cells[1],
                        "details": cells[2],
                        "status": cells[3],
                        "paid_in": cells[4],
                        "withdrawn": cells[5],
                        "balance": cells[6],
                    })
                    continue

                right_shape_wrong_content = (
                    len(cells) == TRANSACTION_COLUMNS
                    and any(cells)
                    and not _is_header_row(cells)
                )
                wrong_shape_looks_like_transaction = (
                    is_transaction_table
                    and len(cells) != TRANSACTION_COLUMNS
                    and bool(cells)
                    and RECEIPT_PATTERN.match(cells[0]) is not None
                )
                if right_shape_wrong_content or wrong_shape_looks_like_transaction:
                    # Never drop a transaction-looking row silently.
                    skipped += 1
                    warnings.append(
                        f"Page {page_number}: skipped a row that did not match "
                        f"the expected layout."
                    )

    return rows, summary, warnings, skipped


def extract_from_tables(tables_per_page):
    """Same as extract_rows, without the skipped count. Kept for older code."""
    rows, summary, warnings, _skipped = extract_rows(tables_per_page)
    return rows, summary, warnings


def _is_password_error(error, _depth=0):
    """
    True if this error, or anything wrapped inside it, means the PDF password
    is wrong.

    pdfplumber hides pdfminer's PDFPasswordIncorrect inside its own
    exception, so checking only the outer error is not enough.
    """
    if isinstance(error, PDFPasswordIncorrect):
        return True
    if _depth >= 5:
        return False

    inside = list(getattr(error, "args", ())) + [error.__cause__, error.__context__]
    if any(
        isinstance(item, BaseException) and _is_password_error(item, _depth + 1)
        for item in inside
    ):
        return True

    return "password" in str(error).lower()


def read_statement_detailed(file, password):
    """
    file: a path or a file-like object (for example the upload from Streamlit).
    password: the PDF password.

    Returns a ParsedStatement. Raises StatementError (or WrongPasswordError)
    with a message that is safe to show the user.

    A missing statement period is NOT an error here: period is simply None,
    and pipeline.py decides what that means (the file is left out).
    """
    try:
        with pdfplumber.open(file, password=password) as pdf:
            tables_per_page = [page.extract_tables() for page in pdf.pages]
            first_page_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
    except FileNotFoundError:
        raise StatementError("File not found.")
    except Exception as error:
        # pdfplumber wraps the real "wrong password" error inside its own
        # exception, so look inside it too (see _is_password_error).
        if _is_password_error(error):
            raise WrongPasswordError("Wrong PDF password. Please check it and try again.")
        raise StatementError("This file could not be read as an M-Pesa statement PDF.")

    # Only the period is kept from the page text. Everything else is discarded.
    period = parse_statement_period(first_page_text)

    rows, summary, warnings, skipped = extract_rows(tables_per_page)

    if not rows:
        raise StatementError(
            "No transactions were found. Please upload the PDF statement "
            "that Safaricom emailed you, not a screenshot or a different file."
        )

    return ParsedStatement(
        rows=rows,
        summary=summary,
        warnings=warnings,
        period=period,
        skipped_rows=skipped,
    )


def read_statement_full(file, password):
    """Returns (rows, summary, warnings, period). Kept for older code."""
    parsed = read_statement_detailed(file, password)
    return parsed.rows, parsed.summary, parsed.warnings, parsed.period


def read_statement(file, password):
    """Returns (rows, summary, warnings). Kept for older code."""
    parsed = read_statement_detailed(file, password)
    return parsed.rows, parsed.summary, parsed.warnings
