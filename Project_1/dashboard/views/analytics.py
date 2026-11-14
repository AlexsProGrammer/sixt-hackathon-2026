"""Analytics page (WP8): verdicts, averages, UQ method comparison, curves, and field diagnostics."""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import analytics_core, cache, nav, state, theme
from dashboard.components import action_button, run_picker, ui
from dashboard.views import analytics_tabs


def render() -> None:
    """Render the Analytics page."""
    ui.page_header(
        "Analytics",
        "Did it work, which UQ method won, and where are the remaining errors?",
        icon=":material/insights:",
    )

    c_runs, c_e, c_help = st.columns([3.0, 1.1, 0.8], gap="medium", vertical_alignment="bottom")
    with c_runs:
        selected_entries = run_picker.pick_runs("analytics_runs", max_default=3)
    with c_e:
        e_choice = st.segmented_control(
            "Error cost E",
            [20, 100, 500],
            default=100,
            key="analytics_error_cost",
            help="Penalty multiplier for a booked wrong/hallucinated field (human review = 1).",
        )
        error_cost = float(e_choice if e_choice is not None else 100)
    with c_help:
        with st.popover("Success formula"):
            be = analytics_core.break_even_precision(error_cost)
            st.markdown(
                f"**Human-only baseline:** `0.0%` net saving.  \n"
                f"**Net saving:** `(accepted - {int(error_cost)} * errors) / n_fields`  \n"
                f"**Break-even precision (E={int(error_cost)}):** `{theme.fmt_pct(be, 1)}`  \n\n"
                "- **Full success:** `accepted > 0`, `precision >= τ`, and `net_saving > 0` (beats human).  \n"
                "- **Partial:** `net_saving > 0` below `τ`, or `precision >= τ` with `0` net saving.  \n"
                "- **Not yet:** `net_saving < 0`."
            )

    if not selected_entries:
        def _empty_actions() -> None:
            b1, b2 = st.columns(2, gap="small")
            with b1:
                if st.button("Start a run", type="primary", width="stretch"):
                    nav.switch_to("run")
            with b2:
                action_button.generate_button("import_legacy", {}, key="an_empty_import", width="stretch")

        ui.empty_state(
            ":material/insights:",
            "No runs selected or available",
            "Start a new run or import legacy runs into the registry to explore analytics.",
            action=_empty_actions,
        )
        return

    tau = state.threshold()
    bundles: dict[str, dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    profiles: dict[str, dict[str, Any]] = {}

    with st.spinner("Loading run artifacts…"):
        for entry in selected_entries:
            rid = entry["run_id"]
            b = entry.get("bundle") or cache.get_run_bundle(rid, include_samples=False)
            bundles[rid] = b
            summaries[rid] = analytics_core.summarize_curve(b.get("score") or {}, tau, error_cost=error_cost)
            profiles[rid] = analytics_core.infer_run_profile(b)

    t_ov, t_meth, t_curv, t_diag, t_cmp = st.tabs([
        "Overview",
        "Methods",
        "Curves",
        "Field diagnostics",
        "Compare two runs",
    ])

    with t_ov:
        with ui.safe_section("Overview"):
            analytics_tabs.render_overview_tab(selected_entries, bundles, summaries, profiles, tau, error_cost)

    with t_meth:
        with ui.safe_section("Methods"):
            analytics_tabs.render_methods_tab(selected_entries, bundles, summaries, profiles, tau, error_cost)

    with t_curv:
        with ui.safe_section("Curves"):
            analytics_tabs.render_curves_tab(selected_entries, bundles, summaries, tau, error_cost)

    with t_diag:
        with ui.safe_section("Field diagnostics"):
            analytics_tabs.render_diagnostics_tab(selected_entries, bundles, tau)

    with t_cmp:
        with ui.safe_section("Compare two runs"):
            analytics_tabs.render_compare_tab(selected_entries, bundles, summaries, error_cost)
