"""Latest run page: manifest summary and business impact headline."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard import cache, data


def render(sidebar_state: dict[str, Any]) -> None:
    st.header("Latest Run")
    session_runs: dict[str, dict] = st.session_state.get("session_runs") or {}
    reg_ids = data.list_run_ids()

    options = [f"[session] {rid}" for rid in session_runs] + reg_ids
    if not options:
        st.info("No runs found yet.")
        return

    choice = st.selectbox("Select run", options, index=0)
    if choice.startswith("[session] "):
        bundle = session_runs[choice[len("[session] "):]]
    else:
        bundle = cache.get_run_bundle(choice)

    run_meta = bundle.get("run") or {}
    man = bundle.get("manifest") or {}
    summary = run_meta.get("summary") or {}
    score = bundle.get("score") or {}

    # ------------------------------------------------------------------ Business summary
    n_fields = summary.get("n_fields") or (score.get("declared") or {}).get("n_fields") or 0
    accepted = summary.get("accepted") if summary.get("accepted") is not None else (score.get("declared") or {}).get("accepted") or 0
    wrong = summary.get("wrong") if summary.get("wrong") is not None else (score.get("declared") or {}).get("wrong") or 0
    halluc = summary.get("hallucinated") if summary.get("hallucinated") is not None else (score.get("declared") or {}).get("hallucinated") or 0
    errors = int(wrong) + int(halluc)
    net_e100 = summary.get("net_saving_pct_e100")
    no_human_pct = (accepted / n_fields * 100.0) if n_fields else 0.0
    net_str = f"{net_e100 * 100:.2f}%" if net_e100 is not None else "n/a"

    st.success(
        f"**{no_human_pct:.1f}% of fields need no human; net saving {net_str} at E=100; {errors} errors**"
    )

    # ------------------------------------------------------------------ Key metrics
    n_written = man.get("n_written") or len(bundle.get("preds") or {})
    elapsed = man.get("elapsed_seconds")
    time_per_doc = (elapsed / n_written) if (elapsed is not None and n_written) else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", run_meta.get("status") or "unknown")
    c2.metric("Docs written / requested", f"{n_written} / {man.get('n_requested', run_meta.get('n_requested', '?'))}")
    c3.metric("Time per doc", f"{time_per_doc:.2f}s" if time_per_doc is not None else "n/a")
    c4.metric("Failures", int(man.get("n_failed") or 0))

    # ------------------------------------------------------------------ Manifest summary
    st.subheader("Manifest Summary")
    pipe = man.get("pipeline") or {}
    models = man.get("models_used") or run_meta.get("models") or ([pipe["model"]] if pipe.get("model") else [])
    routes = man.get("routes_used") or {}
    prompt_versions = man.get("prompt_versions") or ([pipe["prompt_version"]] if pipe.get("prompt_version") else [])
    selector_sha = man.get("selector_sha256") or run_meta.get("decision_sha256") or "—"

    info_rows = [
        {"Key": "Run ID", "Value": bundle["run_id"]},
        {"Key": "Split", "Value": str(run_meta.get("split") or "—")},
        {"Key": "Mode", "Value": str(man.get("mode") or run_meta.get("mode") or "—")},
        {"Key": "Models", "Value": ", ".join(models) if models else "—"},
        {"Key": "Routes", "Value": ", ".join(f"{k}: {v}" for k, v in routes.items()) if routes else "—"},
        {"Key": "Prompt versions", "Value": ", ".join(prompt_versions) if prompt_versions else "—"},
        {"Key": "Selector / decision SHA-256", "Value": str(selector_sha)},
        {"Key": "Total requests / cache hits", "Value": f"{man.get('requests', 0)} / {man.get('cache_hits', 0)}"},
        {"Key": "Elapsed (s)", "Value": str(elapsed if elapsed is not None else "—")},
    ]
    st.table(pd.DataFrame(info_rows))

    req_by_m = man.get("requests_by_model") or {}
    hit_by_m = man.get("cache_hits_by_model") or {}
    if req_by_m or hit_by_m:
        st.subheader("Requests & Cache Hits per Model")
        all_m = sorted(set(req_by_m) | set(hit_by_m))
        st.dataframe(
            pd.DataFrame([
                {"model": m, "requests": req_by_m.get(m, 0), "cache_hits": hit_by_m.get(m, 0)}
                for m in all_m
            ]),
            use_container_width=True,
            hide_index=True,
        )

    failed_ids = man.get("failed_doc_ids") or []
    degraded_ids = man.get("abstained_after_error_doc_ids") or []
    if failed_ids or degraded_ids:
        with st.expander(f"Failures ({len(failed_ids)}) & Degraded ({len(degraded_ids)})"):
            if failed_ids:
                st.write("**Failed doc_ids:**", failed_ids)
            if degraded_ids:
                st.write("**Abstained after errors:**", degraded_ids)
