#!/usr/bin/env python3
"""Import loose result files (results/<name>.jsonl) as registered run folders with tag "legacy". Stdlib only.

For every predictions file the matching gold subset (same doc_ids) is written to the run folder and the run is
re-scored against it, so a score always belongs to its predictions. Existing side files (<name>.diagnostics.jsonl,
.samples.jsonl, .manifest.json) are copied. Runs without a manifest get `provenance: "unknown"`.
Old *_score.json files are ignored (they may not match the predictions). Import is idempotent: a run that is
already imported (same legacy source name) is skipped unless --force.

    python tools/import_legacy_runs.py [--threshold 0.99] [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from evaluation import registry  # noqa: E402

GOLD_FILES = {"dev": "data/unified/dev.jsonl", "test_public": "data/unified/test_public.jsonl"}
SKIP_SUFFIXES = (".diagnostics.jsonl", ".samples.jsonl")
SKIP_PREFIXES = ("release_", "final_dev_input")


def discover(results_dir: Path) -> list[Path]:
    """Top-level prediction files only (results/runs and results/split are not scanned)."""
    out = []
    for p in sorted(Path(results_dir).glob("*.jsonl")):
        if p.name.endswith(SKIP_SUFFIXES) or p.name.startswith(SKIP_PREFIXES) or p.name == registry.INDEX_NAME:
            continue
        if p.stat().st_size == 0:
            continue
        out.append(p)
    return out


def legacy_run_id(src: Path) -> str:
    """Deterministic: file mtime + name + 6 hex of the name hash, so a re-import finds the same folder."""
    when = datetime.fromtimestamp(src.stat().st_mtime)
    digest = hashlib.sha256(src.stem.encode("utf-8")).hexdigest()[:6]
    return f"{when:%Y%m%d-%H%M%S}-{registry.slug(src.stem)}-{digest}"


def load_gold(gold_files: dict[str, Path]) -> dict[str, dict[str, tuple[str, dict]]]:
    """{split: {doc_id: record}} for every gold file that exists."""
    out = {}
    for split, path in gold_files.items():
        if Path(path).exists():
            out[split] = {r["doc_id"]: r for r in registry.read_jsonl(Path(path))}
    return out


def detect_split(ids: set[str], gold: dict[str, dict]) -> str | None:
    for split, recs in gold.items():
        if ids <= recs.keys():
            return split
    return None


def import_one(src: Path, runs_dir: Path, gold: dict[str, dict], gold_files: dict[str, Path], threshold: float,
               force: bool = False, dry_run: bool = False) -> dict:
    """Import one predictions file. Returns {"name", "status", ...}; status is imported, skipped or rejected."""
    name = src.stem
    try:
        preds_rows = registry.read_jsonl(src)
    except ValueError as e:
        return {"name": name, "status": "rejected", "reason": str(e)}
    preds_rows = [r for r in preds_rows if "doc_id" in r]
    ids = {r["doc_id"] for r in preds_rows}
    if not ids:
        return {"name": name, "status": "rejected", "reason": "no predictions"}
    split = detect_split(ids, gold)
    if split is None:
        return {"name": name, "status": "rejected", "reason": "doc_ids not found in any gold file (partially or fully)"}

    run_id = legacy_run_id(src)
    run_dir = runs_dir / run_id
    existing = [p.parent for p in runs_dir.glob(f"*-{registry.slug(name)}-{run_id[-6:]}/run.json")]
    if existing and not force:
        return {"name": name, "status": "skipped", "reason": "already imported", "run_id": existing[0].name}
    if dry_run:
        return {"name": name, "status": "imported", "run_id": run_id, "split": split, "n_docs": len(ids), "dry_run": True}
    for old in existing:
        shutil.rmtree(old)

    manifest_src = src.with_name(name + ".manifest.json")
    run_dir = registry.new_run(name, split, ["legacy"], runs_dir=runs_dir, run_id=run_id,
                               created_at=src.stat().st_mtime,
                               extra={"provenance": "manifest" if manifest_src.exists() else "unknown",
                                      "legacy_source": src.name})
    # the legacy run was not executed from the current checkout, so the recorded commit is not its commit
    registry.update_run(run_dir, git={"commit": None, "dirty": None, "note": "legacy import"})

    shutil.copyfile(src, run_dir / "preds.jsonl")
    for suffix, dest in ((".diagnostics.jsonl", "diagnostics.jsonl"), (".samples.jsonl", "samples.jsonl"),
                         (".manifest.json", "manifest.json")):
        side = src.with_name(name + suffix)
        if side.exists() and side.stat().st_size > 0:
            shutil.copyfile(side, run_dir / dest)

    # same doc_ids as the predictions, in prediction order; gold stays out of input.jsonl
    records = [gold[split][r["doc_id"]] for r in _unique(preds_rows)]
    gold_path = Path(gold_files[split])
    registry.write_inputs(run_dir, records, input_ref=str(_rel(gold_path)),
                          input_sha256=registry.sha256_file(gold_path))
    man = {}
    if (run_dir / "manifest.json").exists():
        try:
            man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        except ValueError:
            man = {}
    complete = man.get("run_complete")
    status = "complete" if complete else ("unknown" if complete is None else "incomplete")
    registry.update_run(run_dir, status=status, n_written=len(ids),
                        models=[man["pipeline"]["model"]] if (man.get("pipeline") or {}).get("model") else [])
    summary = registry.score_run(run_dir, threshold)
    registry.append_index(run_dir)
    return {"name": name, "status": "imported", "run_id": run_id, "split": split, "n_docs": summary["n_docs"],
            "n_fields": summary["n_fields"], "accepted": summary["accepted"], "wrong": summary["wrong"],
            "net_saving_pct_e100": summary["net_saving_pct_e100"], "provenance": "manifest" if man else "unknown"}


def _unique(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        if r["doc_id"] not in seen:
            seen.add(r["doc_id"])
            out.append(r)
    return out


def _rel(path: Path) -> Path:
    try:
        return Path(path).resolve().relative_to(ROOT)
    except ValueError:
        return Path(path)


def import_all(results_dir: Path, runs_dir: Path, gold_files: dict[str, Path], threshold: float,
               force: bool = False, dry_run: bool = False) -> list[dict]:
    gold = load_gold(gold_files)
    Path(runs_dir).mkdir(parents=True, exist_ok=True)
    return [import_one(p, Path(runs_dir), gold, gold_files, threshold, force, dry_run) for p in discover(results_dir)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default=str(ROOT / "results"))
    ap.add_argument("--runs-dir", default=str(registry.RUNS_DIR))
    ap.add_argument("--threshold", type=float, default=registry.DEFAULT_THRESHOLD)
    ap.add_argument("--force", action="store_true", help="re-import runs that already exist")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    gold_files = {k: ROOT / v for k, v in GOLD_FILES.items()}
    res = import_all(Path(a.results_dir), Path(a.runs_dir), gold_files, a.threshold, a.force, a.dry_run)
    for r in res:
        if r["status"] == "imported" and not r.get("dry_run"):
            print(f"imported {r['name']:28s} {r['split']:12s} docs={r['n_docs']:4d} fields={r['n_fields']:6d} "
                  f"accepted={r['accepted']:5d} wrong={r['wrong']:4d} net@100={r['net_saving_pct_e100']:.2%} "
                  f"[provenance: {r['provenance']}]")
        else:
            print(f"{r['status']:8s} {r['name']:28s} {r.get('reason', r.get('run_id', ''))}")
    if not a.dry_run:
        registry.rebuild_index(Path(a.runs_dir))
    n = sum(r["status"] == "imported" for r in res)
    print(f"{n} imported, {sum(r['status'] == 'skipped' for r in res)} skipped, "
          f"{sum(r['status'] == 'rejected' for r in res)} rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
