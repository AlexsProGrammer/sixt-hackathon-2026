"""Pure-Python data loaders and aggregation helpers for the Project 1 dashboard.

This module intentionally does NOT import streamlit so it can be unit-tested directly
and reused outside the UI. Streamlit caching wrappers live in `dashboard/cache.py`.
"""
from __future__ import annotations

import json
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation import registry

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "results" / "runs"
DATA_DIR = ROOT / "data"
REVIEWS_PATH = ROOT / "results" / "reviews.jsonl"


def file_mtime(path: Path | str) -> float:
    """Return file mtime in seconds, or 0.0 if the file does not exist."""
    p = Path(path)
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                rows.append(json.loads(s))
    return rows


def load_index(runs_dir: Path | None = None) -> list[dict]:
    """Load `index.jsonl` from `runs_dir` (newest-first by created_at)."""
    rdir = Path(runs_dir) if runs_dir else RUNS_DIR
    rows = registry.load_index(rdir)
    rows.sort(key=lambda r: (r.get("created_at") or "", r.get("run_id") or ""), reverse=True)
    return rows


def list_run_ids(runs_dir: Path | None = None) -> list[str]:
    """List available run_ids from `index.jsonl` and any run folders with `run.json`."""
    rdir = Path(runs_dir) if runs_dir else RUNS_DIR
    seen: dict[str, str] = {}
    for row in load_index(rdir):
        rid = row.get("run_id")
        if rid:
            seen[rid] = row.get("created_at") or ""
    if rdir.is_dir():
        for p in rdir.glob("*/run.json"):
            rid = p.parent.name
            if rid not in seen:
                meta = _read_json(p)
                seen[rid] = meta.get("created_at") or ""
    return [rid for rid, _ in sorted(seen.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)]


def load_fields_table(run_dir: Path | str) -> list[dict]:
    """Load `fields.jsonl` from a run folder if present."""
    return _read_jsonl(Path(run_dir) / "fields.jsonl")


def load_run_bundle(run_id_or_dir: str | Path, runs_dir: Path | None = None) -> dict[str, Any]:
    """Load all available artifacts for a run folder into a single dict."""
    rdir_base = Path(runs_dir) if runs_dir else RUNS_DIR
    candidate = Path(run_id_or_dir)
    if candidate.is_dir():
        run_dir = candidate
        run_id = run_dir.name
    else:
        run_id = str(run_id_or_dir)
        run_dir = rdir_base / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run folder not found: {run_dir}")

    run_meta = _read_json(run_dir / "run.json")
    manifest = _read_json(run_dir / "manifest.json")
    score = _read_json(run_dir / "score.json")
    preds = {r["doc_id"]: r.get("fields") or {} for r in _read_jsonl(run_dir / "preds.jsonl") if "doc_id" in r}
    diagnostics = {
        r["doc_id"]: r.get("diagnostics") or {}
        for r in _read_jsonl(run_dir / "diagnostics.jsonl")
        if "doc_id" in r
    }
    samples = {
        r["doc_id"]: r.get("samples") or []
        for r in _read_jsonl(run_dir / "samples.jsonl")
        if "doc_id" in r
    }
    gold = {r["doc_id"]: r for r in _read_jsonl(run_dir / "gold.jsonl") if "doc_id" in r}
    inputs = {r["doc_id"]: r for r in _read_jsonl(run_dir / "input.jsonl") if "doc_id" in r}
    fields = load_fields_table(run_dir)

    return {
        "run_id": run_meta.get("run_id") or run_id,
        "run_dir": str(run_dir),
        "run": run_meta,
        "manifest": manifest,
        "score": score,
        "preds": preds,
        "diagnostics": diagnostics,
        "samples": samples,
        "gold": gold,
        "input": inputs,
        "fields": fields,
        "is_session": False,
    }


def _candidate_record_files(data_dir: Path, run_dir: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    if run_dir is not None:
        paths.extend([run_dir / "gold.jsonl", run_dir / "input.jsonl"])
    paths.extend([
        data_dir / "unified" / "dev.jsonl",
        data_dir / "unified" / "test_public.jsonl",
        data_dir / "splits" / "fit.jsonl",
        data_dir / "splits" / "select.jsonl",
        data_dir / "splits" / "audit.jsonl",
        data_dir / "splits" / "audit2.jsonl",
        data_dir / "splits" / "smoke.jsonl",
    ])
    return paths


def load_records_by_doc_id(
    doc_ids: set[str] | list[str] | None = None,
    *,
    data_dir: Path | None = None,
    run_dir: Path | str | None = None,
) -> dict[str, dict]:
    """Load full records for `doc_ids` from run artifacts and local unified/split datasets."""
    ddir = Path(data_dir) if data_dir else DATA_DIR
    rdir = Path(run_dir) if run_dir else None
    wanted = set(doc_ids) if doc_ids is not None else None
    found: dict[str, dict] = {}
    for path in _candidate_record_files(ddir, rdir):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                rec = json.loads(s)
                did = rec.get("doc_id")
                if not did:
                    continue
                if wanted is None or (did in wanted and did not in found):
                    found[did] = rec
                    if wanted is not None and len(found) == len(wanted):
                        return found
    return found


def resolve_dataset_path(source_name: str, *, data_dir: Path | None = None) -> Path:
    """Resolve a dataset source name ('dev', 'test_public', split name, or path) to a JSONL file."""
    ddir = Path(data_dir) if data_dir else DATA_DIR
    mapping = {
        "dev": ddir / "unified" / "dev.jsonl",
        "test_public": ddir / "unified" / "test_public.jsonl",
    }
    if source_name in mapping:
        return mapping[source_name]
    split_path = ddir / "splits" / f"{source_name}.jsonl"
    if split_path.is_file():
        return split_path
    p = Path(source_name)
    if p.is_file():
        return p
    raise FileNotFoundError(f"Dataset source not found: {source_name}")


def load_dataset_records(source_name: str, *, data_dir: Path | None = None) -> list[dict]:
    """Load all records from a named dataset ('dev', 'test_public', split name, or file path)."""
    return _read_jsonl(resolve_dataset_path(source_name, data_dir=data_dir))


def sample_stratified_records(records: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Sample `n` records stratified by `source_dataset` with a deterministic seed."""
    if n <= 0 or not records:
        return []
    if n >= len(records):
        return list(records)
    rng = random.Random(seed)
    buckets: dict[str, list[dict]] = {}
    for rec in records:
        src = str(rec.get("source_dataset") or "unknown")
        buckets.setdefault(src, []).append(rec)
    for src in buckets:
        rng.shuffle(buckets[src])
    sources = sorted(buckets)
    selected: list[dict] = []
    idx = {s: 0 for s in sources}
    while len(selected) < n:
        progressed = False
        for src in sources:
            if idx[src] < len(buckets[src]) and len(selected) < n:
                selected.append(buckets[src][idx[src]])
                idx[src] += 1
                progressed = True
        if not progressed:
            break
    return selected


# ------------------------------------------------------------------ human reviews

def load_reviews(reviews_path: Path | None = None) -> list[dict]:
    """Load human review actions from `results/reviews.jsonl`."""
    path = Path(reviews_path) if reviews_path else REVIEWS_PATH
    return _read_jsonl(path)


def append_review(entry: dict, reviews_path: Path | None = None) -> dict:
    """Append one review action `{ts, run_id, doc_id, field, action, value, reviewer}`."""
    path = Path(reviews_path) if reviews_path else REVIEWS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": entry.get("ts") or datetime.now().isoformat(timespec="seconds"),
        "run_id": str(entry.get("run_id") or ""),
        "doc_id": str(entry.get("doc_id") or ""),
        "field": str(entry.get("field") or ""),
        "action": str(entry.get("action") or ""),
        "value": entry.get("value"),
        "reviewer": str(entry.get("reviewer") or "reviewer"),
    }
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def latest_reviews_map(reviews: list[dict], run_id: str | None = None) -> dict[tuple[str, str], dict]:
    """Return latest review per `(doc_id, field)` (filtered by `run_id` when provided)."""
    out: dict[tuple[str, str], dict] = {}
    for row in reviews:
        if run_id is not None and row.get("run_id") != run_id:
            continue
        key = (str(row.get("doc_id") or ""), str(row.get("field") or ""))
        out[key] = row
    return out


# ------------------------------------------------------------------ document review rows

def _extract_per_view_values(samples: list[dict], field: str) -> list[dict[str, Any]]:
    views: list[dict[str, Any]] = []
    for i, sample in enumerate(samples):
        f = (sample.get("fields") or {}).get(field) or {}
        views.append({
            "view": sample.get("view") or sample.get("model") or f"sample_{i}",
            "value": f.get("value"),
            "status": f.get("status"),
            "confidence": f.get("model_confidence"),
        })
    return views


def _row_color(outcome: str, booked: bool) -> str:
    if outcome == "true_null":
        return "grey"
    if outcome == "correct" and booked:
        return "green"
    if outcome in ("wrong", "hallucinated") and booked:
        return "red"
    if outcome == "correct" and not booked:
        return "yellow"
    return "neutral"


def build_doc_field_rows(
    doc_id: str,
    bundle: dict[str, Any],
    rec: dict | None = None,
    threshold: float = 0.99,
) -> list[dict[str, Any]]:
    """Build per-field review rows for one document in a run."""
    field_rows_by_name = {
        r["field"]: r for r in (bundle.get("fields") or []) if r.get("doc_id") == doc_id
    }
    pred_fields = (bundle.get("preds") or {}).get(doc_id) or {}
    diag = (bundle.get("diagnostics") or {}).get(doc_id) or {}
    per_field_diag = diag.get("per_field") or {}
    samples = (bundle.get("samples") or {}).get(doc_id) or []
    gold_rec = rec or (bundle.get("gold") or {}).get(doc_id) or (bundle.get("input") or {}).get(doc_id) or {}
    gold_map = gold_rec.get("gold") or {}
    schema_props = (gold_rec.get("schema") or {}).get("properties") or {}

    ordered_fields: list[str] = []
    for name in schema_props:
        if name not in ordered_fields:
            ordered_fields.append(name)
    for name in field_rows_by_name:
        if name not in ordered_fields:
            ordered_fields.append(name)
    for name in pred_fields:
        if name not in ordered_fields:
            ordered_fields.append(name)

    rows: list[dict[str, Any]] = []
    for name in ordered_fields:
        frow = field_rows_by_name.get(name) or {}
        p = pred_fields.get(name) or {}
        pf = per_field_diag.get(name) or {}
        pred_val = frow.get("pred_value") if frow else p.get("value")
        conf = frow.get("conf_out") if frow else p.get("confidence")
        if conf is None and p.get("confidence") is not None:
            conf = p.get("confidence")
        conf_num = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.0
        booked = pred_val is not None and conf_num >= threshold
        outcome = frow.get("outcome") or ("unknown" if not gold_map else (
            "true_null" if pred_val is None and gold_map.get(name) is None else "unknown"
        ))
        ev_flags: list[str] = []
        if frow.get("grounded_text"):
            ev_flags.append("grounded_text")
        if frow.get("grounded_ocr"):
            ev_flags.append("grounded_ocr")
        if frow.get("cross_view_agree"):
            ev_flags.append("views_agree")
        if pf.get("grounded") and "grounded_text" not in ev_flags:
            ev_flags.append("grounded")

        rows.append({
            "field": name,
            "kind": frow.get("kind") or (schema_props.get(name) or {}).get("type", ""),
            "value": pred_val,
            "gold": gold_map.get(name) if name in gold_map else None,
            "has_gold": bool(gold_map),
            "confidence": conf_num if pred_val is not None else 0.0,
            "decision": "booked" if booked else "to human",
            "booked": booked,
            "reason": pf.get("reason") or frow.get("kind_policy") or "",
            "evidence_flags": ev_flags,
            "per_view": _extract_per_view_values(samples, name),
            "outcome": outcome,
            "color": _row_color(outcome, booked),
        })
    return rows


# ------------------------------------------------------------------ analytics aggregations

def compute_reliability_bins(fields: list[dict], n_bins: int = 10) -> list[dict]:
    """Bucket predicted-present field rows by `conf_out` and compute empirical precision."""
    bins: list[dict] = []
    step = 1.0 / n_bins
    for i in range(n_bins):
        lo = round(i * step, 4)
        hi = round((i + 1) * step, 4)
        in_bin = [
            r for r in fields
            if r.get("pred_present") and r.get("conf_out") is not None
            and (lo <= float(r["conf_out"]) < hi or (i == n_bins - 1 and float(r["conf_out"]) == 1.0))
        ]
        if not in_bin:
            continue
        correct = sum(1 for r in in_bin if r.get("outcome") == "correct")
        mean_conf = sum(float(r["conf_out"]) for r in in_bin) / len(in_bin)
        bins.append({
            "bin": f"{lo:.1f}-{hi:.1f}",
            "mean_conf": round(mean_conf, 4),
            "precision": round(correct / len(in_bin), 4),
            "count": len(in_bin),
        })
    return bins


def compute_family_field_stats(fields: list[dict], threshold: float = 0.99) -> list[dict]:
    """Aggregate precision and booked count per `(family, field)`."""
    groups: dict[tuple[str, str], dict[str, int]] = {}
    for r in fields:
        key = (str(r.get("family") or "unknown"), str(r.get("field") or "unknown"))
        g = groups.setdefault(key, {"n_total": 0, "booked": 0, "correct": 0})
        g["n_total"] += 1
        conf = r.get("conf_out")
        if r.get("pred_present") and conf is not None and float(conf) >= threshold:
            g["booked"] += 1
            if r.get("outcome") == "correct":
                g["correct"] += 1
    out: list[dict] = []
    for (family, field), g in sorted(groups.items()):
        prec = (g["correct"] / g["booked"]) if g["booked"] else None
        out.append({
            "family": family,
            "field": field,
            "n_total": g["n_total"],
            "booked": g["booked"],
            "correct": g["correct"],
            "precision": round(prec, 4) if prec is not None else None,
        })
    return out


def compute_route_kind_stats(fields: list[dict], threshold: float = 0.99) -> tuple[list[dict], list[dict]]:
    """Aggregate booked, correct, wrong, precision, coverage by `route` and by `kind`."""
    def _agg(key_name: str) -> list[dict]:
        buckets: dict[str, dict[str, int]] = {}
        for r in fields:
            k = str(r.get(key_name) or "unknown")
            b = buckets.setdefault(k, {"n_fields": 0, "gold_present": 0, "booked": 0, "correct": 0, "wrong": 0})
            b["n_fields"] += 1
            if r.get("gold_present"):
                b["gold_present"] += 1
            conf = r.get("conf_out")
            if r.get("pred_present") and conf is not None and float(conf) >= threshold:
                b["booked"] += 1
                if r.get("outcome") == "correct":
                    b["correct"] += 1
                elif r.get("outcome") in ("wrong", "hallucinated"):
                    b["wrong"] += 1
        rows: list[dict] = []
        for k, b in sorted(buckets.items()):
            rows.append({
                key_name: k,
                "n_fields": b["n_fields"],
                "booked": b["booked"],
                "correct": b["correct"],
                "wrong": b["wrong"],
                "precision": round(b["correct"] / b["booked"], 4) if b["booked"] else None,
                "coverage": round(b["correct"] / b["gold_present"], 4) if b["gold_present"] else 0.0,
            })
        return rows

    return _agg("route"), _agg("kind")


def save_session_run_to_registry(bundle: dict[str, Any], runs_dir: Path | None = None) -> Path:
    """Persist a temporary session run folder into `results/runs/<run_id>/` and index it."""
    rdir_base = Path(runs_dir) if runs_dir else RUNS_DIR
    src_dir = Path(bundle["run_dir"])
    run_id = bundle["run_id"]
    dest_dir = rdir_base / run_id
    if dest_dir.exists():
        raise FileExistsError(f"Run already exists in registry: {dest_dir}")
    rdir_base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dest_dir)
    registry.append_index(dest_dir)
    return dest_dir
