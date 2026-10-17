"""
display.py - turns results into plain rows and text for the page.

app.py only draws what this file returns. No calculations of money totals
happen here: those come from metrics.py, categorizer.py and comparison.py.
This file only formats and filters, so it can be tested without Streamlit.
"""

import csv
import io

from analyzer.categorizer import categorize


def money(amount):
    """Decimal -> 'KES 1,234.50'."""
    return f"KES {amount:,.2f}"


def change_text(line):
    """Change and percentage for one comparison line. '-' when not shown."""
    if line.change is None:
        return "-", "-"
    pct = "n/a" if line.change_pct is None else f"{line.change_pct:+.1f}%"
    return f"{line.change:+,.2f}", pct


def comparison_rows(lines):
    """Comparison lines -> list of dicts for a table."""
    rows = []
    for line in lines:
        change, pct = change_text(line)
        rows.append({
            "Item": line.label,
            "Before": f"{line.previous:,.2f}",
            "After": f"{line.current:,.2f}",
            "Change": change,
            "Change %": pct,
        })
    return rows


def transaction_rows(transactions):
    """Newest first, ready for a table."""
    rows = []
    for t in sorted(transactions, key=lambda x: x.time, reverse=True):
        rows.append({
            "Date": t.time.strftime("%Y-%m-%d %H:%M"),
            "Receipt": t.receipt,
            "Details": t.details,
            "Category": categorize(t),
            "Paid in": f"{t.paid_in:,.2f}" if t.paid_in else "",
            "Paid out": f"{t.paid_out:,.2f}" if t.paid_out else "",
            "Balance": f"{t.balance:,.2f}",
        })
    return rows


def filter_rows(rows, search="", category="All"):
    """Keeps rows whose text contains the search words and match the category."""
    words = (search or "").lower().split()
    result = []
    for row in rows:
        if category != "All" and row["Category"] != category:
            continue
        text = f"{row['Receipt']} {row['Details']} {row['Date']}".lower()
        if all(word in text for word in words):
            result.append(row)
    return result


def file_status_lines(result):
    """Plain lines for one file's accuracy box."""
    lines = [f"Rows read: {result.rows_read}", f"Rows skipped: {result.rows_skipped}"]
    if result.period:
        lines.append(f"Statement period: {result.period.start} to {result.period.end}")
    else:
        lines.append("Statement period: not found")
    lines.append("Totals match the statement summary: " + ("yes" if result.ok else "NO"))
    if result.duplicates_removed:
        lines.append(f"Overlapping rows counted once: {result.duplicates_removed}")
    return lines


def category_rows(categories):
    """Category totals -> list of dicts for a table."""
    return [
        {
            "Category": c.category,
            "Rows": c.count,
            "Money in": f"{c.money_in:,.2f}" if c.money_in else "",
            "Money out": f"{c.money_out:,.2f}" if c.money_out else "",
        }
        for c in categories
    ]


CSV_COLUMNS = ["Date", "Receipt", "Details", "Category", "Paid in", "Paid out", "Balance"]
_CSV_MONEY = ("Paid in", "Paid out", "Balance")


def rows_to_csv(rows):
    """
    Transaction rows -> CSV bytes that open cleanly in Excel.
    Money columns have the thousands commas removed so Excel reads them as numbers.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        out = dict(row)
        for column in _CSV_MONEY:
            out[column] = str(out.get(column, "")).replace(",", "")
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8-sig")
