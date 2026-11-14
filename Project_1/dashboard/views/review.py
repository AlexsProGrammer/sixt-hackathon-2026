"""Review page (WP7): inspect one document side-by-side with extracted fields and Review Queue."""
from __future__ import annotations

import json
import random
from typing import Any

import pandas as pd
import streamlit as st

from dashboard import cache, data, nav, state
from dashboard.components import action_button, filters, pdf as pdf_comp, review_queue, run_picker, ui

_COLOR_STYLES = {
    "green": "background-color: #dcfce7; color: #14532d;",
    "red": "background-color: #fee2e2; color: #7f1d1d;",
    "yellow": "background-color: #fef3c7; color: #78350f;",
    "grey": "background-color: #f1f5f9; color: #475569;",
    "neutral": "",
}


def _fmt_val(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def render() -> None:
    """Render the Document Review page."""
    ui.page_header(
        "Document review",
        "Inspect extracted fields side-by-side with the source document, then confirm or edit values.",
        icon=":material/fact_check:",
    )

    c_run, c_doc, c_prev, c_next, c_rand = st.columns([2.2, 2.2, 0.45, 0.45, 0.7], gap="small", vertical_alignment="bottom")
    with c_run:
        run_id, bundle = run_picker.pick_run("review_run_pick", label="Run")
    if bundle is None or run_id is None:
        ui.empty_state(
            ":material/inbox:",
            "No runs available yet",
            "Start a run on the Run page to inspect predictions and review fields.",
            action=lambda: nav.switch_to("run") if st.button("Start a run", type="primary") else None,
        )
        return

    state.set_active_run(run_id)
    doc_ids = sorted((bundle.get("preds") or {}).keys())
    if not doc_ids:
        st.warning(f"Run `{run_id}` has no predicted documents.")
        return

    doc_key = f"review_doc_{run_id}"
    if st.session_state.get(state.K_ACTIVE_DOC) in doc_ids:
        st.session_state.setdefault(doc_key, st.session_state[state.K_ACTIVE_DOC])
    if st.session_state.get(doc_key) not in doc_ids:
        st.session_state[doc_key] = doc_ids[0]

    def _step_doc(delta: int) -> None:
        cur = st.session_state.get(doc_key, doc_ids[0])
        idx = doc_ids.index(cur) if cur in doc_ids else 0
        st.session_state[doc_key] = doc_ids[(idx + delta) % len(doc_ids)]

    def _random_doc() -> None:
        st.session_state[doc_key] = random.choice(doc_ids)

    with c_prev:
        st.button("", icon=":material/chevron_left:", help="Previous document", on_click=_step_doc, args=(-1,), width="stretch")
    with c_next:
        st.button("", icon=":material/chevron_right:", help="Next document", on_click=_step_doc, args=(1,), width="stretch")
    with c_rand:
        st.button("Random", icon=":material/shuffle:", help="Pick a random document", on_click=_random_doc, width="stretch")

    with c_doc:
        doc_id = st.selectbox(
            "Document",
            doc_ids,
            key=doc_key,
            format_func=lambda d: f"{'CUAD' if str(d).startswith('cuad') else 'EB'} · {d}",
        )
    state.set_active_run(run_id, doc_id)

    # Banner if fields.jsonl is missing
    if not (bundle.get("fields") or []):
        b1, b2 = st.columns([3, 1], vertical_alignment="center")
        b1.info("`fields.jsonl` is not built for this run yet — some outcome colours may be unknown.")
        with b2:
            action_button.generate_button(
                "field_table",
                {"run_id": run_id, "run_dir": bundle.get("run_dir")},
                label="Build field table",
                key=f"rev_ft_{run_id}",
                width="stretch",
            )

    threshold = state.threshold()
    records = data.load_records_by_doc_id([doc_id], run_dir=bundle.get("run_dir"))
    rec = (
        records.get(doc_id)
        or (bundle.get("gold") or {}).get(doc_id)
        or (bundle.get("input") or {}).get(doc_id)
        or {"doc_id": doc_id}
    )

    all_rows = data.build_doc_field_rows(doc_id, bundle, rec=rec, threshold=threshold)
    reviews = cache.get_reviews()
    rev_map = data.latest_reviews_map(reviews, run_id=run_id)
    doc_reviews = [v for (d, _), v in rev_map.items() if d == doc_id]

    n_fields = len(all_rows)
    n_booked = sum(1 for r in all_rows if r["booked"])
    n_to_human = n_fields - n_booked
    n_errors = sum(1 for r in all_rows if r["booked"] and r["outcome"] in ("wrong", "hallucinated"))
    sim_cost = n_to_human + len(doc_reviews)

    ui.kpi_row([
        {"label": "Fields", "value": n_fields},
        {"label": "Booked", "value": n_booked, "foot": f"τ = {threshold:.2f}"},
        {"label": "To human", "value": n_to_human, "foot": "Low conf / abstained"},
        {"label": "Errors booked", "value": n_errors, "foot": "Wrong + hallucinated"},
        {"label": "Simulated cost", "value": sim_cost, "delta": f"saved {n_booked} reviews", "foot": f"{len(doc_reviews)} logged"},
    ])

    counts = {m: len(data.filter_field_rows(all_rows, m)) for m in data.DECISION_FILTERS}
    filt = filters.decision_filter(f"review_filter_{run_id}", counts=counts, default="All")
    rows = data.filter_field_rows(all_rows, filt)

    left, right = st.columns([1.05, 1.15], gap="large")
    with left:
        with st.container(border=True, height="stretch"):
            st.subheader("Source document")
            pdf_comp.render_document_pane(rec, all_rows)

    with right:
        with st.container(border=True, height="stretch"):
            st.subheader("Extracted fields")
            ui.badges_row([
                ("Correct booked", "success"),
                ("Error booked", "danger"),
                ("Missed saving", "warning"),
                ("True null", "neutral"),
            ])
            if not rows:
                st.info("No fields match the selected filter.")
            else:
                table_data = []
                row_colors = []
                for r in rows:
                    rev = rev_map.get((doc_id, r["field"]))
                    table_data.append({
                        "Field": r["field"],
                        "Value": _fmt_val(r["value"]),
                        "Gold": _fmt_val(r["gold"]) if r["has_gold"] else "—",
                        "Conf": round(r["confidence"], 3),
                        "Decision": "✓ booked" if r["booked"] else "→ human",
                        "Outcome": r["outcome"],
                        "Review": f"{rev['action']}" if rev else "—",
                    })
                    row_colors.append(r["color"])

                df = pd.DataFrame(table_data)

                def _style_rows(_row: pd.Series) -> list[str]:
                    css = _COLOR_STYLES.get(row_colors[_row.name], "")
                    return [css] * len(_row)

                event = st.dataframe(
                    df.style.apply(_style_rows, axis=1),
                    width="stretch",
                    hide_index=True,
                    height=430,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"rev_tbl_{run_id}_{doc_id}_{filt}",
                    column_config={
                        "Field": st.column_config.TextColumn("Field", width="medium"),
                        "Value": st.column_config.TextColumn("Value", width="medium"),
                        "Gold": st.column_config.TextColumn("Gold", width="medium"),
                        "Conf": st.column_config.ProgressColumn("Conf", min_value=0.0, max_value=1.0, format="%.2f"),
                        "Decision": st.column_config.TextColumn("Decision", width="small"),
                        "Outcome": st.column_config.TextColumn("Outcome", width="small"),
                        "Review": st.column_config.TextColumn("Review", width="small"),
                    },
                )

                sel_rows = (event.selection.rows if hasattr(event, "selection") and event.selection else []) or []
                if sel_rows:
                    detail = rows[sel_rows[0]]
                    with st.expander(f"Field detail: {detail['field']}", expanded=True):
                        d1, d2 = st.columns(2)
                        d1.markdown(f"**Prediction:** `{_fmt_val(detail['value'])}`")
                        d2.markdown(f"**Gold:** `{_fmt_val(detail['gold']) if detail['has_gold'] else '—'}`")
                        if detail["evidence_flags"]:
                            ui.badges_row([(flag, "info") for flag in detail["evidence_flags"]])
                        if detail["reason"]:
                            st.caption(f"Reason: {detail['reason']}")
                        if detail["per_view"]:
                            st.dataframe(pd.DataFrame(detail["per_view"]), width="stretch", hide_index=True)

    # Bottom interactive Review Queue
    review_queue.render_review_queue(run_id, doc_id, all_rows)
