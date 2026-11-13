"""Thin adapter around the official scorer (5_score.py), loaded by path with importlib. The scorer is not modified.

choose_threshold(gold_records, predictions, error_cost=100.0) -> decision dict
- Sweeps thresholds on the given (calibration) set with the official score() and takes business.threshold.
- If no positive saving exists (business.threshold is None or saving <= 0): all-abstain. Threshold 1.0, and every
  prediction is set to null/0 before counting, because threshold 1.0 alone would still accept confidence 1.0.
- Counts and net_saving_pct at the chosen threshold come from the official scorer's declared block.

CLI: python -m evaluation.select_threshold --gold CAL_GOLD.jsonl --pred CAL_PRED.jsonl --manifest RUN.manifest.json
       --out submission/decision.json [--error-cost 100]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from evaluation.validate import validate_predictions

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_VERSION = 1
_scorer = None


def load_scorer():
    """Load 5_score.py by path, once. Its functions are used unchanged."""
    global _scorer
    if _scorer is None:
        spec = importlib.util.spec_from_file_location("score5", ROOT / "5_score.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _scorer = mod
    return _scorer


def _pred_map(predictions: list[dict]) -> dict:
    """doc_id -> fields, the same shape as the scorer's load_preds()."""
    return {p["doc_id"]: p.get("fields", {}) for p in predictions}


def _all_abstain(preds: dict) -> dict:
    return {doc: {f: {"value": None, "confidence": 0.0} for f in fields} for doc, fields in preds.items()}


def choose_threshold(gold_records: list[dict], predictions: list[dict], error_cost: float = 100.0,
                     manifest: dict | None = None) -> dict:
    errors = validate_predictions(gold_records, predictions)
    if errors:
        raise ValueError(f"invalid predictions, first error: {errors[0]}")
    scorer = load_scorer()
    pmap = _pred_map(predictions)
    sweep = scorer.score(gold_records, pmap, review_cost=1.0, error_cost=error_cost)
    best = sweep["business"]
    if best["threshold"] is None or best["saving_pct"] <= 0:
        threshold, abstain_all, count_on = 1.0, True, _all_abstain(pmap)
        method = "all_abstain: no threshold gives positive saving at error cost %g" % error_cost
    else:
        threshold, abstain_all, count_on = float(best["threshold"]), False, pmap
        method = "empirical_threshold: official scorer sweep on this set (not a calibrated probability)"
    res = scorer.score(gold_records, count_on, threshold=threshold, review_cost=1.0, error_cost=error_cost)
    d = res["declared"]
    decision = {
        "contract_version": CONTRACT_VERSION,
        "run_id": (manifest or {}).get("run_id"),
        "threshold": threshold,
        "abstain_all": abstain_all,
        "method": method,
        "pipeline": None if abstain_all else (manifest or {}).get("pipeline"),
        "error_cost": error_cost,
        "n_docs": len(gold_records),
        "n_fields": res["at_threshold_0"]["n_fields"],
        "accepted": d["accepted"],
        "wrong": d["wrong"],
        "hallucinated": d["hallucinated"],
        "net_saving_pct": d["net_saving_pct"],
    }
    if not abstain_all and decision["pipeline"] is None:
        raise ValueError("a positive decision needs the pipeline block from the run manifest")
    return decision


def _read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--error-cost", type=float, default=100.0)
    a = ap.parse_args(argv)
    gold = _read_jsonl(a.gold)
    preds = _read_jsonl(a.pred)
    man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    if man.get("contract_version") != CONTRACT_VERSION:
        raise SystemExit("ERROR: manifest has an unknown contract_version")
    if man.get("n_written") != len(preds):
        raise SystemExit(f"ERROR: manifest n_written={man.get('n_written')} but prediction file has {len(preds)} rows")
    if man.get("n_failed"):
        print(f"WARNING: manifest reports {man['n_failed']} failed document(s); they are not in the prediction file.",
              file=sys.stderr)
    if man.get("n_abstained_after_errors"):
        print(f"WARNING: {man['n_abstained_after_errors']} document(s) were abstained after API/job errors. "
              "They are not measured predictions.", file=sys.stderr)
    decision = choose_threshold(gold, preds, a.error_cost, manifest=man)
    decision["n_abstained_after_errors"] = man.get("n_abstained_after_errors")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
