"""Tests for the look-and-feel helpers. Run: py -m pytest"""

from decimal import Decimal

from analyzer.categorizer import CategoryTotal
from analyzer.display import category_rows, rows_to_csv
from analyzer.theme import (
    CSS, GREEN, NAVY, RED, brand_html, card_html, check_html, figure_layout, header_html, month_html,
)


def test_card_colors_follow_the_tone():
    assert f"color:{GREEN}" in card_html("Money in", "KES 1.00", "in")
    assert f"color:{RED}" in card_html("Money out", "KES 1.00", "out")
    assert f"color:{NAVY}" in card_html("Net", "KES 1.00")


def test_an_unknown_tone_falls_back_to_neutral():
    assert f"color:{NAVY}" in card_html("X", "1", "nonsense")


def test_text_in_cards_and_header_is_escaped():
    card = card_html("<b>x</b>", "<script>", note="a & b")
    assert "<b>" not in card and "<script>" not in card and "a &amp; b" in card
    assert "<i>" not in header_html("e", "<i>t</i>", "tag")


def test_css_has_no_unfilled_placeholders():
    import re
    assert not re.search(r"%[A-Z_]+%", CSS)


def test_figure_layout_allows_overrides():
    layout = figure_layout(height=300)
    assert layout["height"] == 300 and layout["paper_bgcolor"] == "rgba(0,0,0,0)"


def test_category_rows_leave_empty_sides_blank():
    rows = category_rows([CategoryTotal("Fees", 2, Decimal("0"), Decimal("12.5"))])
    assert rows == [{"Category": "Fees", "Rows": 2, "Money in": "", "Money out": "12.50"}]


def test_check_strip_shows_facts_and_marks_a_failure():
    good = check_html("Statement check", "1 of 1", [("Totals", "Match", "good")])
    bad = check_html("Statement check", "0 of 1", [("Totals", "Check", "bad")], ok=False)
    assert "Match" in good and 'class="check"' in good
    assert 'class="check bad"' in bad


def test_brand_and_month_boxes_escape_text():
    assert "<b>" not in brand_html("<b>x</b>", "y")
    assert "<u>" not in month_html("<u>Sep</u>", "1 to 30", "KES 1.00 out")


def test_csv_has_a_header_and_plain_numbers_for_excel():
    rows = [{"Date": "2026-09-01 10:00", "Receipt": "R1", "Details": "Shop, Ltd", "Category": "Shops (Buy Goods)",
             "Paid in": "", "Paid out": "1,234.50", "Balance": "10,000.00"}]
    text = rows_to_csv(rows).decode("utf-8-sig")
    lines = text.strip().split("\r\n")
    assert lines[0] == "Date,Receipt,Details,Category,Paid in,Paid out,Balance"
    assert lines[1] == '2026-09-01 10:00,R1,"Shop, Ltd",Shops (Buy Goods),,1234.50,10000.00'


def test_csv_of_no_rows_is_just_the_header():
    assert rows_to_csv([]).decode("utf-8-sig").strip() == "Date,Receipt,Details,Category,Paid in,Paid out,Balance"
