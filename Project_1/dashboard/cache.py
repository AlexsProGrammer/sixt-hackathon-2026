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
def _cached_run_bundle(run_dir_str: str, mtime_sig: tuple[float, ...]) -> dict[str, Any]:
    return data.load_run_bundle(run_dir_str)


def get_run_bundle(run_id_or_dir: str | Path, runs_dir: Path | None = None) -> dict[str, Any]:
    rdir = Path(runs_dir) if runs_dir else data.RUNS_DIR
    candidate = Path(run_id_or_dir)
    run_dir = candidate if candidate.is_dir() else rdir / str(run_id_or_dir)
    sig = tuple(
        data.file_mtime(run_dir / name)
        for name in ("run.json", "manifest.json", "score.json", "preds.jsonl", "fields.jsonl", "diagnostics.jsonl", "samples.jsonl")
    )
    return _cached_run_bundle(str(run_dir), sig)


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
