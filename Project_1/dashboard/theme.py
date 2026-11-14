"""Design tokens, CSS injection, Altair theme, and formatting helpers for Dashboard v2."""
from __future__ import annotations

from typing import Any

import altair as alt
import streamlit as st

# ------------------------------------------------------------------ colour tokens

BRAND = "#FF5F00"
BRAND_SOFT = "#FFF1E8"
BRAND_TEXT = "#9A3412"

INK = "#0F172A"
INK_MUTED = "#475569"
INK_SUBTLE = "#94A3B8"

SURFACE = "#FFFFFF"
CANVAS = "#F8FAFC"
BORDER = "#E2E8F0"

SUCCESS = "#16A34A"
SUCCESS_SOFT = "#DCFCE7"
SUCCESS_TEXT = "#14532D"

DANGER = "#DC2626"
DANGER_SOFT = "#FEE2E2"
DANGER_TEXT = "#7F1D1D"

WARNING = "#D97706"
WARNING_SOFT = "#FEF3C7"
WARNING_TEXT = "#78350F"

NEUTRAL = "#64748B"
NEUTRAL_SOFT = "#F1F5F9"
NEUTRAL_TEXT = "#334155"

INFO = "#2563EB"
INFO_SOFT = "#DBEAFE"
INFO_TEXT = "#1E3A8A"

CATEGORY_PALETTE = [
    "#FF5F00",
    "#2563EB",
    "#0D9488",
    "#7C3AED",
    "#DB2777",
    "#CA8A04",
    "#475569",
    "#0891B2",
]

OUTCOME_COLORS = {
    "correct": SUCCESS,
    "wrong": DANGER,
    "hallucinated": "#991B1B",
    "missed": WARNING,
    "true_null": NEUTRAL,
}

BADGE_PALETTES: dict[str, tuple[str, str, str]] = {
    "brand": (BRAND_SOFT, BRAND_TEXT, "#FDBA74"),
    "success": (SUCCESS_SOFT, SUCCESS_TEXT, "#86EFAC"),
    "danger": (DANGER_SOFT, DANGER_TEXT, "#FCA5A5"),
    "warning": (WARNING_SOFT, WARNING_TEXT, "#FCD34D"),
    "neutral": (NEUTRAL_SOFT, NEUTRAL_TEXT, "#CBD5E1"),
    "info": (INFO_SOFT, INFO_TEXT, "#93C5FD"),
}


# ------------------------------------------------------------------ CSS & Altair theme

_CSS = """
<style>
/* Page width & breathing room */
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 1440px;
}

/* Cards: bordered containers + equal height in horizontal rows */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
    border-color: #E2E8F0;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
[data-testid="stHorizontalBlock"] {
    align-items: stretch;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div {
    height: 100%;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div > [data-testid="stVerticalBlock"] {
    height: 100%;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"] {
    height: 100%;
}

/* Metrics: tabular numbers and uppercase label */
[data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
}
[data-testid="stMetricLabel"] p {
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 12px;
    color: #475569;
    font-weight: 600;
}

/* Tertiary icon buttons in tables / queues */
[data-testid="stBaseButton-tertiary"] {
    padding: 2px 8px;
    min-height: 28px;
}

/* Clean 2x2 stat grid inside cards (never truncates numbers) */
.p1-stat-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 14px;
    margin: 8px 0 6px 0;
}
.p1-stat-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748B;
}
.p1-stat-val {
    font-size: 18px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #0F172A;
    line-height: 1.25;
}
.p1-pos { color: #16A34A; font-weight: 700; font-variant-numeric: tabular-nums; }
.p1-neg { color: #DC2626; font-weight: 700; font-variant-numeric: tabular-nums; }
.p1-neu { color: #64748B; font-weight: 600; font-variant-numeric: tabular-nums; }

/* Reusable semantic badges & info grid */
.p1-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.3;
    padding: 2px 9px;
    border-radius: 999px;
    border: 1px solid transparent;
    white-space: nowrap;
}
.p1-header-sub {
    color: #475569;
    font-size: 14px;
    margin-top: -6px;
    margin-bottom: 8px;
}
.p1-info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 10px 18px;
    padding: 4px 0;
}
.p1-info-item-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748B;
}
.p1-info-item-val {
    font-size: 13px;
    font-weight: 500;
    color: inherit;
    word-break: break-word;
}
.p1-mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 12px;
}
.p1-queue-hdr {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748B;
    padding-bottom: 4px;
    border-bottom: 1px solid #E2E8F0;
}
</style>
"""


def inject_css() -> None:
    """Inject the Dashboard v2 CSS tokens and layout rules once per run."""
    st.html(_CSS)


_ALTAIR_REGISTERED = False


def register_altair_theme() -> None:
    """Register and enable the custom `p1` Altair theme."""
    global _ALTAIR_REGISTERED
    if _ALTAIR_REGISTERED:
        return

    @alt.theme.register("p1", enable=True)
    def _p1_theme() -> alt.theme.ThemeConfig:
        return {
            "config": {
                "background": "transparent",
                "view": {"stroke": None},
                "font": "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
                "title": {
                    "fontSize": 14,
                    "fontWeight": 600,
                    "anchor": "start",
                    "color": INK,
                    "offset": 10,
                },
                "axis": {
                    "labelColor": INK_MUTED,
                    "titleColor": INK_MUTED,
                    "labelFontSize": 11,
                    "titleFontSize": 12,
                    "gridColor": "#EEF2F7",
                    "gridDash": [2, 3],
                    "domainColor": BORDER,
                    "tickColor": BORDER,
                },
                "legend": {
                    "orient": "bottom",
                    "titleFontSize": 11,
                    "labelFontSize": 11,
                    "labelColor": INK_MUTED,
                    "titleColor": INK_MUTED,
                    "symbolType": "circle",
                },
                "range": {
                    "category": CATEGORY_PALETTE,
                },
            }
        }

    _ALTAIR_REGISTERED = True


# ------------------------------------------------------------------ formatters

def fmt_pct(x: float | None, digits: int = 1) -> str:
    """Format a ratio in [0, 1] (or signed saving) as percentage."""
    if x is None:
        return "—"
    return f"{float(x) * 100:.{digits}f}%"


def fmt_signed_pct(x: float | None, digits: int = 1) -> str:
    """Format a signed ratio as +X.X% / -X.X%."""
    if x is None:
        return "—"
    return f"{float(x) * 100:+.{digits}f}%"


def fmt_int(n: Any) -> str:
    """Format an integer with thin-space thousands separators."""
    if n is None:
        return "—"
    try:
        return f"{int(n):,}".replace(",", "\u2009")
    except (TypeError, ValueError):
        return str(n)


def fmt_secs(s: float | None) -> str:
    """Format a duration in seconds nicely."""
    if s is None:
        return "—"
    val = float(s)
    if val < 60:
        return f"{val:.1f} s"
    mins = int(val // 60)
    rem = int(round(val % 60))
    return f"{mins} m {rem:02d} s"


def fmt_bytes(n: int | float | None) -> str:
    """Format a byte count into KB/MB."""
    if n is None:
        return "—"
    val = float(n)
    if val < 1024:
        return f"{int(val)} B"
    if val < 1024 * 1024:
        return f"{val / 1024:.1f} KB"
    return f"{val / (1024 * 1024):.1f} MB"


def short_hash(h: str | None, n: int = 12) -> str:
    """Truncate a SHA or ID for compact display."""
    if not h:
        return "—"
    s = str(h)
    return s if len(s) <= n else f"{s[:n]}…"
