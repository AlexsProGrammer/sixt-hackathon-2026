"""Merge chunk/batch results into one Sample (contract: merge_sample(job_results, schema, sample_idx) -> Sample).

Rules
- Every planned job must have a result row. A failed job (ok=False) makes the sample incomplete (complete=False).
  Person B then abstains on the whole document.
- Results are sorted by (start offset, batch_id) first, so the outcome does not depend on pool order.
- Scalar fields: non-null candidates from all chunks are compared after normalisation. One distinct value is kept,
  with the lowest candidate confidence. Two or more distinct values give null/0. A null in one chunk never
  discards a value found in another chunk.
- An invalid candidate (missing or non-finite confidence, bool confidence, out-of-range confidence) makes the
  field null/0. The field is not guessed.
- Span fields (x-normalizer "span"): distinct pieces are kept in source order, duplicates from chunk overlap are
  removed, and the pieces are joined with " | ". Confidence is the lowest piece confidence. Policy checks
  evidence later.
- Provenance is not part of the output. Only the Sample fields are returned.
"""
from __future__ import annotations

import math

from uncertainty.contracts import CONTRACT_VERSION, check_job_results, check_plan, valid_confidence
from uncertainty.grounding import SPAN_SEPARATOR, normalise

_NULL = {"value": None, "confidence": 0.0}


def _valid_conf(c: object) -> float | None:
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        return None
    c = float(c)
    return c if math.isfinite(c) and 0.0 <= c <= 1.0 else None


def _candidate(answer: dict, name: str) -> tuple[object, float | None, bool]:
    """(value, confidence, valid). A missing field is a valid null candidate without confidence."""
    entry = answer.get(name)
    if entry is None:
        return None, None, True
    if not isinstance(entry, dict):
        return entry, None, False  # bare value without a confidence object
    value = entry.get("value")
    if value is None:
        return None, None, True
    conf = _valid_conf(entry.get("confidence"))
    return value, conf, conf is not None


def _merge_field(name: str, spec: dict, rows: list[dict]) -> dict:
    is_span = spec.get("x-normalizer") == "span"
    cands = []  # (start, batch_id, value, confidence)
    for row in rows:
        answer = row["answer"] or {}
        value, conf, valid = _candidate(answer, name)
        if not valid:
            return dict(_NULL)
        if value is None:
            continue
        cands.append((row["start"], row["batch_id"], value, conf))
    if not cands:
        return dict(_NULL)

    if is_span:
        seen, pieces, confs = set(), [], []
        for _, _, value, conf in sorted(cands, key=lambda c: (c[0], c[1])):
            if not isinstance(value, str):
                return dict(_NULL)
            for piece in value.split(SPAN_SEPARATOR):
                key = normalise(piece)
                if key and key not in seen:
                    seen.add(key)
                    pieces.append(piece.strip())
            confs.append(conf)
        if not pieces:
            return dict(_NULL)
        return {"value": SPAN_SEPARATOR.join(pieces), "confidence": min(confs)}

    distinct = {}
    for _, _, value, conf in sorted(cands, key=lambda c: (c[0], c[1])):
        key = repr(normalise(value)) if isinstance(value, str) else repr(value)
        distinct.setdefault(key, []).append((value, conf))
    if len(distinct) != 1:
        return dict(_NULL)
    group = next(iter(distinct.values()))
    return {"value": group[0][0], "confidence": min(c for _, c in group)}


def merge_sample(job_results: list[dict], schema: dict, sample_idx: int) -> dict:
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    own = [r for r in job_results if r.get("sample_idx") == sample_idx]
    complete = bool(own) and all(r.get("ok") is True and isinstance(r.get("answer"), dict) for r in own)
    own = sorted(own, key=lambda r: (r.get("start", 0), r.get("batch_id", 0)))
    fields = {}
    for name, spec in props.items():
        rows = [r for r in own if name in r.get("field_names", [])] if complete else []
        fields[name] = _merge_field(name, spec, rows) if complete else dict(_NULL)
    return {"sample_idx": sample_idx, "complete": complete, "fields": fields}


# ---------------------------------------------------------------- contract version 2 (field-wise completeness)

def _obs_for_job(name: str, job: dict, result: dict | None) -> tuple[str, object, float | None, str, dict]:
    """One field observation from one planned job: (kind, value, confidence, reason, span)."""
    span = {"job_id": job["job_id"], "chunk_id": job["chunk_id"], "batch_id": job["batch_id"],
            "start": job["start"], "end": job.get("end")}
    if result is None:
        return "missing", None, None, "no result for planned job", span
    if result.get("ok") is not True:
        return "error", None, None, str(result.get("error") or "job failed"), span
    answer = result.get("answer") if isinstance(result.get("answer"), dict) else {}
    if name not in answer:
        return "missing", None, None, "field absent from reply", span
    entry = answer[name]
    if not isinstance(entry, dict) or "value" not in entry or "confidence" not in entry:
        return "invalid", None, None, "no explicit value and confidence", span
    conf = valid_confidence(entry["confidence"])
    if conf is None:
        return "invalid", None, None, "confidence not a finite number in [0, 1]", span
    if entry["value"] is None:
        return "absent", None, conf, "explicit null", span
    return "present", entry["value"], conf, "", span


def _combine_present(spec: dict, present: list[tuple]) -> tuple[object, float | None]:
    """Same rules as the v1 merge: spans are deduplicated in source order and joined; scalars must agree."""
    cands = sorted(present, key=lambda o: (o[4]["start"], o[4]["batch_id"]))
    if spec.get("x-normalizer") == "span":
        seen, pieces, confs = set(), [], []
        for _, value, conf, _, _ in cands:
            if not isinstance(value, str):
                return None, None
            for piece in value.split(SPAN_SEPARATOR):
                key = normalise(piece)
                if key and key not in seen:
                    seen.add(key)
                    pieces.append(piece.strip())
            confs.append(conf)
        return (SPAN_SEPARATOR.join(pieces), min(confs)) if pieces else (None, None)
    distinct = {repr(normalise(v)) if isinstance(v, str) else repr(v): (v, c) for _, v, c, _, _ in cands}
    if len(distinct) != 1:
        return None, None
    value = next(iter(distinct.values()))[0]
    return value, min(c for _, v, c, _, _ in cands)


def _field_v2(name: str, spec: dict, rel_jobs: list[dict], by_id: dict[str, dict]) -> dict:
    if not rel_jobs:
        return {"status": "missing", "value": None, "model_confidence": None, "complete": False,
                "evidence": [], "reason": "no planned job carries this field"}
    obs = [_obs_for_job(name, j, by_id.get(j["job_id"])) for j in rel_jobs]
    evidence = [o[4] for o in obs if o[0] == "present"]
    bad = [o for o in obs if o[0] in ("error", "missing", "invalid")]
    if bad:
        priority = {"error": 0, "missing": 1, "invalid": 2}
        kind = min(bad, key=lambda o: priority[o[0]])
        return {"status": kind[0], "value": None, "model_confidence": None, "complete": False,
                "evidence": evidence, "reason": kind[3]}
    present = [(i, o[1], o[2], o[3], o[4]) for i, o in enumerate(obs) if o[0] == "present"]
    if not present:
        return {"status": "absent", "value": None, "model_confidence": min(o[2] for o in obs), "complete": True,
                "evidence": [], "reason": "explicit null in every relevant chunk"}
    value, conf = _combine_present(spec, present)
    if value is None:
        return {"status": "invalid", "value": None, "model_confidence": None, "complete": True,
                "evidence": evidence, "reason": "conflicting values across chunks"}
    return {"status": "present", "value": value, "model_confidence": conf, "complete": True,
            "evidence": evidence, "reason": ""}


def merge_sample_v2(job_results: list[dict], schema: dict, sample_idx: int, *, planned_jobs: list[dict]) -> dict:
    """Contract version 2. Every planned job of this sample must have a result row (ok or not).

    - Unplanned or duplicated results raise ContractError. Missing results make the affected fields 'missing'.
    - Completeness is per field: a field is complete if all its relevant jobs succeeded. A failed job in another
      batch does not discard a field whose own jobs are complete.
    - Sample-level `complete` is true only if every planned job of this sample succeeded.
    """
    check_plan(planned_jobs, schema)
    planned = [j for j in planned_jobs if j["sample_idx"] == sample_idx]
    by_id = check_job_results(job_results, planned_jobs, sample_idx)
    props = schema.get("properties", {})
    fields = {name: _field_v2(name, props[name], [j for j in planned if name in j["field_names"]], by_id)
              for name in props}
    complete = all(j["job_id"] in by_id and by_id[j["job_id"]].get("ok") is True for j in planned)
    return {"contract_version": CONTRACT_VERSION, "sample_idx": sample_idx, "complete": complete, "fields": fields}
