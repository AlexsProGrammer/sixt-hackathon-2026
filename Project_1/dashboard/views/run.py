"""Run page (WP9): transparent run builder, live run preview, progress KPIs, and result card."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dashboard import analytics_core, cache, data, nav, pipeline_info, runner, state, theme
from dashboard.components import ui
from pipeline import extractor


def _save_upload(uploaded: Any, suffix: str) -> Path:
    up_dir = Path(tempfile.gettempdir()) / "project1_dashboard_uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    dest = up_dir / f"{int(time.time() * 1000)}_{uploaded.name}"
    if not str(dest).endswith(suffix):
        dest = dest.with_suffix(suffix)
    dest.write_bytes(uploaded.getvalue())
    return dest


def _available_datasets() -> list[str]:
    names: list[str] = []
    for name in ("dev", "test_public", "fit", "select", "audit", "audit2", "smoke"):
        try:
            if data.resolve_dataset_path(name).is_file():
                names.append(name)
        except FileNotFoundError:
            pass
    return names


def _dataset_counts_label(ds_name: str) -> str:
    try:
        recs = cache.get_dataset_records(ds_name)
        return f"{ds_name} · {len(recs)} docs"
    except Exception:  # noqa: BLE001
        return ds_name


def render() -> None:
    """Render the Run page."""
    ui.page_header(
        "Run extraction",
        "Configure an extraction + UQ run, preview models and cache state, and inspect live progress.",
        icon=":material/play_circle:",
    )

    datasets = _available_datasets()
    dec_files = state.find_decision_files()
    dec_options = dec_files + [state.NONE_LABEL]
    default_dec = state.decision_path() or state.NONE_LABEL
    if default_dec not in dec_options:
        default_dec = dec_options[0]

    left, right = st.columns([1.4, 1.0], gap="large")
    selected_records: list[dict] = []
    split_label = "session"
    upload_error: str | None = None

    with left:
        # ① Input
        with st.container(border=True):
            st.markdown("**① Input**")
            src_mode = st.segmented_control(
                "Input source",
                ["Random N", "Single doc", "Full split", "Upload"],
                default="Random N",
                key="run_src_mode",
                label_visibility="collapsed",
            ) or "Random N"

            if src_mode == "Upload":
                c_up1, c_up2 = st.columns(2, gap="small")
                pdf_file = c_up1.file_uploader("PDF file", type=["pdf"], key="run_up_pdf")
                schema_file = c_up2.file_uploader("Schema JSON", type=["json"], key="run_up_schema")
                doc_id_up = st.text_input("Document ID", value="upload:doc_1", key="run_up_id")
                split_label = "upload"
                if pdf_file and schema_file:
                    try:
                        schema = json.loads(schema_file.getvalue().decode("utf-8"))
                        if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
                            upload_error = "Schema JSON must be an object with a `properties` dict."
                        else:
                            pdf_path = _save_upload(pdf_file, ".pdf")
                            selected_records = [{
                                "doc_id": doc_id_up.strip() or "upload:doc_1",
                                "source_dataset": "upload",
                                "pdf_path": str(pdf_path),
                                "schema": schema,
                            }]
                    except Exception as exc:  # noqa: BLE001
                        upload_error = f"Invalid schema JSON: {exc}"
                if upload_error:
                    st.error(upload_error)
            elif not datasets:
                st.warning("No datasets found in `data/`.")
            else:
                ds_name = st.selectbox(
                    "Dataset",
                    datasets,
                    format_func=_dataset_counts_label,
                    key="run_ds_name",
                )
                all_recs = cache.get_dataset_records(ds_name)
                split_label = ds_name
                if src_mode == "Random N":
                    st.session_state.setdefault("run_seed", 42)
                    c_n, c_seed, c_shuf = st.columns([1.2, 1.2, 0.8], gap="small", vertical_alignment="bottom")
                    n_docs = int(c_n.number_input("N documents", min_value=1, max_value=max(1, len(all_recs)), value=min(3, len(all_recs)), key="run_n"))
                    seed = int(c_seed.number_input("Seed", min_value=0, max_value=999999, key="run_seed"))
                    if c_shuf.button("Reshuffle", icon=":material/shuffle:", width="stretch"):
                        st.session_state["run_seed"] = seed + 1
                        st.rerun()
                    selected_records = data.sample_stratified_records(all_recs, n_docs, seed=seed)
                elif src_mode == "Single doc":
                    rec_map = {r["doc_id"]: r for r in all_recs if r.get("doc_id")}
                    chosen_doc = st.selectbox(
                        "Document",
                        list(rec_map.keys()),
                        format_func=lambda d: f"{rec_map[d].get('source_dataset', '?')} · {d}",
                        key="run_single_doc",
                    )
                    if chosen_doc:
                        selected_records = [rec_map[chosen_doc]]
                else:
                    selected_records = list(all_recs)
                    if len(selected_records) > 25:
                        st.warning(f"Full split `{ds_name}` has {len(selected_records)} documents.")

        # ② Pipeline
        with st.container(border=True):
            st.markdown("**② Pipeline & UQ**")
            c_dec, c_mode = st.columns([1.8, 1], gap="small")
            dec_choice = c_dec.selectbox(
                "Decision file",
                dec_options,
                index=dec_options.index(default_dec),
                format_func=lambda p: p if p == state.NONE_LABEL else Path(p).name,
                key="run_dec_choice",
            )
            dec_path = None if dec_choice == state.NONE_LABEL else dec_choice
            mode = c_mode.selectbox("Mode", ["auto", "llm", "offline"], index=0, key="run_mode")

            c_k, c_uq, c_samp = st.columns([0.8, 1.4, 1], gap="small")
            samples = int(c_k.number_input("Samples (K)", min_value=1, max_value=5, value=1, key="run_samples"))
            has_sel = False
            if dec_path and Path(dec_path).is_file():
                try:
                    _d = json.loads(Path(dec_path).read_text(encoding="utf-8"))
                    has_sel = bool(_d.get("selector") or _d.get("selector_path"))
                except (OSError, ValueError):
                    has_sel = False

            uq_opts = ["k1_grounded"] if samples == 1 else ["k_entropy", "k_agreement_conf", "k_agreement_only"]
            if has_sel:
                uq_opts.append("selector")
            uq_method = c_uq.selectbox("UQ method", uq_opts, index=0, key="run_uq")
            sampling = c_samp.selectbox("Sampling", list(extractor.SAMPLING_MODES), index=0, key="run_sampling")

            with st.expander("Advanced options", expanded=False):
                a1, a2, a3 = st.columns(3, gap="small")
                temperature = float(a1.number_input("Temperature", 0.0, 2.0, 0.7, 0.1, key="run_temp"))
                chunk_chars = int(a2.number_input("Chunk chars", 5000, 120000, 45000, 5000, key="run_chunk"))
                overlap_chars = int(a3.number_input("Overlap chars", 0, 15000, 3000, 500, key="run_overlap"))
                a4, a5, a6 = st.columns(3, gap="small")
                batch_size = int(a4.number_input("Batch size", 1, 50, 10, 1, key="run_batch"))
                workers = int(a5.number_input("Workers", 1, 8, 1, 1, key="run_workers"))
                on_error = a6.selectbox("On error", ["raise", "abstain"], index=0, key="run_on_error")

        # ③ Threshold & cache
        with st.container(border=True):
            st.markdown("**③ Threshold & cache**")
            t1, t2, t3 = st.columns([1.2, 1, 1.5], gap="small", vertical_alignment="bottom")
            threshold = float(t1.slider("Threshold τ", 0.50, 1.00, state.threshold(), 0.01, key="run_tau"))
            use_cache = t2.toggle(
                "Use reply cache",
                value=True,
                key="run_use_cache",
                help="Cached replies are reused when model, prompt version, temperature, sample index, and messages match.",
            )
            run_name = t3.text_input("Run name", value=f"dash_{split_label}", key="run_name")

        overrides: dict[str, Any] = {
            "mode": mode,
            "samples": samples,
            "uq_method": uq_method,
            "sampling": sampling,
            "temperature": temperature,
            "chunk_chars": chunk_chars,
            "overlap_chars": overlap_chars,
            "batch_size": batch_size,
            "workers": workers,
            "on_error": on_error,
            "no_cache": not use_cache,
        }
        val_errors = runner.validate_overrides(overrides, dec_path)
        for err in val_errors:
            st.error(err, icon=":material/error:")

        start_disabled = bool(val_errors) or not selected_records or bool(upload_error)
        start_clicked = st.button(
            f"Start run ({len(selected_records)} docs)",
            type="primary",
            icon=":material/play_arrow:",
            disabled=start_disabled,
            width="stretch",
        )

    # Right column: Live Run Preview
    with right:
        with st.container(border=True):
            st.subheader("Run preview")
            if not selected_records:
                st.caption("Select input documents on the left to preview routes, models, and cache status.")
            else:
                src_counts: dict[str, int] = {}
                for r in selected_records:
                    s = str(r.get("source_dataset") or "unknown")
                    src_counts[s] = src_counts.get(s, 0) + 1
                ui.badges_row(
                    [(f"{len(selected_records)} docs", "brand")]
                    + [(f"{k}: {v}", "neutral") for k, v in sorted(src_counts.items())]
                )

                desc = pipeline_info.describe(dec_path, overrides=overrides)
                if len(selected_records) <= 50:
                    rcounts = cache.get_route_counts(selected_records)
                    st.caption("**Estimated routes:** " + ", ".join(f"`{k}` ({v})" for k, v in sorted(rcounts.items())))
                else:
                    st.caption("**Estimated routes:** computed at run time (>50 docs)")

                # Models per route
                route_rows = []
                for r in desc.routes:
                    if not r["active"] and not dec_path:
                        continue
                    route_rows.append({
                        "Route": r["route"],
                        "Pipeline": r["pipeline"],
                        "Views": ", ".join(r["views"]),
                        "Active": "Yes" if r["active"] else "No",
                    })
                if route_rows:
                    st.dataframe(pd.DataFrame(route_rows), width="stretch", hide_index=True)

                # Models in use
                m_chips = " ".join(
                    f"**{role}:** {ui.model_chip_html(info.get('name'))}"
                    for role, info in desc.models.items()
                    if info.get("name")
                )
                if m_chips:
                    st.markdown(m_chips, unsafe_allow_html=True)

                # Expected LLM calls heuristic
                est_calls = len(selected_records) * max(1, samples) * 2
                st.caption(f"**UQ:** `{uq_method}` · **K={samples}** · ≈ {est_calls}–{est_calls * 2} LLM calls (estimate)")

                # Cache heuristic
                doc_map = cache.get_doc_to_runs_map()
                seen_docs = [r["doc_id"] for r in selected_records if r.get("doc_id") in doc_map]
                cstats = cache.get_cache_stats()
                st.caption(
                    f"**Reply cache:** {theme.fmt_int(cstats['total_files'])} files ({theme.fmt_bytes(cstats['total_bytes'])}) · "
                    f"Previously processed: **{len(seen_docs)}/{len(selected_records)}** docs"
                )

                # Environment & warnings
                extractor.load_env(data.ROOT / ".env")
                env_ok = all((os.environ.get(k) or "").strip() for k in extractor.LLM_VARS)
                st.caption(f"**LLM env:** {'✓ configured' if env_ok else '✕ missing'} · `EXTRACT_DATA_DIR={os.environ.get('EXTRACT_DATA_DIR') or 'default'}`")

                for w in desc.warnings:
                    st.warning(w, icon=":material/warning:")
                if src_mode == "Upload":
                    st.info("Upload mode has no gold labels — scoring is skipped.", icon=":material/info:")

    # Execute run if started
    if start_clicked:
        _execute_and_display_run(selected_records, run_name, split_label, dec_path, overrides, threshold)

    # Session runs list
    sess = state.session_runs()
    if sess:
        st.divider()
        st.subheader("Session runs")
        for rid, b in reversed(list(sess.items())):
            idx_row = b.get("index_row") or b.get("run") or {}
            saved = bool(b.get("saved_to_registry"))
            with st.container(border=True):
                c1, c2, c3, c4, c5, c6 = st.columns([2.2, 1.1, 1.0, 0.9, 0.9, 0.8], vertical_alignment="center")
                with c1:
                    st.markdown(f"**{idx_row.get('name') or rid}**")
                    st.caption(f"{rid} · {len(b.get('preds') or {})} docs")
                with c2:
                    ui.badge("saved" if saved else "unsaved", "success" if saved else "warning")
                with c3:
                    st.caption(f"Net@100: **{theme.fmt_signed_pct(idx_row.get('net_saving_pct_e100'))}**")
                with c4:
                    if st.button("Review", key=f"srev_{rid}", icon=":material/fact_check:", width="stretch", on_click=state.set_active_run, args=(rid,)):
                        nav.switch_to("review")
                with c5:
                    if not saved and st.button("Save", key=f"ssav_{rid}", icon=":material/save:", width="stretch"):
                        try:
                            dest = data.save_session_run_to_registry(b)
                            b["run_dir"] = str(dest)
                            b["saved_to_registry"] = True
                            st.cache_data.clear()
                            st.toast(f"Saved {rid} to registry", icon=":material/check:")
                            st.rerun()
                        except FileExistsError:
                            st.warning("Already in registry.")
                with c6:
                    if st.button("Discard", key=f"sdis_{rid}", icon=":material/delete:", type="tertiary", width="stretch"):
                        sess.pop(rid, None)
                        st.rerun()


def _execute_and_display_run(
    records: list[dict],
    run_name: str,
    split_label: str,
    dec_path: str | None,
    overrides: dict[str, Any],
    threshold: float,
) -> None:
    """Run extraction in background thread, stream live KPIs, and render result card."""
    _, ev_q = runner.start_session_run_thread(
        records,
        run_name=run_name or "session",
        split=split_label,
        decision_path=dec_path,
        config_overrides=overrides,
        threshold=threshold,
    )

    with st.status(f"Running extraction on {len(records)} docs…", expanded=True) as status:
        pbar = st.progress(0.0)
        kpi_box = st.empty()
        log_box = st.empty()
        doc_logs: list[dict[str, Any]] = []
        tot_req = 0
        tot_hits = 0

        while True:
            kind, payload = ev_q.get()
            if kind == "progress":
                done = int(payload["done"])
                total = max(1, int(payload["total"]))
                elapsed = float(payload.get("elapsed_s") or 0.0)
                doc_s = float(payload.get("doc_s") or 0.0)
                diag = (payload.get("res") or {}).get("diagnostics") or {}
                reqs = int(diag.get("requests") or 0)
                hits = int(diag.get("cache_hits") or 0)
                tot_req += reqs
                tot_hits += hits
                avg_s = elapsed / max(1, done)
                eta_s = avg_s * (total - done)
                hit_rate = (tot_hits / max(1, tot_req + tot_hits))

                pbar.progress(done / total)
                with kpi_box.container():
                    k1, k2, k3, k4, k5 = st.columns(5)
                    k1.metric("Docs", f"{done}/{total}")
                    k2.metric("Elapsed", theme.fmt_secs(elapsed))
                    k3.metric("ETA", theme.fmt_secs(eta_s))
                    k4.metric("Requests", tot_req)
                    k5.metric("Cache hit rate", theme.fmt_pct(hit_rate, 0))

                doc_logs.append({
                    "doc_id": payload["doc_id"],
                    "route": diag.get("route") or "—",
                    "requests": reqs,
                    "cache_hits": hits,
                    "seconds": doc_s,
                })
                log_box.dataframe(pd.DataFrame(doc_logs[-12:]), width="stretch", hide_index=True)

            elif kind == "done":
                bundle = payload
                rid = bundle["run_id"]
                state.session_runs()[rid] = bundle
                state.set_active_run(rid)
                status.update(label=f"Run {rid} complete", state="complete", expanded=False)
                st.toast(f"Run {rid} complete", icon=":material/check:")
                _render_result_card(bundle, threshold)
                break
            elif kind == "error":
                status.update(label="Run failed", state="error", expanded=True)
                st.error(f"Run failed: {payload}")
                break


def _render_result_card(bundle: dict[str, Any], threshold: float) -> None:
    rid = bundle["run_id"]
    man = bundle.get("manifest") or {}
    reqs = int(man.get("requests") or 0)
    hits = int(man.get("cache_hits") or 0)
    cached_state = "yes" if hits > 0 and reqs == 0 else ("partial" if hits > 0 else "no")

    with st.container(border=True):
        st.subheader(f"Result: {rid}")
        if bundle.get("score"):
            sm = analytics_core.summarize_curve(bundle["score"], threshold, error_cost=100.0)
            ui.verdict_chip(sm["verdict"])
            ui.kpi_row([
                {"label": "Precision @τ", "value": theme.fmt_pct(sm["precision_at_tau"], 2)},
                {"label": "Coverage @τ", "value": theme.fmt_pct(sm["coverage_at_tau"], 1)},
                {"label": "Net @E=100", "value": theme.fmt_signed_pct(sm["net_at_tau"])},
                {"label": "Errors", "value": sm["errors_at_tau"]},
            ])
        ui.info_grid([
            ("Run ID", rid),
            ("Models", ", ".join(man.get("models_used") or []) or "—"),
            ("Routes", json.dumps(man.get("routes_used") or {})),
            ("Mode", man.get("mode") or "—"),
            ("Requests / Hits", f"{reqs} / {hits} ({cached_state} cached)"),
            ("Elapsed", theme.fmt_secs(man.get("elapsed_seconds"))),
            ("Failed docs", man.get("n_failed") or 0),
        ])
        b1, b2 = st.columns(2, gap="small")
        with b1:
            if st.button("Open in Review", key=f"res_rev_{rid}", type="primary", icon=":material/fact_check:", width="stretch", on_click=state.set_active_run, args=(rid,)):
                nav.switch_to("review")
        with b2:
            if st.button("Open Analytics", key=f"res_ana_{rid}", icon=":material/insights:", width="stretch", on_click=state.set_active_run, args=(rid,)):
                nav.switch_to("analytics")
