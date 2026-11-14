"""Run details page (WP10, formerly 'Latest run'): metadata, score breakdown, artifacts, and generate actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import analytics_core, nav, state, theme
from dashboard.components import action_button, run_picker, ui


def render() -> None:
    """Render the Run Details page."""
    ui.page_header(
        "Run details",
        "Inspect run metadata, model usage, per-condition scores, and downloadable artifacts.",
        icon=":material/receipt_long:",
    )

    run_id, bundle = run_picker.pick_run("details_run_pick", label="Select run", include_samples=False)
    if bundle is None or run_id is None:
        ui.empty_state(
            ":material/receipt_long:",
            "No runs found",
            "Start a run on the Run page or import legacy runs.",
            action=lambda: nav.switch_to("run") if st.button("Start a run", type="primary") else None,
        )
        return

    state.set_active_run(run_id)
    tau = state.threshold()
    run_meta = bundle.get("run") or {}
    manifest = bundle.get("manifest") or {}
    score = bundle.get("score") or {}
    tags = run_meta.get("tags") or []
    is_legacy = not manifest or "legacy" in tags

    # Business headline hero card
    sm = analytics_core.summarize_curve(score, tau, error_cost=100.0)
    with st.container(border=True):
        h1, h2 = st.columns([3, 1], vertical_alignment="center")
        with h1:
            if score:
                st.markdown(
                    f"### **{theme.fmt_pct(sm['coverage_at_tau'], 1)}** of fields need no human · "
                    f"net saving **{theme.fmt_signed_pct(sm['net_at_tau'])}** at E=100 · "
                    f"**{sm['errors_at_tau']}** errors"
                )
            else:
                st.markdown(f"### Run `{run_id}` (unscored)")
            badges: list[tuple[str, str]] = [(run_meta.get("split") or "—", "neutral")]
            if is_legacy:
                badges.append(("legacy import: no manifest", "neutral"))
            if bundle.get("is_session"):
                badges.append(("session", "info"))
            ui.badges_row(badges)
        with h2:
            ui.verdict_chip(sm["verdict"])

    # KPI row
    n_req = manifest.get("n_requested") or run_meta.get("n_requested") or "—"
    n_writ = manifest.get("n_written") or len(bundle.get("preds") or {})
    elapsed = manifest.get("elapsed_seconds")
    t_per_doc = (float(elapsed) / max(1, int(n_writ))) if isinstance(elapsed, (int, float)) and n_writ else None
    reqs = int(manifest.get("requests") or 0)
    hits = int(manifest.get("cache_hits") or 0)
    hit_rate = (hits / (reqs + hits)) if (reqs + hits) > 0 else None

    ui.kpi_row([
        {"label": "Status", "value": run_meta.get("status") or "—"},
        {"label": "Docs written", "value": f"{n_writ} / {n_req}"},
        {"label": "Time / doc", "value": theme.fmt_secs(t_per_doc), "foot": f"Total: {theme.fmt_secs(elapsed)}"},
        {"label": "Failed docs", "value": manifest.get("n_failed") if manifest else "—"},
        {"label": "Cache hit rate", "value": theme.fmt_pct(hit_rate, 0), "foot": f"{hits} hits / {reqs} reqs" if manifest else "No manifest"},
    ])

    # Metadata grid
    with st.container(border=True):
        st.subheader("Metadata & provenance")
        git_info = run_meta.get("git") or {}
        git_str = f"{str(git_info.get('commit') or '—')[:8]}{' (dirty)' if git_info.get('dirty') else ''}" if git_info else "—"
        fp = manifest.get("fingerprint") or {}
        ui.info_grid([
            ("Run ID", run_id, run_id),
            ("Name / Split", f"{run_meta.get('name') or '—'} / {run_meta.get('split') or '—'}"),
            ("Mode", manifest.get("mode") or run_meta.get("mode") or "—"),
            ("Models", ", ".join(manifest.get("models_used") or run_meta.get("models") or []) or "—"),
            ("Routes used", ", ".join(f"{k}:{v}" for k, v in (manifest.get("routes_used") or {}).items()) or "—"),
            ("Prompt versions", ", ".join(manifest.get("prompt_versions") or []) or "—"),
            ("Pipeline SHA", theme.short_hash(fp.get("pipeline_sha256") or run_meta.get("pipeline_sha256")), fp.get("pipeline_sha256") or run_meta.get("pipeline_sha256")),
            ("Decision SHA", theme.short_hash(run_meta.get("decision_sha256")), run_meta.get("decision_sha256")),
            ("Git commit", git_str),
            ("Created at", run_meta.get("created_at") or "—"),
            ("Fields contract", run_meta.get("fields_contract_version") or "—"),
            ("Tags", ", ".join(tags) or "—"),
        ], cols=3)

    # Requests & cache hits per model
    req_by_m = manifest.get("requests_by_model") or {}
    hit_by_m = manifest.get("cache_hits_by_model") or {}
    if req_by_m or hit_by_m:
        with st.container(border=True):
            st.subheader("Requests & cache hits by model")
            m_rows = []
            for m in sorted(set(req_by_m) | set(hit_by_m)):
                m_rows.append({"model": m, "kind": "requests", "count": int(req_by_m.get(m) or 0)})
                m_rows.append({"model": m, "kind": "cache_hits", "count": int(hit_by_m.get(m) or 0)})
            ch = (
                alt.Chart(pd.DataFrame(m_rows))
                .mark_bar()
                .encode(
                    y=alt.Y("model:N", title=None),
                    x=alt.X("count:Q", title="Count"),
                    color=alt.Color("kind:N", scale=alt.Scale(domain=["requests", "cache_hits"], range=[theme.BRAND, theme.SUCCESS])),
                    tooltip=["model:N", "kind:N", "count:Q"],
                )
                .properties(height=max(120, 45 * len(set(req_by_m) | set(hit_by_m))))
            )
            st.altair_chart(ch, width="stretch")

    # Score breakdown
    if score:
        c_src, c_cond = st.columns(2, gap="medium")
        with c_src:
            by_src = score.get("by_source") or {}
            if by_src:
                with st.container(border=True):
                    st.markdown("**By source**")
                    rows = [{"Source": k, **(v if isinstance(v, dict) else {})} for k, v in by_src.items()]
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        with c_cond:
            by_cond = score.get("by_condition") or {}
            if by_cond:
                with st.container(border=True):
                    st.markdown("**By condition (perception)**")
                    rows = [{"Condition": k, **(v if isinstance(v, dict) else {})} for k, v in by_cond.items()]
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # Artifacts & Generate actions
    run_dir = Path(bundle["run_dir"])
    with st.container(border=True):
        st.subheader("Artifacts & actions")
        a1, a2, a3 = st.columns(3, gap="small")
        params = {"run_id": run_id, "run_dir": str(run_dir), "threshold": tau}
        with a1:
            action_button.generate_button("field_table", params, key=f"det_ft_{run_id}", width="stretch")
        with a2:
            action_button.generate_button("score_run", params, key=f"det_sc_{run_id}", width="stretch")
        with a3:
            action_button.generate_button("report", params, key=f"det_rep_{run_id}", width="stretch")

        if run_dir.is_dir():
            files = sorted([p for p in run_dir.iterdir() if p.is_file()], key=lambda p: p.name)
            f_rows = [{"File": p.name, "Size": theme.fmt_bytes(p.stat().st_size)} for p in files]
            st.dataframe(pd.DataFrame(f_rows), width="stretch", hide_index=True)

            dl_cols = st.columns(3, gap="small")
            for idx, fname in enumerate(("report.md", "report.json", "preds.jsonl")):
                fpath = run_dir / fname
                if fpath.is_file():
                    dl_cols[idx].download_button(
                        f"Download {fname}",
                        data=fpath.read_bytes(),
                        file_name=f"{run_id}_{fname}",
                        icon=":material/download:",
                        width="stretch",
                    )

            rep_md = run_dir / "report.md"
            if rep_md.is_file():
                with st.expander("Inline report.md", expanded=False):
                    st.markdown(rep_md.read_text(encoding="utf-8", errors="ignore"))

    # Failures / degraded expander
    failed_ids = manifest.get("failed_doc_ids") or []
    abstained_ids = manifest.get("abstained_after_error_doc_ids") or []
    if failed_ids or abstained_ids:
        with st.expander(f"Failures & degraded docs ({len(failed_ids)} failed, {len(abstained_ids)} abstained)", expanded=False):
            if failed_ids:
                st.write("Failed doc IDs:", failed_ids)
            if abstained_ids:
                st.write("Abstained after error doc IDs:", abstained_ids)
