"""Shared run selector components (single and multi-run) across Review, Analytics, and Run details."""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import cache, state, theme


def collect_run_entries() -> list[dict[str, Any]]:
    """Collect deduplicated run entries (unsaved session runs first, then registry runs)."""
    sess = state.session_runs()
    idx_rows = cache.get_index()
    idx_by_id = {r["run_id"]: r for r in idx_rows if r.get("run_id")}

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Unsaved session runs first
    for rid, b in sess.items():
        if rid in idx_by_id:
            continue
        r = b.get("index_row") or b.get("run") or {}
        entries.append({
            "run_id": rid,
            "name": r.get("name") or rid,
            "split": r.get("split") or "session",
            "status": "session",
            "net": r.get("net_saving_pct_e100"),
            "is_session": True,
            "bundle": b,
            "index_row": r,
        })
        seen.add(rid)

    # Registry runs
    for r in idx_rows:
        rid = r.get("run_id")
        if not rid or rid in seen:
            continue
        tags = r.get("tags") or []
        entries.append({
            "run_id": rid,
            "name": r.get("name") or rid,
            "split": r.get("split") or "—",
            "status": "legacy" if "legacy" in tags else (r.get("status") or "—"),
            "net": r.get("net_saving_pct_e100"),
            "is_session": False,
            "bundle": None,
            "index_row": r,
        })
        seen.add(rid)

    return entries


def format_run_label(entry: dict[str, Any]) -> str:
    """Format a concise run label for selectboxes."""
    prefix = "[session] " if entry.get("is_session") else ("[legacy] " if entry.get("status") == "legacy" else "")
    net_str = theme.fmt_signed_pct(entry.get("net")) if entry.get("net") is not None else "unscored"
    return f"{prefix}{entry['name']} · {entry['split']} · {net_str}"


def pick_run(key: str, *, label: str = "Run", include_samples: bool = True) -> tuple[str | None, dict[str, Any] | None]:
    """Render a single-run selectbox and return `(run_id, bundle)`."""
    entries = collect_run_entries()
    if not entries:
        return None, None
    entry_map = {e["run_id"]: e for e in entries}
    options = [e["run_id"] for e in entries]
    active = state.active_run_id()
    default_idx = options.index(active) if active in options else 0

    chosen = st.selectbox(
        label,
        options,
        index=default_idx,
        format_func=lambda rid: format_run_label(entry_map[rid]),
        key=key,
    )
    entry = entry_map[chosen]
    if entry.get("bundle") is not None:
        return chosen, entry["bundle"]
    return chosen, cache.get_run_bundle(chosen, include_samples=include_samples)


def pick_runs(key: str, *, label: str = "Select runs to compare", max_default: int = 3) -> list[dict[str, Any]]:
    """Render a multi-run selector and return list of entry dicts."""
    entries = collect_run_entries()
    if not entries:
        return []
    entry_map = {e["run_id"]: e for e in entries}
    options = [e["run_id"] for e in entries]

    # Default: unsaved session runs + top complete scored runs
    defaults: list[str] = [e["run_id"] for e in entries if e.get("is_session")]
    complete = [
        e for e in entries
        if not e.get("is_session") and (e.get("index_row") or {}).get("status") == "complete" and e.get("net") is not None
    ]
    complete.sort(key=lambda e: float(e.get("net") or -999.0), reverse=True)
    for e in complete[:max_default]:
        if e["run_id"] not in defaults:
            defaults.append(e["run_id"])
    if not defaults:
        defaults = options[:min(max_default, len(options))]

    selected_ids = st.multiselect(
        label,
        options,
        default=defaults,
        format_func=lambda rid: format_run_label(entry_map[rid]),
        key=key,
    )
    return [entry_map[rid] for rid in selected_ids if rid in entry_map]
