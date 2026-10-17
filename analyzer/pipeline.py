"""
pipeline.py - turns uploaded statements into one set of trusted results.

The order is fixed, and the web page and check_statement.py both use it:

 1. Each file is read, cleaned and CHECKED on its own: its rows against its
    own summary totals, and its stated period must be readable. Nothing is
    removed before this check, so a row that also appears in another upload
    can never make a good file fail.
 2. A file that fails is left out, and the results say so. Files that pass
    are merged.
 3. Only now are exact cross-file duplicates removed. A row counts as a
    duplicate only if the SAME row appeared in an EARLIER file. Identical
    rows inside one file stay, because that file's own totals counted them.
 4. Overlapping files are cross-checked: inside the days they both cover they
    should hold exactly the same transactions. If not, we warn.
 5. Coverage is each file's stated period, combined (see comparison.py).
    It is never guessed from transaction dates.

This file holds the logic so that it can be tested. app.py only draws it.
"""

from dataclasses import dataclass, replace
from typing import Optional

from analyzer.cleaner import CleaningError, clean_rows, reconcile
from analyzer.comparison import (
    build_monthly_report,
    latest_comparison,
    report_notes,
)
from analyzer.parser import StatementError, StatementPeriod, read_statement_detailed

COMPLETED = "Completed"


@dataclass(frozen=True)
class FileResult:
    name: str
    ok: bool                           # True only if the file passed every check
    problems: tuple = ()               # why it failed, in plain English
    warnings: tuple = ()               # things worth knowing; they do not fail a file
    rows_read: int = 0
    rows_skipped: int = 0
    period: Optional[StatementPeriod] = None
    transactions: tuple = ()           # rows exactly as read; empty for a failed file
    duplicates_removed: int = 0        # rows dropped because an EARLIER file had them


@dataclass(frozen=True)
class CombinedResult:
    files: tuple                       # every FileResult, in upload order
    included: tuple                    # the files that passed
    excluded: tuple                    # the files that failed
    transactions: tuple                # merged, de-duplicated, oldest first
    cross_file_duplicates_removed: int
    report: object                     # MonthlyReport
    comparison: object                 # MonthComparison, or None
    notes: tuple                       # plain-English notes for the top of the page

    @property
    def has_results(self):
        return bool(self.transactions)


# ---------------------------------------------------------------------------
# Step 1: one file on its own
# ---------------------------------------------------------------------------

def process_parsed(name, parsed):
    """Cleans and checks one already-parsed statement."""
    problems = []
    warnings = list(parsed.warnings)
    cleaned = None

    try:
        cleaned = clean_rows(parsed.rows)
    except CleaningError as error:
        problems.append(str(error))

    if cleaned is not None:
        problems.extend(reconcile(cleaned, parsed.summary))

        other = [t for t in cleaned if t.status != COMPLETED]
        if other:
            statuses = ", ".join(sorted({t.status or "blank" for t in other}))
            warnings.append(
                f"{len(other)} row(s) have a status other than 'Completed' "
                f"({statuses}). They are included in the totals, as the "
                f"statement counts them."
            )

    if parsed.period is None:
        problems.append(
            "The statement period could not be read, so we cannot tell which "
            "days this file covers."
        )

    ok = not problems
    return FileResult(
        name=name,
        ok=ok,
        problems=tuple(problems),
        warnings=tuple(warnings),
        rows_read=len(parsed.rows),
        rows_skipped=parsed.skipped_rows,
        period=parsed.period,
        transactions=tuple(cleaned) if ok else (),
    )


def process_file(name, file, password, reader=read_statement_detailed):
    """Reads, cleans and checks one PDF. Never raises for a bad file."""
    try:
        parsed = reader(file, password)
    except StatementError as error:
        return FileResult(name=name, ok=False, problems=(str(error),))
    return process_parsed(name, parsed)


# ---------------------------------------------------------------------------
# Steps 2 to 5: many files together
# ---------------------------------------------------------------------------

def _merge(transaction_lists):
    """
    Merges lists of transactions in order. A row is dropped only if the same
    row appeared in an EARLIER list. Returns (merged, removed_per_list).
    """
    seen = set()
    merged = []
    removed_per_list = []
    for transactions in transaction_lists:
        removed = 0
        for t in transactions:
            if t.duplicate_key in seen:
                removed += 1
            else:
                merged.append(t)
        seen.update(t.duplicate_key for t in transactions)
        removed_per_list.append(removed)
    return merged, removed_per_list


def merge_transactions(transaction_lists):
    """Returns (merged, total_removed)."""
    merged, removed_per_list = _merge(transaction_lists)
    return merged, sum(removed_per_list)


def _overlap_notes(included):
    """Two files that cover the same days must hold the same transactions there."""
    notes = []
    for i in range(len(included)):
        for j in range(i + 1, len(included)):
            a, b = included[i], included[j]
            start = max(a.period.start, b.period.start)
            end = min(a.period.end, b.period.end)
            if start > end:
                continue

            keys_a = {t.duplicate_key for t in a.transactions if start <= t.time.date() <= end}
            keys_b = {t.duplicate_key for t in b.transactions if start <= t.time.date() <= end}
            if keys_a != keys_b:
                notes.append(
                    f"{a.name} and {b.name} both cover {start} to {end}, but the "
                    f"transactions in those days do not match exactly "
                    f"({len(keys_a)} in the first file, {len(keys_b)} in the second, "
                    f"{len(keys_a ^ keys_b)} differ). Some transactions may be "
                    f"counted twice or missing."
                )
    return notes


def combine(results):
    results = list(results)

    passed_positions = [i for i, r in enumerate(results) if r.ok]
    merged, removed_per_file = _merge([results[i].transactions for i in passed_positions])
    merged.sort(key=lambda t: t.time)     # stable: ties keep their original order

    files = list(results)
    for position, removed in zip(passed_positions, removed_per_file):
        files[position] = replace(results[position], duplicates_removed=removed)

    included = tuple(f for f in files if f.ok)
    excluded = tuple(f for f in files if not f.ok)
    total_removed = sum(removed_per_file)

    notes = []
    if excluded:
        names = ", ".join(f.name for f in excluded)
        notes.append(
            f"Results exclude {len(excluded)} file(s) that did not pass their "
            f"checks: {names}."
        )
    if files and not included:
        notes.append(
            "None of the uploaded files passed their checks, so there are no "
            "results to show."
        )
    if total_removed:
        notes.append(
            f"{total_removed} overlapping transaction(s) appear in more than one "
            f"file and are counted once."
        )
    for f in included:
        if f.transactions and f.duplicates_removed == len(f.transactions):
            notes.append(
                f"{f.name} contains only transactions that are already in an "
                f"earlier file, so it adds nothing new."
            )
    notes.extend(_overlap_notes(included))

    report = build_monthly_report(merged, [f.period for f in included])
    notes.extend(report_notes(report))

    return CombinedResult(
        files=tuple(files),
        included=included,
        excluded=excluded,
        transactions=tuple(merged),
        cross_file_duplicates_removed=total_removed,
        report=report,
        comparison=latest_comparison(report),
        notes=tuple(notes),
    )
