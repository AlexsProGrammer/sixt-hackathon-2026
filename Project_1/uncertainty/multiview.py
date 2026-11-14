"""Multi-view agreement with probly entropy (T09).

    aggregate_views(views, schema, sources, *, view_priority=None) -> dict

Pure function: no network calls, no file writes.
Replaces same-model K-sample voting with agreement across heterogeneous views
(different model families and input kinds: PDF, PNG, text).
Output contract_version = 3 (compatible with `uncertainty.decision.make_prediction`).
"""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from functools import lru_cache
from math import log
from pathlib import Path

import numpy as np
from probly.quantification import entropy
from probly.representation.distribution import create_categorical_distribution

from pipeline.models import model_spec

from .evidence import KIND_POLICY, canonical_number, evidence, field_kind
from .policy import valid_confidence
from .schema_check import check_value

CONTRACT_VERSION = 3
NULL_KEY = "null"
MAX_DIAG_VALUE_CHARS = 200
MULTIVIEW_METHOD = (
    "multiview_cluster(scorer_norm / span_f1>=0.8; error/missing excluded) "
    "+ probly_categorical_entropy_norm + t08_evidence"
)
_ROOT = Path(__file__).resolve().parent.parent
_PDF_KINDS = ("pdf", "pdf_file", "pdf_image_url", "png")


@lru_cache(maxsize=1)
def _scorer():
    """Load 5_score.py once so clustering uses the scorer's exact normalisation."""
    spec = importlib.util.spec_from_file_location("score5_multiview", _ROOT / "5_score.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load 5_score.py from {_ROOT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_empty(v: object) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _model_family(model: str | None) -> str:
    if not model:
        return "unknown"
    fam = model_spec(model).get("family")
    if fam and fam != "unknown":
        return str(fam)
    low = model.lower()
    for known in ("gemini", "claude", "gpt", "mistral", "llama", "qwen"):
        if known in low:
            return known
    return model


def _normalize_sources(sources: dict | str | None) -> dict:
    if isinstance(sources, dict):
        return sources
    if isinstance(sources, str):
        return {"text": sources, "ocr": None}
    return {"text": None, "ocr": None}


def _view_sort_key(view: dict, priority_map: dict[str, int] | None) -> tuple:
    view_id = str(view.get("view_id") or "")
    model = str(view.get("model") or "")
    input_kind = str(view.get("input_kind") or "")
    fam_rank = 0 if _model_family(model) == "gemini" else 1
    kind_rank = 0 if input_kind in _PDF_KINDS else 1
    if priority_map is not None:
        return (priority_map.get(view_id, len(priority_map)), fam_rank, kind_rank, view_id, model, input_kind)
    return (fam_rank, kind_rank, view_id, model, input_kind)


def _truncate_value(val: object, limit: int = MAX_DIAG_VALUE_CHARS) -> object:
    if val is None or isinstance(val, (bool, int, float)):
        return val
    s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, sort_keys=True)
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def _cluster_observations(valid_obs: list[dict], kind: str, spec: dict) -> list[str]:
    """Assign each valid observation a cluster key using the scorer's own normalisation."""
    scorer = _scorer()
    if kind == "span":
        span_clusters: list[tuple[str, str]] = []
        keys: list[str] = []
        for item in valid_obs:
            if item["status"] == "absent":
                keys.append(NULL_KEY)
                continue
            val_str = str(item["value"])
            matched = None
            for cid, rep in span_clusters:
                if scorer.span_f1(val_str, rep) >= scorer.SPAN_F1_THRESHOLD:
                    matched = cid
                    break
            if matched is None:
                matched = f"span:{len(span_clusters)}"
                span_clusters.append((matched, val_str))
            keys.append(matched)
        return keys

    normalizer = spec.get("x-normalizer", "string") if isinstance(spec, dict) else "string"
    if normalizer not in scorer.NORMALIZERS:
        normalizer = "string"

    keys = []
    for item in valid_obs:
        if item["status"] == "absent":
            keys.append(NULL_KEY)
            continue
        val = item["value"]
        if kind == "number":
            num = float(val)
            num = 0.0 if num == 0.0 else num
            keys.append(f"n:{repr(num)}")
        elif kind == "boolean":
            keys.append(f"b:{bool(val)}")
        elif kind == "json":
            keys.append(f"j:{scorer.norm_json(val)}")
        else:
            keys.append(f"s:{scorer.normalize(val, normalizer)}")
    return keys


def _validate_field_observations(
    sorted_views: list[dict], name: str, spec: dict, defs: dict | None
) -> tuple[list[dict], Counter, list[dict]]:
    """Separate valid observations from error/missing/invalid ones and build member diagnostics."""
    valid_obs: list[dict] = []
    status_counts: Counter = Counter()
    member_diag: list[dict] = []

    for v in sorted_views:
        raw_obs = (v.get("fields") or {}).get(name)
        obs = raw_obs if isinstance(raw_obs, dict) else {"status": "missing"}
        raw_status = str(obs.get("status") or "missing")

        if raw_status == "absent":
            conf = valid_confidence(obs.get("model_confidence"))
            status_counts["absent"] += 1
            valid_obs.append({
                "view": v,
                "status": "absent",
                "value": None,
                "conf": conf,
                "family": _model_family(v.get("model")),
            })
            member_diag.append({
                "view_id": v.get("view_id"),
                "model": v.get("model"),
                "input_kind": v.get("input_kind"),
                "status": "absent",
                "value": None,
                "model_confidence": conf,
            })
            continue

        if raw_status == "present":
            val = obs.get("value")
            conf = valid_confidence(obs.get("model_confidence"))
            if _is_empty(val) or conf is None:
                eff_status = "invalid"
            else:
                ok, _ = check_value(val, spec, defs)
                eff_status = "present" if ok else "invalid"

            status_counts[eff_status] += 1
            if eff_status == "present":
                valid_obs.append({
                    "view": v,
                    "status": "present",
                    "value": val,
                    "conf": conf,
                    "family": _model_family(v.get("model")),
                })
            member_diag.append({
                "view_id": v.get("view_id"),
                "model": v.get("model"),
                "input_kind": v.get("input_kind"),
                "status": eff_status,
                "value": _truncate_value(val),
                "model_confidence": conf,
            })
            continue

        status_counts[raw_status] += 1
        member_diag.append({
            "view_id": v.get("view_id"),
            "model": v.get("model"),
            "input_kind": v.get("input_kind"),
            "status": raw_status,
            "value": None,
            "model_confidence": None,
        })

    return valid_obs, status_counts, member_diag


def _aggregate_field(
    name: str,
    spec: dict,
    defs: dict | None,
    sorted_views: list[dict],
    sources: dict,
) -> tuple[dict, dict]:
    kind = field_kind(spec)
    k_policy = KIND_POLICY.get(kind, "evidence_or_views")
    n_views = len(sorted_views)
    text = sources.get("text")

    valid_obs, status_counts, member_diag = _validate_field_observations(sorted_views, name, spec, defs)
    n_valid = len(valid_obs)

    base_features: dict = {
        "n_views": n_views,
        "n_valid": n_valid,
        "k_expected": n_views,
        "k_samples": n_views,
        "k_valid": n_valid,
        "kind": kind,
        "kind_policy": k_policy,
        "status_counts": dict(status_counts),
        "unanimous_nonnull": False,
        "families_agreeing": 0,
    }

    if n_valid == 0:
        base_features.update({
            "agreement": 0.0,
            "entropy_nats": None,
            "entropy_norm": None,
            "n_clusters": 0,
            "null_share": None,
            "grounded": False,
            "grounded_text": False if isinstance(text, str) and text.strip() else None,
            "grounded_ocr": None,
        })
        cand = {"value": None, "eligible": False, "reason": "incomplete_observations", "features": base_features}
        diag = {**{k: base_features[k] for k in ("n_views", "n_valid", "k_valid", "agreement", "entropy_nats",
                                                 "entropy_norm", "n_clusters", "null_share", "unanimous_nonnull",
                                                 "families_agreeing", "grounded", "grounded_text", "grounded_ocr",
                                                 "kind_policy")},
                "eligible": False, "reason": "incomplete_observations", "members": member_diag}
        return cand, diag

    keys = _cluster_observations(valid_obs, kind, spec)
    counts = Counter(keys)
    cluster_keys = sorted(counts)
    probs = np.array([counts[c] / n_valid for c in cluster_keys], dtype=float)
    h = float(entropy(create_categorical_distribution(probs)))
    h_norm = h / log(n_valid) if n_valid > 1 else 0.0

    top = max(counts.values())
    leaders = [c for c in cluster_keys if counts[c] == top]
    agreement = top / n_valid
    null_share = counts.get(NULL_KEY, 0) / n_valid

    base_features.update({
        "agreement": agreement,
        "entropy_nats": h,
        "entropy_norm": h_norm,
        "n_clusters": len(counts),
        "null_share": null_share,
    })

    if len(leaders) > 1 or leaders[0] == NULL_KEY:
        reason = "tie" if len(leaders) > 1 else "null_majority"
        base_features.update({
            "grounded": False,
            "grounded_text": False if isinstance(text, str) and text.strip() else None,
            "grounded_ocr": None,
        })
        cand = {"value": None, "eligible": False, "reason": reason, "features": base_features}
        diag = {**{k: base_features[k] for k in ("n_views", "n_valid", "k_valid", "agreement", "entropy_nats",
                                                 "entropy_norm", "n_clusters", "null_share", "unanimous_nonnull",
                                                 "families_agreeing", "grounded", "grounded_text", "grounded_ocr",
                                                 "kind_policy")},
                "eligible": False, "reason": reason, "members": member_diag}
        return cand, diag

    leader = leaders[0]
    winning = [item for item, cid in zip(valid_obs, keys) if cid == leader]
    rep_value = winning[0]["value"]
    value = canonical_number(rep_value, text, spec)
    ev = evidence(value, spec, sources)

    model_confs = [item["conf"] for item in winning if item["conf"] is not None]
    unanimous_nonnull = (n_valid == n_views and n_views >= 1 and len(counts) == 1)
    families_agreeing = len({item["family"] for item in winning})

    base_features.update(ev)
    base_features.update({
        "unanimous_nonnull": unanimous_nonnull,
        "families_agreeing": families_agreeing,
        "grounded": bool(ev["grounded_text"] or ev["grounded_ocr"]),
    })
    if model_confs:
        base_features["model_conf_min"] = min(model_confs)
        base_features["model_conf_mean"] = sum(model_confs) / len(model_confs)

    reason = "single_view" if n_views == 1 else ("unanimous" if unanimous_nonnull else "majority")
    cand = {"value": value, "eligible": True, "reason": reason, "features": base_features}
    diag = {**{k: base_features[k] for k in ("n_views", "n_valid", "k_valid", "agreement", "entropy_nats",
                                             "entropy_norm", "n_clusters", "null_share", "unanimous_nonnull",
                                             "families_agreeing", "grounded", "grounded_text", "grounded_ocr",
                                             "kind_policy")},
            "eligible": True, "reason": reason, "members": member_diag}
    return cand, diag


def aggregate_views(
    views: list[dict],
    schema: dict,
    sources: dict | str | None = None,
    *,
    view_priority: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Aggregate heterogeneous views into per-field candidates, features, and member diagnostics."""
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    defs = schema.get("$defs") if isinstance(schema, dict) else None
    src = _normalize_sources(sources)

    priority_map = {str(v): i for i, v in enumerate(view_priority)} if view_priority else None
    sorted_views = sorted(views, key=lambda v: _view_sort_key(v, priority_map))

    candidates: dict = {}
    per_field: dict = {}
    for name, spec in props.items():
        field_spec = spec if isinstance(spec, dict) else {}
        cand, fdiag = _aggregate_field(name, field_spec, defs, sorted_views, src)
        candidates[name] = cand
        per_field[name] = fdiag

    return {
        "contract_version": CONTRACT_VERSION,
        "candidates": candidates,
        "diagnostics": {
            "n_samples": len(sorted_views),
            "n_views": len(sorted_views),
            "expected_k": len(sorted_views),
            "method": MULTIVIEW_METHOD,
            "per_field": per_field,
        },
    }


def _rec_family(rec: dict) -> str:
    if rec.get("source_dataset") == "cuad":
        return "cuad"
    if rec.get("family"):
        return str(rec["family"])
    title = (rec.get("schema") or {}).get("title")
    if title:
        return str(title)[:45]
    return ""


def should_run_secondary_views(primary_view: dict, rec: dict, candidate_cells: object) -> bool:
    """Cascade gate: run views B/C only if view A returned non-null for >= 1 bookable candidate cell.

    Without a selector (`candidate_cells is None`), all views run.
    `candidate_cells` may be a collection of field names, `(family, field)` pairs, or `"family::field"` strings.
    """
    if candidate_cells is None:
        return True
    if isinstance(candidate_cells, dict) and "candidate_cells" in candidate_cells:
        candidate_cells = candidate_cells["candidate_cells"]
    if not candidate_cells:
        return False

    allowed_fields: set[str] = set()
    allowed_pairs: set[tuple[str, str]] = set()
    for item in candidate_cells:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            allowed_pairs.add((str(item[0]), str(item[1])))
        elif isinstance(item, str):
            if "::" in item:
                fam, _, fld = item.partition("::")
                allowed_pairs.add((fam, fld))
            else:
                allowed_fields.add(item)

    family = _rec_family(rec)
    for name, obs in (primary_view.get("fields") or {}).items():
        if not isinstance(obs, dict):
            continue
        if obs.get("status") == "present" and obs.get("value") is not None:
            if name in allowed_fields or (family, name) in allowed_pairs:
                return True
    return False
