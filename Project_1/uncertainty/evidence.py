"""Per-type, per-source evidence features (T08).

Pure functions: no file access, no API calls.

Replaces the single hard pass/fail grounding filter with structured evidence features:
- `grounded_text`, `grounded_ocr`: bool or None when the source is missing/blank.
- `number_strength`: "strong" (>= 4 digits or non-trivial decimals), "weak" (0, 1, 100, < 4 digits,
  or repeating percentage-like decimals such as 33.3333), or None for non-numbers.
- `occurrences`: count of matches in the primary available source (text, else ocr).
- `components_grounded`: for ", "-joined strings (e.g. addresses), share of components found in [0, 1].
- `kind_policy`: "never_book" (json), "views_only" (boolean), or "evidence_or_views" (all others).
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .grounding import (
    SPAN_SEPARATOR,
    _bounded,
    _grounded_json,
    _grounded_piece,
    canonical_number,
    field_kind,
    normalise,
)

__all__ = [
    "KIND_POLICY",
    "evidence",
    "extract_numbers",
    "number_strength",
    "canonical_number",
]

KIND_POLICY = {"json": "never_book", "boolean": "views_only"}

_NUM_CORE = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+"
# Parenthesised accounting negative: (500), (1,234), ($1,234.50), $(1,234.50)
_PAREN_NUM_RE = re.compile(
    r"(?<![\w.,])"
    r"(?:[$€£]\s*)?\(\s*[$€£]?\s*(?P<sign>[+-]?)\s*(?P<num>" + _NUM_CORE + r")\s*%?\s*\)"
    r"(?![\w.,])"
)
# Standard signed/currency/percent number: $7,689.00, -3,186, 33.3333%, 1234.50
# A leading +/- only counts as a sign when not immediately preceded by a digit (so 2026-7 is 2026 and 7, not -7).
_PLAIN_NUM_RE = re.compile(
    r"(?<![\w.,])"
    r"(?:(?<![\d])(?P<sign>[+-])\s*)?"
    r"(?:[$€£]\s*)?"
    r"(?P<num>" + _NUM_CORE + r")"
    r"(?:\s*%)?"
    r"(?![\w.,])"
)
_REPEATED_DEC_RE = re.compile(r"\.(\d)\1{2,}")


def _parse_float(raw: str, negative: bool) -> float | None:
    try:
        val = float(raw.replace(",", ""))
    except ValueError:
        return None
    if not math.isfinite(val):
        return None
    if negative:
        val = -val
    return 0.0 if val == 0.0 else val


def extract_numbers(text: str) -> Counter[float]:
    """Parse printed numbers in `text` into a multiset (Counter) of floats."""
    hay = normalise(text)
    counts: Counter[float] = Counter()
    used_spans: list[tuple[int, int]] = []

    for m in _PAREN_NUM_RE.finditer(hay):
        val = _parse_float(m.group("num"), negative=(m.group("sign") != "+"))
        if val is not None:
            counts[val] += 1
            used_spans.append(m.span())

    for m in _PLAIN_NUM_RE.finditer(hay):
        s, e = m.span()
        if any(us <= s and e <= ue for us, ue in used_spans):
            continue
        val = _parse_float(m.group("num"), negative=(m.group("sign") == "-"))
        if val is not None:
            counts[val] += 1

    return counts


def number_strength(value: object) -> str | None:
    """Classify numeric specificity: 'strong', 'weak', or None for non-numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    av = abs(v)
    if av in (0.0, 1.0, 100.0):
        return "weak"
    if not v.is_integer():
        formatted = f"{av:.6f}".rstrip("0")
        if _REPEATED_DEC_RE.search(formatted):
            return "weak"
        return "strong"
    return "strong" if av >= 1000.0 else "weak"


def _count_piece(piece: str, hay: str) -> int:
    needle = normalise(piece)
    if not needle:
        return 0
    return len(_bounded(needle).findall(hay))


def _components_share(value: str, hay: str) -> float | None:
    if "," not in value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) < 2:
        return None
    hits = sum(1 for p in parts if _grounded_piece(p, hay))
    return hits / len(parts)


def _check_source(value: object, kind: str, field_schema: dict, source_text: str | None) -> tuple[bool | None, int, float | None]:
    """Evaluate (grounded, occurrences, components_grounded) against one text source."""
    if not isinstance(source_text, str) or not source_text.strip():
        return None, 0, None
    if value is None or isinstance(value, bool):
        return False, 0, None

    if kind == "boolean":
        return False, 0, None

    hay = normalise(source_text)
    if kind == "json":
        ok = _grounded_json(value, hay, field_schema if isinstance(field_schema, dict) else {})
        return ok, (1 if ok else 0), None

    if kind == "number":
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return False, 0, None
        target = 0.0 if float(value) == 0.0 else float(value)
        occ = extract_numbers(source_text).get(target, 0)
        return occ > 0, occ, None

    if isinstance(value, (dict, list)) or not isinstance(value, (str, int, float)):
        return False, 0, None

    s = str(value)
    if kind == "span":
        pieces = [p for p in s.split(SPAN_SEPARATOR) if normalise(p)]
        if not pieces:
            return False, 0, None
        counts = [_count_piece(p, hay) for p in pieces]
        occ = min(counts)
        return occ > 0, occ, None

    occ = _count_piece(s, hay)
    comp = _components_share(s, hay) if isinstance(value, str) else None
    return occ > 0, occ, comp


def evidence(
    value: object,
    field_schema: dict,
    sources: dict | None = None,
    *,
    views: list | None = None,
) -> dict:
    """Compute per-source, per-type evidence features for a predicted field value.

    `sources` is {"text": str|None, "ocr": str|None} (and may optionally carry "views").
    """
    src = sources if isinstance(sources, dict) else {}
    text = src.get("text")
    ocr = src.get("ocr")
    _ = views if views is not None else src.get("views")  # reserved for T09 view-aware extensions

    schema = field_schema if isinstance(field_schema, dict) else {}
    kind = field_kind(schema)
    k_policy = KIND_POLICY.get(kind, "evidence_or_views")
    strength = number_strength(value) if kind == "number" else None

    g_text, occ_text, comp_text = _check_source(value, kind, schema, text)
    g_ocr, occ_ocr, comp_ocr = _check_source(value, kind, schema, ocr)

    if g_text is not None:
        occurrences, components = occ_text, comp_text
    elif g_ocr is not None:
        occurrences, components = occ_ocr, comp_ocr
    else:
        occurrences, components = 0, None

    return {
        "grounded_text": g_text,
        "grounded_ocr": g_ocr,
        "number_strength": strength,
        "occurrences": occurrences,
        "components_grounded": components,
        "kind_policy": k_policy,
    }
