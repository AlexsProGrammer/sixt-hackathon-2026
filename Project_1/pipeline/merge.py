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
