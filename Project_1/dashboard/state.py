"""Centralized Streamlit session state keys, defaults, and callbacks."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st

from dashboard import data
from evaluation import registry

K_THRESHOLD = "p1_threshold"
K_DECISION = "p1_decision_path"
K_ACTIVE_RUN = "active_run_id"
K_ACTIVE_DOC = "active_doc_id"
K_SESSION_RUNS = "session_runs"
K_REVIEWER = "p1_reviewer"
K_EDITING = "p1_review_editing"
K_ACTION_RUNNING = "p1_action_running"

NONE_LABEL = "(None)"


def find_decision_files() -> list[str]:
    """Return sorted list of unique `*decision*.json` paths in standard project folders."""
    found: list[str] = []
    for folder in (data.ROOT / "submission", data.ROOT / "results", data.ROOT / "uncertainty", data.ROOT):
        if folder.is_dir():
            for p in sorted(folder.glob("*decision*.json")):
                s = str(p)
                if s not in found:
                    found.append(s)
    return found


def init_state() -> None:
    """Initialize all dashboard session-state keys with defaults (idempotent)."""
    st.session_state.setdefault(K_THRESHOLD, float(registry.DEFAULT_THRESHOLD))
    if K_DECISION not in st.session_state:
        files = find_decision_files()
        st.session_state[K_DECISION] = files[0] if files else NONE_LABEL
    st.session_state.setdefault(K_ACTIVE_RUN, None)
    st.session_state.setdefault(K_ACTIVE_DOC, None)
    st.session_state.setdefault(K_SESSION_RUNS, {})
    st.session_state.setdefault(K_REVIEWER, os.environ.get("USER") or os.environ.get("USERNAME") or "reviewer")
    st.session_state.setdefault(K_EDITING, None)
    st.session_state.setdefault(K_ACTION_RUNNING, False)


def threshold() -> float:
    """Current declared confidence threshold τ from session state."""
    return float(st.session_state.get(K_THRESHOLD, registry.DEFAULT_THRESHOLD))


def decision_path() -> str | None:
    """Current decision file path, or None if `(None)` is selected."""
    val = st.session_state.get(K_DECISION)
    if not val or val == NONE_LABEL:
        return None
    return str(val) if Path(str(val)).is_file() else None


def reviewer() -> str:
    """Current reviewer name."""
    val = str(st.session_state.get(K_REVIEWER) or "").strip()
    return val or "reviewer"


def active_run_id() -> str | None:
    """Currently selected run_id across pages."""
    return st.session_state.get(K_ACTIVE_RUN)


def session_runs() -> dict[str, dict[str, Any]]:
    """Map of session run_id -> run bundle."""
    return st.session_state.setdefault(K_SESSION_RUNS, {})


def set_active_run(run_id: str | None, doc_id: str | None = None) -> None:
    """Callback/helper to set the active run (and optionally doc_id)."""
    st.session_state[K_ACTIVE_RUN] = run_id
    if doc_id is not None:
        st.session_state[K_ACTIVE_DOC] = doc_id


def set_threshold_value(val: float) -> None:
    """Callback to update the declared threshold slider safely."""
    st.session_state[K_THRESHOLD] = max(0.0, min(1.0, float(val)))
