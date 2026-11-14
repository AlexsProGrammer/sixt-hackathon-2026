"""Decision rules over an aggregation (contract: make_prediction(aggregation, schema, *, method, calibration) -> fields).

Fixed, separately named methods. Each returns a score in [0, 1] for eligible candidates. Every other field is null/0.
- k1_grounded       K=1. The model confidence of the single valid observation (the baseline).
- k_agreement_only  K>1. Winner share only (agreement). No model confidence: a pure consistency baseline.
- k_agreement_conf  K>1. min(winner share, lowest model confidence among winner observations).
                    This was the former name "k_agreement"; the rename prevents mixing the two definitions.
- k_entropy         K>1. 1 - H / log(K), H from probly (nats). Uses probly directly in the decision.
                    Uncalibrated: it ignores the model confidence, so three identical grounded answers score 1.0.
- selector          Applies a trained whitelist/calibrator artefact (selector.json, T10) per (source, family, field).
- calibrated        Needs a trained artefact. Not available in this codebase: raises a clear error.

Threshold filtering is not done here. The official scorer applies the declared threshold to these scores.
"""
from __future__ import annotations

import math

from .contracts import ContractError
from .evidence import field_kind

METHODS = ("k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy", "selector", "calibrated")
MULTI_SAMPLE_METHODS = ("k_agreement_only", "k_agreement_conf", "k_entropy")
VALID_EVIDENCE_CLAUSES = ("none", "any", "grounded_text", "grounded_ocr", "grounded_any", "grounded", "views_agree")


def views_agree(features: dict) -> bool:
    """True when at least two valid views agree completely."""
    if features.get("cross_view_agree") is not None:
        return bool(features["cross_view_agree"])
    n = features.get("n_views") if features.get("n_views") is not None else features.get("k_valid")
    return bool(n is not None and n >= 2 and features.get("agreement") == 1.0)


def _check_evidence_clause(features: dict, clause: str) -> bool:
    if clause in ("none", "any"):
        return True
    if clause == "grounded_text":
        if "grounded_text" in features:
            return bool(features["grounded_text"])
        return bool(features.get("grounded"))
    if clause == "grounded_ocr":
        return bool(features.get("grounded_ocr"))
    if clause in ("grounded_any", "grounded"):
        return bool(features.get("grounded_text") or features.get("grounded_ocr") or features.get("grounded"))
    if clause == "views_agree":
        return views_agree(features)
    raise ValueError(f"unknown evidence requirement: {clause!r}")


def evidence_satisfied(features: dict, spec: str | None) -> bool:
    """Evaluate a `|`-separated evidence requirement (e.g. 'grounded_text|views_agree') against features."""
    if not spec or spec in ("none", "any"):
        return True
    clauses = [part.strip() for part in str(spec).split("|") if part.strip()]
    if not clauses:
        return True
    results = [_check_evidence_clause(features, c) for c in clauses]
    return any(results)


def _score_calibrator(calibrator: dict, features: dict) -> float:
    """Evaluate a logistic calibrator stored in selector.json."""
    names = calibrator.get("feature_names") or []
    weights = calibrator.get("weights") or []
    bias = float(calibrator.get("bias", 0.0))
    if len(names) != len(weights):
        raise ContractError("selector calibrator feature_names and weights length mismatch")
    z = bias
    for name, w in zip(names, weights):
        val = features.get(name, 0.0)
        if val is None or isinstance(val, bool):
            val = 1.0 if val else 0.0
        z += float(w) * float(val)
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def score_for(method: str, features: dict) -> float:
    k_expected = features.get("k_expected", features.get("n_views"))
    if method == "k1_grounded":
        if k_expected != 1:
            raise ValueError("k1_grounded needs K=1")
        return float(features["model_conf_min"])
    if method in MULTI_SAMPLE_METHODS and (k_expected is None or k_expected < 2):
        raise ValueError(f"{method} needs K>1")
    if method == "k_agreement_only":
        return float(features["agreement"])
    if method == "k_agreement_conf":
        return min(float(features["agreement"]), float(features["model_conf_min"]))
    if method == "k_entropy":
        if k_expected is None or k_expected < 2:
            raise ValueError("k_entropy needs K>1")
        return 1.0 - float(features["entropy_norm"])
    raise ValueError(f"unknown method: {method}")


def _selector_score(cand: dict, spec: dict, *, cell_map: dict, kind_rules: dict,
                    calibrator: dict | None, declared_threshold: float,
                    source: str, family: str, name: str) -> float | None:
    """Return confidence in (0, 1] if the candidate passes all selector rules, else None (abstain)."""
    kind = field_kind(spec)
    if kind_rules.get(kind) == "never":
        return None
    cell = cell_map.get((source, family, name))
    if cell is None:
        return None
    feats = cand.get("features") or {}
    if kind_rules.get(kind) == "views_only" and not views_agree(feats):
        return None
    req = cell.get("require") or {}
    if not evidence_satisfied(feats, req.get("evidence", "none")):
        return None
    min_families = int(req.get("min_families", 1) or 1)
    if min_families > 1:
        fam_agree = feats.get("families_agreeing")
        if fam_agree is None or int(fam_agree) < min_families:
            return None
    if calibrator is not None:
        if int(cell.get("errors", 0)) > 0:
            return None
        prob = _score_calibrator(calibrator, feats)
        if not math.isfinite(prob) or not 0.0 <= prob <= 1.0:
            raise ContractError(f"calibrator score for {name!r} outside [0, 1]: {prob!r}")
        return prob if prob >= declared_threshold else None
    return 1.0


def make_prediction(
    aggregation: dict,
    schema: dict,
    *,
    method: str,
    calibration: dict | None = None,
    selector: dict | None = None,
    record_meta: dict | None = None,
) -> dict:
    """Exactly the schema fields, each {"value", "confidence"} with a finite confidence in [0, 1]."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; allowed: {', '.join(METHODS)}")
    if method == "calibrated":
        if calibration is None:
            raise ContractError("method 'calibrated' needs a trained calibration artefact; none was provided")
        raise ContractError("calibrated predictions are not implemented in this codebase")
    if aggregation.get("contract_version") not in (2, 3):
        raise ContractError("make_prediction needs an aggregation of contract version 2 or 3")

    cell_map: dict = {}
    kind_rules: dict = {}
    calibrator: dict | None = None
    declared_threshold = 0.99
    source = ""
    family = ""
    if method == "selector":
        if not isinstance(selector, dict) or selector.get("selector_version") != 1:
            raise ContractError("method 'selector' needs a valid selector artefact (selector_version=1)")
        if not isinstance(record_meta, dict) or not record_meta.get("source") or not record_meta.get("family"):
            raise ContractError("method 'selector' needs record_meta with 'source' and 'family'")
        source = str(record_meta["source"])
        family = str(record_meta["family"])
        cell_map = {(c["source"], c["family"], c["field"]): c for c in selector.get("cells") or []}
        kind_rules = selector.get("kind_rules") or {"json": "never", "boolean": "views_only"}
        calibrator = selector.get("calibrator")
        declared_threshold = float(selector.get("declared_threshold", 0.99))

    props = schema.get("properties", {})
    out = {}
    for name, spec in props.items():
        cand = aggregation["candidates"].get(name)
        if cand is None:
            raise ContractError(f"aggregation has no candidate for field {name!r}")
        if not cand["eligible"] or cand["value"] is None:
            out[name] = {"value": None, "confidence": 0.0}
            continue
        if method == "selector":
            score = _selector_score(
                cand,
                spec if isinstance(spec, dict) else {},
                cell_map=cell_map,
                kind_rules=kind_rules,
                calibrator=calibrator,
                declared_threshold=declared_threshold,
                source=source,
                family=family,
                name=name,
            )
            if score is None or score <= 0.0:
                out[name] = {"value": None, "confidence": 0.0}
            else:
                out[name] = {"value": cand["value"], "confidence": float(score)}
            continue
        score = score_for(method, cand["features"])
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ContractError(f"score for {name!r} outside [0, 1]: {score!r}")
        if score <= 0.0:
            # A value with score 0 carries no confidence. At threshold 0 the scorer would accept it, so abstain instead.
            out[name] = {"value": None, "confidence": 0.0}
            continue
        out[name] = {"value": cand["value"], "confidence": float(score)}
    return out
