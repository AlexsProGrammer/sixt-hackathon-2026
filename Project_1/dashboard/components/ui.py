"""Reusable UI components for Dashboard v2."""
from __future__ import annotations

import html
import traceback
from contextlib import contextmanager
from typing import Any, Callable, Iterator

import streamlit as st

from dashboard import theme


def badge_html(text: str, kind: str = "neutral") -> str:
    """Return an HTML pill badge styled with semantic tokens."""
    bg, fg, border = theme.BADGE_PALETTES.get(kind, theme.BADGE_PALETTES["neutral"])
    safe = html.escape(str(text))
    return (
        f'<span class="p1-badge" style="background:{bg};color:{fg};border-color:{border};">'
        f"{safe}</span>"
    )


def badge(text: str, kind: str = "neutral") -> None:
    """Render a semantic pill badge."""
    st.html(badge_html(text, kind=kind))


def badges_row(items: list[tuple[str, str]]) -> None:
    """Render multiple badges inline."""
    if not items:
        return
    html_str = " ".join(badge_html(text, kind) for text, kind in items if text)
    st.html(f'<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">{html_str}</div>')


_VERDICT_MAP: dict[str, tuple[str, str]] = {
    "full_success": ("✅ Beats human", "success"),
    "partial": ("⚠️ Below target τ", "warning"),
    "fails": ("❌ Loss vs human", "danger"),
    "no_gold": ("— No gold", "neutral"),
}


def verdict_chip(verdict: str, *, help_text: str | None = None) -> None:
    """Render a prominent verdict chip."""
    label, kind = _VERDICT_MAP.get(verdict, ("— Unknown", "neutral"))
    bg, fg, border = theme.BADGE_PALETTES.get(kind, theme.BADGE_PALETTES["neutral"])
    title_attr = f' title="{html.escape(help_text)}"' if help_text else ""
    st.html(
        f'<span class="p1-badge" style="background:{bg};color:{fg};border-color:{border};'
        f'font-size:12px;padding:4px 12px;"{title_attr}>{html.escape(label)}</span>'
    )


def model_family(model_name: str | None) -> tuple[str, str]:
    """Return `(family_label, badge_kind)` for a model string."""
    s = (model_name or "").lower()
    if not s:
        return ("unset", "neutral")
    if "gemini" in s:
        return ("gemini", "info")
    if "claude" in s:
        return ("claude", "warning")
    if "gpt" in s or "openai" in s or "o1" in s or "o3" in s:
        return ("gpt", "success")
    if "gemma" in s:
        return ("gemma", "brand")
    return ("model", "neutral")


def model_chip_html(model_name: str | None) -> str:
    """Return HTML chip for a model name with family colour."""
    if not model_name:
        return badge_html("unset", "neutral")
    _, kind = model_family(model_name)
    short = str(model_name).split("/")[-1]
    bg, fg, border = theme.BADGE_PALETTES.get(kind, theme.BADGE_PALETTES["neutral"])
    return (
        f'<span class="p1-badge p1-mono" title="{html.escape(str(model_name))}" '
        f'style="background:{bg};color:{fg};border-color:{border};">{html.escape(short)}</span>'
    )


def model_chip(model_name: str | None) -> None:
    """Render a model chip."""
    st.html(model_chip_html(model_name))


def page_header(
    title: str,
    subtitle: str = "",
    *,
    icon: str | None = None,
    right: Callable[[], None] | None = None,
) -> None:
    """Render a consistent page header with optional right-aligned controls."""
    heading = f"{icon} {title}" if icon else title
    if right is not None:
        left_col, right_col = st.columns([3, 1.4], gap="medium", vertical_alignment="center")
        with left_col:
            st.title(heading)
            if subtitle:
                st.markdown(f'<p class="p1-header-sub">{html.escape(subtitle)}</p>', unsafe_allow_html=True)
        with right_col:
            right()
    else:
        st.title(heading)
        if subtitle:
            st.markdown(f'<p class="p1-header-sub">{html.escape(subtitle)}</p>', unsafe_allow_html=True)
    st.divider()


def kpi_card(
    label: str,
    value: Any,
    *,
    delta: str | None = None,
    delta_color: str = "normal",
    help: str | None = None,
    foot: str | None = None,
    chart_data: list[float] | None = None,
) -> None:
    """Render a bordered KPI card using `st.metric` with uniform height."""
    with st.container(border=True, height="stretch"):
        st.metric(
            label=label,
            value=value,
            delta=delta,
            delta_color=delta_color,
            help=help,
            chart_data=chart_data,
            chart_type="line",
        )
        st.caption(foot if foot else "\u00a0")


def kpi_row(cards: list[dict[str, Any]]) -> None:
    """Render up to 5 KPI cards in an evenly spaced horizontal row."""
    if not cards:
        return
    cols = st.columns(len(cards), gap="medium")
    for col, spec in zip(cols, cards):
        with col:
            kpi_card(**spec)


def section(
    title: str,
    caption: str | None = None,
    *,
    actions: Callable[[], None] | None = None,
) -> None:
    """Render a section heading with optional right-aligned action buttons."""
    if actions is not None:
        c_left, c_right = st.columns([3, 1.5], gap="medium", vertical_alignment="center")
        with c_left:
            st.subheader(title)
            if caption:
                st.caption(caption)
        with c_right:
            actions()
    else:
        st.subheader(title)
        if caption:
            st.caption(caption)


def empty_state(
    icon: str,
    title: str,
    body: str,
    *,
    action: Callable[[], None] | None = None,
) -> None:
    """Render a centered muted card explaining an empty state and offering a fix."""
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 2.5, 1])
        with c2:
            st.markdown(f"#### {icon} {title}" if icon else f"#### {title}")
            st.caption(body)
            if action is not None:
                action()


def info_grid(items: list[tuple[str, Any, str | None]] | list[tuple[str, Any]], cols: int = 3) -> None:
    """Render a clean responsive key/value metadata grid.

    Each item may be `(label, value)` or `(label, value, tooltip)`.
    """
    if not items:
        return
    cells: list[str] = []
    for item in items:
        if len(item) == 3:
            label, val, tip = item
        else:
            label, val = item
            tip = None
        val_str = "—" if val is None or val == "" else str(val)
        tip_attr = f' title="{html.escape(str(tip))}"' if tip else ""
        cells.append(
            f'<div><div class="p1-info-item-label">{html.escape(str(label))}</div>'
            f'<div class="p1-info-item-val"{tip_attr}>{html.escape(val_str)}</div></div>'
        )
    st.html(
        f'<div class="p1-info-grid" style="grid-template-columns:repeat({max(1, cols)}, minmax(160px, 1fr));">'
        + "".join(cells)
        + "</div>"
    )


@contextmanager
def safe_section(title: str) -> Iterator[None]:
    """Error boundary so one broken chart or section never crashes the whole page."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not render **{title}**: {type(exc).__name__}: {exc}")
        with st.expander("Traceback", expanded=False):
            st.code(traceback.format_exc(), language="python")
