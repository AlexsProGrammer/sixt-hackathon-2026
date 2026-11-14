"""Main entry point for the Project 1 Streamlit dashboard (v2).

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

from dashboard import nav, state, theme  # noqa: E402


def main() -> None:
    st.set_page_config(
        page_title="Project 1 — Extraction & UQ Dashboard",
        page_icon=":material/verified_user:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    state.init_state()
    theme.inject_css()
    theme.register_altair_theme()

    with st.sidebar:
        st.markdown("### Project 1 · A-Team")
        st.caption('*Teach a machine to say "I don\'t know"*')

    pages = nav.get_pages()
    current_page = st.navigation(list(pages.values()), position="sidebar")
    current_page.run()


if __name__ == "__main__":
    main()
