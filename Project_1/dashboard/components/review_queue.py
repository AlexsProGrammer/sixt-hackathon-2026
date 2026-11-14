"""Per-row interactive Review Queue component (WP7)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

import streamlit as st

from dashboard import cache, data, state
from dashboard.components import filters, ui

_PAGE_SIZE = 20
_COL_WIDTHS = [2.1, 3.0, 2.1, 0.85, 1.2, 1.2, 1.35]


def _format_cell(val: Any, max_len: int = 120) -> str:
    if val is None:
        return "—"
    if isinstance(val, (list, dict)):
        s = json.dumps(val, ensure_ascii=False)
    else:
        s = str(val)
    return s if len(s) <= max_len else s[:max_len] + "…"


def _parse_edited_value(raw_val: Any, original_val: Any, kind: str) -> Any:
    if isinstance(raw_val, bool):
        return raw_val
    if isinstance(raw_val, (int, float)):
        return raw_val
    s = str(raw_val).strip()
    if s == "":
        return None
    if isinstance(original_val, (list, dict)) or (s.startswith(("{", "[")) and s.endswith(("}", "]"))):
        try:
            return json.loads(s)
        except ValueError:
            return s
    return s


def _reviews_csv(reviews: list[dict], run_id: str, doc_id: str) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["ts", "run_id", "doc_id", "field", "action", "value", "original_value", "reviewer"],
    )
    writer.writeheader()
    for r in reviews:
        if r.get("run_id") == run_id and r.get("doc_id") == doc_id:
            writer.writerow({k: r.get(k, "") for k in writer.fieldnames})
    return buf.getvalue()


@st.fragment
def render_review_queue(run_id: str, doc_id: str, all_rows: list[dict[str, Any]]) -> None:
    """Render the interactive per-row Review Queue at the bottom of the Review page."""
    st.divider()
    h_left, h_rev, h_bulk = st.columns([2.6, 1.1, 1.3], gap="medium", vertical_alignment="bottom")
    with h_left:
        st.subheader("Review queue")
        st.caption("Showcase: how reviewers confirm or correct extracted values in production.")
    with h_rev:
        st.text_input("Reviewer", key=state.K_REVIEWER, help="Recorded in results/reviews.jsonl")
    with h_bulk:
        booked_rows = [r for r in all_rows if r.get("booked")]
        confirm_key = f"_confirm_bulk_{run_id}_{doc_id}"
        if st.session_state.get(confirm_key):
            b1, b2 = st.columns(2, gap="small")
            if b1.button("Confirm", key=f"bulk_yes_{run_id}_{doc_id}", type="primary", width="stretch"):
                rev_name = state.reviewer()
                for r in booked_rows:
                    data.append_review({
                        "run_id": run_id,
                        "doc_id": doc_id,
                        "field": r["field"],
                        "action": "accept",
                        "value": r["value"],
                        "reviewer": rev_name,
                    })
                st.session_state[confirm_key] = False
                st.cache_data.clear()
                st.toast(f"Accepted {len(booked_rows)} booked fields", icon=":material/check:")
                st.rerun(scope="fragment")
            if b2.button("Cancel", key=f"bulk_no_{run_id}_{doc_id}", width="stretch"):
                st.session_state[confirm_key] = False
                st.rerun(scope="fragment")
        else:
            if st.button(
                f"Accept all booked ({len(booked_rows)})",
                icon=":material/done_all:",
                disabled=not booked_rows,
                width="stretch",
                key=f"bulk_btn_{run_id}_{doc_id}",
            ):
                st.session_state[confirm_key] = True
                st.rerun(scope="fragment")

    counts = {mode: len(data.filter_field_rows(all_rows, mode)) for mode in data.DECISION_FILTERS}
    q_filter = filters.decision_filter(
        f"queue_filter_{run_id}",
        counts=counts,
        default="Only to human",
        label="Queue filter",
    )
    filtered = data.filter_field_rows(all_rows, q_filter)

    reviews = cache.get_reviews()
    rev_map = data.latest_reviews_map(reviews, run_id=run_id)
    prog = data.review_progress(all_rows, rev_map, doc_id)

    if not filtered:
        st.info("No fields match the selected queue filter.")
    else:
        total_pages = max(1, (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        page_key = f"queue_page_{run_id}_{doc_id}"
        page_num = 1
        if total_pages > 1:
            page_num = int(
                st.number_input(
                    f"Page (1–{total_pages})",
                    min_value=1,
                    max_value=total_pages,
                    value=min(int(st.session_state.get(page_key, 1)), total_pages),
                    step=1,
                    key=page_key,
                )
            )
        start = (page_num - 1) * _PAGE_SIZE
        page_rows = filtered[start : start + _PAGE_SIZE]

        # Header row
        hdrs = st.columns(_COL_WIDTHS, gap="small")
        for col, title in zip(hdrs, ("Field", "Value", "Gold", "Conf", "Decision", "Status", "Actions")):
            col.markdown(f'<div class="p1-queue-hdr">{title}</div>', unsafe_allow_html=True)

        editing_target = st.session_state.get(state.K_EDITING)

        for r in page_rows:
            fname = str(r["field"])
            rev = rev_map.get((doc_id, fname))
            st_name = data.review_status(rev)
            is_editing = editing_target == (run_id, doc_id, fname)

            cols = st.columns(_COL_WIDTHS, gap="small", vertical_alignment="center")
            with cols[0]:
                st.markdown(f"**{fname}**")
                if r.get("kind"):
                    st.caption(str(r["kind"]))

            with cols[1]:
                if is_editing:
                    cur_val = rev.get("value") if rev and rev.get("action") == "edit" else r.get("value")
                    kind_l = str(r.get("kind") or "").lower()
                    edit_key = f"edit_val_{run_id}_{doc_id}_{fname}"
                    if isinstance(cur_val, bool) or kind_l == "boolean":
                        edited_input = st.checkbox("Value", value=bool(cur_val), key=edit_key, label_visibility="collapsed")
                    elif isinstance(cur_val, (list, dict)) or (isinstance(cur_val, str) and len(cur_val) > 90):
                        init_txt = json.dumps(cur_val, ensure_ascii=False) if isinstance(cur_val, (list, dict)) else str(cur_val or "")
                        edited_input = st.text_area("Value", value=init_txt, height=85, key=edit_key, label_visibility="collapsed")
                        if isinstance(cur_val, (list, dict)):
                            st.caption("JSON value")
                    else:
                        edited_input = st.text_input("Value", value="" if cur_val is None else str(cur_val), key=edit_key, label_visibility="collapsed")
                else:
                    if st_name == "edited" and rev is not None:
                        old_s = _format_cell(r.get("value"), 50)
                        new_s = _format_cell(rev.get("value"), 80)
                        st.markdown(f"~~{old_s}~~ → **{new_s}**")
                    else:
                        st.text(_format_cell(r.get("value"), 110))

            with cols[2]:
                st.text(_format_cell(r.get("gold"), 90) if r.get("has_gold") else "—")

            with cols[3]:
                st.text(f"{float(r.get('confidence') or 0.0):.2f}")

            with cols[4]:
                if r.get("booked"):
                    ui.badge("✓ booked", "success")
                else:
                    ui.badge("→ human", "warning")

            with cols[5]:
                status_kind = {
                    "pending": "neutral",
                    "accepted": "success",
                    "edited": "info",
                    "declined": "danger",
                }.get(st_name, "neutral")
                ui.badge(st_name.capitalize(), status_kind)

            with cols[6]:
                if is_editing:
                    a1, a2 = st.columns(2, gap="small")
                    if a1.button("", icon=":material/check:", key=f"save_{run_id}_{doc_id}_{fname}", help="Save & accept edited value", type="primary"):
                        parsed = _parse_edited_value(edited_input, r.get("value"), str(r.get("kind") or ""))
                        data.append_review({
                            "run_id": run_id,
                            "doc_id": doc_id,
                            "field": fname,
                            "action": "edit",
                            "value": parsed,
                            "original_value": r.get("value"),
                            "reviewer": state.reviewer(),
                        })
                        st.session_state[state.K_EDITING] = None
                        st.cache_data.clear()
                        st.toast(f"Saved edit for {fname}", icon=":material/check:")
                        st.rerun(scope="fragment")
                    if a2.button("", icon=":material/close:", key=f"cancel_{run_id}_{doc_id}_{fname}", help="Cancel edit", type="tertiary"):
                        st.session_state[state.K_EDITING] = None
                        st.rerun(scope="fragment")
                else:
                    a1, a2, a3 = st.columns(3, gap="small")
                    if a1.button("", icon=":material/check:", key=f"qacc_{run_id}_{doc_id}_{fname}", help="Accept value", type="tertiary"):
                        data.append_review({
                            "run_id": run_id,
                            "doc_id": doc_id,
                            "field": fname,
                            "action": "accept",
                            "value": r.get("value"),
                            "reviewer": state.reviewer(),
                        })
                        st.cache_data.clear()
                        st.toast(f"Accepted {fname}", icon=":material/check:")
                        st.rerun(scope="fragment")
                    if a2.button("", icon=":material/edit:", key=f"qedit_{run_id}_{doc_id}_{fname}", help="Edit value", type="tertiary"):
                        st.session_state[state.K_EDITING] = (run_id, doc_id, fname)
                        st.rerun(scope="fragment")
                    if a3.button("", icon=":material/block:", key=f"qdec_{run_id}_{doc_id}_{fname}", help="Decline value", type="tertiary"):
                        data.append_review({
                            "run_id": run_id,
                            "doc_id": doc_id,
                            "field": fname,
                            "action": "decline",
                            "value": None,
                            "reviewer": state.reviewer(),
                        })
                        st.cache_data.clear()
                        st.toast(f"Declined {fname}", icon=":material/block:")
                        st.rerun(scope="fragment")

    # Summary footer + CSV export
    st.divider()
    f_left, f_right = st.columns([3, 1], gap="medium", vertical_alignment="center")
    with f_left:
        total = max(1, prog["total"])
        st.progress(prog["reviewed"] / total)
        st.caption(
            f"Reviewed **{prog['reviewed']} / {prog['total']}** · "
            f"Accepted {prog['accepted']} · Edited {prog['edited']} · Declined {prog['declined']} · "
            f"Remaining {prog['pending']}"
        )
    with f_right:
        st.download_button(
            "Export reviews (CSV)",
            data=_reviews_csv(reviews, run_id, doc_id),
            file_name=f"reviews_{run_id}_{doc_id}.csv".replace(":", "_"),
            mime="text/csv",
            icon=":material/download:",
            width="stretch",
        )
