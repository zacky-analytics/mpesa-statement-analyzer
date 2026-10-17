"""
Runs the real pipeline on YOUR statement(s) and checks the totals.

    py check_statement.py statement.pdf
    py check_statement.py statement1.pdf statement2.pdf     (several files)

You are asked for each file's password. The output prints only counts,
amounts, dates and file names. It does not print names, phone numbers or
transaction descriptions, so it is safe to paste.
"""

import sys
from getpass import getpass

from analyzer.categorizer import (
    category_totals,
    top_spending_categories,
    uncategorized_rows,
    uncategorized_share,
)
from analyzer.metrics import calculate_totals, fee_review_list
from analyzer.parser import read_statement_detailed
from analyzer.pipeline import combine, process_file


def format_line(line):
    """A comparison line. change and change_pct are None when the comparison is not fair."""
    if line.change is None:
        change = "-"
        pct = "not shown"
    else:
        change = f"{line.change:+,.2f}"
        pct = "n/a" if line.change_pct is None else f"{line.change_pct:+.1f}%"
    return (
        f"  {line.label:<24} {line.previous:>10,.2f} -> {line.current:>10,.2f}"
        f"   {change:>10}  ({pct})"
    )


def main(reader=read_statement_detailed):
    paths = sys.argv[1:]
    if not paths:
        print("Usage: py check_statement.py statement.pdf [more_statements.pdf ...]")
        return

    results = []
    for path in paths:
        password = getpass(f"Password for {path} (typing is hidden): ")
        results.append(process_file(path, path, password, reader=reader))

    # ---- Accuracy box: one block per file ----
    print("\n=== FILE CHECKS ===")
    for r in results:
        print(f"\n{r.name}")
        print(f"  Rows read:        {r.rows_read}")
        print(f"  Rows skipped:     {r.rows_skipped}")
        if r.period:
            print(f"  Statement period: {r.period.start} to {r.period.end}")
        else:
            print("  Statement period: NOT FOUND")
        print(f"  Totals match the statement summary: {'YES' if r.ok else 'NO'}")
        for p in r.problems:
            print(f"  PROBLEM: {p}")
        for w in r.warnings:
            print(f"  Warning: {w}")

    combined = combine(results)

    print("\n=== COMBINED ===")
    print(f"Files included:       {len(combined.included)}")
    print(f"Files excluded:       {len(combined.excluded)}")
    print(f"Overlapping rows counted once: {combined.cross_file_duplicates_removed}")
    for note in combined.notes:
        print(f"NOTE: {note}")

    if not combined.has_results:
        print("\nNo file passed its checks, so there is nothing to show.")
        return

    unique = list(combined.transactions)
    print(f"\nTransactions:         {len(unique)}")
    print(f"Earliest:             {min(t.time for t in unique):%Y-%m-%d}")
    print(f"Latest:               {max(t.time for t in unique):%Y-%m-%d}")
    print(f"Statuses found:       {sorted({t.status for t in unique})}")

    # Numbers only. No names, phone numbers or descriptions are printed.
    totals = calculate_totals(unique)
    print("\n--- Metrics ---")
    print(f"Money in:             {totals.money_in:,.2f}")
    print(f"Money out:            {totals.money_out:,.2f}")
    print(f"  of which fees:      {totals.fees_paid:,.2f}  ({totals.fee_count} fee rows)")
    print(f"  spending:           {totals.spending:,.2f}")
    print(f"  reversals out:      {totals.reversals_out:,.2f}")
    print(f"Reversals in:         {totals.reversals_in:,.2f}")
    print(f"Net (in - out):       {totals.net:,.2f}")

    review = fee_review_list(unique)
    print(f"\nRows mentioning charge/fee that were NOT counted as fees: {len(review)}")

    print("\n--- Categories ---")
    for c in category_totals(unique):
        print(f"  {c.category:<22} {c.count:>3} rows   "
              f"in {c.money_in:>10,.2f}   out {c.money_out:>10,.2f}")

    unknown = uncategorized_rows(unique)
    print(f"\nUncategorized rows: {len(unknown)}  "
          f"({uncategorized_share(unique) * 100:.1f}% of all money moved)")

    print("\nTop spending categories:")
    for c in top_spending_categories(unique, count=3):
        print(f"  {c.category:<22} {c.money_out:>10,.2f}")

    # ---- Months, labelled by the days the statements STATE they cover ----
    print("\n--- Months ---")
    for m in combined.report.months:
        t = m.totals
        print(f"  {m.description}")
        print(f"      in {t.money_in:,.2f}   out {t.money_out:,.2f}   fees {t.fees_paid:,.2f}")

    comparison = combined.comparison
    if comparison is None:
        print("\nOnly one month found, so there is nothing to compare yet.")
        return

    print(f"\n--- {comparison.previous.name} vs {comparison.current.name} ---")
    for line in comparison.totals:
        print(format_line(line))

    if not comparison.like_for_like:
        print("\nPer day (amounts only, divided by the days the statements cover):")
        for line in comparison.per_day:
            print(format_line(line))

    print("\nMoney out by category:")
    for line in comparison.out_categories:
        print(format_line(line))

    print("\nMoney in by category:")
    for line in comparison.in_categories:
        print(format_line(line))

    for note in comparison.notes:
        print(f"\nNOTE: {note}")


if __name__ == "__main__":
    main()
