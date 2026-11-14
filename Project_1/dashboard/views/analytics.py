"""Analytics page: precision-coverage, net saving vs threshold, reliability, heatmap, route/kind bars, run comparison."""
from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import cache, data


def _curve_rows(bundle: dict[str, Any], label: str, is_session: bool) -> list[dict]:
    score = bundle.get("score") or {}
    curve = score.get("curve") or []
    rows: list[dict] = []
    for pt in curve:
        n_fields = pt.get("n_fields") or 0
        correct = pt.get("correct") or 0
        wrong = pt.get("wrong") or 0
        halluc = pt.get("hallucinated") or 0
        errors = wrong + halluc
        accepted = pt.get("accepted") or 0
        row: dict[str, Any] = {
            "run": label,
            "is_session": is_session,
            "threshold": pt.get("threshold"),
            "precision": pt.get("precision"),
            "coverage": pt.get("coverage"),
            "accepted": accepted,
        }
        if n_fields > 0:
            for e_cost in (20, 100, 500):
                row[f"E={e_cost}"] = ((accepted - e_cost * errors) / n_fields) * 100.0
        rows.append(row)
    return rows


def render(sidebar_state: dict[str, Any]) -> None:
    st.header("Analytics")
    index_rows = cache.get_index()
    session_runs: dict[str, dict] = st.session_state.get("session_runs") or {}
    unsaved_sessions = {rid: b for rid, b in session_runs.items() if not b.get("saved_to_registry")}

    # ------------------------------------------------------------------ 1. Run comparison table
    st.subheader("Run Comparison")
    comp_rows = list(index_rows)
    for rid, b in unsaved_sessions.items():
        if b.get("index_row"):
            comp_rows.insert(0, {**b["index_row"], "tags": ["session (unsaved)"]})

    if not comp_rows:
        st.info("No runs in index yet.")
        return

    comp_df = pd.DataFrame([
        {
            "run_id": r.get("run_id"),
            "name": r.get("name"),
            "split": r.get("split"),
            "status": r.get("status"),
            "docs": r.get("n_docs"),
            "accepted": r.get("accepted"),
            "correct": r.get("correct"),
            "wrong": r.get("wrong"),
            "halluc": r.get("hallucinated"),
            "precision": round(r["precision"], 4) if r.get("precision") is not None else None,
            "coverage": round(r["coverage"], 4) if r.get("coverage") is not None else None,
            "net@20 (%)": round(r["net_saving_pct_e20"] * 100, 2) if r.get("net_saving_pct_e20") is not None else None,
            "net@100 (%)": round(r["net_saving_pct_e100"] * 100, 2) if r.get("net_saving_pct_e100") is not None else None,
            "net@500 (%)": round(r["net_saving_pct_e500"] * 100, 2) if r.get("net_saving_pct_e500") is not None else None,
            "tags": ", ".join(r.get("tags") or []),
        }
        for r in comp_rows
    ])
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------ 2. Select runs for curve & field charts
    scored_ids = [r["run_id"] for r in index_rows if r.get("status") == "complete" and r.get("n_docs")]
    default_selected = scored_ids[:3] if scored_ids else [r["run_id"] for r in index_rows[:2]]
    selected_ids = st.multiselect("Registry runs to plot", [r["run_id"] for r in index_rows], default=default_selected)

    curve_data: list[dict] = []
    primary_bundle: dict[str, Any] | None = None
    for rid in selected_ids:
        try:
            b = cache.get_run_bundle(rid)
        except FileNotFoundError:
            continue
        if primary_bundle is None and b.get("fields"):
            primary_bundle = b
        curve_data.extend(_curve_rows(b, rid, is_session=False))

    for rid, b in unsaved_sessions.items():
        if primary_bundle is None and b.get("fields"):
            primary_bundle = b
        curve_data.extend(_curve_rows(b, f"{rid} (session)", is_session=True))

    if curve_data:
        cdf = pd.DataFrame(curve_data)
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Precision vs Coverage")
            pr_df = cdf.dropna(subset=["precision", "coverage"])
            if not pr_df.empty:
                chart_pc = (
                    alt.Chart(pr_df)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("coverage:Q", title="Coverage", scale=alt.Scale(domain=[0, 1])),
                        y=alt.Y("precision:Q", title="Precision", scale=alt.Scale(domain=[0, 1])),
                        color=alt.Color("run:N", title="Run"),
                        strokeDash=alt.condition(
                            alt.datum.is_session, alt.value([5, 4]), alt.value([1, 0])
                        ),
                        tooltip=["run", "threshold", "precision", "coverage", "accepted"],
                    )
                    .properties(height=320)
                )
                st.altair_chart(chart_pc, use_container_width=True)

        with c2:
            st.subheader("Net Saving (%) vs Threshold")
            e_cols = [c for c in ("E=20", "E=100", "E=500") if c in cdf.columns]
            if e_cols:
                melted = cdf.melt(
                    id_vars=["run", "is_session", "threshold"],
                    value_vars=e_cols,
                    var_name="error_cost",
                    value_name="net_saving_pct",
                ).dropna(subset=["net_saving_pct"])
                chart_ns = (
                    alt.Chart(melted)
                    .mark_line()
                    .encode(
                        x=alt.X("threshold:Q", title="Threshold"),
                        y=alt.Y("net_saving_pct:Q", title="Net saving (%)"),
                        color=alt.Color("run:N", title="Run"),
                        strokeDash=alt.condition(
                            alt.datum.is_session, alt.value([5, 4]), alt.value([1, 0])
                        ),
                        facet=alt.Facet("error_cost:N", columns=1),
                        tooltip=["run", "error_cost", "threshold", "net_saving_pct"],
                    )
                    .properties(height=105)
                )
                st.altair_chart(chart_ns, use_container_width=True)

    # ------------------------------------------------------------------ 3. Field-level charts
    field_run_options = [rid for rid in selected_ids] + [f"[session] {rid}" for rid in unsaved_sessions]
    if not field_run_options:
        return
    chosen_field_run = st.selectbox("Run for field-level diagnostics (reliability, heatmap, route/kind)", field_run_options)
    if chosen_field_run.startswith("[session] "):
        fbundle = unsaved_sessions[chosen_field_run[len("[session] "):]]
    else:
        fbundle = cache.get_run_bundle(chosen_field_run)

    fields = fbundle.get("fields") or []
    if not fields:
        st.info("Selected run has no `fields.jsonl`. Run `python -m evaluation.field_table <run_id>` to generate it.")
        return

    threshold = float(sidebar_state.get("threshold", 0.99))

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Reliability (Confidence vs Precision)")
        rel = data.compute_reliability_bins(fields, n_bins=10)
        if rel:
            rdf = pd.DataFrame(rel)
            diag_df = pd.DataFrame({"x": [0.0, 1.0], "y": [0.0, 1.0]})
            pts = (
                alt.Chart(rdf)
                .mark_circle()
                .encode(
                    x=alt.X("mean_conf:Q", title="Mean confidence", scale=alt.Scale(domain=[0, 1])),
                    y=alt.Y("precision:Q", title="Actual precision", scale=alt.Scale(domain=[0, 1])),
                    size=alt.Size("count:Q", title="Count"),
                    tooltip=["bin", "mean_conf", "precision", "count"],
                )
            )
            diag_line = alt.Chart(diag_df).mark_line(strokeDash=[4, 4], color="gray").encode(x="x:Q", y="y:Q")
            st.altair_chart((diag_line + pts).properties(height=300), use_container_width=True)
        else:
            st.info("No predicted-present fields with confidence values.")

    with c4:
        st.subheader("By Route & Kind")
        route_stats, kind_stats = data.compute_route_kind_stats(fields, threshold=threshold)
        tab_r, tab_k = st.tabs(["By Route", "By Kind"])
        with tab_r:
            if route_stats:
                rs_df = pd.DataFrame(route_stats).melt(id_vars=["route"], value_vars=["correct", "wrong", "booked"])
                ch_r = alt.Chart(rs_df).mark_bar().encode(
                    x="route:N", y="value:Q", color="variable:N", xOffset="variable:N",
                    tooltip=["route", "variable", "value"],
                ).properties(height=260)
                st.altair_chart(ch_r, use_container_width=True)
        with tab_k:
            if kind_stats:
                ks_df = pd.DataFrame(kind_stats).melt(id_vars=["kind"], value_vars=["correct", "wrong", "booked"])
                ch_k = alt.Chart(ks_df).mark_bar().encode(
                    x="kind:N", y="value:Q", color="variable:N", xOffset="variable:N",
                    tooltip=["kind", "variable", "value"],
                ).properties(height=260)
                st.altair_chart(ch_k, use_container_width=True)

    st.subheader("Family × Field Heatmap")
    metric_choice = st.radio("Heatmap metric", ["precision", "booked"], horizontal=True)
    ff_stats = data.compute_family_field_stats(fields, threshold=threshold)
    if ff_stats:
        ff_df = pd.DataFrame(ff_stats)
        if metric_choice == "precision":
            ff_df = ff_df.dropna(subset=["precision"])
        if not ff_df.empty:
            # Keep top 35 fields by total count for readability if huge
            top_fields = ff_df.groupby("field")["n_total"].sum().nlargest(35).index.tolist()
            ff_df = ff_df[ff_df["field"].isin(top_fields)]
            hm = (
                alt.Chart(ff_df)
                .mark_rect()
                .encode(
                    x=alt.X("field:N", title="Field"),
                    y=alt.Y("family:N", title="Family"),
                    color=alt.Color(f"{metric_choice}:Q", scale=alt.Scale(scheme="viridis")),
                    tooltip=["family", "field", "booked", "correct", "precision", "n_total"],
                )
                .properties(height=max(260, min(600, 22 * ff_df["family"].nunique())))
            )
            st.altair_chart(hm, use_container_width=True)
        else:
            st.info("No booked cells at this threshold.")
