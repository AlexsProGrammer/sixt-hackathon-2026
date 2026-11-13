"""Evidence check for predicted values (contract: is_grounded(value, text, field_schema) -> bool).

Pure functions: no file access, no API calls, no imports from other team modules.

Rules
- A value counts as grounded only if its normalised form occurs in the normalised document text as a
  contiguous, token-bounded span. Normalisation = casefold + collapsed whitespace. Commas, points and
  currency symbols are kept, so "1234.50" does NOT match a printed "1,234.50" (conservative).
- Token bounds: "12" does not match inside "312", "12.50" or "1,12"; "-12" does not match "12".
- CUAD-style compound answers joined with " | " are checked piece by piece; every piece must be grounded.
  Each piece must be a whole contiguous text span. Scattered single words are never accepted.
- JSON, native booleans, and objects/arrays return False (not yet checkable, so abstain).
- Missing text returns False.

Limits (documented, not hidden)
- Grounding shows that the text occurs in the document. It does NOT show that the value belongs to this
  field. Example: a date printed in another section still passes.
- Span grounding is stricter than the scorer's token F1 >= 0.8. It can cost recall when the model
  paraphrases or slightly changes a clause.
"""
from __future__ import annotations

import math
import re

SPAN_SEPARATOR = " | "
_WS = re.compile(r"\s+")
_NUMERIC_TEXT = re.compile(r"[\d\s.,+\-$€£%()]+")


def normalise(s: str) -> str:
    """Casefold and collapse whitespace. Keeps commas, points and currency symbols."""
    return _WS.sub(" ", str(s)).strip().casefold()


def _types(field_schema: dict) -> set[str]:
    out: set[str] = set()
    t = field_schema.get("type")
    if isinstance(t, str):
        out.add(t)
    elif isinstance(t, list):
        out.update(x for x in t if isinstance(x, str))
    for alt in field_schema.get("anyOf") or []:
        if isinstance(alt, dict) and isinstance(alt.get("type"), str):
            out.add(alt["type"])
    return out


def field_kind(field_schema: dict) -> str:
    """One of: span, string, number, boolean, json, unknown."""
    if not isinstance(field_schema, dict):
        return "unknown"
    norm = field_schema.get("x-normalizer")
    if norm == "span":
        return "span"
    if norm == "json":
        return "json"
    types = _types(field_schema)
    if "boolean" in types:
        return "boolean"
    if types & {"number", "integer"}:
        return "number"
    if "string" in types or not types:
        return "string"
    return "json"  # object, array, ...


def _bounded(needle: str) -> re.Pattern:
    """Token-bounded pattern. Numeric-looking needles also refuse a neighbouring digit separator."""
    esc = re.escape(needle)
    if _NUMERIC_TEXT.fullmatch(needle) and re.search(r"\d", needle):
        return re.compile(r"(?<![\w.,+\-])(?<!\d[.,])" + esc + r"(?!\w)(?![.,]\d)")
    return re.compile(r"(?<!\w)" + esc + r"(?!\w)")


def _number_forms(value: float | int) -> list[str]:
    forms = [normalise(str(value))]
    if isinstance(value, float) and value.is_integer():
        forms.append(str(int(value)))
    if float(value).is_integer():
        forms.append(f"{int(value):,}")  # printed with thousands separators, e.g. 1,234
    return list(dict.fromkeys(forms))


def _grounded_piece(piece: str, hay: str) -> bool:
    needle = normalise(piece)
    if not needle:
        return False
    return _bounded(needle).search(hay) is not None


def is_grounded(value: object, text: str | None, field_schema: dict) -> bool:
    """True only if the value is visible in the text as a contiguous, token-bounded span."""
    if text is None or not isinstance(text, str) or not text.strip():
        return False
    if value is None or isinstance(value, bool):
        return False
    kind = field_kind(field_schema)
    if kind in ("boolean", "json", "unknown"):
        return False
    hay = normalise(text)

    if kind == "number":
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return False
        return any(_bounded(form).search(hay) is not None for form in _number_forms(value))

    if isinstance(value, (dict, list)) or not isinstance(value, (str, int, float)):
        return False
    s = str(value)
    if kind == "span":
        pieces = s.split(SPAN_SEPARATOR)
        return all(_grounded_piece(p, hay) for p in pieces)
    return _grounded_piece(s, hay)
