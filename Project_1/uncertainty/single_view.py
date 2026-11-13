"""Temporary single-view aggregation (T06). Replaced by `uncertainty.multiview.aggregate_views` (T09).

    aggregate_single_view(view, schema, text, *, route) -> aggregation (contract version 2)

Same output contract as `aggregate_v2`, so `decision.make_prediction(..., method="k1_grounded")` keeps working.
Difference to the text pipeline: textual grounding is a FEATURE here, not a hard filter. A PDF view reads values
the text layer cannot confirm (scans, damaged layers), so "not in the text layer" must not discard them.
The hard exclusions are the ones that do not depend on a text layer: failed/invalid observations and values that
violate the field schema. The selector (T10) decides which (family, field) cells are booked.

Features per eligible field: k_expected=1, k_samples=1, k_valid, model_conf_min, model_conf_mean, agreement=1.0,
entropy_norm=0.0, null_share, grounded_text (bool, None without a text layer), grounded (same, for the field table),
kind, kind_policy ("never_book" for json, "views_only" for boolean, "evidence_or_views" otherwise; T08 refines this).
"""
from __future__ import annotations

from .contracts import CONTRACT_VERSION
from .grounding import canonical_number, field_kind, is_grounded
from .policy import valid_confidence
from .schema_check import check_value

METHOD = "single_view(view A); schema validity hard, text grounding as a feature; no vote"
KIND_POLICY = {"json": "never_book", "boolean": "views_only"}


def _is_empty(v: object) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _candidate(name: str, obs: dict, spec: dict, text: str | None, defs: dict | None) -> dict:
    kind = field_kind(spec)
    feat: dict = {"k_expected": 1, "k_samples": 1, "kind": kind,
                  "kind_policy": KIND_POLICY.get(kind, "evidence_or_views"),
                  "status_counts": {obs.get("status", "invalid"): 1}}
    status = obs.get("status")
    if status == "absent":
        feat.update({"k_valid": 1, "agreement": 1.0, "entropy_nats": 0.0, "entropy_norm": 0.0, "null_share": 1.0,
                     "grounded": False, "grounded_text": None})
        return {"value": None, "eligible": False, "reason": "null_majority", "features": feat}
    if status != "present":
        feat["k_valid"] = 0
        return {"value": None, "eligible": False, "reason": "incomplete_observations", "features": feat}
    value = obs.get("value")
    conf = valid_confidence(obs.get("model_confidence"))
    if _is_empty(value) or conf is None:
        feat["k_valid"] = 0
        return {"value": None, "eligible": False, "reason": "invalid", "features": feat}
    ok, why = check_value(value, spec, defs)
    if not ok:
        feat["k_valid"] = 0
        return {"value": None, "eligible": False, "reason": f"invalid:{why}"[:120], "features": feat}
    grounded = is_grounded(value, text, spec) if text and text.strip() else None
    value = canonical_number(value, text, spec)
    feat.update({"k_valid": 1, "agreement": 1.0, "entropy_nats": 0.0, "entropy_norm": 0.0, "null_share": 0.0,
                 "model_conf_min": conf, "model_conf_mean": conf, "grounded_text": grounded,
                 "grounded": bool(grounded)})
    return {"value": value, "eligible": True, "reason": "single_view", "features": feat}


def aggregate_single_view(view: dict, schema: dict, text: str | None, *, route: str | None = None) -> dict:
    """`view` is a ViewResult of pipeline.eb_pipeline (fields in the merge v2 observation format)."""
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    defs = schema.get("$defs") if isinstance(schema, dict) else None
    fields = view.get("fields") or {}
    candidates = {name: _candidate(name, fields.get(name) or {"status": "missing"}, spec, text, defs)
                  for name, spec in props.items()}
    per_field = {n: {"eligible": c["eligible"], "reason": c["reason"],
                     **{k: c["features"][k] for k in ("k_valid", "status_counts", "agreement", "entropy_nats",
                                                      "entropy_norm", "grounded", "grounded_text", "kind_policy")
                        if k in c["features"]}}
                 for n, c in candidates.items()}
    return {"contract_version": CONTRACT_VERSION, "candidates": candidates,
            "diagnostics": {"n_samples": 1, "expected_k": 1, "method": METHOD, "route": route,
                            "view_id": view.get("view_id"), "model": view.get("model"),
                            "input_kind": view.get("input_kind"), "per_field": per_field}}

