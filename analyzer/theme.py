"""
theme.py - the look of the app, in one place (colors, CSS, small HTML pieces).

Design idea: a clean finance dashboard.
- A dark navy side panel and white rounded cards on a light page.
- Green and red are used ONLY for money in and money out, so the color means
  something every time you see it. Amber means "look at this".
- Numbers use tabular figures, so digits line up like a ledger.

This file holds no money logic. It only styles what other files calculated.
"""

import html

NAVY = "#10233f"       # side panel, text, headings
PAPER = "#eaeff6"      # page background
CARD = "#ffffff"       # cards and tables
GREEN = "#12805c"      # money in, buttons, active tab
RED = "#c23b3b"        # money out
AMBER = "#b7791f"      # fees and things to check
MUTED = "#5b6b82"      # labels and notes
RULE = "#cdd7e5"       # thin lines
AMBER_BG = "#fff6e0"
GREEN_BG = "#e8f5ef"
SOFT_BG = "#f1f4f9"

FONT = '"IBM Plex Sans", "Segoe UI", system-ui, -apple-system, sans-serif'

TONES = {"in": GREEN, "out": RED, "warn": AMBER, "neutral": NAVY}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, .stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3,
.stApp li, .stApp input, .stApp button, .stApp textarea { font-family: %FONT%; }

.stApp { background: %PAPER%; }
.block-container { max-width: 1180px; padding-top: 3.2rem; padding-bottom: 3rem; }

/* hide Streamlit's own Deploy button, menu and footer */
.stDeployButton, footer, #MainMenu { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }

/* ------------------------------------------------ side panel */
section[data-testid="stSidebar"] { background: %NAVY%; }
section[data-testid="stSidebar"] * { color: #e6edf7; }
section[data-testid="stSidebar"] button {
    background: transparent; border: 1px solid rgba(255,255,255,.28); color: #ffffff; }
section[data-testid="stSidebar"] button:hover { border-color: #ffffff; }
.brand { display: flex; align-items: center; gap: .7rem; padding: .4rem 0 1rem 0;
         border-bottom: 1px solid rgba(255,255,255,.12); margin-bottom: 1rem; }
.brand-mark { width: 38px; height: 38px; border-radius: 50%; background: %GREEN%;
              display: flex; align-items: center; justify-content: center;
              color: #ffffff; font-weight: 700; font-size: 1.1rem; }
.brand-name { font-weight: 600; font-size: 1.02rem; line-height: 1.15; color: #ffffff; }
.brand-sub { font-size: .78rem; color: #9fb2cf; }
.side-label { font-size: .72rem; letter-spacing: .08em; text-transform: uppercase;
              color: #9fb2cf; margin: 1.2rem 0 .4rem 0; }
.side-step { font-size: .88rem; color: #dbe5f3; margin: .25rem 0; }
.privacy { background: rgba(255,255,255,.08); border-radius: 10px; padding: .8rem .9rem;
           font-size: .82rem; color: #dbe5f3; margin-top: 1.5rem; }
.privacy b { color: #ffffff; letter-spacing: .06em; font-size: .72rem; }

/* ------------------------------------------------ page header (hero band) */
.hero { background: %NAVY%; border-bottom: 4px solid %GREEN%; border-radius: 16px;
        padding: 1.4rem 1.5rem 1.3rem 1.5rem; margin-bottom: 1.3rem;
        box-shadow: 0 6px 18px rgba(16,35,63,.22); }
.eyebrow { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: #8fb3e0; }
.page-title { font-size: 2.1rem; font-weight: 600; color: #ffffff; margin: .2rem 0 .3rem 0;
              line-height: 1.15; }
.page-sub { color: #c9d6ea; font-size: .98rem; margin: 0; max-width: 46rem; }
.chips { margin-top: .9rem; }
.chip { display: inline-block; background: rgba(255,255,255,.12); color: #e6edf7;
        border-radius: 999px; padding: .25rem .75rem; font-size: .76rem; margin: 0 .4rem .4rem 0; }
.chip b { color: #5fd3a6; margin-right: .3rem; }

/* ------------------------------------------------ cards */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: %CARD%; border: 1px solid %RULE%; border-radius: 14px;
    box-shadow: 0 2px 8px rgba(16,35,63,.10); }

.stat { background: %CARD%; border: 1px solid %RULE%; border-top: 5px solid %NAVY%;
        border-radius: 14px; padding: .95rem 1.1rem 1rem 1.1rem;
        box-shadow: 0 2px 8px rgba(16,35,63,.10); }
.stat-label { color: %MUTED%; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }
.stat-value { font-size: 1.4rem; font-weight: 600; font-variant-numeric: tabular-nums;
              white-space: nowrap; line-height: 1.35; margin-top: .15rem; }
.stat-note { color: %MUTED%; font-size: .78rem; margin-top: .1rem; }

.panel-title { font-size: 1.05rem; font-weight: 600; color: %NAVY%; margin: 0; }
.panel-sub { font-size: .8rem; color: %MUTED%; margin: .1rem 0 .6rem 0; }

/* statement check strip */
.check { display: flex; align-items: center; gap: 1.6rem; flex-wrap: wrap;
         background: %CARD%; border: 1px solid %RULE%; border-radius: 14px;
         padding: .9rem 1.2rem; margin: .2rem 0 1rem 0; border-left: 6px solid %GREEN%;
         box-shadow: 0 2px 8px rgba(16,35,63,.10); }
.check.bad { border-left-color: %RED%; }
.check-main { flex: 1 1 200px; }
.check-title { font-weight: 600; color: %NAVY%; }
.check-sub { font-size: .8rem; color: %MUTED%; }
.fact { min-width: 70px; }
.fact-label { font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: %MUTED%; }
.fact-value { font-size: 1.1rem; font-weight: 600; color: %NAVY%; font-variant-numeric: tabular-nums; }
.fact-value.good { color: %GREEN%; }
.fact-value.bad { color: %RED%; }

/* month comparison boxes */
.month { border-radius: 8px; padding: .7rem .9rem; margin-bottom: .55rem; background: %SOFT_BG%;
         display: flex; justify-content: space-between; align-items: center; gap: .6rem; }
.month.current { background: %GREEN_BG%; }
.month-name { font-weight: 600; font-size: .88rem; color: %NAVY%; }
.month-range { font-size: .74rem; color: %MUTED%; }
.month-amount { font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.month-note { background: %AMBER_BG%; border-radius: 8px; padding: .65rem .85rem;
              font-size: .8rem; color: #6b4a10; }
.badge { display: inline-block; background: %AMBER_BG%; color: #6b4a10; border-radius: 999px;
         padding: .15rem .65rem; font-size: .78rem; }
.badge.ok { background: %GREEN_BG%; color: %GREEN%; }

/* tabs */
button[role="tab"] p { font-weight: 500; font-size: .98rem; }
[data-baseweb="tab-highlight"] { background-color: %GREEN% !important; }
button[role="tab"][aria-selected="true"] p { color: %GREEN%; }

[data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }

.footer-note { color: %MUTED%; font-size: .76rem; margin-top: 2rem; text-align: center; }

/* phones */
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 4rem; }
  .hero { padding: 1.1rem 1.1rem 1rem 1.1rem; border-radius: 14px; }
  .page-title { font-size: 1.55rem; }
  .page-sub { font-size: .9rem; }
  .stat { margin-bottom: .6rem; }
  .stat-value { font-size: 1.25rem; }
  .check { gap: .8rem 1.2rem; padding: .8rem 1rem; }
  .fact { min-width: 40%; }
  .month { flex-wrap: wrap; }
}
[data-testid="stAlert"] { border-radius: 10px; }
.stButton > button, .stDownloadButton > button { border-radius: 8px; font-weight: 500; }
</style>
"""

CSS = _CSS
for _key, _val in {
    "FONT": FONT, "NAVY": NAVY, "CARD": CARD, "RULE": RULE, "MUTED": MUTED, "PAPER": PAPER,
    "GREEN_BG": GREEN_BG, "AMBER_BG": AMBER_BG, "SOFT_BG": SOFT_BG, "GREEN": GREEN, "RED": RED,
}.items():
    CSS = CSS.replace(f"%{_key}%", _val)


def _e(text):
    return html.escape(str(text))


def header_html(eyebrow, title, subtitle, chips=()):
    chip_html = "".join(f'<span class="chip"><b>&#10003;</b>{_e(c)}</span>' for c in chips)
    chips_block = f'<div class="chips">{chip_html}</div>' if chip_html else ""
    return (f'<div class="hero"><div class="eyebrow">{_e(eyebrow)}</div>'
            f'<div class="page-title">{_e(title)}</div>'
            f'<p class="page-sub">{_e(subtitle)}</p>{chips_block}</div>')


def brand_html(name, sub):
    return (f'<div class="brand"><div class="brand-mark">&#10003;</div>'
            f'<div><div class="brand-name">{_e(name)}</div>'
            f'<div class="brand-sub">{_e(sub)}</div></div></div>')


def privacy_html():
    return ('<div class="privacy"><b>PRIVACY</b><br>Files are read in memory on the server while you use the app. '
            'Nothing is saved by the app.</div>')


def panel_title_html(title, sub=""):
    sub_html = f'<p class="panel-sub">{_e(sub)}</p>' if sub else ""
    return f'<p class="panel-title">{_e(title)}</p>{sub_html}'


def card_html(label, value, tone="neutral", note=""):
    """One number card. tone: in (green), out (red), warn (amber) or neutral (navy)."""
    color = TONES.get(tone, TONES["neutral"])
    note_html = f'<div class="stat-note">{_e(note)}</div>' if note else ""
    return (f'<div class="stat" style="border-top-color:{color}">'
            f'<div class="stat-label">{_e(label)}</div>'
            f'<div class="stat-value" style="color:{color}">{_e(value)}</div>'
            f'{note_html}</div>')


def check_html(title, sub, facts, ok=True):
    """The statement-check strip. facts = [(label, value, 'good'|'bad'|'')]."""
    parts = "".join(
        f'<div class="fact"><div class="fact-label">{_e(label)}</div>'
        f'<div class="fact-value {_e(kind)}">{_e(value)}</div></div>'
        for label, value, kind in facts
    )
    return (f'<div class="check{"" if ok else " bad"}"><div class="check-main">'
            f'<div class="check-title">{_e(title)}</div><div class="check-sub">{_e(sub)}</div>'
            f'</div>{parts}</div>')


def month_html(name, range_text, amount_text, current=False):
    return (f'<div class="month{" current" if current else ""}"><div>'
            f'<div class="month-name">{_e(name)}</div><div class="month-range">{_e(range_text)}</div>'
            f'</div><div class="month-amount" style="color:{RED}">{_e(amount_text)}</div></div>')


def note_html(text):
    return f'<div class="month-note">{_e(text)}</div>'


def badge_html(text, ok=False):
    return f'<span class="badge{" ok" if ok else ""}">{_e(text)}</span>'


def figure_layout(**overrides):
    """Shared look for every Plotly chart. Pass extra keys to change or add settings."""
    layout = {
        "font": {"family": FONT, "color": NAVY, "size": 13},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 0, "r": 0, "t": 10, "b": 0},
        "xaxis": {"automargin": True, "gridcolor": RULE, "linecolor": RULE, "zerolinecolor": RULE},
        "yaxis": {"automargin": True, "gridcolor": RULE, "linecolor": RULE, "zerolinecolor": RULE},
        "hoverlabel": {"font": {"family": FONT}},
    }
    layout.update(overrides)
    return layout


def footer_html():
    return ('<div class="footer-note">Independent tool. Not affiliated with Safaricom or M-Pesa. '
            'It shows facts from your statement and is not financial advice.</div>')
