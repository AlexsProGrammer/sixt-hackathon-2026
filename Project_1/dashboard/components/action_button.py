"""UI wrapper for running whitelisted `dashboard.actions` with live status and confirmation."""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import actions


def _execute_with_status(action_id: str, params: dict[str, Any], label: str) -> None:
    log_lines: list[str] = []
    try:
        with st.status(f"Running: {label}…", expanded=True) as status:
            log_box = st.empty()

            def _on_line(line: str) -> None:
                log_lines.append(line)
                log_box.code("\n".join(log_lines[-20:]), language="text")

            res = actions.run_action(action_id, params, on_line=_on_line)
            if res["ok"]:
                status.update(label=f"{label} completed in {res['elapsed_s']}s", state="complete", expanded=False)
                st.cache_data.clear()
                st.toast(f"{label} finished", icon=":material/check:")
                st.rerun()
            else:
                status.update(label=f"{label} failed (exit {res['returncode']})", state="error", expanded=True)
                if res["stderr_tail"]:
                    with st.expander("Error output", expanded=True):
                        st.code(res["stderr_tail"], language="text")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Action failed: {exc}")


def generate_button(
    action_id: str,
    params: dict[str, Any] | None = None,
    *,
    label: str | None = None,
    type: str = "secondary",
    key: str,
    width: str = "content",
) -> None:
    """Render a button that executes a whitelisted CLI action."""
    act = actions.ACTIONS[action_id]
    btn_label = label or act.label
    confirm_key = f"_confirm_{key}"

    if act.confirm and st.session_state.get(confirm_key):
        c1, c2 = st.columns([1.4, 1], gap="small")
        with c1:
            if st.button(f"Confirm: {btn_label}", key=f"{key}_yes", type="primary", icon=":material/check:", width="stretch"):
                st.session_state[confirm_key] = False
                _execute_with_status(action_id, dict(params or {}), btn_label)
        with c2:
            if st.button("Cancel", key=f"{key}_no", type="secondary", icon=":material/close:", width="stretch"):
                st.session_state[confirm_key] = False
                st.rerun()
        return

    if st.button(
        btn_label,
        key=key,
        type=type,
        icon=act.icon,
        help=act.help,
        width=width,
    ):
        if act.confirm:
            st.session_state[confirm_key] = True
            st.rerun()
        else:
            _execute_with_status(action_id, dict(params or {}), btn_label)
