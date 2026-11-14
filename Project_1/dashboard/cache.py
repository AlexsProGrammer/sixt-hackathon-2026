"""Streamlit cache wrappers keyed on file mtime for `dashboard.data`."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from dashboard import data


@st.cache_data(show_spinner=False)
def _cached_index(runs_dir_str: str, mtime: float) -> list[dict]:
    return data.load_index(Path(runs_dir_str))


def get_index(runs_dir: Path | None = None) -> list[dict]:
    rdir = Path(runs_dir) if runs_dir else data.RUNS_DIR
    return _cached_index(str(rdir), data.file_mtime(rdir / "index.jsonl"))


@st.cache_data(show_spinner=False)
def _cached_run_bundle(run_dir_str: str, mtime_sig: tuple[float, ...], include_samples: bool) -> dict[str, Any]:
    return data.load_run_bundle(run_dir_str, include_samples=include_samples)


def get_run_bundle(
    run_id_or_dir: str | Path,
    runs_dir: Path | None = None,
    *,
    include_samples: bool = True,
) -> dict[str, Any]:
    rdir = Path(runs_dir) if runs_dir else data.RUNS_DIR
    candidate = Path(run_id_or_dir)
    run_dir = candidate if candidate.is_dir() else rdir / str(run_id_or_dir)
    sig = tuple(
        data.file_mtime(run_dir / name)
        for name in ("run.json", "manifest.json", "score.json", "preds.jsonl", "fields.jsonl", "diagnostics.jsonl", "samples.jsonl")
    )
    return _cached_run_bundle(str(run_dir), sig, include_samples)


@st.cache_data(show_spinner=False)
def _cached_dataset(path_str: str, mtime: float) -> list[dict]:
    return data._read_jsonl(Path(path_str))


def get_dataset_records(source_name: str, *, data_dir: Path | None = None) -> list[dict]:
    path = data.resolve_dataset_path(source_name, data_dir=data_dir)
    return _cached_dataset(str(path), data.file_mtime(path))


@st.cache_data(show_spinner=False)
def _cached_reviews(path_str: str, mtime: float) -> list[dict]:
    return data.load_reviews(Path(path_str))


def get_reviews(reviews_path: Path | None = None) -> list[dict]:
    path = Path(reviews_path) if reviews_path else data.REVIEWS_PATH
    return _cached_reviews(str(path), data.file_mtime(path))


@st.cache_data(ttl=60, show_spinner=False)
def get_cache_stats() -> dict[str, Any]:
    """Return reply cache totals and per-model breakdown (TTL 60s)."""
    from tools import cache_stats

    rows = cache_stats.collect(data.ROOT / "cache")
    total_files = sum(r[2] for r in rows)
    total_bytes = sum(r[3] for r in rows)
    return {
        "rows": [{"model": m, "prompt_version": pv, "files": n, "bytes": b} for m, pv, n, b in rows],
        "total_files": total_files,
        "total_bytes": total_bytes,
    }


@st.cache_data(show_spinner=False)
def _cached_pipeline_desc(dec_path_str: str, dec_mtime: float, models_mtime: float) -> Any:
    from dashboard import pipeline_info

    return pipeline_info.describe(dec_path_str or None)


def get_pipeline_description(decision_path: str | None) -> Any:
    """Cached wrapper around `pipeline_info.describe` keyed on decision + models.json mtimes."""
    dec_str = decision_path or ""
    dec_mtime = data.file_mtime(dec_str) if dec_str else 0.0
    models_mtime = data.file_mtime(data.ROOT / "models.json")
    return _cached_pipeline_desc(dec_str, dec_mtime, models_mtime)


@st.cache_data(ttl=120, show_spinner=False)
def get_doc_to_runs_map() -> dict[str, list[str]]:
    """Map doc_id -> list of registry run_ids that already processed it."""
    import json

    mapping: dict[str, list[str]] = {}
    if not data.RUNS_DIR.is_dir():
        return mapping
    for run_dir in sorted(data.RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        rid = run_dir.name
        src = run_dir / "preds.jsonl"
        if not src.is_file():
            src = run_dir / "input.jsonl"
        if not src.is_file():
            continue
        try:
            with open(src, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    did = json.loads(s).get("doc_id")
                    if did:
                        mapping.setdefault(str(did), []).append(rid)
        except (OSError, ValueError):
            continue
    return mapping


@st.cache_data(show_spinner=False)
def _cached_route_for_doc(doc_id: str, pdf_path: str, text_len: int, family: str) -> str:
    from pipeline import router

    rec = {"doc_id": doc_id, "pdf_path": pdf_path or None, "family": family or None}
    return str(router.route(rec, data.DATA_DIR).get("route") or "unknown")


def get_route_counts(records: list[dict]) -> dict[str, int]:
    """Compute route distribution for up to 50 records."""
    counts: dict[str, int] = {}
    for rec in records[:50]:
        r = _cached_route_for_doc(
            str(rec.get("doc_id") or ""),
            str(rec.get("pdf_path") or ""),
            len(str(rec.get("text") or "")),
            str(rec.get("family") or ""),
        )
        counts[r] = counts.get(r, 0) + 1
    return counts
