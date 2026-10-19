"""
app.py - the web page. It only DRAWS results.

All checking, merging and calculating happens in analyzer/pipeline.py and the
files it uses. Nothing is written to disk: files are read from memory and the
results live only in this browser session until you press "Clear results".

Run:  py -m streamlit run app.py
"""

import io

import plotly.graph_objects as go
import streamlit as st

from analyzer.categorizer import (
    CATEGORY_ORDER,
    category_totals,
    uncategorized_rows,
    uncategorized_share,
)
from analyzer.display import (
    category_rows,
    comparison_rows,
    file_status_lines,
    filter_rows,
    money,
    rows_to_csv,
    transaction_rows,
)
from analyzer.insights import average_per_day, biggest_day, busiest_weekday, top_payees
from analyzer.metrics import calculate_totals
from analyzer.pipeline import combine, process_file
from analyzer.report import build_report
from analyzer.sample import sample_combined
from analyzer.series import closing_balances, daily_flow
from analyzer.summary import build_summary, reversal_note
from analyzer.theme import (
    CSS, GREEN, NAVY, RED,
    badge_html, brand_html, card_html, check_html, figure_layout, footer_html, header_html,
    month_html, note_html, panel_title_html, privacy_html,
)

st.set_page_config(page_title="M-Pesa Statement Analyzer", page_icon="📒", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

if "round" not in st.session_state:
    st.session_state["round"] = 0      # changing this resets the upload box
if "combined" not in st.session_state:
    st.session_state["combined"] = None
if "sample" not in st.session_state:
    st.session_state["sample"] = False


def clear_results():
    st.session_state["combined"] = None
    st.session_state["sample"] = False
    st.session_state["round"] += 1


def analyze(uploads, passwords):
    results = []
    for upload, password in zip(uploads, passwords):
        data = io.BytesIO(upload.getvalue())
        results.append(process_file(upload.name, data, password))
    st.session_state["combined"] = combine(results)
    st.session_state["sample"] = False


def load_sample():
    st.session_state["combined"] = sample_combined()
    st.session_state["sample"] = True


# ---------------------------------------------------------------- side panel
with st.sidebar:
    st.markdown(brand_html("M-Pesa Statement", "Analyzer"), unsafe_allow_html=True)
    st.markdown('<div class="side-label">How it works</div>'
                '<div class="side-step">1. Upload your PDF statement(s)</div>'
                '<div class="side-step">2. Enter the PDF password</div>'
                '<div class="side-step">3. Read, check and download</div>', unsafe_allow_html=True)
    st.markdown('<div class="side-label">Session</div>', unsafe_allow_html=True)
    st.button("Clear results", on_click=clear_results, width="stretch")
    st.markdown(privacy_html(), unsafe_allow_html=True)

# ---------------------------------------------------------------- header
st.markdown(
    header_html(
        "Personal finance / overview",
        "Your M-Pesa, at a glance",
        "A clear view of the money moving through your account.",
        chips=["Checked against your statement's own totals", "Nothing is saved",
               "Works with password-protected PDFs"],
    ),
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- upload
with st.container(border=True):
    st.markdown(panel_title_html("Upload M-Pesa statement",
                                 "PDF files. Enter the password for each protected statement. "
                                 "Multiple files are supported."), unsafe_allow_html=True)
    uploads = st.file_uploader(
        "M-Pesa statement PDF(s)",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['round']}",
        label_visibility="collapsed",
    )
    st.button("Or try it with sample data (fake statements)", on_click=load_sample)
    if uploads:
        with st.form("passwords", border=False):
            passwords = [
                st.text_input(f"Password for {u.name}", type="password",
                              key=f"pw_{st.session_state['round']}_{i}")
                for i, u in enumerate(uploads)
            ]
            submitted = st.form_submit_button("Analyze", type="primary")
        if submitted:
            with st.spinner("Reading and checking your statement(s)..."):
                analyze(uploads, passwords)

combined = st.session_state["combined"]

if combined is None:
    st.info("Upload a statement to see your results.")
    st.markdown(footer_html(), unsafe_allow_html=True)
    st.stop()

if not combined.has_results:
    # Nothing passed: say why, once, next to each file. No stacked generic messages.
    for f in combined.files:
        st.error(f"{f.name}: " + " ".join(f.problems))
    st.info("Fix the problem above (for example the password) and press Analyze again.")
    st.stop()

transactions = list(combined.transactions)
totals = calculate_totals(transactions)

if st.session_state["sample"]:
    st.info("You are looking at FAKE sample data (two made-up months). "
            "Upload your own statement above to see your real numbers.")

# ---------------------------------------------------------------- statement check strip
passed = len(combined.included)
all_passed = not combined.excluded
periods = [f.period for f in combined.included if f.period]
if periods:
    first = min(p.start for p in periods)
    last = max(p.end for p in periods)
    period_text = f"Statement period: {first:%d %b %Y} to {last:%d %b %Y}"
else:
    period_text = "Statement period not found"
rows_read = sum(f.rows_read for f in combined.included)
rows_skipped = sum(f.rows_skipped for f in combined.included)
duplicates = combined.cross_file_duplicates_removed + sum(f.duplicates_removed for f in combined.included)

st.markdown(
    check_html(
        "Statement check",
        f"{passed} of {len(combined.files)} file(s) checked. {period_text}",
        [
            ("Rows read", f"{rows_read:,}", ""),
            ("Skipped", f"{rows_skipped:,}", "bad" if rows_skipped else ""),
            ("Duplicates removed", f"{duplicates:,}", ""),
            ("Totals", "Match" if all_passed else "Check", "good" if all_passed else "bad"),
        ],
        ok=all_passed,
    ),
    unsafe_allow_html=True,
)
needs_attention = bool(combined.excluded or combined.notes)
with st.expander("Accuracy details, file by file", expanded=needs_attention):
    for note in combined.notes:
        st.warning(note)
    for f in combined.files:
        if f.ok:
            st.success(f"{f.name}: passed its checks")
        else:
            st.error(f"{f.name}: left out of the results. " + " ".join(f.problems))
        for line in file_status_lines(f):
            st.write(line)
        for warning in f.warnings:
            st.warning(warning)

# ---------------------------------------------------------------- number cards
in_note = f"Includes {money(totals.loans_in)} borrowed from Fuliza" if totals.loans_in else "All money received"
out_note = (f"Includes {money(totals.loans_repaid)} Fuliza repayments" if totals.loans_repaid
            else "Includes fees and reversals")
unknown = uncategorized_rows(transactions)

cards = st.columns(4)
cards[0].markdown(card_html("Money in", money(totals.money_in), "in", in_note), unsafe_allow_html=True)
cards[1].markdown(card_html("Money out", money(totals.money_out), "out", out_note), unsafe_allow_html=True)
cards[2].markdown(card_html("Fees paid", money(totals.fees_paid), "warn", "Already included in money out"),
                  unsafe_allow_html=True)
cards[3].markdown(card_html("Net flow", ("+" if totals.net >= 0 else "") + money(totals.net),
                            "in" if totals.net >= 0 else "out", "Money in minus money out"),
                  unsafe_allow_html=True)
reversal_warning = reversal_note(totals)
if reversal_warning:
    st.warning(reversal_warning)
else:
    st.write("")

# ---------------------------------------------------------------- tabs
tab_spend, tab_trends, tab_summary, tab_tx = st.tabs(
    ["Overview", "Trends", "Summary", "Transactions"]
)

# ---- Overview
with tab_spend:
    categories = category_totals(transactions)
    spent = sorted([c for c in categories if c.money_out > 0], key=lambda c: c.money_out)
    left, right = st.columns([2, 1])

    with left:
        with st.container(border=True):
            st.markdown(panel_title_html("Money out by category",
                                         "Where the money went. Fees and Fuliza repayments are shown as their own lines."),
                        unsafe_allow_html=True)
            if spent:
                figure = go.Figure(go.Bar(
                    x=[float(c.money_out) for c in spent],
                    y=[c.category for c in spent],
                    orientation="h",
                    marker_color=NAVY,
                    hovertemplate="%{y}: KES %{x:,.2f}<extra></extra>",
                ))
                figure.update_layout(**figure_layout(height=70 + 38 * len(spent),
                                                     xaxis_title="Money out (KES)"))
                st.plotly_chart(figure, width="stretch")
            if unknown:
                st.markdown(badge_html(f"{len(unknown)} row(s) could not be categorized. We never guess."),
                            unsafe_allow_html=True)
            else:
                st.markdown(badge_html("Every transaction was placed in a category", ok=True),
                            unsafe_allow_html=True)

    with right:
        with st.container(border=True):
            comparison = combined.comparison
            st.markdown(panel_title_html("Month comparison", "Money out, by calendar month"),
                        unsafe_allow_html=True)

            def month_box(m, current):
                kind = "Full month" if m.is_full else "Partial"
                rng = f"{m.first_covered:%d %b} to {m.last_covered:%d %b} - {kind}"
                return month_html(m.name, rng, f"{money(m.totals.money_out)} out", current)

            if comparison is not None:
                st.markdown(month_box(comparison.previous, False) + month_box(comparison.current, True),
                            unsafe_allow_html=True)
                out_line = next((ln for ln in comparison.totals if ln.label.lower().startswith("money out")), None)
                if out_line is not None and out_line.change is not None:
                    if out_line.change_pct is None:
                        text = f"Money out changed by {money(abs(out_line.change))}."
                    else:
                        word = "higher" if out_line.change > 0 else "lower"
                        text = f"Money out was {abs(out_line.change_pct):.1f}% {word}. Both months are fully covered."
                    st.markdown(note_html(text), unsafe_allow_html=True)
                elif comparison.notes:
                    st.markdown(note_html(comparison.notes[0]), unsafe_allow_html=True)
            else:
                months = combined.report.months
                if months:
                    st.markdown("".join(month_box(m, i == len(months) - 1) for i, m in enumerate(months)),
                                unsafe_allow_html=True)
                st.markdown(note_html("Only one month found, so there is nothing to compare yet."),
                            unsafe_allow_html=True)

    days_covered = sum(m.days_covered for m in combined.report.months)
    average = average_per_day(transactions, days_covered)
    big_day = biggest_day(transactions)
    weekday = busiest_weekday(transactions)
    if average is not None or big_day or weekday:
        st.markdown(panel_title_html("Spending facts",
                                     "Spending only: fees, reversals and Fuliza repayments are not counted."),
                    unsafe_allow_html=True)
        facts = st.columns(3)
        if average is not None:
            facts[0].markdown(card_html("Average per day", money(average), "neutral",
                                        f"Over the {days_covered} days the statements cover"),
                              unsafe_allow_html=True)
        if big_day:
            facts[1].markdown(card_html("Biggest spending day", money(big_day[1]), "out",
                                        f"{big_day[0]:%A, %d %b %Y}"), unsafe_allow_html=True)
        if weekday:
            facts[2].markdown(card_html("Busiest weekday", weekday[0], "neutral",
                                        f"{money(weekday[1])} spent on this weekday in total"),
                              unsafe_allow_html=True)
        st.write("")

    payees = top_payees(transactions)
    if payees:
        with st.container(border=True):
            st.markdown(panel_title_html("Where the most money went",
                                         "Rows with the same description are added together."),
                        unsafe_allow_html=True)
            st.dataframe(
                [{"Description": p.name, "Times": p.count, "Total (KES)": f"{p.total:,.2f}"} for p in payees],
                width="stretch", hide_index=True,
            )

    with st.container(border=True):
        st.markdown(panel_title_html("Category table"), unsafe_allow_html=True)
        st.dataframe(category_rows(categories), width="stretch", hide_index=True)

    d1, _ = st.columns([1, 3])
    d1.download_button(
        "Download PDF report",
        data=build_report(combined),
        file_name="mpesa-report.pdf",
        mime="application/pdf",
        type="primary",
    )

# ---- Trends
with tab_trends:
    st.subheader("Money in and out, day by day")
    flows = daily_flow(transactions)
    flow_figure = go.Figure([
        go.Bar(name="Money in", x=[f.day for f in flows], y=[float(f.money_in) for f in flows],
               marker_color=GREEN, hovertemplate="%{x|%d %b}: in KES %{y:,.2f}<extra></extra>"),
        go.Bar(name="Money out", x=[f.day for f in flows], y=[float(f.money_out) for f in flows],
               marker_color=RED, hovertemplate="%{x|%d %b}: out KES %{y:,.2f}<extra></extra>"),
    ])
    flow_figure.update_layout(**figure_layout(barmode="group", height=320, yaxis_title="KES",
                                              legend=dict(orientation="h", y=1.12)))
    st.plotly_chart(flow_figure, width="stretch")
    st.caption("Only days with transactions are shown.")

    st.subheader("Closing balance")
    balances = closing_balances(transactions)
    balance_figure = go.Figure(go.Scatter(
        x=[b.day for b in balances], y=[float(b.balance) for b in balances],
        mode="lines+markers", line=dict(color=NAVY),
        hovertemplate="%{x|%d %b}: KES %{y:,.2f}<extra></extra>",
    ))
    balance_figure.update_layout(**figure_layout(height=300, yaxis_title="KES"))
    st.plotly_chart(balance_figure, width="stretch")
    unsure = sum(1 for b in balances if not b.certain)
    caption = "Balance on the last transaction of each day that has transactions."
    if unsure:
        caption += f" {unsure} day(s) had transactions in the same second that could not be ordered exactly."
    st.caption(caption)

    st.subheader("Month by month")
    for m in combined.report.months:
        st.write(f"**{m.description}**: in {money(m.totals.money_in)}, "
                 f"out {money(m.totals.money_out)}, fees {money(m.totals.fees_paid)}")

    comparison = combined.comparison
    if comparison is None:
        st.caption("Only one month found, so there is nothing to compare yet.")
    else:
        st.write(f"**{comparison.previous.name} vs {comparison.current.name}**")
        for note in comparison.notes:
            st.info(note)
        st.dataframe(comparison_rows(comparison.totals), width="stretch", hide_index=True)
        if not comparison.like_for_like:
            st.caption("Per day (amounts only, divided by the days covered):")
            st.dataframe(comparison_rows(comparison.per_day), width="stretch", hide_index=True)
        with st.expander("By category"):
            st.write("Money out")
            st.dataframe(comparison_rows(comparison.out_categories), width="stretch", hide_index=True)
            st.write("Money in")
            st.dataframe(comparison_rows(comparison.in_categories), width="stretch", hide_index=True)

# ---- Summary
with tab_summary:
    st.subheader("Summary in plain English")
    for sentence in build_summary(combined):
        st.markdown(f"- {sentence}")

# ---- Transactions
with tab_tx:
    st.subheader("All transactions")
    rows = transaction_rows(transactions)
    f1, f2 = st.columns([3, 1])
    search = f1.text_input("Search", placeholder="name, receipt number, date...")
    category = f2.selectbox("Category", ["All"] + CATEGORY_ORDER)
    shown = filter_rows(rows, search, category)
    st.caption(f"Showing {len(shown)} of {len(rows)} transactions.")
    st.dataframe(shown, width="stretch", hide_index=True)
    st.download_button(
        "Download these rows (CSV for Excel)",
        data=rows_to_csv(shown),
        file_name="mpesa-transactions.csv",
        mime="text/csv",
    )

st.markdown(footer_html(), unsafe_allow_html=True)
