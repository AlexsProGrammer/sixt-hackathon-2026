"""Shared filter components (WP5)."""
from __future__ import annotations

import streamlit as st

from dashboard import data

_FILTER_HELP = (
    "**Booked**: prediction present and confidence >= τ.  \n"
    "**To human**: everything not booked (low confidence, abstained, or null).  \n"
    "**Missed saving**: to human, but prediction was correct.  \n"
    "**Error**: booked, and wrong or hallucinated."
)


def decision_filter(
    key: str,
    *,
    options: tuple[str, ...] = data.DECISION_FILTERS,
    counts: dict[str, int] | None = None,
    default: str = "All",
    label: str = "Filter",
) -> str:
    """Render a shared segmented control for decision/outcome filtering."""
    if default not in options:
        default = options[0]

    def _fmt(opt: str) -> str:
        if counts is not None and opt in counts:
            return f"{opt} · {counts[opt]}"
        return opt

    if hasattr(st, "segmented_control"):
        val = st.segmented_control(
            label,
            list(options),
            default=default,
            format_func=_fmt,
            key=key,
            help=_FILTER_HELP,
            label_visibility="collapsed",
        )
        return str(val) if val in options else default

    val = st.radio(
        label,
        list(options),
        index=list(options).index(default),
        format_func=_fmt,
        horizontal=True,
        key=key,
        help=_FILTER_HELP,
        label_visibility="collapsed",
    )
    return str(val)
