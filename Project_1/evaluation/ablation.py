"""Offline ablation over stored samples: identical observations, several decision rules, the official scorer.

    python -m evaluation.ablation --input IN.jsonl --samples RUN.samples.jsonl --manifest RUN.manifest.json \
        [--gold GOLD.jsonl] --out-dir results/ablation_<split>

Contract checks (all raise SplitError, nothing is silently repaired):
- expected documents = the ids of the frozen input file; duplicates are refused; gold keys in the input are refused.
- expected_k = pipeline.samples from the run manifest. A missing sample index never lowers expected_k: the
  document's fields become ineligible (reason incomplete_observations).
- every sample record must belong to an input document; no duplicate document ids; sample indices must be exactly
  0..K-1 without duplicates.
- a document without samples must be explained: unreadable (no text layer, planned abstention, no request) or a
  recorded technical failure (failed_doc_ids / abstained_after_error_doc_ids in the manifest). Anything else is an error.

Methods (no new API calls):
- k1_grounded       sample 0 only (temperature 0): the deterministic K=1 baseline
- k_agreement_only  winner share only
- k_agreement_conf  min(winner share, lowest winner model confidence)
- k_entropy         1 - H/log(K), probly entropy
Methods that need K>1 are skipped with a reason when the run has K=1.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

from evaluation.select_threshold import load_scorer
from uncertainty.decision import make_prediction
from uncertainty.uq_probly import aggregate_v2

ROOT = Path(__file__).resolve().parent.parent
METHODS = ("k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy")
THRESHOLDS = (0.5, 0.8, 0.9, 0.95)


class SplitError(ValueError):
    """The stored inputs do not match the frozen contract. Measurement must not continue."""


def _extractor():
    spec = importlib.util.spec_from_file_location("extract4", ROOT / "4_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def null_fields(schema: dict) -> dict:
    return {n: {"value": None, "confidence": 0.0} for n in schema.get("properties", {})}


def load_split(input_path: Path, samples_path: Path, manifest_path: Path, ex, gold_path: Path | None = None) -> dict:
    records = _read(input_path)
    ids = [r["doc_id"] for r in records]
    if len(set(ids)) != len(ids):
        raise SplitError("duplicate doc_id in the frozen input")
    if any(k.startswith("gold") for r in records for k in r):
        raise SplitError("the frozen input contains gold keys")
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    pipeline = man.get("pipeline") or {}
    k = pipeline.get("samples")
    if not isinstance(k, int) or k < 1:
        raise SplitError("manifest has no valid pipeline.samples")
    technical = set(man.get("failed_doc_ids", [])) | set(man.get("abstained_after_error_doc_ids", []))
    side: dict[str, list[dict]] = {}
    for row in _read(samples_path):
        doc = row.get("doc_id")
        if doc in side:
            raise SplitError(f"duplicate sample record for {doc}")
        if doc not in set(ids):
            raise SplitError(f"sample record for a document not in the input: {doc}")
        samples = row.get("samples")
        idxs = [s.get("sample_idx") for s in samples] if isinstance(samples, list) else []
        if len(idxs) != len(set(idxs)) or set(idxs) != set(range(k)):
            raise SplitError(f"{doc}: sample indices {sorted(idxs)} do not match expected 0..{k - 1}")
        side[doc] = samples
    gold = {}
    if gold_path is not None:
        gold = {r["doc_id"]: r for r in _read(gold_path)}
        missing_gold = [d for d in ids if d not in gold]
        if missing_gold:
            raise SplitError(f"{len(missing_gold)} input document(s) have no gold record")
    unexplained = []
    for rec in records:
        if rec["doc_id"] in side:
            continue
        text = ex.full_text(rec)
        if text is None or not text.strip():
            continue  # planned unreadable: no request was made
        if rec["doc_id"] in technical:
            continue
        unexplained.append(rec["doc_id"])
    if unexplained:
        raise SplitError(f"{len(unexplained)} document(s) without samples and without an explanation, e.g. {unexplained[0]}")
    return {"records": records, "samples": side, "K": k, "pipeline": pipeline, "technical": technical,
            "run_id": man.get("run_id"), "run_complete": man.get("run_complete") is True, "gold": gold}


def predictions_for(method: str, split: dict, ex) -> tuple[list[dict], Counter]:
    rows, reasons = [], Counter()
    k_run = split["K"]
    if method != "k1_grounded" and k_run < 2:
        raise SplitError(f"{method} needs a run with K>1 (this run has K={k_run})")
    for rec in split["records"]:
        doc, schema = rec["doc_id"], rec["schema"]
        if doc in split["samples"]:
            text = ex.full_text(rec)
            if method == "k1_grounded":
                use, k = [s for s in split["samples"][doc] if s["sample_idx"] == 0], 1
            else:
                use, k = split["samples"][doc], k_run
            agg = aggregate_v2(use, schema, text, expected_k=k)
            fields = make_prediction(agg, schema, method=method)
            reasons.update(c["reason"] for c in agg["candidates"].values())
        else:
            text = ex.full_text(rec)
            fields = null_fields(schema)
            reasons.update(["unreadable" if (text is None or not text.strip()) else "technical_failure"]
                           * len(schema.get("properties", {})))
        rows.append({"doc_id": doc, "fields": fields})
    return rows, reasons


def run(input_path: Path, samples_path: Path, manifest_path: Path, out_dir: Path, gold_path: Path | None,
        error_cost: float = 100.0) -> dict:
    scorer = load_scorer()
    ex = _extractor()
    split = load_split(input_path, samples_path, manifest_path, ex, gold_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"run_id": split["run_id"], "run_complete": split["run_complete"], "expected_k": split["K"],
              "n_input_docs": len(split["records"]), "n_docs_with_samples": len(split["samples"]),
              "n_docs_unreadable": sum(1 for r in split["records"] if r["doc_id"] not in split["samples"]
                                       and not (ex.full_text(r) or "").strip()),
              "n_docs_technical_failure": sum(1 for r in split["records"] if r["doc_id"] not in split["samples"]
                                              and (ex.full_text(r) or "").strip()),
              "error_cost": error_cost, "methods": {}}
    gold_list = [split["gold"][r["doc_id"]] for r in split["records"]] if split["gold"] else None
    for method in METHODS:
        if method != "k1_grounded" and split["K"] < 2:
            report["methods"][method] = {"skipped": "needs K>1"}
            continue
        rows, reasons = predictions_for(method, split, ex)
        (out_dir / f"{method}_predictions.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        entry = {"candidate_reasons": dict(reasons)}
        if gold_list is not None:
            pmap = {r["doc_id"]: r["fields"] for r in rows}
            per_threshold = {}
            for t in THRESHOLDS:
                d = scorer.score(gold_list, pmap, threshold=t, review_cost=1.0, error_cost=error_cost)["declared"]
                per_threshold[str(t)] = {k: d[k] for k in ("accepted", "wrong", "hallucinated", "precision",
                                                           "coverage", "hallucination_rate", "net_saving_pct")}
            sweep = scorer.score(gold_list, pmap, review_cost=1.0, error_cost=error_cost)["business"]
            entry.update({"per_threshold": per_threshold,
                          "business_best": {"threshold": sweep["threshold"], "saving_pct": sweep["saving_pct"]}})
        report["methods"][method] = entry
    (out_dir / "ablation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="frozen gold-free input of the split")
    ap.add_argument("--samples", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--gold", help="gold records of the same split; omit to write predictions only")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--error-cost", type=float, default=100.0)
    a = ap.parse_args(argv)
    try:
        rep = run(Path(a.input), Path(a.samples), Path(a.manifest), Path(a.out_dir),
                  Path(a.gold) if a.gold else None, a.error_cost)
    except SplitError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: rep[k] for k in rep if k != "methods"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
