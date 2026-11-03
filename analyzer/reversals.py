"""
reversals.py - links a reversal row to the ONE payment it cancels, but only
when the statement itself gives exact evidence. Otherwise nothing is matched.

Real wording this was built from (names are the statement's own):
  Funds received from - 254711***470 HILDAH LUSIGI            +3,100.00  (30 Oct)
  Send Money Reversal via API to - 254711***470 HILDAH LUSIGI  -3,100.00  (31 Oct)

A reversal and a payment are paired only if ALL of this is true:
  1. Same other party: the text after the first ' - ' is identical
     (phone mask AND name), ignoring case and spacing.
  2. Exactly the same amount, moving in opposite directions: a reversal that
     sends money out cancels a payment that came in, and the other way round.
  3. The payment is earlier than the reversal.
  4. The payment is an ordinary row: not a fee, not a reversal, not Fuliza.
  5. It is the ONLY such payment, and no other reversal could claim it.

If two payments fit (for example two identical amounts from the same person),
nobody can tell which one was reversed, so NOTHING is matched and the warning
stays. We never pick one.

A matched pair gets matched_reversal=True on both rows. Money in and money out
are not changed: they still equal the statement's own checked totals.
"""

from collections import defaultdict
from dataclasses import replace


def other_party(details):
    """
    The text after the first ' - ', lower case, or None when there is none.
    '... Reversal via API to - 254711***470 HILDAH LUSIGI' -> '254711***470 hildah lusigi'
    """
    text = " ".join(details.split())
    if " - " not in text:
        return None
    party = text.split(" - ", 1)[1].strip().lower()
    return party or None


def _could_be_cancelled_by(reversal, row, party):
    """True if `row` is an ordinary earlier payment that this reversal could cancel."""
    if row.is_reversal or row.is_fee or row.is_loan_draw or row.is_loan_repayment:
        return False
    if row.time >= reversal.time:
        return False
    if other_party(row.details) != party:
        return False
    if reversal.paid_out > 0 and reversal.paid_in == 0:      # money went out: cancels money that came in
        return row.paid_in == reversal.paid_out and row.paid_out == 0
    if reversal.paid_in > 0 and reversal.paid_out == 0:      # money came back: cancels money that went out
        return row.paid_out == reversal.paid_in and row.paid_in == 0
    return False


def mark_reversal_pairs(transactions):
    """Returns the transactions with matched_reversal set on every proven pair."""
    rows = list(transactions)

    options = {}                                  # reversal position -> positions of possible payments
    for position, row in enumerate(rows):
        if not row.is_reversal:
            continue
        party = other_party(row.details)
        if party is None:
            continue
        options[position] = [
            other for other, candidate in enumerate(rows)
            if _could_be_cancelled_by(row, candidate, party)
        ]

    claimed_by = defaultdict(list)                # payment position -> reversals that could claim it
    for reversal_position, candidates in options.items():
        for candidate in candidates:
            claimed_by[candidate].append(reversal_position)

    marked = set()
    for reversal_position, candidates in options.items():
        if len(candidates) == 1 and len(claimed_by[candidates[0]]) == 1:
            marked.add(reversal_position)
            marked.add(candidates[0])

    return [replace(row, matched_reversal=True) if position in marked else row
            for position, row in enumerate(rows)]
