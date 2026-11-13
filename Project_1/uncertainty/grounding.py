"""Evidence check for predicted values (contract: is_grounded(value, text, field_schema) -> bool).

Pure functions: no file access, no API calls, no imports from other team modules.

Rules
- A value counts as grounded only if its normalised form occurs in the normalised document text as a
  contiguous, token-bounded span. Normalisation = casefold + collapsed whitespace. Commas, points and
  currency symbols are kept, so "1234.50" does NOT match a printed "1,234.50" (conservative).
- Token bounds: "12" does not match inside "312", "12.50" or "1,12"; "-12" does not match "12".
- CUAD-style compound answers joined with " | " are checked piece by piece; every piece must be grounded.
  Each piece must be a whole contiguous text span. Scattered single words are never accepted.
- Native booleans return False: no reliable evidence rule exists, so they are never accepted as "true"/"false".
- JSON (x-normalizer "json" or object/array type) is accepted only if the structure matches the schema type and
  every non-null scalar leaf is grounded. A boolean leaf makes the structure unverifiable (False).
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


# Typographic variants of the same character. Only the glyph is unified; words, numbers and punctuation stay exact.
# Curly quotes occur in CUAD texts next to straight ones; a model may print either form.
_TYPO = str.maketrans({"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"',
                       "–": "-", "—": "-", "−": "-", " ": " ", " ": " ", " ": " "})


def normalise(s: str) -> str:
    """Unify typographic glyphs, casefold and collapse whitespace. Keeps commas, points and currency symbols."""
    return _WS.sub(" ", str(s).translate(_TYPO)).strip().casefold()


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


def _leaves(value: object):
    """Scalar leaves of a nested JSON value. Object keys are labels and are not values."""
    if isinstance(value, dict):
        for v in value.values():
            yield from _leaves(v)
    elif isinstance(value, list):
        for v in value:
            yield from _leaves(v)
    else:
        yield value


def _grounded_json(value: object, hay: str, field_schema: dict) -> bool:
    """A nested object/array counts only with a matching structure and every non-null leaf grounded.

    Conservative limits: a boolean leaf makes the whole structure unverifiable (False); an empty container
    or an empty string leaf is False; a grounded leaf proves presence of the number or text, not its
    place in the table. Leaf presence is therefore weaker evidence than a span match.
    """
    if not isinstance(value, (dict, list)) or not value:
        return False
    want = _types(field_schema)
    if want and not (want & {"object", "array"}):
        return False
    leaves = [v for v in _leaves(value) if v is not None]
    if not leaves:
        return False
    for leaf in leaves:
        if isinstance(leaf, bool):
            return False
        if isinstance(leaf, (int, float)):
            if not math.isfinite(float(leaf)) or not any(_bounded(f).search(hay) for f in _number_forms(leaf)):
                return False
        elif isinstance(leaf, str):
            if not _grounded_piece(leaf, hay):
                return False
        else:
            return False
    return True


def is_grounded(value: object, text: str | None, field_schema: dict) -> bool:
    """True only if the value is visible in the text as a contiguous, token-bounded span."""
    if text is None or not isinstance(text, str) or not text.strip():
        return False
    if value is None or isinstance(value, bool):
        return False
    kind = field_kind(field_schema)
    hay = normalise(text)
    if kind == "json":
        return _grounded_json(value, hay, field_schema if isinstance(field_schema, dict) else {})
    if kind in ("boolean", "unknown"):
        return False

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
