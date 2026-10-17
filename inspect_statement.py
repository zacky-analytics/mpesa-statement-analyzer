"""
Step 1: look inside an M-Pesa statement PDF and print what we can read.

Usage (in VS Code terminal):
    python inspect_statement.py path/to/statement.pdf

It asks for the PDF password, so it never sits in your code.
Nothing is saved anywhere. The output only shows in your terminal.
"""

import sys
from getpass import getpass

import pdfplumber

PAGES_TO_PREVIEW = 2   # how many pages to look at
ROWS_TO_PREVIEW = 15   # how many rows to print per page


def main():
    if len(sys.argv) != 2:
        print("Usage: python inspect_statement.py path/to/statement.pdf")
        return

    pdf_path = sys.argv[1]
    password = getpass("PDF password (typing is hidden): ")

    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            print(f"\nTotal pages: {len(pdf.pages)}")

            for page_number, page in enumerate(pdf.pages[:PAGES_TO_PREVIEW], start=1):
                print(f"\n=== PAGE {page_number} ===")

                tables = page.extract_tables()
                print(f"Tables found: {len(tables)}")

                for table_number, table in enumerate(tables, start=1):
                    print(f"\n--- Table {table_number}: {len(table)} rows ---")
                    for row in table[:ROWS_TO_PREVIEW]:
                        print(row)

                # Also show the raw text, in case the table reader misses things
                text = page.extract_text() or ""
                print("\n--- Raw text (first 15 lines) ---")
                for line in text.splitlines()[:15]:
                    print(line)

    except FileNotFoundError:
        print("File not found. Check the path.")
    except Exception as error:
        # Wrong password is the most common problem
        print(f"Could not open the PDF: {error}")


if __name__ == "__main__":
    main()
