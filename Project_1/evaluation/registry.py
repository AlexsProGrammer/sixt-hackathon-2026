"""Run registry: one self-contained folder per run, one index file for all runs. Stdlib only.

    results/runs/<run_id>/       run_id = YYYYMMDD-HHMMSS-<name>-<6hex>
        run.json        name, split, created_at, tags, git commit, status, input info, score summary
        input.jsonl     gold-free copy of the records that were run (or input_ref + sha256 when > 5 MB)
        gold.jsonl      gold records with exactly the doc_ids of preds.jsonl (only when gold is available)
        preds.jsonl, diagnostics.jsonl, samples.jsonl, manifest.json    written by 4_extract.py
        score.json      official scorer output (5_score.py logic) on gold.jsonl vs preds.jsonl
    results/runs/index.jsonl     one summary row per run (upserted by run_id)

Predictions, manifest, diagnostics and score of a run can never be separated. Scoring always uses the gold subset
whose doc_ids equal the prediction doc_ids, because the scorer iterates over gold (a --limit subset scored against the
full gold file would dilute every number).

CLI:
    python -m evaluation.registry list
    python -m evaluation.registry score RUN_ID_OR_DIR [--threshold 0.99]
    python -m evaluation.registry rebuild            # rebuild index.jsonl from the run folders
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "results" / "runs"
INDEX_NAME = "index.jsonl"
DEFAULT_THRESHOLD = 0.99
ERROR_COSTS = (20.0, 100.0, 500.0)
MAX_INPUT_COPY_BYTES = 5 * 1024 * 1024
STATUSES = ("created", "running", "complete", "incomplete", "failed", "unknown")

_scorer = None


# ---------------------------------------------------------------- small helpers

def load_scorer():
    """Load 5_score.py by path, once. Its functions are used unchanged."""
    global _scorer
    if _scorer is None:
        spec = importlib.util.spec_from_file_location("score5_registry", ROOT / "5_score.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _scorer = mod
    return _scorer


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Write to a temp file in the same folder, fsync, then os.replace: readers never see a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                raise ValueError(f"{path} line {n} is not valid JSON") from None
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    atomic_write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    return s[:60] or "run"


@contextlib.contextmanager
def _locked(path: Path):
    """Exclusive lock on <path>.lock (fcntl on POSIX, msvcrt on Windows, none if neither exists)."""
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    kind = None
    try:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            kind = "fcntl"
        except ImportError:
            try:
                import msvcrt
                f.seek(0)
                while True:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
                kind = "msvcrt"
            except ImportError:
                kind = None
        yield
    finally:
        try:
            if kind == "fcntl":
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            elif kind == "msvcrt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        f.close()


def git_info() -> dict:
    def run(*args):
        try:
            r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain", "--", ".")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def _now(ts: float | None = None) -> datetime:
    return datetime.fromtimestamp(ts) if ts is not None else datetime.now()


# ---------------------------------------------------------------- run folders

def new_run(name: str, split: str, tags: list[str] | None = None, *, runs_dir: Path | None = None,
            run_id: str | None = None, created_at: float | None = None, extra: dict | None = None) -> Path:
    """Create results/runs/<run_id>/ with run.json (status "created") and return the folder."""
    runs = Path(runs_dir) if runs_dir else RUNS_DIR
    when = _now(created_at)
    if run_id is None:
        suffix = hashlib.sha256(f"{name}{when.isoformat()}{os.getpid()}{time.time_ns()}".encode()).hexdigest()[:6]
        run_id = f"{when:%Y%m%d-%H%M%S}-{slug(name)}-{suffix}"
    run_dir = runs / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    run = {"run_id": run_id, "name": name, "split": split, "created_at": when.isoformat(timespec="seconds"),
           "tags": list(tags or []), "git": git_info(), "status": "created", **(extra or {})}
    atomic_write_text(run_dir / "run.json", json.dumps(run, indent=2, ensure_ascii=False) + "\n")
    return run_dir


def init_run_dir(run_dir: Path, *, name: str | None = None, split: str = "unknown",
                 tags: list[str] | None = None) -> dict:
    """Make `run_dir` a registered run folder if it is not one yet (used by `4_extract.py --run-dir`)."""
    run_dir = Path(run_dir)
    if (run_dir / "run.json").exists():
        return read_run(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    when = _now()
    run = {"run_id": run_dir.name, "name": name or run_dir.name, "split": split,
           "created_at": when.isoformat(timespec="seconds"), "tags": list(tags or ["cli"]),
           "git": git_info(), "status": "created"}
    atomic_write_text(run_dir / "run.json", json.dumps(run, indent=2, ensure_ascii=False) + "\n")
    return run


def read_run(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "run.json").read_text(encoding="utf-8"))


def update_run(run_dir: Path, **fields) -> dict:
    """Merge fields into run.json (one writer per run). Returns the new content."""
    run = read_run(run_dir)
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"unknown status {fields['status']!r}")
    run.update(fields)
    atomic_write_text(Path(run_dir) / "run.json", json.dumps(run, indent=2, ensure_ascii=False) + "\n")
    return run


def finish_run(run_dir: Path, status: str, **fields) -> dict:
    return update_run(run_dir, status=status, finished_at=_now().isoformat(timespec="seconds"), **fields)


def strip_gold(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("gold")}


def write_inputs(run_dir: Path, records: list[dict], *, input_ref: str | None = None,
                 input_sha256: str | None = None, max_copy_bytes: int = MAX_INPUT_COPY_BYTES) -> dict:
    """Write the gold-free input copy and (when records carry gold) gold.jsonl with the same doc_ids.

    The input copy is replaced by a reference (`input_ref` + sha256) when it exceeds `max_copy_bytes` and a
    reference is available. Returns the `input` block that is also stored in run.json."""
    run_dir = Path(run_dir)
    clean = "".join(json.dumps(strip_gold(r), ensure_ascii=False) + "\n" for r in records)
    info: dict = {"n_docs": len(records)}
    big = len(clean.encode("utf-8")) > max_copy_bytes
    if big and input_ref:
        info.update({"kind": "ref", "input_ref": input_ref, "input_sha256": input_sha256})
        (run_dir / "input.jsonl").unlink(missing_ok=True)
    else:
        atomic_write_text(run_dir / "input.jsonl", clean)
        info.update({"kind": "copy", "input_sha256": sha256_bytes(clean.encode("utf-8"))})
        if input_ref:
            info["input_ref"] = input_ref
    gold = [r for r in records if "gold" in r]
    if gold:
        write_jsonl(run_dir / "gold.jsonl", gold)
        info["n_gold"] = len(gold)
    update_run(run_dir, input=info)
    return info


# ---------------------------------------------------------------- scoring

def _by_source(scorer, gold: list[dict], preds: dict, threshold: float) -> dict:
    rows = scorer.collect(gold, preds)
    out = {}
    for src in sorted({r["source"] for r in rows}):
        m = scorer.at_threshold([r for r in rows if r["source"] == src], threshold)
        out[src] = {"n_fields": m["n_fields"], "accepted": m["accepted"], "correct": m["correct"],
                    "wrong": m["wrong"], "hallucinated": m["hallucinated"],
                    "precision": m["precision"] if m["accepted"] else None, "coverage": m["coverage"],
                    "net_saving_pct_e100": scorer.net_saving(m, 1.0, 100.0)["saving_pct"]}
    return out


def score_run(run_dir: Path, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Score preds.jsonl against the gold subset with the same doc_ids and write score.json (identical to
    `5_score.py --gold gold.jsonl --pred preds.jsonl --threshold T --json score.json`). Stores a summary in run.json.

    gold.jsonl is trimmed to the predicted doc_ids when documents are missing from preds (failed documents).
    Raises ValueError when preds contain doc_ids without gold."""
    run_dir = Path(run_dir)
    scorer = load_scorer()
    gold_path, preds_path = run_dir / "gold.jsonl", run_dir / "preds.jsonl"
    if not gold_path.exists():
        raise FileNotFoundError(f"{run_dir.name}: no gold.jsonl (run without gold cannot be scored)")
    if not preds_path.exists():
        raise FileNotFoundError(f"{run_dir.name}: no preds.jsonl")
    gold_all = scorer.read_jsonl(gold_path)
    preds = scorer.load_preds(preds_path)
    gold_ids = {r["doc_id"] for r in gold_all}
    missing = sorted(set(preds) - gold_ids)
    if missing:
        raise ValueError(f"{run_dir.name}: {len(missing)} predicted doc_ids have no gold, e.g. {missing[:3]}")
    gold = [r for r in gold_all if r["doc_id"] in preds]
    if len(gold) != len(gold_all):
        write_jsonl(gold_path, gold)
    res = scorer.score(gold, preds, threshold=threshold, review_cost=1.0, error_cost=100.0)
    atomic_write_text(run_dir / "score.json", json.dumps(res, indent=2))
    # savings for other error costs come from the same counts (the sweep behind score() is the slow part)
    saving = {f"net_saving_pct_e{int(e)}": scorer.net_saving(res["at_threshold"], 1.0, e)["saving_pct"]
              for e in ERROR_COSTS}
    d, z, best = res["declared"], res["at_threshold_0"], res["business"]
    summary = {
        "threshold": threshold, "n_docs": len(gold), "n_fields": z["n_fields"],
        "accepted": d["accepted"], "correct": res["at_threshold"]["correct"], "wrong": d["wrong"],
        "hallucinated": d["hallucinated"], "precision": d["precision"] if d["accepted"] else None,
        "coverage": d["coverage"], **saving,
        "best_threshold_e100": best["threshold"], "best_threshold_net_e100": best["saving_pct"],
        "by_source": _by_source(scorer, gold, preds, threshold),
        "scored_at": _now().isoformat(timespec="seconds"),
    }
    update_run(run_dir, summary=summary)
    return summary


# ---------------------------------------------------------------- index

def build_row(run_dir: Path) -> dict:
    """One index row, derived only from the run folder (run.json, manifest.json)."""
    run_dir = Path(run_dir)
    run = read_run(run_dir)
    man = {}
    if (run_dir / "manifest.json").exists():
        try:
            man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        except ValueError:
            man = {}
    pipe = man.get("pipeline") or {}
    fp = man.get("fingerprint") or {}
    s = run.get("summary") or {}
    models = run.get("models") or ([pipe["model"]] if pipe.get("model") else [])
    return {
        "run_id": run["run_id"], "name": run["name"], "split": run.get("split"),
        "created_at": run.get("created_at"), "status": run.get("status"), "tags": run.get("tags", []),
        "provenance": run.get("provenance", "manifest" if man else "unknown"),
        "n_requested": run.get("n_requested") or man.get("n_requested"),
        "n_docs": s.get("n_docs"), "n_fields": s.get("n_fields"), "models": models,
        "pipeline_sha256": fp.get("pipeline_sha256"),
        "prompt_version": fp.get("prompt_version") or pipe.get("prompt_version"),
        "decision_sha256": run.get("decision_sha256"),
        "threshold": s.get("threshold"), "accepted": s.get("accepted"), "correct": s.get("correct"),
        "wrong": s.get("wrong"), "hallucinated": s.get("hallucinated"), "precision": s.get("precision"),
        "coverage": s.get("coverage"), "net_saving_pct_e20": s.get("net_saving_pct_e20"),
        "net_saving_pct_e100": s.get("net_saving_pct_e100"), "net_saving_pct_e500": s.get("net_saving_pct_e500"),
        "best_threshold_e100": s.get("best_threshold_e100"),
        "best_threshold_net_e100": s.get("best_threshold_net_e100"), "by_source": s.get("by_source", {}),
    }


def load_index(runs_dir: Path | None = None) -> list[dict]:
    path = (Path(runs_dir) if runs_dir else RUNS_DIR) / INDEX_NAME
    return read_jsonl(path) if path.exists() else []


def append_index(run_dir: Path) -> dict:
    """Add the run's row to <runs_dir>/index.jsonl, replacing an existing row with the same run_id.
    Atomic (temp file + os.replace) and serialised by a file lock, so parallel runs cannot corrupt the index."""
    run_dir = Path(run_dir)
    row = build_row(run_dir)
    path = run_dir.parent / INDEX_NAME
    with _locked(path):
        rows = [r for r in load_index(run_dir.parent) if r.get("run_id") != row["run_id"]]
        rows.append(row)
        write_jsonl(path, rows)
    return row


def rebuild_index(runs_dir: Path | None = None) -> list[dict]:
    runs = Path(runs_dir) if runs_dir else RUNS_DIR
    rows = [build_row(p.parent) for p in sorted(runs.glob("*/run.json"))]
    rows.sort(key=lambda r: (r.get("created_at") or "", r["run_id"]))
    with _locked(runs / INDEX_NAME):
        write_jsonl(runs / INDEX_NAME, rows)
    return rows


def get_run(run_id: str, runs_dir: Path | None = None) -> dict:
    """run.json content plus `path` (the folder). Raises KeyError for an unknown run_id."""
    runs = Path(runs_dir) if runs_dir else RUNS_DIR
    if not (runs / run_id / "run.json").exists():
        raise KeyError(run_id)
    return {**read_run(runs / run_id), "path": str(runs / run_id)}


def resolve_run(ref: str, runs_dir: Path | None = None) -> Path:
    """A run folder from a run_id, an unambiguous run_id prefix/name, or a path."""
    runs = Path(runs_dir) if runs_dir else RUNS_DIR
    if (Path(ref) / "run.json").exists():
        return Path(ref)
    if (runs / ref / "run.json").exists():
        return runs / ref
    hits = [p.parent for p in runs.glob("*/run.json") if ref in p.parent.name]
    if len(hits) == 1:
        return hits[0]
    raise KeyError(f"{ref!r}: {'ambiguous' if hits else 'no such run'}")


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("rebuild")
    sc = sub.add_parser("score")
    sc.add_argument("run")
    sc.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for r in load_index():
            ns = r.get("net_saving_pct_e100")
            print(f"{r['run_id']:55s} {str(r.get('split')):12s} {str(r.get('status')):10s} docs={r.get('n_docs')} "
                  f"net@100={'n/a' if ns is None else format(ns, '.1%')}")
    elif a.cmd == "rebuild":
        print(f"index rebuilt: {len(rebuild_index())} runs")
    else:
        run_dir = resolve_run(a.run)
        s = score_run(run_dir, a.threshold)
        append_index(run_dir)
        print(f"{run_dir.name}: docs={s['n_docs']} accepted={s['accepted']} wrong={s['wrong']} "
              f"net@100={s['net_saving_pct_e100']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
