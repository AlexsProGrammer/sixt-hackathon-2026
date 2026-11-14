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


DEFAULT_SELECTOR_GRID = [
    {"min_n": mn, "min_groups": mg, "evidence": ev, "min_families": 1}
    for ev in ("grounded_text", "grounded_any", "grounded_text|views_agree")
    for mg in (2, 3)
    for mn in (2, 3, 5)
]


def apply_selector_to_rows(rows: list[dict], selector: dict) -> dict[str, dict]:
    """Apply a selector.json to field-table rows, returning a scorer-compatible pmap."""
    from uncertainty.decision import _score_calibrator, evidence_satisfied, views_agree

    cell_map = {(c["source"], c["family"], c["field"]): c for c in selector.get("cells") or []}
    kind_rules = selector.get("kind_rules") or {"json": "never", "boolean": "views_only"}
    calibrator = selector.get("calibrator")
    decl_thr = float(selector.get("declared_threshold", 0.99))

    pmap: dict[str, dict] = {}
    for r in rows:
        doc_id = r["doc_id"]
        field = r["field"]
        doc_fields = pmap.setdefault(doc_id, {})
        if not r.get("pred_present"):
            doc_fields[field] = {"value": None, "confidence": 0.0}
            continue
        kind = r.get("kind", "string")
        if kind_rules.get(kind) == "never":
            doc_fields[field] = {"value": None, "confidence": 0.0}
            continue
        cell = cell_map.get((str(r["source"]), str(r["family"]), str(field)))
        if cell is None:
            doc_fields[field] = {"value": None, "confidence": 0.0}
            continue
        if kind_rules.get(kind) == "views_only" and not views_agree(r):
            doc_fields[field] = {"value": None, "confidence": 0.0}
            continue
        req = cell.get("require") or {}
        if not evidence_satisfied(r, req.get("evidence", "none")):
            doc_fields[field] = {"value": None, "confidence": 0.0}
            continue
        min_families = int(req.get("min_families", 1) or 1)
        if min_families > 1:
            fam_agree = r.get("families_agreeing")
            if fam_agree is None or int(fam_agree) < min_families:
                doc_fields[field] = {"value": None, "confidence": 0.0}
                continue
        if calibrator is not None:
            if int(cell.get("errors", 0)) > 0:
                doc_fields[field] = {"value": None, "confidence": 0.0}
                continue
            prob = _score_calibrator(calibrator, r)
            if prob < decl_thr:
                doc_fields[field] = {"value": None, "confidence": 0.0}
                continue
            conf = float(prob)
        else:
            conf = 1.0
        doc_fields[field] = {"value": r.get("pred_value"), "confidence": conf}
    return pmap


def _by_family_from_rows(rows: list[dict], pmap: dict, threshold: float, error_cost: float) -> dict[str, dict]:
    """Per-family breakdown of selector-accepted rows using field-table labels."""
    by_fam: dict[str, dict] = {}
    for r in rows:
        fam = str(r["family"])
        st = by_fam.setdefault(fam, {"n_fields": 0, "accepted": 0, "correct": 0, "wrong": 0, "hallucinated": 0})
        st["n_fields"] += 1
        pred = (pmap.get(r["doc_id"], {}) or {}).get(r["field"]) or {}
        if pred.get("value") is not None and float(pred.get("confidence", 0.0)) >= threshold:
            st["accepted"] += 1
            outc = r.get("outcome")
            if outc == "correct":
                st["correct"] += 1
            elif outc == "hallucinated":
                st["hallucinated"] += 1
            else:
                st["wrong"] += 1
    for st in by_fam.values():
        errs = st["wrong"] + st["hallucinated"]
        st["net_saving_pct"] = (st["correct"] - error_cost * errs) / st["n_fields"] if st["n_fields"] else 0.0
    return dict(sorted(by_fam.items()))


def score_selector(
    gold: list[dict],
    rows: list[dict],
    selector: dict,
    *,
    threshold: float | None = 0.99,
    error_cost: float = 100.0,
) -> dict:
    """Score a selector against gold using 5_score.py, with per-family breakdown."""
    pmap = apply_selector_to_rows(rows, selector)
    metrics = declared_at(gold, pmap, threshold, error_cost)
    if threshold is None:
        by_family = _by_family_from_rows(rows, _all_abstain(pmap), 1.0, error_cost)
    else:
        by_family = _by_family_from_rows(rows, pmap, threshold, error_cost)
    metrics["families_with_booked"] = sum(1 for st in by_family.values() if st["accepted"] > 0)
    metrics["by_family"] = by_family
    return metrics


def freeze_selector(
    fit_rows: list[dict],
    select_gold: list[dict],
    select_rows: list[dict],
    *,
    param_grid: list[dict] | None = None,
    threshold: float = 0.99,
    error_cost: float = 100.0,
    fit_run_ids: tuple[str, ...] | list[str] = (),
    fit_fingerprint: dict | None = None,
) -> tuple[dict, dict | None]:
    """Select selector hyperparameters on dev_select, train on fit, and freeze."""
    from evaluation.train_selector import build_selector

    grid = param_grid or DEFAULT_SELECTOR_GRID
    candidates: list[dict] = []
    best_entry = None
    best_selector = None
    best_key = None

    for params in grid:
        sel = build_selector(
            fit_rows,
            min_n=params["min_n"],
            min_groups=params["min_groups"],
            evidence=params["evidence"],
            min_families=params.get("min_families", 1),
            declared_threshold=threshold,
            run_ids=fit_run_ids,
            split="fit",
            fingerprint=fit_fingerprint,
            error_cost=error_cost,
        )
        m = score_selector(select_gold, select_rows, sel, threshold=threshold, error_cost=error_cost)
        entry = {
            "params": params,
            "n_cells": len(sel["cells"]),
            "accepted": m["accepted"],
            "wrong": m["wrong"],
            "hallucinated": m["hallucinated"],
            "families_with_booked": m["families_with_booked"],
            "net_saving_pct": m["net_saving_pct"],
            "metrics": m,
        }
        candidates.append(entry)
        if m["net_saving_pct"] > 0 and m["accepted"] > 0:
            errs = m["wrong"] + m["hallucinated"]
            key = (round(m["net_saving_pct"], 9), -errs, m["accepted"], params["min_groups"], params["min_n"])
            if best_key is None or key > best_key:
                best_key = key
                best_entry = entry
                best_selector = sel

    if best_entry is not None and best_selector is not None:
        frozen = {
            "status": "frozen",
            "method": "selector",
            "threshold": threshold,
            "params": best_entry["params"],
            "n_cells": best_entry["n_cells"],
            "dev_select": best_entry["metrics"],
            "error_cost": error_cost,
            "candidates": [{k: v for k, v in c.items() if k != "metrics"} for c in candidates],
        }
    else:
        frozen = {
            "status": "frozen",
            "method": None,
            "threshold": None,
            "params": None,
            "n_cells": 0,
            "dev_select": None,
            "note": f"no selector configuration has positive dev_select saving at error cost {error_cost:g}",
            "error_cost": error_cost,
            "candidates": [{k: v for k, v in c.items() if k != "metrics"} for c in candidates],
        }
    return frozen, best_selector


def audit_selector(
    frozen: dict,
    selector: dict | None,
    audit_gold: list[dict],
    audit_rows: list[dict],
    *,
    error_cost: float = 100.0,
) -> dict:
    """Apply frozen selector once to dev_audit without re-optimisation."""
    thr = frozen.get("threshold")
    if thr is None or selector is None:
        main = score_selector(audit_gold, audit_rows, {"cells": []}, threshold=None, error_cost=error_cost)
        s20 = s500 = 0.0
    else:
        main = score_selector(audit_gold, audit_rows, selector, threshold=thr, error_cost=error_cost)
        s20 = score_selector(audit_gold, audit_rows, selector, threshold=thr, error_cost=20.0)["net_saving_pct"]
        s500 = score_selector(audit_gold, audit_rows, selector, threshold=thr, error_cost=500.0)["net_saving_pct"]
    return {
        "status": "audited",
        "method": frozen.get("method"),
        "threshold": thr,
        "params": frozen.get("params"),
        "audit": main,
        "net_saving_pct_error_cost_20": s20,
        "net_saving_pct_error_cost_500": s500,
        "error_cost": error_cost,
    }


def decide_selector(
    frozen: dict,
    audit_result: dict | None,
    *,
    selector_path: str | None,
    selector_sha256: str | None,
    select_manifest: dict,
    audit_manifest: dict | None,
    min_booked: int = 300,
    min_families: int = 3,
) -> dict:
    """Gate G1 release decision for selector (decision file contract_version=2)."""
    sel_pipe = select_manifest.get("pipeline") or {}
    aud_pipe = (audit_manifest or {}).get("pipeline") or {}
    audit_metrics = (audit_result or {}).get("audit") or {}
    criteria = {
        "select_run_complete": select_manifest.get("run_complete") is True,
        "audit_run_complete": bool(audit_manifest) and audit_manifest.get("run_complete") is True,
        "provenance_present": bool(select_manifest.get("fingerprint")) and bool(audit_manifest and audit_manifest.get("fingerprint")),
        "independent_audit": bool(audit_manifest) and audit_manifest.get("run_id") != select_manifest.get("run_id"),
        "same_pipeline": {k: v for k, v in sel_pipe.items() if k != "uq_method"}
                         == {k: v for k, v in aud_pipe.items() if k != "uq_method"} and bool(aud_pipe),
        "candidate_frozen": frozen.get("threshold") is not None and bool(selector_path) and bool(selector_sha256),
        "audit_net_saving_positive": audit_metrics.get("net_saving_pct", 0.0) > 0,
        "audit_accepted_at_least_min": audit_metrics.get("accepted", 0) >= min_booked,
        "audit_families_at_least_min": audit_metrics.get("families_with_booked", 0) >= min_families,
    }
    diagnostic = audit_metrics.get("wilson_diagnostic")
    incomplete = not (criteria["select_run_complete"] and criteria["audit_run_complete"]
                      and criteria["provenance_present"])
    active = all(criteria.values())
    status = "measurement_incomplete" if incomplete else ("active" if active else "all_abstain")
    decision = {
        "contract_version": 2,
        "status": status,
        "abstain_all": not active,
        "threshold": frozen["threshold"] if active else 1.0,
        "method": "selector" if active else None,
        "selector_path": selector_path,
        "selector_sha256": selector_sha256,
        "pipeline": None,
        "criteria": criteria,
        "diagnostic_wilson_audit": diagnostic,
        "frozen_on_dev_select": frozen.get("dev_select"),
        "audit": audit_result,
    }
    if active:
        pipe = dict(aud_pipe)
        pipe["uq_method"] = "selector"
        decision["pipeline"] = pipe
        decision["pipeline_sha256"] = sha256_obj(pipe)
        decision["method_text"] = "active: selector trained on fit, frozen on dev_select, passed Gate G1 on dev_audit"
    else:
        failing = [k for k, v in criteria.items() if not v]
        decision["method_text"] = "all_abstain: " + (f"measurement incomplete ({', '.join(failing)})" if incomplete
                                                     else f"criteria not met ({', '.join(failing)})")
    return decision


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

    fs = sub.add_parser("freeze-selector", help="dev_select: choose selector params, train on fit, freeze")
    fs.add_argument("--fit-runs", nargs="+", required=True)
    fs.add_argument("--select-run", required=True)
    fs.add_argument("--out-frozen", required=True)
    fs.add_argument("--out-selector", required=True)
    fs.add_argument("--threshold", type=float, default=0.99)
    fs.add_argument("--error-cost", type=float, default=100.0)
    fs.add_argument("--runs-dir", help="default: results/runs")
    fs.add_argument("--splits-dir", help="default: data/splits")

    aus = sub.add_parser("audit-selector", help="dev_audit: apply frozen selector once")
    aus.add_argument("--frozen", required=True)
    aus.add_argument("--selector", required=True)
    aus.add_argument("--audit-run", required=True)
    aus.add_argument("--out", required=True)
    aus.add_argument("--error-cost", type=float, default=100.0)
    aus.add_argument("--runs-dir", help="default: results/runs")

    ds = sub.add_parser("decide-selector", help="Gate G1 release decision for selector (decision.json v2)")
    ds.add_argument("--frozen", required=True)
    ds.add_argument("--audit", required=True)
    ds.add_argument("--selector", required=True)
    ds.add_argument("--select-manifest", required=True)
    ds.add_argument("--audit-manifest", required=True)
    ds.add_argument("--min-booked", type=int, default=300)
    ds.add_argument("--min-families", type=int, default=3)
    ds.add_argument("--out", required=True)
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
    if a.cmd == "freeze-selector":
        from evaluation import field_table, registry
        from evaluation.train_selector import load_training_rows

        runs_dir = Path(a.runs_dir) if a.runs_dir else None
        splits_dir = Path(a.splits_dir) if a.splits_dir else None
        fit_rows, fit_run_ids, fit_fp = load_training_rows(
            a.fit_runs, split="fit", runs_dir=runs_dir, splits_dir=splits_dir
        )
        sel_dir = registry.resolve_run(a.select_run, runs_dir=runs_dir)
        sel_man = json.loads((sel_dir / "manifest.json").read_text(encoding="utf-8"))
        sel_gold = _read_jsonl(str(sel_dir / "gold.jsonl"))
        sel_rows = field_table.load_field_table(sel_dir)
        frozen, selector = freeze_selector(
            fit_rows,
            sel_gold,
            sel_rows,
            threshold=a.threshold,
            error_cost=a.error_cost,
            fit_run_ids=fit_run_ids,
            fit_fingerprint=fit_fp,
        )
        frozen["select_run_id"] = sel_man.get("run_id")
        if selector is not None:
            _write(a.out_selector, selector)
        _write(a.out_frozen, frozen)
        return 0
    if a.cmd == "audit-selector":
        from evaluation import field_table, registry

        runs_dir = Path(a.runs_dir) if a.runs_dir else None
        frozen = json.loads(Path(a.frozen).read_text(encoding="utf-8"))
        selector = json.loads(Path(a.selector).read_text(encoding="utf-8")) if Path(a.selector).exists() else None
        aud_dir = registry.resolve_run(a.audit_run, runs_dir=runs_dir)
        aud_man = json.loads((aud_dir / "manifest.json").read_text(encoding="utf-8"))
        aud_gold = _read_jsonl(str(aud_dir / "gold.jsonl"))
        aud_rows = field_table.load_field_table(aud_dir)
        res = audit_selector(frozen, selector, aud_gold, aud_rows, error_cost=a.error_cost)
        res["audit_run_id"] = aud_man.get("run_id")
        res["audit_manifest_run_complete"] = aud_man.get("run_complete") is True
        _write(a.out, res)
        return 0
    if a.cmd == "decide-selector":
        frozen = json.loads(Path(a.frozen).read_text(encoding="utf-8"))
        res = json.loads(Path(a.audit).read_text(encoding="utf-8"))
        sel_man = json.loads(Path(a.select_manifest).read_text(encoding="utf-8"))
        aud_man = json.loads(Path(a.audit_manifest).read_text(encoding="utf-8"))
        sel_path = Path(a.selector)
        sel_sha = hashlib.sha256(sel_path.read_bytes()).hexdigest() if sel_path.exists() else None
        dec = decide_selector(
            frozen,
            res,
            selector_path=a.selector,
            selector_sha256=sel_sha,
            select_manifest=sel_man,
            audit_manifest=aud_man,
            min_booked=a.min_booked,
            min_families=a.min_families,
        )
        _write(a.out, dec)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
