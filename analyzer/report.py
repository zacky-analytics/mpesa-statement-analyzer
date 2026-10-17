"""
report.py - builds the downloadable PDF report, in memory.

Like app.py, this file only DRAWS results that were already checked and
calculated elsewhere (pipeline, metrics, categorizer, comparison, series).
It does no money calculations of its own.

Privacy: the report holds totals, categories and dates only. It never lists
individual transactions, names or phone numbers. Nothing is saved to disk.
"""

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from analyzer.categorizer import category_totals, uncategorized_rows, uncategorized_share
from analyzer.display import comparison_rows, money
from analyzer.metrics import calculate_totals
from analyzer.series import closing_balances, daily_flow
from analyzer.summary import build_summary

NAVY = colors.HexColor("#10233f")
BLUE = NAVY
RED = colors.HexColor("#c23b3b")
GREEN = colors.HexColor("#12805c")
GREY = colors.HexColor("#5b6b82")
LIGHT = colors.HexColor("#f2f4f7")
LINE = colors.HexColor("#d9e0ea")
AMBER_BG = colors.HexColor("#fff6e0")

PAGE_WIDTH = A4[0] - 30 * mm      # usable width with 15 mm side margins

_styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_styles["Normal"], fontSize=9, leading=12)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10, textColor=GREY)
H1 = ParagraphStyle("h1", parent=_styles["Title"], fontSize=20, leading=24, alignment=0,
                    spaceAfter=2, textColor=NAVY)
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=13, leading=16, spaceBefore=12,
                    spaceAfter=4, textColor=NAVY)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=3)
NOTE = ParagraphStyle("note", parent=BODY, backColor=AMBER_BG, borderPadding=5,
                     leftIndent=6, rightIndent=6, spaceAfter=8)


def _p(text, style=BODY):
    """A paragraph with user-supplied text made safe for the PDF engine."""
    return Paragraph(escape(str(text)), style)


def _table(data, widths, header=True, align_right_from=1):
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT"),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    table.setStyle(TableStyle(style))
    return table


def _thin(labels, max_labels=16):
    """Keeps every k-th label so the axis stays readable."""
    step = max(1, -(-len(labels) // max_labels))
    return [label if i % step == 0 else "" for i, label in enumerate(labels)]


def _thousands(value):
    return f"{value:,.0f}"


def _short_day(day):
    return f"{day.day} {day.strftime('%b')}"


# ------------------------------------------------------------------ charts

def _category_chart(categories):
    cats = sorted([c for c in categories if c.money_out > 0], key=lambda c: c.money_out)
    if not cats:
        return None
    height = 30 + 22 * len(cats)
    drawing = Drawing(PAGE_WIDTH, height)
    chart = HorizontalBarChart()
    chart.x, chart.y = 105, 12
    chart.width, chart.height = PAGE_WIDTH - 125, height - 20
    chart.data = [[float(c.money_out) for c in cats]]
    chart.categoryAxis.categoryNames = [c.category for c in cats]
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = _thousands
    chart.bars[0].fillColor = BLUE
    chart.bars.strokeColor = None
    chart.barLabelFormat = lambda v: f"{v:,.2f}"
    chart.barLabels.fontSize = 7
    chart.barLabels.nudge = 22
    drawing.add(chart)
    return drawing


def _flow_chart(flows):
    if not flows:
        return None
    drawing = Drawing(PAGE_WIDTH, 170)
    chart = VerticalBarChart()
    chart.x, chart.y = 45, 40
    chart.width, chart.height = PAGE_WIDTH - 60, 115
    chart.data = [[float(f.money_in) for f in flows], [float(f.money_out) for f in flows]]
    chart.categoryAxis.categoryNames = _thin([_short_day(f.day) for f in flows])
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.angle = 60
    chart.categoryAxis.labels.dy = -14
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labelTextFormat = _thousands
    chart.bars[0].fillColor = GREEN
    chart.bars[1].fillColor = RED
    chart.bars.strokeColor = None
    chart.groupSpacing = 4
    drawing.add(chart)
    drawing.add(String(PAGE_WIDTH - 110, 160, "Green: money in", fontSize=7, fillColor=GREEN))
    drawing.add(String(PAGE_WIDTH - 50, 160, "Red: out", fontSize=7, fillColor=RED))
    return drawing


def _balance_chart(balances):
    if not balances:
        return None
    drawing = Drawing(PAGE_WIDTH, 160)
    chart = LinePlot()
    chart.x, chart.y = 45, 30
    chart.width, chart.height = PAGE_WIDTH - 60, 115
    first = balances[0].day
    chart.data = [[((b.day - first).days, float(b.balance)) for b in balances]]
    chart.lines[0].strokeColor = BLUE
    chart.lines[0].strokeWidth = 1.4
    chart.lines[0].symbol = None
    chart.xValueAxis.labels.fontSize = 7
    chart.yValueAxis.labels.fontSize = 7
    chart.yValueAxis.labelTextFormat = _thousands
    span = max((balances[-1].day - first).days, 1)
    ticks = sorted({round(i * span / 4) for i in range(5)})
    chart.xValueAxis.valueSteps = ticks
    chart.xValueAxis.labelTextFormat = lambda v: _short_day(
        date.fromordinal(first.toordinal() + int(v))
    )
    drawing.add(chart)
    return drawing


# ------------------------------------------------------------------ report

def build_report(combined):
    """Returns the PDF as bytes. `combined` is a pipeline.CombinedResult with results."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title="M-Pesa Statement Report", author="M-Pesa Statement Analyzer",
    )
    transactions = list(combined.transactions)
    totals = calculate_totals(transactions)
    report = combined.report
    story = []

    # ---- title and coverage
    story.append(Paragraph("M-Pesa Statement Report", H1))
    story.append(HRFlowable(width="100%", thickness=2, color=GREEN, spaceAfter=4))
    if report.coverage:
        spans = "; ".join(f"{p.start:%d %b %Y} to {p.end:%d %b %Y}" for p in report.coverage)
        story.append(_p(f"Days covered: {spans}"))
    story.append(_p(f"Report created: {date.today():%d %b %Y}", SMALL))

    # ---- warnings
    if combined.notes:
        story.append(Spacer(1, 6))
        for note in combined.notes:
            story.append(_p(note, NOTE))

    # ---- accuracy check
    story.append(Paragraph("Accuracy check", H2))
    rows = [["File", "Rows read", "Skipped", "Statement period", "Totals match"]]
    for f in combined.files:
        period = f"{f.period.start:%d %b %Y} to {f.period.end:%d %b %Y}" if f.period else "not found"
        rows.append([_p(f.name, SMALL), f.rows_read, f.rows_skipped, period,
                     "Yes" if f.ok else "NO - left out"])
    story.append(_table(rows, [PAGE_WIDTH * 0.32, 55, 45, PAGE_WIDTH * 0.26, None], align_right_from=1))
    for f in combined.files:
        for item in list(f.problems) + list(f.warnings):
            story.append(_p(f"{f.name}: {item}", SMALL))

    # ---- summary numbers
    story.append(Paragraph("Summary numbers", H2))
    kpis = [
        ["Money in", money(totals.money_in), "Money out", money(totals.money_out)],
        ["Fees paid (inside money out)", money(totals.fees_paid), "Net (in - out)", money(totals.net)],
        ["Transactions", str(totals.transaction_count),
         "Uncategorized", f"{len(uncategorized_rows(transactions))} rows "
                          f"({uncategorized_share(transactions) * 100:.1f}% of money moved)"],
    ]
    table = _table(kpis, [PAGE_WIDTH * 0.28, PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.2, PAGE_WIDTH * 0.32],
                   header=False)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"), ("ALIGN", (2, 0), (2, -1), "LEFT"),
    ]))
    story.append(table)

    # ---- categories
    categories = category_totals(transactions)
    story.append(Paragraph("Where the money went", H2))
    chart = _category_chart(categories)
    if chart:
        story.append(chart)
    cat_rows = [["Category", "Rows", "Money in", "Money out"]]
    for c in categories:
        cat_rows.append([c.category, c.count, f"{c.money_in:,.2f}", f"{c.money_out:,.2f}"])
    story.append(_table(cat_rows, [PAGE_WIDTH * 0.4, 50, None, None]))

    # ---- time charts
    flow = _flow_chart(daily_flow(transactions))
    story.append(KeepTogether([
        Paragraph("Money in and out, day by day", H2),
        *([flow] if flow else []),
        _p("Only days with transactions are shown.", SMALL),
    ]))

    balances = closing_balances(transactions)
    line = _balance_chart(balances)
    unsure = sum(1 for b in balances if not b.certain)
    caption = "Balance on the last transaction of each day that has transactions."
    if unsure:
        caption += f" {unsure} day(s) had transactions in the same second that could not be ordered exactly."
    story.append(KeepTogether([
        Paragraph("Closing balance", H2),
        *([line] if line else []),
        _p(caption, SMALL),
    ]))

    # ---- months
    story.append(Paragraph("Month by month", H2))
    month_rows = [["Month (days covered)", "Money in", "Money out", "Fees"]]
    for m in report.months:
        month_rows.append([_p(m.description, SMALL), f"{m.totals.money_in:,.2f}",
                           f"{m.totals.money_out:,.2f}", f"{m.totals.fees_paid:,.2f}"])
    story.append(_table(month_rows, [PAGE_WIDTH * 0.52, None, None, None]))

    comparison = combined.comparison
    if comparison is not None:
        block = [Paragraph(f"{escape(comparison.previous.name)} vs {escape(comparison.current.name)}", H2)]
        for note in comparison.notes:
            block.append(_p(note, NOTE))
        comp_rows = [["Item", "Before", "After", "Change", "Change %"]]
        for r in comparison_rows(comparison.totals):
            comp_rows.append([r["Item"], r["Before"], r["After"], r["Change"], r["Change %"]])
        block.append(_table(comp_rows, [PAGE_WIDTH * 0.3, None, None, None, None]))
        story.append(KeepTogether(block))

    # ---- plain-English summary
    sentences = build_summary(combined)
    if sentences:
        story.append(Paragraph("Summary in plain English", H2))
        for sentence in sentences:
            story.append(Paragraph(escape(sentence), BULLET, bulletText="\u2022"))

    story.append(Spacer(1, 10))
    story.append(_p(
        "All figures are calculated from the uploaded statement(s) and checked against "
        "each statement's own totals. This report lists no individual transactions. "
        "It is a summary of your records, not financial advice.", SMALL))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(15 * mm, 10 * mm, "M-Pesa Statement Analyzer")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
