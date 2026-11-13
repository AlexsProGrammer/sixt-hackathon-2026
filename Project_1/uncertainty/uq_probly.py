"""Sample aggregation with probly entropy (contract: aggregate_samples(samples, schema, text) -> dict).

Input: a list of Sample dicts {"sample_idx": int, "complete": bool, "fields": {name: {"value", "confidence"}}}.
Output: {"fields": {name: {"value", "confidence"}}, "diagnostics": {...}}. Pure function: no I/O, no API calls.

Method (per document)
1. Every sample is checked with apply_policy first (grounding, valid confidence, abstention).
2. Any incomplete sample, a duplicate sample_idx, or an empty list -> abstain for the whole document
   (all fields null/0). Reason is written to diagnostics. Multiple chunks are never counted as samples.
3. Per field, the policy outputs are clustered by normalised value. null is its own cluster.
   Spans use exact comparison after casefold and whitespace collapse. No fuzzy matching: the scorer's
   token-F1 match is not transitive, so it cannot define clusters.
4. The cluster frequencies form a probly CategoricalDistribution. Its entropy (natural log, nats) is a
   diagnostic.
5. Decision:
   - Tie for the top count, or null as the top cluster -> value null, confidence 0.0.
   - Otherwise the winner's conservative score is min(winner share, lowest valid model confidence among the
     winner's samples). Agreement never raises the model's confidence (agreement 1 keeps the model score).
   - K=1 returns exactly apply_policy's output.
   The representative value is taken from the lowest sample_idx, so the result does not depend on list order.

What this is NOT
- Not a calibrated probability. The confidence is an uncalibrated conservative score.
- Not an epistemic/aleatoric decomposition. No credal set or model ensemble is modelled here.
- Entropy and agreement are diagnostics only.

Coverage cost (known, documented)
- Abstaining on the whole document when one sample is incomplete loses every field of that document, even
  fields that all completed samples agree on. A field-wise contract would need a joint change with A and C.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
from probly.quantification import entropy
from probly.representation.distribution import create_categorical_distribution

from math import log

from .contracts import CONTRACT_VERSION, VALID_STATUSES, ContractError, check_sample
from .grounding import normalise
from .policy import apply_policy, classify_field_v2

METHOD = "apply_policy_per_sample + exact_cluster_vote(null=cluster, tie->null) + probly_entropy_nats"
NULL_KEY = "null"


def _cluster_key(value: object) -> str:
    if value is None:
        return NULL_KEY
    if isinstance(value, bool):  # not reachable through the policy, kept defensive
        return f"b:{value}"
    if isinstance(value, str):
        return "s:" + normalise(value)
    if isinstance(value, (int, float)):
        return "n:" + repr(float(value))
    return "j:" + json.dumps(value, sort_keys=True, ensure_ascii=False)


def _abstain_all(schema: dict, reason: str, n_samples: int) -> dict:
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    per_field = {
        name: {"agreement": 0.0, "entropy": None, "n_clusters": 0, "grounded": False, "reason": reason}
        for name in props
    }
    return {
        "fields": {name: {"value": None, "confidence": 0.0} for name in props},
        "diagnostics": {"n_samples": n_samples, "complete": False, "method": "abstain_document",
                        "per_field": per_field},
    }


def _valid_sample(s: object) -> bool:
    return isinstance(s, dict) and s.get("complete") is True and isinstance(s.get("fields"), dict)


UQ_V2_METHOD = ("classify_field_v2 per sample; exact cluster vote (explicit null = its own cluster, "
                "unsupported = excluded); probly categorical entropy in nats and normalised by log(K)")


def _cluster_key_v2(status: str, value: object) -> str:
    if status == "absent":
        return NULL_KEY
    if status == "unsupported":
        return "unsupported"
    return _cluster_key(value)


def aggregate_v2(samples: list[dict], schema: dict, text: str | None, *, expected_k: int) -> dict:
    """Contract version 2: per-field votes over exactly `expected_k` valid observations.

    Returns {"contract_version", "candidates": {field: {"value", "eligible", "reason", "features"}},
    "diagnostics": {...}}. A candidate is eligible only with all K observations valid (present, absent or
    unsupported), a unique winner, and a non-null, grounded winner. Null and unsupported winners are never
    eligible. Errors and missing fields are not counted as null votes. Confidence is not calibrated.
    """
    if not isinstance(expected_k, int) or isinstance(expected_k, bool) or expected_k < 1:
        raise ValueError("expected_k must be a positive integer")
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    for s in samples:
        problems = check_sample(s, schema)
        if problems:
            raise ContractError("invalid sample: " + "; ".join(problems))
    idxs = [s["sample_idx"] for s in samples]
    if len(set(idxs)) != len(idxs):
        raise ContractError("duplicate sample_idx")
    ordered = sorted(samples, key=lambda s: s["sample_idx"])
    k_actual = len(ordered)
    mismatch = k_actual != expected_k
    unreadable = text is None or not str(text).strip()

    candidates: dict = {}
    for name, spec in props.items():
        defs = schema.get("$defs") if isinstance(schema, dict) else None
        cls = [classify_field_v2(s["fields"][name], spec, text, defs=defs) for s in ordered]
        feat: dict = {"k_expected": expected_k, "k_samples": k_actual,
                      "status_counts": dict(Counter(c["status"] for c in cls))}
        if unreadable:
            candidates[name] = {"value": None, "eligible": False, "reason": "unreadable", "features": feat}
            continue
        if mismatch:
            candidates[name] = {"value": None, "eligible": False, "reason": "sample_count_mismatch", "features": feat}
            continue
        valid = [i for i, c in enumerate(cls) if c["status"] in VALID_STATUSES]
        feat["k_valid"] = len(valid)
        if len(valid) < expected_k:
            candidates[name] = {"value": None, "eligible": False, "reason": "incomplete_observations",
                                "features": feat}
            continue
        keys = [_cluster_key_v2(c["status"], c["value"]) for c in cls]
        counts = Counter(keys)
        cluster_keys = sorted(counts)
        probs = np.array([counts[c] / expected_k for c in cluster_keys], dtype=float)
        h = float(entropy(create_categorical_distribution(probs)))
        h_norm = h / log(expected_k) if expected_k > 1 else 0.0
        top = max(counts.values())
        leaders = [c for c in cluster_keys if counts[c] == top]
        leader = leaders[0]
        members = [i for i, key in enumerate(keys) if key == leader]
        model_confs = [cls[i]["model_confidence"] for i in members if cls[i]["model_confidence"] is not None]
        feat.update({"agreement": top / expected_k, "entropy_nats": h, "entropy_norm": h_norm,
                     "n_clusters": len(counts), "null_share": counts.get(NULL_KEY, 0) / expected_k,
                     "grounded": leader not in (NULL_KEY, "unsupported")})
        if model_confs:
            feat["model_conf_min"] = min(model_confs)
            feat["model_conf_mean"] = sum(model_confs) / len(model_confs)
        if len(leaders) > 1:
            candidates[name] = {"value": None, "eligible": False, "reason": "tie", "features": feat}
        elif leader == NULL_KEY:
            candidates[name] = {"value": None, "eligible": False, "reason": "null_majority", "features": feat}
        elif leader == "unsupported":
            candidates[name] = {"value": None, "eligible": False, "reason": "unsupported_majority", "features": feat}
        else:
            value = cls[members[0]]["value"]
            reason = "single_sample" if expected_k == 1 else "majority"
            candidates[name] = {"value": value, "eligible": True, "reason": reason, "features": feat}

    per_field = {n: {"eligible": c["eligible"], "reason": c["reason"],
                     **{k: c["features"][k] for k in ("k_valid", "agreement", "entropy_nats", "entropy_norm",
                                                      "n_clusters", "grounded") if k in c["features"]}}
                 for n, c in candidates.items()}
    return {"contract_version": CONTRACT_VERSION, "candidates": candidates,
            "diagnostics": {"n_samples": k_actual, "expected_k": expected_k, "method": UQ_V2_METHOD,
                            "per_field": per_field}}


def aggregate_samples(samples: list[dict], schema: dict, text: str | None) -> dict:
    if not samples:
        return _abstain_all(schema, "no_samples", 0)
    if not all(_valid_sample(s) for s in samples):
        return _abstain_all(schema, "incomplete_sample", len(samples))
    idxs = [s.get("sample_idx") for s in samples]
    if len(set(idxs)) != len(idxs):
        return _abstain_all(schema, "duplicate_sample_idx", len(samples))

    ordered = sorted(samples, key=lambda s: s["sample_idx"])  # order-independent result
    k = len(ordered)
    policied = [apply_policy(s["fields"], schema, text) for s in ordered]
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}

    fields: dict = {}
    per_field: dict = {}
    for name in props:
        keys = [_cluster_key(p[name]["value"]) for p in policied]
        counts = Counter(keys)
        cluster_keys = sorted(counts)
        probs = np.array([counts[c] / k for c in cluster_keys], dtype=float)
        ent = float(entropy(create_categorical_distribution(probs)))

        top = max(counts.values())
        leaders = [c for c in cluster_keys if counts[c] == top]
        agreement = top / k
        if len(leaders) > 1:
            reason, winner = "tie", None
        elif leaders[0] == NULL_KEY:
            reason, winner = "null_majority", None
        else:
            winner = leaders[0]
            reason = "single_sample" if k == 1 else "majority"

        if winner is None:
            fields[name] = {"value": None, "confidence": 0.0}
            grounded = False
        else:
            members = [i for i, key in enumerate(keys) if key == winner]
            first = members[0]
            min_conf = min(policied[i][name]["confidence"] for i in members)
            fields[name] = {
                "value": policied[first][name]["value"],
                "confidence": min(agreement, min_conf),  # never above the model's own score
            }
            grounded = True

        per_field[name] = {"agreement": agreement, "entropy": ent, "n_clusters": len(counts),
                           "grounded": grounded, "reason": reason}

    return {
        "fields": fields,
        "diagnostics": {"n_samples": k, "complete": True, "method": METHOD, "per_field": per_field},
    }
