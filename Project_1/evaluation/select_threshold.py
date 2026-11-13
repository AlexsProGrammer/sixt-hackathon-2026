"""Threshold selection, frozen evaluation and release decision, on top of the official scorer (5_score.py, unchanged).

Three steps, in this order, on separate dev splits:

1. freeze   (dev_select)  every pre-declared method is scored with the official sweep; the best dev_select saving
                          chooses method and threshold. The choice is written with all candidates, regardless of
                          any release rule.
2. audit    (dev_audit)   the frozen method and threshold are applied once, without re-optimisation.
3. decide                 active only if every release criterion holds (see decide()). Otherwise all-abstain.

Diagnostic, not a release gate: the Wilson 95% upper bound of the error rate among accepted fields. Its
assumption is that fields are independent binomial trials. Fields of one document are correlated, so the bound
is optimistic. It is reported next to the audit result and never decides on its own.

Scorer conventions are kept: review cost 1, error cost 100 by default, the official declared block for counts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from evaluation.validate import validate_predictions

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_VERSION = 1
# HEURISTIC, not a statistical result: a release needs at least 30 accepted audit fields. The coding agent chose this
# value during the project as a minimum for a visible audit signal (not from a power or error-bound calculation).
# The team should confirm or replace it before any release.
# The Wilson bound (wilson_diagnostic) is the statistical diagnostic and is reported separately.
MIN_AUDIT_ACCEPTED = 30
SELECTION_ORDER = ("k_agreement_conf", "k_agreement_only", "k_entropy", "k1_grounded")  # tie-break order
DIAGNOSTIC_ERROR_UPPER = 0.01
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


def sha256_obj(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def wilson_upper(errors: int, n: int, z: float = 1.959963984540054) -> float:
    """Upper limit of the two-sided 95% Wilson score interval for an error rate (about 3.8/n with 0 errors)."""
    if n <= 0:
        return 1.0
    p = errors / n
    z2 = z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * ((p * (1 - p) + z2 / (4 * n)) / n) ** 0.5 / (1 + z2 / n)
    return min(1.0, centre + half)


def wilson_diagnostic(errors: int, accepted: int) -> dict:
    upper = wilson_upper(errors, accepted)
    return {"name": "wilson_upper_95_diagnostic", "errors": errors, "accepted": accepted,
            "upper_95": upper, "at_most_1_percent": upper <= DIAGNOSTIC_ERROR_UPPER,
            "assumption": ("binomial model, accepted fields treated as independent; fields of one document are "
                           "correlated, so the bound is optimistic. Diagnostic only; not a release gate.")}


def _pred_map(predictions: list[dict]) -> dict:
    return {p["doc_id"]: p.get("fields", {}) for p in predictions}


def _all_abstain(pmap: dict) -> dict:
    return {doc: {f: {"value": None, "confidence": 0.0} for f in fields} for doc, fields in pmap.items()}


def declared_at(gold: list[dict], pmap: dict, threshold: float | None, error_cost: float) -> dict:
    """Counts and rates at a fixed threshold, from the official scorer. None means all-abstain."""
    scorer = load_scorer()
    if threshold is None:
        pmap, threshold = _all_abstain(pmap), 1.0  # threshold 1.0 alone would still accept confidence 1.0
    res = scorer.score(gold, pmap, threshold=threshold, review_cost=1.0, error_cost=error_cost)
    d = res["declared"]
    out = {k: d[k] for k in ("accepted", "wrong", "hallucinated", "precision", "coverage",
                             "hallucination_rate", "net_saving_pct")}
    out.update({"threshold": threshold, "all_abstain": threshold == 1.0 and d["accepted"] == 0,
                "n_docs": len(gold), "n_fields": res["at_threshold_0"]["n_fields"],
                "wilson_diagnostic": wilson_diagnostic(d["wrong"] + d["hallucinated"], d["accepted"])})
    return out


def select_candidate(gold: list[dict], pmap: dict, error_cost: float) -> dict:
    """Sweep on one set (dev_select). The result is kept whether or not any release rule later accepts it."""
    scorer = load_scorer()
    best = scorer.score(gold, pmap, review_cost=1.0, error_cost=error_cost)["business"]
    thr = float(best["threshold"]) if best["threshold"] is not None and best["saving_pct"] > 0 else None
    return {"threshold": thr, "dev_select_saving_pct": best["saving_pct"],
            "metrics": declared_at(gold, pmap, thr, error_cost)}


def freeze(gold: list[dict], pred_by_method: dict[str, list[dict]], error_cost: float = 100.0) -> dict:
    """Choose method and threshold on dev_select. Ties go to the earlier name in SELECTION_ORDER."""
    candidates = {}
    for method in SELECTION_ORDER:
        if method not in pred_by_method:
            continue
        pmap = _pred_map(pred_by_method[method])
        candidates[method] = select_candidate(gold, pmap, error_cost)
    eligible = {m: c for m, c in candidates.items() if c["threshold"] is not None}
    if eligible:
        best = max(eligible, key=lambda m: (eligible[m]["dev_select_saving_pct"], -SELECTION_ORDER.index(m)))
        frozen = {"status": "frozen", "method": best, "threshold": eligible[best]["threshold"],
                  "dev_select": eligible[best]["metrics"]}
    else:
        frozen = {"status": "frozen", "method": None, "threshold": None, "dev_select": None,
                  "note": "no method has positive dev_select saving at error cost %g" % error_cost}
    frozen["error_cost"] = error_cost
    frozen["candidates"] = {m: {"threshold": c["threshold"], "dev_select_saving_pct": c["dev_select_saving_pct"],
                                "accepted": c["metrics"]["accepted"], "net_saving_pct": c["metrics"]["net_saving_pct"]}
                            for m, c in candidates.items()}
    return frozen


def audit(frozen: dict, gold: list[dict], predictions: list[dict], error_cost: float = 100.0) -> dict:
    """Apply the frozen threshold once to the audit predictions of the frozen method. No re-optimisation."""
    pmap = _pred_map(predictions)
    thr = frozen.get("threshold")
    main = declared_at(gold, pmap, thr, error_cost)
    sensitivity = {str(c): declared_at(gold, pmap, thr, c)["net_saving_pct"] for c in (20.0, 500.0)}
    return {"status": "audited", "method": frozen.get("method"), "threshold": thr, "audit": main,
            "net_saving_pct_error_cost_20": sensitivity["20.0"], "net_saving_pct_error_cost_500": sensitivity["500.0"],
            "error_cost": error_cost}


def decide(frozen: dict, audit_result: dict | None, select_manifest: dict, audit_manifest: dict | None) -> dict:
    """Release rule. Active only if all criteria hold. Otherwise all-abstain, with the failing criteria listed."""
    sel_pipe = select_manifest.get("pipeline") or {}
    aud_pipe = (audit_manifest or {}).get("pipeline") or {}
    audit_metrics = (audit_result or {}).get("audit") or {}
    criteria = {
        "select_run_complete": select_manifest.get("run_complete") is True,
        "audit_run_complete": bool(audit_manifest) and audit_manifest.get("run_complete") is True,
        "provenance_present": bool(select_manifest.get("fingerprint")) and bool(audit_manifest and audit_manifest.get("fingerprint")),
        "independent_audit": bool(audit_manifest) and audit_manifest.get("run_id") != select_manifest.get("run_id"),
        "same_pipeline_except_method": {k: v for k, v in sel_pipe.items() if k != "uq_method"}
                                      == {k: v for k, v in aud_pipe.items() if k != "uq_method"} and bool(aud_pipe),
        "candidate_frozen": frozen.get("threshold") is not None,
        "audit_accepted_at_least_min": audit_metrics.get("accepted", 0) >= MIN_AUDIT_ACCEPTED,
        "audit_net_saving_positive": audit_metrics.get("net_saving_pct", 0.0) > 0,
    }
    diagnostic = audit_metrics.get("wilson_diagnostic")
    incomplete = not (criteria["select_run_complete"] and criteria["audit_run_complete"]
                      and criteria["provenance_present"])
    active = all(criteria.values())
    if incomplete:
        status = "measurement_incomplete"
    elif active:
        status = "active"
    else:
        status = "all_abstain"
    decision = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "abstain_all": not active,
        "threshold": frozen["threshold"] if active else 1.0,
        "method": frozen.get("method") if active else None,
        "pipeline": None,
        "criteria": criteria,
        "diagnostic_wilson_audit": diagnostic,
        "frozen_on_dev_select": frozen.get("dev_select"),
        "audit": audit_result,
    }
    if active:
        pipe = dict(aud_pipe)
        pipe["uq_method"] = frozen["method"]  # the frozen method is part of the pipeline that the decision binds
        decision["pipeline"] = pipe
        decision["pipeline_sha256"] = sha256_obj(pipe)
        decision["method_text"] = "active: frozen on dev_select, checked once on dev_audit"
    else:
        failing = [k for k, v in criteria.items() if not v]
        decision["method_text"] = "all_abstain: " + (f"measurement incomplete ({', '.join(failing)})" if incomplete
                                                     else f"criteria not met ({', '.join(failing)})")
    return decision


def choose_threshold(gold: list[dict], predictions: list[dict], error_cost: float = 100.0,
                     manifest: dict | None = None) -> dict:
    """In-sample convenience: selection and evaluation on the same set. It can never activate a decision."""
    errors = validate_predictions(gold, predictions)
    if errors:
        raise ValueError(f"invalid predictions, first error: {errors[0]}")
    pmap = _pred_map(predictions)
    cand = select_candidate(gold, pmap, error_cost)
    frozen = {"status": "frozen", "method": None, "threshold": cand["threshold"], "dev_select": cand["metrics"]}
    man = manifest or {}
    result = audit(frozen, gold, predictions, error_cost)
    dec = decide(frozen, result, man, None)
    dec["status"] = "all_abstain"  # in-sample selection never activates a decision
    dec["abstain_all"] = True
    dec["threshold"] = 1.0
    dec["method"] = None
    dec["pipeline"] = None
    dec.pop("pipeline_sha256", None)
    dec["method_text"] = "all_abstain: in-sample only, no independent dev_audit run"
    dec["n_docs"] = len(gold)
    dec["error_cost"] = error_cost
    dec["accepted"] = cand["metrics"]["accepted"]
    dec["wrong"] = cand["metrics"]["wrong"]
    dec["hallucinated"] = cand["metrics"]["hallucinated"]
    dec["net_saving_pct"] = cand["metrics"]["net_saving_pct"]
    return dec


# ---------------------------------------------------------------- CLI

def _read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _manifest_ok(man: dict, n_rows: int) -> None:
    if man.get("contract_version") != CONTRACT_VERSION:
        raise SystemExit("ERROR: manifest has an unknown contract_version")
    if man.get("n_written") != n_rows:
        raise SystemExit(f"ERROR: manifest n_written={man.get('n_written')} but prediction file has {n_rows} rows")


def _write(path: str, obj: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="dev_select: choose method and threshold")
    f.add_argument("--gold", required=True)
    f.add_argument("--pred-dir", required=True, help="folder with <method>_predictions.jsonl from ablation")
    f.add_argument("--manifest", required=True, help="select run manifest")
    f.add_argument("--out", required=True)
    f.add_argument("--error-cost", type=float, default=100.0)
    a_ = sub.add_parser("audit", help="dev_audit: apply the frozen choice once")
    a_.add_argument("--frozen", required=True)
    a_.add_argument("--gold", required=True)
    a_.add_argument("--pred", required=True, help="predictions of the frozen method on dev_audit")
    a_.add_argument("--manifest", required=True, help="audit run manifest")
    a_.add_argument("--out", required=True)
    a_.add_argument("--error-cost", type=float, default=100.0)
    d = sub.add_parser("decide", help="release decision from frozen choice, audit result and manifests")
    d.add_argument("--frozen", required=True)
    d.add_argument("--audit", required=True)
    d.add_argument("--select-manifest", required=True)
    d.add_argument("--audit-manifest", required=True)
    d.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "freeze":
        gold = _read_jsonl(a.gold)
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        pred_dir = Path(a.pred_dir)
        preds = {}
        for p in sorted(pred_dir.glob("*_predictions.jsonl")):
            method = p.name[: -len("_predictions.jsonl")]
            rows = _read_jsonl(str(p))
            if validate_predictions(gold, rows):
                raise SystemExit(f"ERROR: predictions for {method} do not match the gold ids/schema")
            preds[method] = rows
        if not preds:
            raise SystemExit("ERROR: no *_predictions.jsonl in --pred-dir")
        frozen = freeze(gold, preds, a.error_cost)
        frozen["select_run_id"] = man.get("run_id")
        _write(a.out, frozen)
        return 0
    if a.cmd == "audit":
        frozen = json.loads(Path(a.frozen).read_text(encoding="utf-8"))
        gold = _read_jsonl(a.gold)
        rows = _read_jsonl(a.pred)
        man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
        _manifest_ok(man, len(rows))
        if validate_predictions(gold, rows):
            raise SystemExit("ERROR: audit predictions do not match the audit gold ids/schema")
        res = audit(frozen, gold, rows, a.error_cost)
        res["audit_run_id"] = man.get("run_id")
        res["audit_manifest_run_complete"] = man.get("run_complete") is True
        _write(a.out, res)
        return 0
    if a.cmd == "decide":
        frozen = json.loads(Path(a.frozen).read_text(encoding="utf-8"))
        res = json.loads(Path(a.audit).read_text(encoding="utf-8"))
        sel_man = json.loads(Path(a.select_manifest).read_text(encoding="utf-8"))
        aud_man = json.loads(Path(a.audit_manifest).read_text(encoding="utf-8"))
        dec = decide(frozen, res, sel_man, aud_man)
        _write(a.out, dec)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
