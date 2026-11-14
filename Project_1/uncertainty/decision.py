"""Decision rules over an aggregation (contract: make_prediction(aggregation, schema, *, method, calibration) -> fields).

Fixed, separately named methods. Each returns a score in [0, 1] for eligible candidates. Every other field is null/0.
- k1_grounded       K=1. The model confidence of the single valid observation (the baseline).
- k_agreement_only  K>1. Winner share only (agreement). No model confidence: a pure consistency baseline.
- k_agreement_conf  K>1. min(winner share, lowest model confidence among winner observations).
                    This was the former name "k_agreement"; the rename prevents mixing the two definitions.
- k_entropy         K>1. 1 - H / log(K), H from probly (nats). Uses probly directly in the decision.
                    Uncalibrated: it ignores the model confidence, so three identical grounded answers score 1.0.
- calibrated        Needs a trained artefact. Not available in this codebase: raises a clear error.

Threshold filtering is not done here. The official scorer applies the declared threshold to these scores.
"""
from __future__ import annotations

import math

from .contracts import ContractError

METHODS = ("k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy", "calibrated")
MULTI_SAMPLE_METHODS = ("k_agreement_only", "k_agreement_conf", "k_entropy")


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


def make_prediction(aggregation: dict, schema: dict, *, method: str, calibration: dict | None = None) -> dict:
    """Exactly the schema fields, each {"value", "confidence"} with a finite confidence in [0, 1]."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; allowed: {', '.join(METHODS)}")
    if method == "calibrated":
        if calibration is None:
            raise ContractError("method 'calibrated' needs a trained calibration artefact; none was provided")
        raise ContractError("calibrated predictions are not implemented in this codebase")
    if aggregation.get("contract_version") not in (2, 3):
        raise ContractError("make_prediction needs an aggregation of contract version 2 or 3")
    props = schema.get("properties", {})
    out = {}
    for name in props:
        cand = aggregation["candidates"].get(name)
        if cand is None:
            raise ContractError(f"aggregation has no candidate for field {name!r}")
        if not cand["eligible"] or cand["value"] is None:
            out[name] = {"value": None, "confidence": 0.0}
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
