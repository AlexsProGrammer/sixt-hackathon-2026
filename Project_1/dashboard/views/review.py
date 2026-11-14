"""Review page: inspect one document side-by-side with extracted fields, gold, and human review actions."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from dashboard import cache, data
from dashboard.components import pdf as pdf_comp

COLOR_STYLES = {
    "green": "background-color: #dcfce7; color: #14532d;",
    "red": "background-color: #fee2e2; color: #7f1d1d;",
    "yellow": "background-color: #fef9c3; color: #713f12;",
    "grey": "background-color: #f3f4f6; color: #4b5563;",
    "neutral": "",
}


def _fmt_val(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _pick_bundle() -> dict[str, Any] | None:
    session_runs: dict[str, dict] = st.session_state.get("session_runs") or {}
    reg_ids = data.list_run_ids()
    options: list[str] = []
    for rid in session_runs:
        options.append(f"[session] {rid}")
    for rid in reg_ids:
        options.append(rid)
    if not options:
        st.info("No runs available yet. Start a run on the Run page.")
        return None

    active = st.session_state.get("active_run_id")
    default_idx = 0
    if active:
        for i, opt in enumerate(options):
            if opt == active or opt == f"[session] {active}":
                default_idx = i
                break

    choice = st.selectbox("Run", options, index=default_idx)
    if choice.startswith("[session] "):
        rid = choice[len("[session] "):]
        return session_runs[rid]
    return cache.get_run_bundle(choice)


def render(sidebar_state: dict[str, Any]) -> None:
    st.header("Document Review")
    bundle = _pick_bundle()
    if bundle is None:
        return

    run_id = bundle["run_id"]
    doc_ids = sorted(bundle.get("preds", {}).keys())
    if not doc_ids:
        st.warning(f"Run `{run_id}` has no predicted documents.")
        return

    c_doc, c_filt = st.columns([2, 2])
    doc_id = c_doc.selectbox("Document", doc_ids)
    filt = c_filt.radio(
        "Filter fields",
        ["All", "Only booked", "Only missed savings", "Only errors"],
        horizontal=True,
    )

    records = data.load_records_by_doc_id([doc_id], run_dir=bundle.get("run_dir"))
    rec = records.get(doc_id) or (bundle.get("gold") or {}).get(doc_id) or (bundle.get("input") or {}).get(doc_id) or {"doc_id": doc_id}
    threshold = float(sidebar_state.get("threshold", 0.99))
    reviewer = str(sidebar_state.get("reviewer") or "reviewer")

    all_rows = data.build_doc_field_rows(doc_id, bundle, rec=rec, threshold=threshold)
    if filt == "Only booked":
        rows = [r for r in all_rows if r["booked"]]
    elif filt == "Only missed savings":
        rows = [r for r in all_rows if r["outcome"] == "correct" and not r["booked"]]
    elif filt == "Only errors":
        rows = [r for r in all_rows if r["outcome"] in ("wrong", "hallucinated")]
    else:
        rows = all_rows

    reviews = cache.get_reviews()
    rev_map = data.latest_reviews_map(reviews, run_id=run_id)
    doc_reviews = [v for (d, _), v in rev_map.items() if d == doc_id]
    n_to_human = sum(1 for r in all_rows if not r["booked"])
    sim_human_cost = n_to_human + len(doc_reviews)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fields", len(all_rows))
    m2.metric("Booked", sum(1 for r in all_rows if r["booked"]))
    m3.metric("To human", n_to_human)
    m4.metric("Simulated human cost", f"{sim_human_cost} ({len(doc_reviews)} reviewed)")

    left, right = st.columns([1.05, 1.15], gap="large")
    with left:
        st.subheader("Document")
        pdf_comp.render_document_pane(rec, all_rows)

    with right:
        st.subheader("Extracted Fields")
        if not rows:
            st.info("No fields match the selected filter.")
        else:
            table_data = []
            row_colors = []
            for r in rows:
                rev = rev_map.get((doc_id, r["field"]))
                views_str = ", ".join(
                    f"{v['view']}: {_fmt_val(v['value'])}" for v in r["per_view"]
                ) if r["per_view"] else "—"
                table_data.append({
                    "Field": r["field"],
                    "Value": _fmt_val(r["value"]),
                    "Gold": _fmt_val(r["gold"]) if r["has_gold"] else "—",
                    "Conf": round(r["confidence"], 3),
                    "Decision": r["decision"],
                    "Reason": r["reason"] or "—",
                    "Evidence": ", ".join(r["evidence_flags"]) or "—",
                    "Per-view": views_str,
                    "Review": f"{rev['action']} ({_fmt_val(rev['value'])})" if rev else "—",
                })
                row_colors.append(r["color"])

            df = pd.DataFrame(table_data)

            def _style_row(s: pd.Series) -> list[str]:
                css = COLOR_STYLES.get(row_colors[s.name], "")
                return [css] * len(s)

            st.dataframe(
                df.style.apply(_style_row, axis=1),
                use_container_width=True,
                hide_index=True,
                height=380,
            )

            st.caption("Row colors: green = correct & booked · red = wrong/hallucinated & booked · yellow = missed saving · grey = true null")

            st.subheader("Field Review Action")
            selected_field = st.selectbox("Field to review", [r["field"] for r in rows])
            sel_row = next(r for r in rows if r["field"] == selected_field)
            b1, b2, b3 = st.columns(3)
            if b1.button("Accept", key=f"acc_{run_id}_{doc_id}_{selected_field}", use_container_width=True):
                data.append_review({
                    "run_id": run_id,
                    "doc_id": doc_id,
                    "field": selected_field,
                    "action": "accept",
                    "value": sel_row["value"],
                    "reviewer": reviewer,
                })
                st.cache_data.clear()
                st.rerun()
            if b2.button("Decline", key=f"dec_{run_id}_{doc_id}_{selected_field}", use_container_width=True):
                data.append_review({
                    "run_id": run_id,
                    "doc_id": doc_id,
                    "field": selected_field,
                    "action": "decline",
                    "value": None,
                    "reviewer": reviewer,
                })
                st.cache_data.clear()
                st.rerun()
            edited_val = b3.text_input(
                "Edit value",
                value="" if sel_row["value"] is None else str(sel_row["value"]),
                key=f"edit_in_{run_id}_{doc_id}_{selected_field}",
                label_visibility="collapsed",
                placeholder="Edited value...",
            )
            if st.button("Save Edit", key=f"edit_btn_{run_id}_{doc_id}_{selected_field}"):
                data.append_review({
                    "run_id": run_id,
                    "doc_id": doc_id,
                    "field": selected_field,
                    "action": "edit",
                    "value": edited_val,
                    "reviewer": reviewer,
                })
                st.cache_data.clear()
                st.rerun()
