"""
cleaner.py - turns raw text rows into typed transactions, removes true
duplicates, and checks our numbers against the statement's own summary.

All money uses Decimal, never float, so there are no rounding surprises.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation


class CleaningError(Exception):
    """A value could not be understood. The message is safe to show the user."""


@dataclass(frozen=True)
class Transaction:
    receipt: str
    time: datetime
    details: str
    status: str
    paid_in: Decimal    # money received, 0 or more
    paid_out: Decimal   # money that left, 0 or more (the statement shows it as negative)
    balance: Decimal

    # ---- The ONE place where fees and reversals are recognized ----
    # metrics.py only uses these two checks. It never matches text itself.

    @property
    def is_reversal(self):
        return "reversal" in self.details.lower()

    @property
    def is_fee(self):
        """
        A fee row is money going out whose description ENDS with 'charge',
        like 'Pay Bill Charge' or 'Customer Transfer of Funds Charge'.
        Matching is not case sensitive.

        'Ends with' is stricter than 'contains' on purpose, so a shop named
        'Charge Point Ltd' is not counted as a fee. Rows that mention
        charge/fee but fail this check are listed for review by metrics.py.
        """
        if self.is_reversal or self.paid_out <= 0 or self.paid_in > 0:
            return False
        return self.details.strip().lower().endswith("charge")

    # ---- Fuliza (M-Pesa overdraft) ----
    # Borrowed money is not income and repaying it is not spending, so these
    # rows are recognized here, in the same place as fees and reversals.
    # EXACT statement wording only: the text must START with one of these.
    # A payment made WITH Fuliza money ('Pay Bill Fuliza M-Pesa to ...') is
    # normal spending and is NOT a loan row, so no keyword matching is used.
    LOAN_PREFIXES = ("overdraft of credit party", "od loan repayment")

    def _looks_like_loan(self):
        text = " ".join(self.details.lower().split())
        return text.startswith(self.LOAN_PREFIXES)

    @property
    def is_loan_draw(self):
        """Money IN that is Fuliza lending to you. Fees and reversals never count."""
        if self.is_reversal or self.is_fee or self.paid_in <= 0 or self.paid_out > 0:
            return False
        return self._looks_like_loan()

    @property
    def is_loan_repayment(self):
        """Money OUT that repays Fuliza. Fees and reversals never count."""
        if self.is_reversal or self.is_fee or self.paid_out <= 0 or self.paid_in > 0:
            return False
        return self._looks_like_loan()

    @property
    def duplicate_key(self):
        """
        Two rows are the same transaction only if ALL of these match.
        The receipt number alone is not enough: one receipt can have two real
        rows (a payment and its charge).
        """
        return (self.receipt, self.time, self.details,
                self.paid_in, self.paid_out, self.balance)


def parse_amount(text):
    """'1,069.94' -> Decimal('1069.94'). Empty text -> Decimal('0')."""
    text = (text or "").replace(",", "").strip()
    if text == "":
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise CleaningError(f"Could not read the amount '{text}'.")


def clean_rows(raw_rows):
    transactions = []
    for row in raw_rows:
        try:
            time = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise CleaningError(f"Could not read the date '{row['time']}'.")

        paid_in = parse_amount(row["paid_in"])
        paid_out = abs(parse_amount(row["withdrawn"]))  # statement shows -28.00

        transactions.append(Transaction(
            receipt=row["receipt"],
            time=time,
            details=row["details"],
            status=row["status"],
            paid_in=paid_in,
            paid_out=paid_out,
            balance=parse_amount(row["balance"]),
        ))
    return transactions


def remove_duplicates(transactions):
    """
    Removes rows that appear twice, for example when two uploaded statements
    overlap.

    IMPORTANT: the receipt number alone is NOT enough. One receipt can have
    two real rows, the payment and its charge (for example 'Pay Bill to ...'
    and 'Pay Bill Charge'). So a row only counts as a duplicate when
    everything matches.
    """
    seen = set()
    unique = []
    for t in transactions:
        key = t.duplicate_key
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique, len(transactions) - len(unique)


def _summary_totals(summary):
    """Reads the TOTAL line of the statement's summary table, or None."""
    total = summary.get("TOTAL")
    if not total:
        return None
    return parse_amount(total["paid_in"]), parse_amount(total["paid_out"])


def reconcile(transactions, summary):
    """
    Compares our totals with the totals printed on the statement itself.
    Returns a list of problems. An empty list means the numbers match exactly.

    Only valid for ONE statement (the summary belongs to one file), and only
    before duplicates from other files are merged.
    """
    totals = _summary_totals(summary)
    if totals is None:
        return ["The statement summary was not found, so totals could not be checked."]

    statement_in, statement_out = totals
    our_in = sum((t.paid_in for t in transactions), Decimal("0"))
    our_out = sum((t.paid_out for t in transactions), Decimal("0"))

    problems = []
    if our_in != statement_in:
        problems.append(
            f"Money in does not match the statement: we calculated {our_in:,.2f}, "
            f"the statement says {statement_in:,.2f}."
        )
    if our_out != statement_out:
        problems.append(
            f"Money out does not match the statement: we calculated {our_out:,.2f}, "
            f"the statement says {statement_out:,.2f}."
        )
    return problems
