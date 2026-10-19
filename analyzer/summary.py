"""
summary.py - the plain-English summary, written by code (no AI, no cost).

Every sentence is built from numbers that were already checked elsewhere
(metrics, categorizer, comparison, series, pipeline). This file only turns
those numbers into words.

Rules
-----
- Facts only. No advice, no guesses, no opinions.
- Names, phone numbers and transaction descriptions are never used.
- A month-to-month change is stated ONLY when comparison.py produced one
  (both months fully covered). Otherwise the summary says why it is not stated.
- The same sentences are used on the page and in the PDF, so they always agree.
"""

from decimal import Decimal

from analyzer.categorizer import (
    FULIZA_BORROWED,
    category_totals,
    top_spending_categories,
    uncategorized_rows,
    uncategorized_share,
)
from analyzer.display import money
from analyzer.metrics import calculate_totals, top_transactions

HUNDRED = Decimal("100")


def _percent(part, whole):
    """'64.3%' or None when the whole is zero."""
    if whole == 0:
        return None
    return f"{part / whole * HUNDRED:.1f}%"


def _plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _coverage_sentence(combined, transactions):
    coverage = combined.report.coverage
    count = _plural(len(transactions), "transaction")
    if not coverage:
        return f"The statement(s) hold {count}."
    days = sum((p.end - p.start).days + 1 for p in coverage)
    spans = " and ".join(f"{p.start:%d %b %Y} to {p.end:%d %b %Y}" for p in coverage)
    return f"The statement(s) cover {spans} ({_plural(days, 'day')}) and hold {count}."


def _flow_sentence(totals):
    net = totals.net
    if net < 0:
        outcome = f"so your balance went down by {money(-net)}"
    elif net > 0:
        outcome = f"so your balance went up by {money(net)}"
    else:
        outcome = "so your balance did not change"
    return (f"Money in was {money(totals.money_in)} and money out was "
            f"{money(totals.money_out)}, {outcome}.")


def _spending_sentence(transactions, totals):
    top = top_spending_categories(transactions, count=3)
    if not top or totals.spending <= 0:
        return None
    parts = []
    for c in top:
        share = _percent(c.money_out, totals.spending)
        parts.append(f"{c.category} ({money(c.money_out)}, {share})")
    return ("Biggest spending categories: " + "; ".join(parts) +
            ". Spending means money out without fees and reversals.")


def _largest_payment_sentence(transactions):
    top = top_transactions(transactions, count=1)
    if not top:
        return None
    t = top[0]
    return f"The largest single payment was {money(t.paid_out)}, on {t.time:%d %b %Y}."


def _income_sentence(transactions, totals):
    # Borrowed Fuliza money is not income, so it is left out of this sentence.
    sources = [c for c in category_totals(transactions)
               if c.money_in > 0 and c.category != FULIZA_BORROWED]
    received = totals.money_in - totals.loans_in
    if not sources or received <= 0:
        return None
    best = max(sources, key=lambda c: c.money_in)
    share = _percent(best.money_in, received)
    basis = "money in" if totals.loans_in == 0 else "money in, not counting Fuliza"
    return (f"Most money in came from {best.category}: "
            f"{money(best.money_in)} ({share} of {basis}).")


def _fuliza_sentence(transactions, totals):
    if totals.loans_in == 0 and totals.loans_repaid == 0:
        return None
    text = (f"Fuliza: you borrowed {money(totals.loans_in)} and repaid "
            f"{money(totals.loans_repaid)}. Borrowed money is not counted as income "
            f"and repayments are not counted as spending.")
    if totals.loans_repaid > totals.loans_in:
        loan_rows = sorted(
            (t for t in transactions if t.is_loan_draw or t.is_loan_repayment),
            key=lambda t: (t.time, not t.is_loan_draw),
        )
        if loan_rows and loan_rows[0].is_loan_repayment:
            text += (" The first Fuliza row in this statement is a repayment, so you "
                     "may have owed Fuliza before the statement began.")
        else:
            text += (" Repayments are higher than the amount borrowed in this period; "
                     "they may include Fuliza fees.")
    return text


def _fees_sentence(totals):
    if totals.fee_count == 0:
        return "No transaction fees were charged."
    share = _percent(totals.fees_paid, totals.money_out)
    text = (f"You paid {money(totals.fees_paid)} in fees across "
            f"{_plural(totals.fee_count, 'charge')}")
    return text + (f", which is {share} of money out." if share else ".")


def reversal_note(totals):
    """
    The plain warning shown wherever reversals appear (page, summary, PDF).
    None when the statements have no reversals.

    Reversals are NOT matched to the payment they cancel, because matching
    would be a guess. So the original payment stays in its own category.
    """
    if totals.reversals_in == 0 and totals.reversals_out == 0:
        return None
    return (f"Reversals found: {money(totals.reversals_in)} came back and "
            f"{money(totals.reversals_out)} went out. Reversal rows are never counted as "
            f"spending, but they are not matched to the payment they cancel, so that "
            f"original payment is still counted in its own category and in spending.")


def _reversal_sentence(totals):
    return reversal_note(totals)


def _uncategorized_sentence(transactions):
    unknown = uncategorized_rows(transactions)
    if not unknown:
        return "Every transaction was placed in a category."
    share = uncategorized_share(transactions) * HUNDRED
    return (f"{_plural(len(unknown), 'transaction')} could not be categorized "
            f"({share:.1f}% of the money moved), so the category figures are not complete.")


def _comparison_sentence(comparison):
    if comparison is None:
        return None
    if not comparison.like_for_like:
        partial = [m.name for m in (comparison.previous, comparison.current) if not m.is_full]
        if partial:
            verb = "is" if len(partial) == 1 else "are"
            return (f"{' and '.join(partial)} {verb} only partly covered by the "
                    f"statement(s), so no month-to-month change is stated.")
        return (f"{comparison.previous.name} and {comparison.current.name} are not "
                f"consecutive months, so no month-to-month change is stated.")

    line = next((l for l in comparison.totals if l.label == "Money out"), None)
    if line is None or line.change is None:
        return None
    previous, current = comparison.previous.name, comparison.current.name
    if line.change == 0:
        return f"Money out in {current} was the same as in {previous} ({money(line.current)})."
    direction = "higher" if line.change > 0 else "lower"
    amount = money(abs(line.change))
    if line.change_pct is None:
        return (f"Money out in {current} was {amount} {direction} than in {previous} "
                f"({money(line.previous)} to {money(line.current)}).")
    return (f"Money out in {current} was {abs(line.change_pct):.1f}% {direction} than in "
            f"{previous} ({money(line.previous)} to {money(line.current)}).")


def build_summary(combined):
    """Returns a list of plain sentences. Empty if there are no results."""
    transactions = list(combined.transactions)
    if not transactions:
        return []

    totals = calculate_totals(transactions)
    sentences = [
        _coverage_sentence(combined, transactions),
        _flow_sentence(totals),
        _spending_sentence(transactions, totals),
        _largest_payment_sentence(transactions),
        _income_sentence(transactions, totals),
        _fuliza_sentence(transactions, totals),
        _fees_sentence(totals),
        _reversal_sentence(totals),
        _uncategorized_sentence(transactions),
        _comparison_sentence(combined.comparison),
    ]
    if combined.excluded:
        sentences.append(
            f"{_plural(len(combined.excluded), 'file')} left out because "
            f"{'it' if len(combined.excluded) == 1 else 'they'} did not pass the checks, "
            f"so this summary covers only the files that passed."
        )
    return [s for s in sentences if s]
