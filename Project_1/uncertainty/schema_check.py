"""Schema validity of one predicted field value (contract v3). Separate from textual evidence (grounding.py).

check_value(value, field_spec, defs, strict_keys=True) -> (ok, reason)

1. jsonschema validation against the field schema, with the referenced $defs in the same document, so that
   "#/$defs/..." references resolve. Types are strict: a string is not a number, a bool is not a number.
2. Key check on objects, following the schema:
   - "$ref" to "#/$defs/<name>" is resolved before any type or key decision.
   - anyOf/oneOf: only the alternatives whose JSON type fits the value are considered. A null branch never
     accepts an object or an array, so an unknown-key object cannot pass through it.
   - properties: keys that are declared are checked recursively.
   - patternProperties: a key matching a pattern is allowed and checked against that pattern's schema.
   - additionalProperties as a schema: other keys are allowed and checked against that schema.
   - additionalProperties false: other keys are rejected (this is also a JSON Schema rule).
   - objects without declared properties are free-form and not checked here.

EXTRACTION RULE BEYOND JSON SCHEMA (strict_keys=True, the default):
   JSON Schema allows undeclared keys unless additionalProperties is false. For extraction we reject them
   when the schema declares "properties" and does not allow the key explicitly (patternProperties or a
   schema-valued additionalProperties). Reason: the model must reproduce the declared key names of every table row.
   Passing strict_keys=False gives the plain JSON Schema behaviour.

A value of None is not checked here (null means "absent").
"""
from __future__ import annotations

import re

import jsonschema


def _resolve(spec: object, defs: dict, depth: int = 0) -> object:
    """Follow local references '#/$defs/<name>'. Unknown references are returned unresolved."""
    if depth > 20 or not isinstance(spec, dict):
        return spec
    ref = spec.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return _resolve(defs.get(ref.split("/")[-1], {}), defs, depth + 1)
    return spec


def _type_fits(value: object, t: str) -> bool:
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if isinstance(value, bool):  # a bool is never a number, string, object or array here
        return False
    if t == "number":
        return isinstance(value, (int, float))
    if t == "integer":
        return isinstance(value, int)
    if t == "string":
        return isinstance(value, str)
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    return True  # unknown type keyword: left to jsonschema


def _branch_fits(value: object, spec: object, defs: dict) -> bool:
    """A schema branch is considered for this value only if its JSON type fits the value (no type = any)."""
    spec = _resolve(spec, defs)
    if not isinstance(spec, dict):
        return False
    t = spec.get("type")
    if t is None:
        return True
    types = t if isinstance(t, list) else [t]
    return any(_type_fits(value, x) for x in types if isinstance(x, str))


def _keys_ok(value: object, spec: object, defs: dict, strict: bool, depth: int = 0) -> bool:
    if value is None or depth > 30:
        return True
    spec = _resolve(spec, defs)
    if not isinstance(spec, dict):
        return True
    alts = spec.get("anyOf") or spec.get("oneOf")
    if alts:
        branches = [a for a in alts if isinstance(a, dict) and _branch_fits(value, a, defs)]
        if not branches:
            return False  # no alternative has the value's type; jsonschema reports the type error
        return any(_keys_ok(value, a, defs, strict, depth + 1) for a in branches)
    if isinstance(value, dict):
        props = spec.get("properties")
        if not isinstance(props, dict):
            return True  # free-form object: nothing declared to check against
        patterns = spec.get("patternProperties") if isinstance(spec.get("patternProperties"), dict) else {}
        additional = spec.get("additionalProperties", True)
        for key, val in value.items():
            if key in props:
                if not _keys_ok(val, props[key], defs, strict, depth + 1):
                    return False
                continue
            matched = [sub for pat, sub in patterns.items() if re.search(pat, key)]
            if matched:
                if not all(_keys_ok(val, sub, defs, strict, depth + 1) for sub in matched):
                    return False
                continue
            if additional is False:
                return False
            if isinstance(additional, dict):
                if not _keys_ok(val, additional, defs, strict, depth + 1):
                    return False
                continue
            if strict:  # additionalProperties true or absent: JSON Schema allows it, the extraction rule does not
                return False
        return True
    if isinstance(value, list):
        items = spec.get("items")
        if not isinstance(items, dict):
            return True
        return all(_keys_ok(v, items, defs, strict, depth + 1) for v in value)
    return True


def check_value(value: object, field_spec: dict, defs: dict | None = None, strict_keys: bool = True) -> tuple[bool, str]:
    if value is None:
        return True, ""
    defs = defs or {}
    if not isinstance(field_spec, dict):
        return False, "schema: field has no schema definition"
    schema = {"$defs": defs, **field_spec} if defs else dict(field_spec)
    try:
        jsonschema.validate(instance=value, schema=schema)
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path) or "value"
        return False, f"schema: {path}: {e.message[:160]}"
    except jsonschema.SchemaError:
        return False, "schema: field schema is itself invalid"
    if not _keys_ok(value, field_spec, defs, strict_keys):
        return False, "schema: object uses keys that the schema does not allow"
    return True, ""
