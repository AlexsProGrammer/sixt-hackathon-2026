"""Run page: execute small batches, single docs, or uploaded PDF+schema as session runs."""
from __future__ import annotations

import json
import queue
import tempfile
import time
from pathlib import Path
from typing import Any

import streamlit as st

from dashboard import cache, data, runner


def _available_decision_files() -> list[str]:
    candidates: list[Path] = []
    for base in (data.ROOT / "submission", data.ROOT / "results", data.ROOT / "uncertainty", data.ROOT):
        if base.is_dir():
            candidates.extend(sorted(base.glob("*decision*.json")))
    seen: list[str] = []
    for p in candidates:
        s = str(p)
        if s not in seen:
            seen.append(s)
    return seen


def _select_records(source_mode: str) -> tuple[list[dict], str]:
    if source_mode == "Upload PDF + Schema JSON":
        col1, col2 = st.columns(2)
        up_pdf = col1.file_uploader("Upload PDF", type=["pdf"])
        up_schema = col2.file_uploader("Upload Schema JSON", type=["json"])
        if not up_pdf or not up_schema:
            return [], "upload"
        schema_obj = json.loads(up_schema.read().decode("utf-8"))
        tmp_dir = Path(tempfile.gettempdir()) / "project1_dashboard_uploads"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = tmp_dir / up_pdf.name
        pdf_path.write_bytes(up_pdf.getvalue())
        rec = {
            "doc_id": f"upload:{pdf_path.stem}",
            "source_dataset": "extractbench",
            "split": "upload",
            "pages": [str(pdf_path)],
            "schema": schema_obj,
        }
        return [rec], "upload"

    dataset_choice = st.selectbox(
        "Dataset / split",
        ["dev", "test_public", "fit", "select", "audit", "audit2", "smoke"],
        index=0,
    )
    all_recs = cache.get_dataset_records(dataset_choice)

    if source_mode == "Single doc_id":
        doc_ids = [r["doc_id"] for r in all_recs]
        chosen_id = st.selectbox("doc_id", doc_ids)
        return [r for r in all_recs if r["doc_id"] == chosen_id], dataset_choice

    if source_mode == "Random N (stratified)":
        c1, c2 = st.columns(2)
        n = int(c1.number_input("N documents", min_value=1, max_value=min(50, len(all_recs)), value=min(3, len(all_recs))))
        seed = int(c2.number_input("Seed", min_value=0, max_value=999999, value=42))
        sampled = data.sample_stratified_records(all_recs, n=n, seed=seed)
        st.caption(f"Stratified sample (seed={seed}): " + ", ".join(r["doc_id"] for r in sampled))
        return sampled, dataset_choice

    if source_mode == "Full split / batch":
        limit = int(st.number_input("Limit (0 = all)", min_value=0, max_value=len(all_recs), value=min(10, len(all_recs))))
        return (all_recs[:limit] if limit > 0 else all_recs), dataset_choice

    return [], dataset_choice


def render(sidebar_state: dict[str, Any]) -> None:
    st.header("Run Extraction")
    st.caption("Run small batches, single documents, or uploaded PDFs. Unsaved runs stay in session state only.")

    source_mode = st.radio(
        "Input source",
        ["Random N (stratified)", "Single doc_id", "Full split / batch", "Upload PDF + Schema JSON"],
        horizontal=True,
    )
    records, split_name = _select_records(source_mode)

    with st.expander("Run configuration", expanded=True):
        c1, c2, c3 = st.columns(3)
        dec_files = ["(None — use overrides)"] + _available_decision_files()
        default_dec = sidebar_state.get("decision_path")
        default_idx = dec_files.index(default_dec) if default_dec in dec_files else 0
        dec_choice = c1.selectbox("Decision file", dec_files, index=default_idx)
        dec_path = None if dec_choice.startswith("(None") else dec_choice

        threshold = float(c2.slider("Threshold", 0.0, 1.0, float(sidebar_state.get("threshold", 0.99)), 0.01))
        use_cache = c3.toggle("Use cache", value=True)
        run_name = st.text_input("Run name", value=f"session-{split_name}")

        overrides: dict[str, Any] = {"no_cache": not use_cache, "on_error": "abstain"}
        if dec_path is None:
            o1, o2, o3 = st.columns(3)
            mode_opt = o1.selectbox("Mode", ["auto", "llm", "offline"], index=0)
            samples_k = int(o2.number_input("Samples (K)", min_value=1, max_value=5, value=1))
            uq_method = o3.selectbox("UQ method", ["k1_grounded", "k_agreement_conf", "k_agreement_only", "k_entropy"], index=0)
            overrides.update({"mode": mode_opt, "samples": samples_k, "uq_method": uq_method})

    can_run = len(records) > 0
    if st.button("Start run", type="primary", disabled=not can_run):
        started = time.time()
        with st.status(f"Running {len(records)} document(s)...", expanded=True) as status:
            prog_bar = st.progress(0.0)
            metrics_box = st.empty()
            _thread, q = runner.start_session_run_thread(
                records,
                run_name=run_name,
                split=split_name,
                decision_path=dec_path,
                config_overrides=overrides,
                threshold=threshold,
            )
            bundle = None
            err_msg = None
            total_reqs = 0
            total_hits = 0
            while True:
                try:
                    kind, payload = q.get(timeout=0.15)
                except queue.Empty:
                    elapsed = time.time() - started
                    metrics_box.caption(f"Elapsed: {elapsed:.1f}s")
                    continue
                if kind == "progress":
                    done = payload["done"]
                    total = max(1, payload["total"])
                    res = payload.get("res") or {}
                    diag = res.get("diagnostics") or {}
                    total_reqs += int(diag.get("requests", 0) or 0)
                    total_hits += int(diag.get("cache_hits", 0) or 0)
                    prog_bar.progress(min(1.0, done / total))
                    metrics_box.write(
                        f"Doc {done}/{total}: `{payload['doc_id']}` · "
                        f"elapsed {time.time() - started:.1f}s"
                    )
                elif kind == "done":
                    bundle = payload
                    break
                elif kind == "error":
                    err_msg = str(payload)
                    break

            if err_msg:
                status.update(label=f"Run failed: {err_msg}", state="error")
                st.error(err_msg)
            elif bundle is not None:
                man = bundle.get("manifest") or {}
                status.update(
                    label=(
                        f"Completed {man.get('n_written', 0)}/{man.get('n_requested', len(records))} docs "
                        f"in {man.get('elapsed_seconds', 0)}s "
                        f"(requests={man.get('requests', 0)}, cache_hits={man.get('cache_hits', 0)})"
                    ),
                    state="complete",
                )
                st.session_state.setdefault("session_runs", {})[bundle["run_id"]] = bundle
                st.session_state["active_run_id"] = bundle["run_id"]

    session_runs: dict[str, dict] = st.session_state.get("session_runs") or {}
    if session_runs:
        st.subheader("Session runs (unsaved until saved to registry)")
        for rid, bundle in list(session_runs.items()):
            man = bundle.get("manifest") or {}
            score = (bundle.get("run") or {}).get("summary") or {}
            c1, c2, c3 = st.columns([4, 2, 2])
            c1.write(
                f"**{rid}** · docs={man.get('n_written', 0)}/{man.get('n_requested', 0)} · "
                f"reqs={man.get('requests', 0)} · hits={man.get('cache_hits', 0)} · "
                + (f"net@100={score['net_saving_pct_e100']:.2%}" if "net_saving_pct_e100" in score else "no gold")
            )
            if c2.button("Review", key=f"rev_{rid}"):
                st.session_state["active_run_id"] = rid
                st.session_state["nav_page"] = "Review"
                st.rerun()
            if bundle.get("saved_to_registry"):
                c3.success("Saved")
            elif c3.button("Save to registry", key=f"save_{rid}"):
                dest = data.save_session_run_to_registry(bundle)
                bundle["saved_to_registry"] = True
                bundle["run_dir"] = str(dest)
                st.cache_data.clear()
                st.success(f"Saved to {dest.name}")
