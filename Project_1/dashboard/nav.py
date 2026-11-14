"""Top-level page registry for `st.navigation(..., position='top')`."""
from __future__ import annotations

from typing import Any

import streamlit as st

_PAGES: dict[str, Any] | None = None


def get_pages() -> dict[str, Any]:
    """Return the mapping of page key -> `st.Page` object (created lazily)."""
    global _PAGES
    if _PAGES is None:
        from dashboard.views import analytics, home, latest, review, run

        _PAGES = {
            "home": st.Page(home.render, title="Home", icon=":material/home:", url_path="home", default=True),
            "run": st.Page(run.render, title="Run", icon=":material/play_circle:", url_path="run"),
            "review": st.Page(review.render, title="Review", icon=":material/fact_check:", url_path="review"),
            "analytics": st.Page(analytics.render, title="Analytics", icon=":material/insights:", url_path="analytics"),
            "details": st.Page(latest.render, title="Run details", icon=":material/receipt_long:", url_path="run-details"),
        }
    return _PAGES


def switch_to(page_key: str) -> None:
    """Switch to a named page (`home`, `run`, `review`, `analytics`, `details`)."""
    pages = get_pages()
    st.switch_page(pages[page_key])
