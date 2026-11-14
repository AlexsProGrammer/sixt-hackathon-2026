"""Sub-tab renderers for the Analytics page (WP8)."""
from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import analytics_core, cache, data, nav, state, theme
from dashboard.components import action_button, filters, ui
from evaluation import report as eval_report


def render_overview_tab(
    selected_entries: list[dict[str, Any]],
    bundles: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    tau: float,
    error_cost: float,
) -> None:
    """Render Overview tab: verdict cards, average performance table, net-vs-human bar, by-source, registry."""
    # 1. Verdict cards (3 per row, equal height, 2x2 non-truncating stat grid)
    st.subheader("Run performance at a glance")
    for i in range(0, len(selected_entries), 3):
        cols = st.columns(3, gap="medium")
        for col, entry in zip(cols, selected_entries[i : i + 3]):
            rid = entry["run_id"]
            sm = summaries[rid]
            prof = profiles[rid]
            net_val = sm["net_at_tau"]
            net_cls = "p1-neu" if net_val is None else ("p1-pos" if net_val > 0 else ("p1-neg" if net_val < 0 else "p1-neu"))
            prec_s = theme.fmt_pct(sm["precision_at_tau"], 1)
            cov_s = theme.fmt_pct(sm["coverage_at_tau"], 1)
            net_s = theme.fmt_signed_pct(net_val)
            err_s = theme.fmt_int(sm["errors_at_tau"])
            with col:
                with st.container(border=True, height="stretch"):
                    top_l, top_r = st.columns([1.8, 1.2], vertical_alignment="center")
                    top_l.markdown(f"**{entry['name']}**")
                    with top_r:
                        ui.verdict_chip(sm["verdict"])
                    ui.badges_row([
                        (entry["split"], "neutral"),
                        ("session" if entry["is_session"] else entry["status"], "info" if entry["is_session"] else "neutral"),
                        (f"{prof['uq_method']} (K={prof['samples']})", "brand"),
                    ])
                    st.html(
                        f'<div class="p1-stat-grid">'
                        f'<div><div class="p1-stat-label">Prec @τ</div><div class="p1-stat-val">{prec_s}</div></div>'
                        f'<div><div class="p1-stat-label">Cov @τ</div><div class="p1-stat-val">{cov_s}</div></div>'
                        f'<div><div class="p1-stat-label">Net @E={int(error_cost)}</div><div class="p1-stat-val {net_cls}">{net_s}</div></div>'
                        f'<div><div class="p1-stat-label">Errors</div><div class="p1-stat-val">{err_s}</div></div>'
                        f'</div>'
                    )
                    if sm["sparkline"]:
                        sp_df = pd.DataFrame({"idx": range(len(sm["sparkline"])), "net": sm["sparkline"]})
                        sp_ch = (
                            alt.Chart(sp_df)
                            .mark_line(color=theme.BRAND, strokeWidth=1.8)
                            .encode(
                                x=alt.X("idx:Q", axis=None),
                                y=alt.Y("net:Q", axis=None),
                            )
                            .properties(height=50)
                        )
                        zero_rule = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=theme.INK_SUBTLE, strokeDash=[2, 2]).encode(y="y:Q")
                        st.altair_chart(sp_ch + zero_rule, width="stretch")

    # 2. Average performance table
    st.subheader("Average performance across thresholds")
    st.caption(
        f"Curve averages summarize performance across all thresholds in `score.json`. "
        f"Break-even precision at E={int(error_cost)} is **{theme.fmt_pct(analytics_core.break_even_precision(error_cost), 1)}**."
    )
    avg_rows = []
    for entry in selected_entries:
        rid = entry["run_id"]
        sm = summaries[rid]
        prof = profiles[rid]
        idx_row = entry.get("index_row") or {}
        n_docs = idx_row.get("n_docs") or len((bundles[rid].get("preds") or {}))
        ub = sm["wilson_error_ub"]
        avg_rows.append({
            "Run": entry["name"],
            "Method": prof["uq_method"],
            "K": prof["samples"],
            "Docs": n_docs,
            "Prec @τ": sm["precision_at_tau"],
            "Cov @τ": sm["coverage_at_tau"],
            f"Net @E{int(error_cost)}": sm["net_at_tau"],
            "Avg prec (curve)": sm["avg_precision_curve"],
            f"Avg net @E{int(error_cost)}": sm["avg_net_curve"],
            "Robustness": sm["robustness_pct"],
            "Best τ": sm["best_tau"],
            "Best net": sm["best_net"],
            "Cov @99%": sm["coverage_at_99"],
            "Wilson-95 UB": f"<= {ub * 100:.1f}%" if ub is not None else "—",
            "Verdict": sm["verdict"],
        })
    avg_df = pd.DataFrame(avg_rows)
    net_col = f"Net @E{int(error_cost)}"
    avg_net_col = f"Avg net @E{int(error_cost)}"

    def _color_signed(val: Any) -> str:
        if isinstance(val, (int, float)) and not pd.isna(val):
            if val > 0:
                return "color: #16A34A; font-weight: 700;"
            if val < 0:
                return "color: #DC2626; font-weight: 700;"
        return ""

    styled_avg = avg_df.style.map(_color_signed, subset=[c for c in (net_col, avg_net_col, "Best net") if c in avg_df.columns])
    st.dataframe(
        styled_avg,
        width="stretch",
        hide_index=True,
        column_config={
            "Prec @τ": st.column_config.NumberColumn("Prec @τ", format="%.3f"),
            "Cov @τ": st.column_config.NumberColumn("Cov @τ", format="%.3f"),
            f"Net @E{int(error_cost)}": st.column_config.NumberColumn(f"Net @E{int(error_cost)}", format="%.3f"),
            "Avg prec (curve)": st.column_config.NumberColumn("Avg prec (curve)", format="%.3f"),
            f"Avg net @E{int(error_cost)}": st.column_config.NumberColumn(f"Avg net @E{int(error_cost)}", format="%.3f"),
            "Robustness": st.column_config.ProgressColumn("Robustness", min_value=0.0, max_value=1.0, format="%.0%%"),
            "Best τ": st.column_config.NumberColumn("Best τ", format="%.2f"),
            "Best net": st.column_config.NumberColumn("Best net", format="%.3f"),
            "Cov @99%": st.column_config.NumberColumn("Cov @99%", format="%.3f"),
        },
    )

    # 3. Net saving vs human baseline bar chart
    c_bar, c_src = st.columns(2, gap="medium")
    with c_bar:
        with st.container(border=True, height="stretch"):
            bar_data = []
            for entry in selected_entries:
                rid = entry["run_id"]
                sm = summaries[rid]
                if sm["net_at_tau"] is not None:
                    bar_data.append({
                        "run": entry["name"],
                        "net_at_tau": float(sm["net_at_tau"]),
                        "avg_net": float(sm["avg_net_curve"] or 0.0),
                        "sign": "Beats human" if sm["net_at_tau"] >= 0 else "Below human",
                    })
            if bar_data:
                bdf = pd.DataFrame(bar_data)
                bars = (
                    alt.Chart(bdf)
                    .mark_bar(cornerRadiusEnd=4)
                    .encode(
                        y=alt.Y("run:N", sort="-x", title=None),
                        x=alt.X("net_at_tau:Q", title=f"Net saving @E={int(error_cost)}", axis=alt.Axis(format=".0%")),
                        color=alt.Color(
                            "sign:N",
                            scale=alt.Scale(domain=["Beats human", "Below human"], range=[theme.SUCCESS, theme.DANGER]),
                            legend=None,
                        ),
                        tooltip=["run:N", alt.Tooltip("net_at_tau:Q", format=".1%"), alt.Tooltip("avg_net:Q", format=".1%", title="Curve avg")],
                    )
                )
                ticks = alt.Chart(bdf).mark_tick(color=theme.INK, thickness=2, size=18).encode(y="run:N", x="avg_net:Q")
                zero = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(color=theme.INK_MUTED, strokeWidth=1.5).encode(x="x:Q")
                st.altair_chart((bars + ticks + zero).properties(height=280, title="Net saving @τ (bar) & curve avg (tick) vs human = 0%"), width="stretch")
            else:
                st.caption("No scored runs selected for net saving comparison.")

    # 4. By source (CUAD vs ExtractBench)
    with c_src:
        with st.container(border=True, height="stretch"):
            src_rows = []
            for entry in selected_entries:
                rid = entry["run_id"]
                by_src = (bundles[rid].get("score") or {}).get("by_source") or (entry.get("index_row") or {}).get("by_source") or {}
                for src_name, svals in by_src.items():
                    if isinstance(svals, dict):
                        src_rows.append({
                            "run": entry["name"],
                            "source": src_name,
                            "precision": svals.get("precision"),
                            "coverage": svals.get("coverage"),
                        })
            if src_rows:
                sdf = pd.DataFrame(src_rows).dropna(subset=["precision"])
                if not sdf.empty:
                    ch_s = (
                        alt.Chart(sdf)
                        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                        .encode(
                            x=alt.X("source:N", title="Dataset source"),
                            y=alt.Y("precision:Q", title="Precision", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%")),
                            xOffset="run:N",
                            color="run:N",
                            tooltip=["run:N", "source:N", alt.Tooltip("precision:Q", format=".1%"), alt.Tooltip("coverage:Q", format=".1%")],
                        )
                        .properties(height=280, title="Precision by dataset source")
                    )
                    st.altair_chart(ch_s, width="stretch")
                else:
                    st.caption("No per-source precision data available.")
            else:
                st.caption("No per-source breakdown available.")

    # 5. Registry comparison table + maintenance actions
    st.divider()
    h1, h2 = st.columns([2.5, 1.5], vertical_alignment="center")
    h1.subheader("All runs in registry")
    with h2:
        b1, b2 = st.columns(2, gap="small")
        with b1:
            action_button.generate_button("rebuild_index", {}, key="ov_rebuild_idx", width="stretch")
        with b2:
            action_button.generate_button("compare_plots", {}, key="ov_comp_plots", width="stretch")

    t1, t2 = st.columns(2)
    show_legacy = t1.toggle("Show legacy runs", value=True, key="ov_show_legacy")
    only_complete = t2.toggle("Only complete & scored", value=False, key="ov_only_complete")
    idx_rows = cache.get_index()
    filtered_idx = []
    for r in idx_rows:
        tags = r.get("tags") or []
        if not show_legacy and "legacy" in tags:
            continue
        if only_complete and (r.get("status") != "complete" or r.get("precision") is None):
            continue
        filtered_idx.append({
            "Run ID": r.get("run_id"),
            "Name": r.get("name"),
            "Split": r.get("split"),
            "Status": r.get("status"),
            "Docs": r.get("n_docs"),
            "Fields": r.get("n_fields"),
            "Precision": r.get("precision"),
            "Coverage": r.get("coverage"),
            "Net @E100": r.get("net_saving_pct_e100"),
            "Tags": tags,
        })
    if filtered_idx:
        st.dataframe(
            pd.DataFrame(filtered_idx),
            width="stretch",
            hide_index=True,
            column_config={
                "Precision": st.column_config.NumberColumn("Precision", format="%.3f"),
                "Coverage": st.column_config.ProgressColumn("Coverage", min_value=0.0, max_value=1.0, format="%.1%%"),
                "Net @E100": st.column_config.NumberColumn("Net @E100", format="%.3f"),
                "Tags": st.column_config.ListColumn("Tags"),
            },
        )


def render_methods_tab(
    selected_entries: list[dict[str, Any]],
    bundles: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    tau: float,
    error_cost: float,
) -> None:
    """Render Methods tab: UQ method leaderboard, frontier, and field-level UQ signal quality."""
    st.subheader("UQ method leaderboard")
    run_rows = []
    for entry in selected_entries:
        rid = entry["run_id"]
        run_rows.append({**profiles[rid], **summaries[rid], "run_id": rid, "name": entry["name"]})

    grouped = analytics_core.group_runs_by_method(run_rows)
    if grouped:
        st.dataframe(
            pd.DataFrame(grouped),
            width="stretch",
            hide_index=True,
            column_config={
                "mean_precision": st.column_config.NumberColumn("Mean prec", format="%.3f"),
                "mean_coverage": st.column_config.NumberColumn("Mean cov", format="%.3f"),
                "mean_net": st.column_config.NumberColumn("Mean net @E", format="%.3f"),
                "mean_avg_net": st.column_config.NumberColumn("Mean curve avg net", format="%.3f"),
            },
        )

    # Precision-coverage frontier per method (best run per method)
    best_by_method: dict[str, dict[str, Any]] = {}
    for entry in selected_entries:
        rid = entry["run_id"]
        m_key = f"{profiles[rid]['uq_method']} (K={profiles[rid]['samples']})"
        cur_net = summaries[rid]["net_at_tau"]
        prev = best_by_method.get(m_key)
        if prev is None or (cur_net is not None and (prev["net"] is None or cur_net > prev["net"])):
            best_by_method[m_key] = {"entry": entry, "net": cur_net, "curve": (bundles[rid].get("score") or {}).get("curve") or []}

    pc_rows = []
    for m_key, item in best_by_method.items():
        for pt in item["curve"]:
            if int(pt.get("accepted") or 0) > 0:
                pc_rows.append({
                    "method": m_key,
                    "coverage": pt.get("coverage"),
                    "precision": pt.get("precision"),
                    "threshold": pt.get("threshold"),
                })
    if pc_rows:
        pc_df = pd.DataFrame(pc_rows)
        ch = (
            alt.Chart(pc_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("coverage:Q", title="Coverage", axis=alt.Axis(format=".0%")),
                y=alt.Y("precision:Q", title="Precision", scale=alt.Scale(zero=False), axis=alt.Axis(format=".0%")),
                color="method:N",
                tooltip=["method:N", alt.Tooltip("threshold:Q", format=".2f"), alt.Tooltip("precision:Q", format=".1%"), alt.Tooltip("coverage:Q", format=".1%")],
            )
            .properties(height=300, title="Precision–coverage frontier by UQ method")
        )
        tau_rule = alt.Chart(pd.DataFrame({"y": [tau]})).mark_rule(color=theme.BRAND, strokeDash=[5, 4]).encode(y="y:Q")
        be_rule = alt.Chart(pd.DataFrame({"y": [analytics_core.break_even_precision(error_cost)]})).mark_rule(color=theme.INK_MUTED, strokeDash=[2, 2]).encode(y="y:Q")
        st.altair_chart(ch + tau_rule + be_rule, width="stretch")

    # UQ Signal quality (needs fields.jsonl)
    st.divider()
    st.subheader("UQ signal quality (field-level)")
    entry_map = {e["run_id"]: e for e in selected_entries}
    primary_rid = st.selectbox(
        "Inspect UQ signals for run",
        [e["run_id"] for e in selected_entries],
        format_func=lambda r: entry_map[r]["name"],
        key="methods_primary_run",
    )
    fields = bundles[primary_rid].get("fields") or []
    if not fields:
        ui.empty_state(
            ":material/table_chart:",
            "No field table yet",
            "fields.jsonl powers agreement buckets, entropy histograms, and grounding checks.",
            action=lambda: action_button.generate_button(
                "field_table",
                {"run_id": primary_rid, "run_dir": bundles[primary_rid].get("run_dir")},
                type="primary",
                key=f"m_ft_{primary_rid}",
                width="stretch",
            ),
        )
        return

    sig = analytics_core.compute_uq_signal_stats(fields)
    if sig["entropy_ratio"] is not None:
        st.info(f"Wrong predictions have **{sig['entropy_ratio']}x** higher mean normalized entropy than correct ones.")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        ag_rows = []
        for bucket, vals in sig["agreement_buckets"].items():
            for out_k in ("correct", "wrong", "other"):
                if vals[out_k]:
                    ag_rows.append({"bucket": bucket, "outcome": out_k, "count": vals[out_k]})
        if ag_rows:
            ch_ag = (
                alt.Chart(pd.DataFrame(ag_rows))
                .mark_bar()
                .encode(
                    x=alt.X("bucket:N", title="Sample agreement"),
                    y=alt.Y("count:Q", title="Fields"),
                    color=alt.Color("outcome:N", scale=alt.Scale(domain=["correct", "wrong", "other"], range=[theme.SUCCESS, theme.DANGER, theme.NEUTRAL])),
                    tooltip=["bucket:N", "outcome:N", "count:Q"],
                )
                .properties(height=260, title="Does sample agreement predict correctness?")
            )
            st.altair_chart(ch_ag, width="stretch")
        else:
            st.caption("No `agreement` values in `fields.jsonl` (single-sample run).")

    with c2:
        ent_rows = [{"entropy": x, "outcome": "correct"} for x in sig["entropy_correct"]] + [
            {"entropy": x, "outcome": "wrong"} for x in sig["entropy_wrong"]
        ]
        if ent_rows:
            ch_ent = (
                alt.Chart(pd.DataFrame(ent_rows))
                .mark_bar(opacity=0.65)
                .encode(
                    x=alt.X("entropy:Q", bin=alt.Bin(maxbins=20), title="Normalized entropy"),
                    y=alt.Y("count():Q", stack=None, title="Fields"),
                    color=alt.Color("outcome:N", scale=alt.Scale(domain=["correct", "wrong"], range=[theme.SUCCESS, theme.DANGER])),
                )
                .properties(height=260, title="Normalized entropy distribution (correct vs wrong)")
            )
            st.altair_chart(ch_ent, width="stretch")
        else:
            st.caption("No `entropy_norm` values in `fields.jsonl`.")


def render_curves_tab(
    selected_entries: list[dict[str, Any]],
    bundles: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    tau: float,
    error_cost: float,
) -> None:
    """Render Curves tab: Precision vs Coverage, Net Saving vs Threshold (with curve avg lines), Targets."""
    curve_rows = []
    avg_lines = []
    for entry in selected_entries:
        rid = entry["run_id"]
        label = f"{entry['name']} (session)" if entry["is_session"] else entry["name"]
        curve = (bundles[rid].get("score") or {}).get("curve") or []
        sm = summaries[rid]
        if sm["avg_net_curve"] is not None:
            avg_lines.append({"run": label, "avg_net": float(sm["avg_net_curve"])})
        for pt in curve:
            net = analytics_core.curve_net_saving(pt, error_cost=error_cost)
            curve_rows.append({
                "run": label,
                "threshold": float(pt.get("threshold") or 0.0),
                "precision": pt.get("precision"),
                "coverage": pt.get("coverage"),
                "accepted": int(pt.get("accepted") or 0),
                "errors": int(pt.get("wrong") or 0) + int(pt.get("hallucinated") or 0),
                "net_saving": net,
            })

    if not curve_rows:
        st.info("No threshold curve points found in the selected runs.")
        return

    cdf = pd.DataFrame(curve_rows)
    sel = alt.selection_point(fields=["run"], bind="legend")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        pc_df = cdf[cdf["accepted"] > 0].dropna(subset=["precision", "coverage"])
        if not pc_df.empty:
            ch_pc = (
                alt.Chart(pc_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("coverage:Q", title="Coverage", axis=alt.Axis(format=".0%")),
                    y=alt.Y("precision:Q", title="Precision", scale=alt.Scale(zero=False), axis=alt.Axis(format=".0%")),
                    color="run:N",
                    opacity=alt.condition(sel, alt.value(1.0), alt.value(0.2)),
                    tooltip=["run:N", alt.Tooltip("threshold:Q", format=".2f"), alt.Tooltip("precision:Q", format=".1%"), alt.Tooltip("coverage:Q", format=".1%"), "accepted:Q", "errors:Q"],
                )
                .add_params(sel)
                .properties(height=320, title="Precision vs coverage")
            )
            tau_r = alt.Chart(pd.DataFrame({"y": [tau]})).mark_rule(color=theme.BRAND, strokeDash=[5, 4]).encode(y="y:Q")
            be_r = alt.Chart(pd.DataFrame({"y": [analytics_core.break_even_precision(error_cost)]})).mark_rule(color=theme.INK_MUTED, strokeDash=[2, 2]).encode(y="y:Q")
            st.altair_chart(ch_pc + tau_r + be_r, width="stretch")

    with c2:
        ch_ns = (
            alt.Chart(cdf)
            .mark_line(point=True)
            .encode(
                x=alt.X("threshold:Q", title="Confidence threshold τ"),
                y=alt.Y("net_saving:Q", title=f"Net saving @E={int(error_cost)}", axis=alt.Axis(format=".0%")),
                color="run:N",
                opacity=alt.condition(sel, alt.value(1.0), alt.value(0.2)),
                tooltip=["run:N", alt.Tooltip("threshold:Q", format=".2f"), alt.Tooltip("net_saving:Q", format=".1%"), "accepted:Q", "errors:Q"],
            )
            .add_params(sel)
            .properties(height=320, title=f"Net saving vs threshold (E={int(error_cost)}) · dashed = curve avg")
        )
        zero_line = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=theme.INK_MUTED, strokeWidth=1.8).encode(y="y:Q")
        tau_vline = alt.Chart(pd.DataFrame({"x": [tau]})).mark_rule(color=theme.BRAND, strokeDash=[5, 4]).encode(x="x:Q")
        layers = ch_ns + zero_line + tau_vline
        if avg_lines:
            avg_rule = (
                alt.Chart(pd.DataFrame(avg_lines))
                .mark_rule(strokeDash=[4, 4], opacity=0.75)
                .encode(y="avg_net:Q", color="run:N", tooltip=["run:N", alt.Tooltip("avg_net:Q", format=".1%", title="Curve avg")])
            )
            layers = layers + avg_rule
        st.altair_chart(layers, width="stretch")


def render_diagnostics_tab(
    selected_entries: list[dict[str, Any]],
    bundles: dict[str, dict[str, Any]],
    tau: float,
) -> None:
    """Render Field diagnostics tab: scope filter, outcomes, reliability, route/kind, heatmap, missed/errors."""
    entry_map = {e["run_id"]: e for e in selected_entries}
    primary_rid = st.selectbox(
        "Primary run for field diagnostics",
        [e["run_id"] for e in selected_entries],
        format_func=lambda r: entry_map[r]["name"],
        key="diag_primary_run",
    )
    bundle = bundles[primary_rid]
    all_fields = bundle.get("fields") or []
    if not all_fields:
        ui.empty_state(
            ":material/table_chart:",
            "No field table yet",
            "`fields.jsonl` powers reliability, route/kind bars, heatmap, and error tables.",
            action=lambda: action_button.generate_button(
                "field_table",
                {"run_id": primary_rid, "run_dir": bundle.get("run_dir")},
                type="primary",
                key=f"diag_ft_{primary_rid}",
                width="stretch",
            ),
        )
        return

    counts = {m: len(data.filter_field_table(all_fields, m, tau)) for m in data.DECISION_FILTERS}
    scope = filters.decision_filter("diag_scope_filter", counts=counts, default="All")
    fields = data.filter_field_table(all_fields, scope, tau)
    st.caption(f"Showing **{len(fields)}** / {len(all_fields)} fields from `fields.jsonl` at τ = {tau:.2f}.")

    oc = analytics_core.compute_outcome_counts(fields)
    bins = data.compute_reliability_bins(fields)
    ece = analytics_core.compute_ece(bins)
    ui.kpi_row([
        {"label": "Correct", "value": oc["correct"]},
        {"label": "Wrong", "value": oc["wrong"]},
        {"label": "Hallucinated", "value": oc["hallucinated"]},
        {"label": "Missed", "value": oc["missed"]},
        {"label": "ECE", "value": f"{ece:.3f}" if ece is not None else "—"},
    ])

    c_rel, c_hist = st.columns(2, gap="medium")
    with c_rel:
        if bins:
            bdf = pd.DataFrame(bins)
            line = alt.Chart(bdf).mark_line(point=True, color=theme.BRAND).encode(
                x=alt.X("mean_conf:Q", title="Mean confidence", scale=alt.Scale(domain=[0, 1])),
                y=alt.Y("precision:Q", title="Empirical precision", scale=alt.Scale(domain=[0, 1])),
                tooltip=["bin:N", "count:Q", alt.Tooltip("mean_conf:Q", format=".3f"), alt.Tooltip("precision:Q", format=".3f")],
            )
            diag_ref = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(strokeDash=[4, 4], color=theme.INK_SUBTLE).encode(x="x:Q", y="y:Q")
            st.altair_chart((diag_ref + line).properties(height=280, title="Reliability diagram"), width="stretch")

    with c_hist:
        conf_rows = [
            {"conf": float(r["conf_out"]), "outcome": str(r.get("outcome") or "unknown")}
            for r in fields
            if r.get("pred_present") and r.get("conf_out") is not None
        ]
        if conf_rows:
            ch_h = (
                alt.Chart(pd.DataFrame(conf_rows))
                .mark_bar()
                .encode(
                    x=alt.X("conf:Q", bin=alt.Bin(maxbins=20), title="Output confidence"),
                    y=alt.Y("count():Q", title="Fields"),
                    color=alt.Color(
                        "outcome:N",
                        scale=alt.Scale(domain=list(theme.OUTCOME_COLORS.keys()), range=list(theme.OUTCOME_COLORS.values())),
                    ),
                )
                .properties(height=280, title="Confidence histogram by outcome")
            )
            st.altair_chart(ch_h, width="stretch")

    # Route & kind bars
    rt_stats, kd_stats = data.compute_route_kind_stats(fields, threshold=tau)
    c_rt, c_kd = st.columns(2, gap="medium")
    with c_rt:
        if rt_stats:
            rdf = pd.DataFrame(rt_stats)
            rdf["to_human"] = rdf["n_fields"] - rdf["booked"]
            ch_r = (
                alt.Chart(rdf.melt(id_vars=["route", "n_fields"], value_vars=["booked", "to_human"], var_name="bucket", value_name="count"))
                .mark_bar()
                .encode(
                    x=alt.X("route:N", title="Route"),
                    y=alt.Y("count:Q", title="Fields"),
                    color=alt.Color("bucket:N", scale=alt.Scale(domain=["booked", "to_human"], range=[theme.SUCCESS, theme.WARNING])),
                    tooltip=["route:N", "bucket:N", "count:Q", "n_fields:Q"],
                )
                .properties(height=260, title="Booked vs To Human by route")
            )
            st.altair_chart(ch_r, width="stretch")
    with c_kd:
        if kd_stats:
            kdf = pd.DataFrame(kd_stats)
            kdf["to_human"] = kdf["n_fields"] - kdf["booked"]
            ch_k = (
                alt.Chart(kdf.melt(id_vars=["kind", "n_fields"], value_vars=["booked", "to_human"], var_name="bucket", value_name="count"))
                .mark_bar()
                .encode(
                    x=alt.X("kind:N", title="Field kind"),
                    y=alt.Y("count:Q", title="Fields"),
                    color=alt.Color("bucket:N", scale=alt.Scale(domain=["booked", "to_human"], range=[theme.SUCCESS, theme.WARNING])),
                    tooltip=["kind:N", "bucket:N", "count:Q", "n_fields:Q"],
                )
                .properties(height=260, title="Booked vs To Human by field kind")
            )
            st.altair_chart(ch_k, width="stretch")

    # Family x Field heatmap
    ff_stats = data.compute_family_field_stats(fields, threshold=tau)
    if ff_stats:
        st.subheader("Family × Field heatmap")
        f1, f2 = st.columns([2, 1])
        search_q = f1.text_input("Filter fields", placeholder="Type field name…", key="hm_search").strip().lower()
        metric_opt = f2.selectbox("Metric", ["precision", "booked", "n_total"], key="hm_metric")
        ff_df = pd.DataFrame(ff_stats)
        if search_q:
            ff_df = ff_df[ff_df["field"].str.lower().str.contains(search_q, na=False)]
        top_fields = ff_df.groupby("field")["n_total"].sum().nlargest(35).index.tolist()
        ff_df = ff_df[ff_df["field"].isin(top_fields)]
        if not ff_df.empty:
            hm_h = max(260, min(600, 22 * len(top_fields)))
            hm = (
                alt.Chart(ff_df)
                .mark_rect()
                .encode(
                    x=alt.X("family:N", title="Document family"),
                    y=alt.Y("field:N", title="Field"),
                    color=alt.Color(f"{metric_opt}:Q", scale=alt.Scale(scheme="oranges" if metric_opt != "precision" else "redyellowgreen")),
                    tooltip=["family:N", "field:N", "n_total:Q", "booked:Q", "correct:Q", alt.Tooltip("precision:Q", format=".3f")],
                )
                .properties(height=hm_h)
            )
            st.altair_chart(hm, width="stretch")

    # Top missed savings & top errors
    t_left, t_right = st.columns(2, gap="medium")
    with t_left:
        st.subheader("Top missed savings")
        missed = analytics_core.compute_top_missed_savings(all_fields, tau)
        if missed:
            st.dataframe(pd.DataFrame(missed), width="stretch", hide_index=True)
        else:
            st.caption("No missed savings at current τ.")
    with t_right:
        st.subheader("Top booked errors")
        errs = analytics_core.compute_top_errors(all_fields, tau)
        if errs:
            st.dataframe(pd.DataFrame(errs), width="stretch", hide_index=True)
            err_docs = [e["doc_id"] for e in errs if e.get("doc_id")]
            if err_docs and st.button("Open first error in Review", icon=":material/fact_check:"):
                state.set_active_run(primary_rid, err_docs[0])
                nav.switch_to("review")
        else:
            st.caption("Zero booked errors at current τ.")


def render_compare_tab(
    selected_entries: list[dict[str, Any]],
    bundles: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    error_cost: float,
) -> None:
    """Render Compare Two Runs tab: KPI diff + field-level transitions + diff.md generator."""
    if len(selected_entries) < 2:
        st.info("Select at least 2 runs above to compare them side-by-side.")
        return

    entry_map = {e["run_id"]: e for e in selected_entries}
    ids = [e["run_id"] for e in selected_entries]
    c1, c2 = st.columns(2, gap="medium")
    run_a = c1.selectbox("Run A (baseline)", ids, index=0, format_func=lambda r: entry_map[r]["name"], key="cmp_a")
    run_b = c2.selectbox("Run B (candidate)", ids, index=1, format_func=lambda r: entry_map[r]["name"], key="cmp_b")

    sa, sb = summaries[run_a], summaries[run_b]
    dp = (sb["precision_at_tau"] - sa["precision_at_tau"]) if (sb["precision_at_tau"] is not None and sa["precision_at_tau"] is not None) else None
    dc = (sb["coverage_at_tau"] - sa["coverage_at_tau"]) if (sb["coverage_at_tau"] is not None and sa["coverage_at_tau"] is not None) else None
    dn = (sb["net_at_tau"] - sa["net_at_tau"]) if (sb["net_at_tau"] is not None and sa["net_at_tau"] is not None) else None

    ui.kpi_row([
        {"label": "Precision (B)", "value": theme.fmt_pct(sb["precision_at_tau"], 2), "delta": f"{dp * 100:+.1f} pp vs A" if dp is not None else None},
        {"label": "Coverage (B)", "value": theme.fmt_pct(sb["coverage_at_tau"], 1), "delta": f"{dc * 100:+.1f} pp vs A" if dc is not None else None},
        {"label": f"Net @E={int(error_cost)} (B)", "value": theme.fmt_signed_pct(sb["net_at_tau"]), "delta": f"{dn * 100:+.1f} pp vs A" if dn is not None else None},
        {"label": "Errors (B vs A)", "value": sb["errors_at_tau"], "delta": f"{sb['errors_at_tau'] - sa['errors_at_tau']:+d} vs A", "delta_color": "inverse"},
    ])

    fa = bundles[run_a].get("fields") or []
    fb = bundles[run_b].get("fields") or []
    if fa and fb:
        diff = eval_report.diff_field_tables(fa, fb, name_a=entry_map[run_a]["name"], name_b=entry_map[run_b]["name"])
        counts = diff.get("counts") or {}
        st.caption(
            f"Field transitions (A → B): **{counts.get('improved', 0)}** improved · "
            f"**{counts.get('regressed', 0)}** regressed · "
            f"**{counts.get('unchanged', 0)}** unchanged"
        )
        if not entry_map[run_a]["is_session"] and not entry_map[run_b]["is_session"]:
            action_button.generate_button("diff", {"run_a": run_a, "run_b": run_b}, key=f"cmp_diff_{run_a}_{run_b}")
    else:
        st.info("Both runs need `fields.jsonl` for field-level diffing.")
