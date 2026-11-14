"""Home showcase page (WP4): project overview, live KPIs, dynamic pipeline diagram, models & routes."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import analytics_core, cache, nav, pipeline_info, state, theme
from dashboard.components import mermaid, ui

_UQ_EXPLAINERS: list[tuple[str, str]] = [
    ("k1_grounded", "Single sample (K=1); books only when evidence is grounded in text/PDF."),
    ("k_agreement_only", "Multi-sample (K>=2); confidence equals modal answer agreement across samples."),
    ("k_agreement_conf", "Multi-sample (K>=2); combines modal agreement with mean model confidence."),
    ("k_entropy", "Probly discrete entropy across K>=2 samples; penalizes spread across distinct values."),
    ("selector", "Trained calibrated selector / whitelist combining UQ, grounding, and field priors."),
]


def _pick_default_showcase_run(index_rows: list[dict]) -> str | None:
    complete = [
        r for r in index_rows
        if r.get("status") == "complete" and r.get("net_saving_pct_e100") is not None
    ]
    if complete:
        best = max(complete, key=lambda r: float(r.get("net_saving_pct_e100") or -999.0))
        return best.get("run_id")
    return index_rows[0].get("run_id") if index_rows else None


def render() -> None:
    """Render the Home showcase page."""
    def _hero_actions() -> None:
        c1, c2 = st.columns(2, gap="small")
        with c1:
            if st.button("Start a run", icon=":material/play_circle:", type="primary", width="stretch"):
                nav.switch_to("run")
        with c2:
            if st.button("Open analytics", icon=":material/insights:", type="secondary", width="stretch"):
                nav.switch_to("analytics")

    ui.page_header(
        'Teach a machine to say "I don\'t know"',
        "We book only the fields we can prove and route everything else to a human.",
        icon=":material/verified_user:",
        right=_hero_actions,
    )

    # 1. Problem-in-one-line strip
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.5], gap="medium")
    with c1:
        ui.kpi_card("Human review", "1", foot="Baseline cost per field")
    with c2:
        ui.kpi_card("Booked correct", "0", foot="Automated saving = +1")
    with c3:
        ui.kpi_card("Booked wrong", "100", foot="Error penalty (E = 100)")
    with c4:
        with st.container(border=True, height="stretch"):
            st.markdown("**Break-even rule**")
            st.markdown("Automation pays only above **99.0% precision** on booked fields at E=100.")
            st.caption("Formula: `net = (accepted - E * errors) / n_fields` vs human-only = 0%.")

    tau = state.threshold()
    dec_path = state.decision_path()
    desc = cache.get_pipeline_description(dec_path)

    if desc.warnings:
        for w in desc.warnings:
            st.warning(w, icon=":material/warning:")

    # 2. Live KPI row from showcase run
    index_rows = cache.get_index()
    reviews = cache.get_reviews()

    with ui.safe_section("Showcase KPIs"):
        if not index_rows:
            ui.empty_state(
                ":material/inbox:",
                "No runs in registry yet",
                "Run an extraction on the Run page or import legacy runs to see live metrics.",
                action=lambda: nav.switch_to("run") if st.button("Start first run", type="primary") else None,
            )
        else:
            default_rid = _pick_default_showcase_run(index_rows)
            run_ids = [r["run_id"] for r in index_rows if r.get("run_id")]
            row_map = {r["run_id"]: r for r in index_rows if r.get("run_id")}

            def _pick_showcase() -> None:
                pass

            h1, h2 = st.columns([2.5, 1.5], gap="medium", vertical_alignment="center")
            with h1:
                st.subheader("Live benchmark KPIs")
                st.caption(f"Evaluated at declared threshold τ = {tau:.2f} · E = 100")
            with h2:
                selected_rid = st.selectbox(
                    "Showcase run",
                    run_ids,
                    index=run_ids.index(default_rid) if default_rid in run_ids else 0,
                    format_func=lambda rid: f"{row_map[rid].get('name') or rid} · {row_map[rid].get('split') or '—'}",
                    label_visibility="collapsed",
                    key="home_showcase_run",
                )

            bundle = cache.get_run_bundle(selected_rid, include_samples=False)
            summary = analytics_core.summarize_curve(bundle.get("score") or {}, tau, error_cost=100.0)
            srow = row_map.get(selected_rid, {})
            n_fields = int(srow.get("n_fields") or 0)
            prec = summary.get("precision_at_tau")
            cov = summary.get("coverage_at_tau")
            net = summary.get("net_at_tau")
            errs = summary.get("errors_at_tau") or 0
            acc = summary.get("accepted_at_tau") or 0

            k1, k2, k3, k4, k5 = st.columns(5, gap="medium")
            with k1:
                ui.kpi_card(
                    "Fields automated",
                    theme.fmt_pct(cov),
                    foot=f"{theme.fmt_int(acc)} / {theme.fmt_int(n_fields)} fields",
                )
            with k2:
                delta_p = f"{(prec - tau) * 100:+.1f} pp vs τ" if prec is not None else None
                ui.kpi_card(
                    "Precision (booked)",
                    theme.fmt_pct(prec, 2),
                    delta=delta_p,
                    foot=f"Target τ = {tau:.2f}",
                )
            with k3:
                ui.kpi_card(
                    "Net saving @E=100",
                    theme.fmt_signed_pct(net),
                    delta=f"{theme.fmt_signed_pct(net)} vs human" if net is not None else None,
                    foot="Human baseline = 0.0%",
                    chart_data=summary.get("sparkline") or None,
                )
            with k4:
                ui.kpi_card(
                    "Errors booked",
                    theme.fmt_int(errs),
                    foot="Wrong + hallucinated",
                )
            with k5:
                with st.container(border=True, height="stretch"):
                    st.caption("**VERDICT**")
                    ui.verdict_chip(summary.get("verdict") or "no_gold")
                    st.caption(f"Split: {srow.get('split') or '—'} · {srow.get('n_docs') or 0} docs")

            # Secondary stats strip
            complete_runs = [r for r in index_rows if r.get("status") == "complete"]
            total_docs = sum(int(r.get("n_docs") or 0) for r in complete_runs)
            total_fields = sum(int(r.get("n_fields") or 0) for r in complete_runs)
            st.caption(
                f"Registry: **{len(index_rows)}** runs ({len(complete_runs)} complete) · "
                f"**{theme.fmt_int(total_docs)}** docs processed · "
                f"**{theme.fmt_int(total_fields)}** fields scored · "
                f"**{theme.fmt_int(len(reviews))}** human reviews logged"
            )

    # 3. Dynamic Mermaid pipeline diagram
    with ui.safe_section("How it works"):
        ui.section(
            "How the pipeline works",
            "Updates dynamically when you change the Decision file or Declared threshold τ in the sidebar.",
        )
        route_counts: dict[str, int] | None = None
        if index_rows and "home_showcase_run" in st.session_state:
            b_show = cache.get_run_bundle(st.session_state["home_showcase_run"], include_samples=False)
            ru = (b_show.get("manifest") or {}).get("routes_used")
            if isinstance(ru, dict) and ru:
                route_counts = {str(k): int(v) for k, v in ru.items()}

        mmd_src = pipeline_info.build_mermaid(desc, threshold=tau, route_counts=route_counts)
        dot_src = pipeline_info.build_dot(desc, threshold=tau)

        col_diag, col_leg = st.columns([2.2, 1], gap="medium")
        with col_diag:
            with st.container(border=True, height="stretch"):
                mermaid.render_mermaid(mmd_src, height=430, dot_fallback=dot_src)
            with st.expander("Mermaid source (copy for slides)", expanded=False):
                st.code(mmd_src, language="mermaid")
        with col_leg:
            with st.container(border=True, height="stretch"):
                st.markdown("**Active configuration**")
                ui.info_grid(
                    [
                        ("Decision contract", f"v{desc.contract_version}" if desc.contract_version else "Default"),
                        ("Mode", desc.mode),
                        ("UQ method", desc.uq_method or "auto"),
                        ("Samples K", desc.samples or 1),
                        ("Declared τ", f"{tau:.2f}"),
                        ("Abstain all", "ON (disabled)" if desc.abstain_all else "Off"),
                        ("Router τ_q", f"{desc.router_gate.get('tau_q', '—')}"),
                        ("Damaged families", desc.router_gate.get("damaged_families_count", 0)),
                    ],
                    cols=2,
                )
                if desc.method:
                    st.caption(desc.method)

    # 4. Model & route matrix
    with ui.safe_section("Models & routes"):
        st.subheader("Models & routes")
        c_mod, c_rt = st.columns(2, gap="medium")
        with c_mod:
            with st.container(border=True, height="stretch"):
                st.markdown("**Models in use**")
                m_rows = []
                for role, info in desc.models.items():
                    sup = info.get("supports") or {}
                    m_rows.append({
                        "Role": role,
                        "Model": info.get("name") or "—",
                        "Source": info.get("source") or "—",
                        "Family": info.get("family") or "—",
                        "text": bool(sup.get("text")),
                        "pdf": bool(sup.get("pdf_file")),
                        "png": bool(sup.get("png")),
                        "img_url": bool(sup.get("pdf_image_url")),
                        "Max ctx": theme.fmt_int(info.get("max_context_chars")),
                    })
                st.dataframe(pd.DataFrame(m_rows), width="stretch", hide_index=True)

        with c_rt:
            with st.container(border=True, height="stretch"):
                st.markdown("**Routes**")
                r_rows = []
                for r in desc.routes:
                    r_rows.append({
                        "Route": r["route"],
                        "Pipeline": r["pipeline"],
                        "Views": ", ".join(r["views"]),
                        "K": r["samples"],
                        "UQ": r["uq_method"],
                        "Active": bool(r["active"]),
                    })
                st.dataframe(pd.DataFrame(r_rows), width="stretch", hide_index=True)

    # 5. UQ methods explainer
    with ui.safe_section("UQ methods"):
        st.subheader("Uncertainty quantification methods")
        cols = st.columns(len(_UQ_EXPLAINERS), gap="small")
        for col, (name, text) in zip(cols, _UQ_EXPLAINERS):
            is_active = desc.uq_method == name
            with col:
                with st.container(border=True, height="stretch"):
                    ui.badge(name, "brand" if is_active else "neutral")
                    st.caption(text)

    # 6. Recent activity
    with ui.safe_section("Recent activity"):
        st.subheader("Recent runs")
        sess_runs = state.session_runs()
        recent: list[dict] = []
        for rid, b in sess_runs.items():
            r = b.get("index_row") or b.get("run") or {}
            recent.append({
                "run_id": rid,
                "name": r.get("name") or rid,
                "split": r.get("split") or "session",
                "status": "session" if not b.get("saved_to_registry") else "saved",
                "net": r.get("net_saving_pct_e100"),
                "n_docs": r.get("n_docs") or len(b.get("preds") or {}),
            })
        seen_ids = {x["run_id"] for x in recent}
        for r in index_rows:
            if r.get("run_id") and r["run_id"] not in seen_ids:
                recent.append({
                    "run_id": r["run_id"],
                    "name": r.get("name") or r["run_id"],
                    "split": r.get("split") or "—",
                    "status": r.get("status") or "—",
                    "net": r.get("net_saving_pct_e100"),
                    "n_docs": r.get("n_docs") or 0,
                })
            if len(recent) >= 5:
                break

        if not recent:
            st.caption("No recent runs.")
        else:
            for item in recent[:5]:
                with st.container(border=True):
                    r1, r2, r3, r4, r5 = st.columns([2.5, 1, 1, 1, 1], vertical_alignment="center")
                    with r1:
                        st.markdown(f"**{item['name']}**")
                        st.caption(item["run_id"])
                    with r2:
                        ui.badge(item["split"], "neutral")
                    with r3:
                        kind = "info" if item["status"] == "session" else ("success" if item["status"] in ("complete", "saved") else "neutral")
                        ui.badge(item["status"], kind)
                    with r4:
                        st.caption(f"Net@100: **{theme.fmt_signed_pct(item['net'])}** · {item['n_docs']} docs")
                    with r5:
                        if st.button("Open", key=f"home_open_{item['run_id']}", icon=":material/open_in_new:", width="stretch"):
                            state.set_active_run(item["run_id"])
                            nav.switch_to("details")
