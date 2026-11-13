"""Batch runner (T03): one command runs a frozen subset end to end and leaves a complete run folder.

    python -m evaluation.run_batch --split smoke --name smoke-baseline --mode llm
    python -m evaluation.run_batch --split select --name sel-k1 --mode llm --workers 4
    python -m evaluation.run_batch --input data/unified/dev.jsonl --random 60 --seed 7 --name dev-sample --mode llm
    python -m evaluation.run_batch --split smoke --name smoke-decision --decision submission/decision.json
    python -m evaluation.run_batch --split smoke --name smoke-abstain --abstain-all        # no API call

Steps: select documents -> new run folder (T02) -> `4_extract.py --run-dir` as a subprocess (exact CLI parity with
what `run_hidden.sh` executes; it also writes preds, diagnostics, samples, manifest, gold subset, score.json and
the index row) -> optional re-score at --threshold -> field table (fields.jsonl) -> report (report.md/json).

Selection
  --split NAME     frozen split from data/splits/ (fit, select, audit, audit2, smoke). Hash checked.
  --input FILE     any jsonl with the dev record layout (gold needed for scoring and the field table)
  --limit N        first N documents of the selection
  --random N --seed S   N documents stratified by (source, family), deterministic

Every other option (--mode, --samples, --workers, --decision, --abstain-all, --uq-method, --cache-dir, ...) is
forwarded unchanged to 4_extract.py. Options that select documents must not be forwarded: use the ones above.

Audit discipline: `audit` and `audit2` print a warning, and the run is tagged "audit". They are meant to run once
per release candidate (master plan, decision gates).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import registry, splits  # noqa: E402
from evaluation.field_table import build_field_table, outcome_counts  # noqa: E402
from evaluation.report import write_report  # noqa: E402

FORBIDDEN_FORWARD = ("--data", "--out", "--run-dir", "--run-name", "--limit")
AUDIT_SPLITS = ("audit", "audit2")


def select_records(a) -> tuple[list[dict], dict]:
    """(records, selection info). Records keep their gold, which is only used for scoring."""
    if bool(a.split) == bool(a.input):
        raise SystemExit("ERROR: give exactly one of --split NAME or --input FILE.")
    if a.split:
        recs = splits.load_split(a.split, Path(a.splits_dir) if a.splits_dir else None)
        info = {"kind": "split", "split": a.split}
    else:
        recs = splits.read_jsonl(Path(a.input))
        info = {"kind": "input", "input": a.input}
    n_all = len(recs)
    if a.random is not None:
        if a.random < 1:
            raise SystemExit("ERROR: --random needs a positive number.")
        recs = splits.stratified_sample(recs, a.random, a.seed)
        info.update({"random": a.random, "seed": a.seed})
    if a.limit:
        recs = recs[: a.limit]
        info["limit"] = a.limit
    if a.source:
        recs = [r for r in recs if r.get("source_dataset") == a.source]
        info["source"] = a.source
    if not recs:
        raise SystemExit("ERROR: the selection is empty.")
    info.update({"n_available": n_all, "n_docs": len(recs),
                 "ids_sha256": hashlib.sha256("\n".join(sorted(r["doc_id"] for r in recs)).encode()).hexdigest()})
    return recs, info


def whole_file(a, info: dict) -> Path | None:
    """The existing file to hand to 4_extract.py when the selection is a complete file (keeps input_ref stable)."""
    if info.get("random") is not None or info.get("limit"):
        return None
    if a.split:
        return Path(a.splits_dir or ROOT / "data" / "splits") / f"{a.split}.jsonl"
    return Path(a.input)


def run_extract(run_dir: Path, data: Path, name: str, forward: list[str]) -> int:
    cmd = [sys.executable, str(ROOT / "4_extract.py"), "--data", str(data), "--run-dir", str(run_dir),
           "--run-name", name, *forward]
    print("+ " + " ".join(cmd[1:]), file=sys.stderr)
    return subprocess.run(cmd, cwd=ROOT).returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Unknown options are forwarded to 4_extract.py.")
    ap.add_argument("--split", help="frozen split name in data/splits/")
    ap.add_argument("--input", help="jsonl with dev-layout records (alternative to --split)")
    ap.add_argument("--source", help="keep only records of this source_dataset (e.g. extractbench)")
    ap.add_argument("--splits-dir", help="default: data/splits")
    ap.add_argument("--limit", type=int, help="first N documents of the selection")
    ap.add_argument("--random", type=int, metavar="N", help="N documents stratified by (source, family)")
    ap.add_argument("--seed", type=int, default=13, help="seed of --random (default 13)")
    ap.add_argument("--name", required=True, help="run name (the folder is <timestamp>-<name>-<hash>)")
    ap.add_argument("--threshold", type=float, help="declared threshold for score.json (default: decision file or 0.99)")
    ap.add_argument("--tag", action="append", default=[], help="extra run tag (repeatable)")
    ap.add_argument("--runs-dir", help="default: results/runs")
    ap.add_argument("--no-report", action="store_true", help="skip fields.jsonl and report.md/json")
    a, forward = ap.parse_known_args(argv)
    bad = [f for f in forward if f.split("=", 1)[0] in FORBIDDEN_FORWARD]
    if bad:
        raise SystemExit(f"ERROR: {', '.join(bad)} is set by run_batch; use --split/--input/--limit/--random/--name.")
    if "--threshold" in forward:
        raise SystemExit("ERROR: --threshold is a run_batch option, give it before the forwarded options.")

    recs, info = select_records(a)
    if a.split in AUDIT_SPLITS:
        print(f"WARNING: {a.split} is an audit split: run it ONCE per release candidate and report it as is "
              f"(a change after seeing these numbers needs a fresh audit split).", file=sys.stderr)
    has_gold = all("gold" in r for r in recs)
    if not has_gold:
        print("NOTE: records carry no gold: no score, field table or report will be made.", file=sys.stderr)

    tags = ["batch", *([a.split] if a.split else []), *(["audit"] if a.split in AUDIT_SPLITS else []), *a.tag]
    run_dir = registry.new_run(a.name, a.split or Path(a.input).stem, tags,
                               runs_dir=Path(a.runs_dir) if a.runs_dir else None, extra={"selection": info})
    data = whole_file(a, info)
    if data is None:
        data = run_dir / "selection.jsonl"
        registry.write_jsonl(data, recs)
    print(f"run folder: {run_dir}  ({info['n_docs']} docs of {info['n_available']})", file=sys.stderr)

    code = run_extract(run_dir, data, a.name, forward)
    if not (run_dir / "preds.jsonl").exists():
        registry.update_run(run_dir, status="failed")
        registry.append_index(run_dir)
        print("ERROR: 4_extract.py wrote no predictions.", file=sys.stderr)
        return code or 1

    summary = None
    if has_gold:
        run = registry.read_run(run_dir)
        want = a.threshold
        if want is not None and (run.get("summary") or {}).get("threshold") != want:
            registry.score_run(run_dir, want)
        elif "summary" not in run:
            registry.score_run(run_dir, want if want is not None else registry.DEFAULT_THRESHOLD)
        registry.append_index(run_dir)
        summary = registry.read_run(run_dir).get("summary")
        if not a.no_report:
            rows = build_field_table(run_dir)
            write_report(run_dir, rows)
            print(f"field table: {len(rows)} rows {json.dumps(outcome_counts(rows))}", file=sys.stderr)
            print(f"report: {run_dir / 'report.md'}", file=sys.stderr)
    if summary:
        print(f"{run_dir.name}: docs={summary['n_docs']} accepted={summary['accepted']} wrong={summary['wrong']} "
              f"hallucinated={summary['hallucinated']} net@100={summary['net_saving_pct_e100']:+.2%} "
              f"(threshold {summary['threshold']})")
    else:
        print(run_dir.name)
    return code


if __name__ == "__main__":
    sys.exit(main())
