"""Main entry point for the Project 1 Streamlit dashboard.

Start from Project_1/:
    .venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from dashboard import data  # noqa: E402
from dashboard.views import analytics, latest, review, run  # noqa: E402

PAGES = {
    "Run": run.render,
    "Review": review.render,
    "Analytics": analytics.render,
    "Latest run": latest.render,
}


def _find_decision_files() -> list[str]:
    found: list[str] = []
    for folder in (data.ROOT / "submission", data.ROOT / "results", data.ROOT / "uncertainty", data.ROOT):
        if folder.is_dir():
            for p in sorted(folder.glob("*decision*.json")):
                s = str(p)
                if s not in found:
                    found.append(s)
    return found


def main() -> None:
    st.set_page_config(
        page_title="Project 1 — Extraction & UQ Dashboard",
        layout="wide",
    )

    with st.sidebar:
        st.title("Project 1")
        st.caption("Local Extraction & Uncertainty Dashboard")

        default_page = st.session_state.get("nav_page", "Run")
        page_names = list(PAGES.keys())
        page_idx = page_names.index(default_page) if default_page in page_names else 0
        page = st.radio("Navigation", page_names, index=page_idx)
        st.session_state["nav_page"] = page

        st.divider()
        dataset = st.selectbox("Default dataset", ["dev", "test_public", "fit", "select", "audit", "smoke"], index=0)
        dec_options = ["(None)"] + _find_decision_files()
        dec_choice = st.selectbox("Decision file", dec_options, index=1 if len(dec_options) > 1 else 0)
        threshold = st.slider("Declared threshold", 0.0, 1.0, 0.99, 0.01)
        reviewer = st.text_input("Reviewer", value="reviewer")

        session_runs = st.session_state.get("session_runs") or {}
        unsaved = sum(1 for b in session_runs.values() if not b.get("saved_to_registry"))
        if session_runs:
            st.caption(f"Session runs: {len(session_runs)} ({unsaved} unsaved)")

    sidebar_state = {
        "dataset": dataset,
        "decision_path": None if dec_choice == "(None)" else dec_choice,
        "threshold": threshold,
        "reviewer": reviewer,
    }
    PAGES[page](sidebar_state)


if __name__ == "__main__":
    main()
