"""Field validation and abstention (contract: apply_policy(answer, schema, text) -> fields).

Pure function: no file access, no API calls.

Rules
- The output has exactly the schema fields, from schema["properties"] only. Extra model fields are ignored.
- A value needs a finite numeric confidence in [0, 1]. Bool, NaN, Infinity, strings, and out-of-range
  values are invalid.
- A value that is missing, empty, invalid, or not grounded in the text becomes value=null, confidence=0.0.
  Confidence 0 alone is not enough: at threshold 0 a non-null value would still be accepted.
- A valid score is passed through unchanged. Grounding never raises it.

Output entries: {"value": <JSON value or None>, "confidence": <float in [0, 1]>}.
"""
from __future__ import annotations

import math

from .grounding import is_grounded


def _abstain() -> dict:
    return {"value": None, "confidence": 0.0}


def valid_confidence(c: object) -> float | None:
    """Finite number in [0, 1], bool rejected. Returns None if invalid."""
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        return None
    c = float(c)
    if not math.isfinite(c) or not 0.0 <= c <= 1.0:
        return None
    return c


def _is_empty(v: object) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def decide_field(entry: object, field_schema: dict, text: str | None) -> dict:
    """Policy for one field. entry is the model's {"value", "confidence"} object for this field."""
    if not isinstance(entry, dict):
        return _abstain()  # bare value without confidence, or missing
    value = entry.get("value")
    conf = valid_confidence(entry.get("confidence"))
    if _is_empty(value) or conf is None:
        return _abstain()
    if not is_grounded(value, text, field_schema if isinstance(field_schema, dict) else {}):
        return _abstain()
    return {"value": value, "confidence": conf}


def apply_policy(answer: dict, schema: dict, text: str | None) -> dict:
    """Full field map for one sample. answer maps field name -> {"value", "confidence"}."""
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    raw = answer if isinstance(answer, dict) else {}
    return {name: decide_field(raw.get(name), spec, text) for name, spec in props.items()}
