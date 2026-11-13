"""Prediction validation (contract: validate_predictions(records, predictions) -> list[str]).

An empty list means valid. Gold is not needed here. Checks:
- exactly one prediction per input document, no unknown or duplicate doc_ids
- exactly the schema fields, no missing and no extra fields
- every field has an explicit confidence: finite number in [0, 1], bool rejected
- value null requires confidence exactly 0 (abstention)

CLI:  python -m evaluation.validate --input INPUT.jsonl --pred PRED.jsonl   -> VALID (exit 0) or errors (exit 1)
"""
from __future__ import annotations

import argparse
import json
import math
import sys


def _valid_conf(c: object) -> bool:
    return not isinstance(c, bool) and isinstance(c, (int, float)) and math.isfinite(c) and 0.0 <= c <= 1.0


def validate_predictions(records: list[dict], predictions: list[dict]) -> list[str]:
    errors: list[str] = []
    schema_fields = {r["doc_id"]: set(r.get("schema", {}).get("properties", {})) for r in records}
    seen: dict[str, int] = {}
    for p in predictions:
        if not isinstance(p, dict) or not isinstance(p.get("doc_id"), str):
            errors.append(f"prediction without a string doc_id: {str(p)[:80]}")
            continue
        seen[p["doc_id"]] = seen.get(p["doc_id"], 0) + 1
    for doc_id, n in seen.items():
        if n > 1:
            errors.append(f"duplicate doc_id: {doc_id} ({n} rows)")
        if doc_id not in schema_fields:
            errors.append(f"unknown doc_id: {doc_id}")
    for doc_id in schema_fields:
        if doc_id not in seen:
            errors.append(f"missing prediction for doc_id: {doc_id}")

    for p in predictions:
        if not isinstance(p, dict) or p.get("doc_id") not in schema_fields:
            continue
        doc_id = p["doc_id"]
        fields = p.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"{doc_id}: 'fields' is not an object")
            continue
        expected = schema_fields[doc_id]
        for name in sorted(expected - set(fields)):
            errors.append(f"{doc_id}: missing field {name}")
        for name in sorted(set(fields) - expected):
            errors.append(f"{doc_id}: unexpected field {name}")
        for name in sorted(expected & set(fields)):
            entry = fields[name]
            if not isinstance(entry, dict) or "value" not in entry or "confidence" not in entry:
                errors.append(f"{doc_id}.{name}: needs explicit 'value' and 'confidence'")
                continue
            value, conf = entry["value"], entry["confidence"]
            if not _valid_conf(conf):
                errors.append(f"{doc_id}.{name}: confidence {conf!r} is not a finite number in [0, 1]")
            elif value is None and conf != 0:
                errors.append(f"{doc_id}.{name}: null value requires confidence 0, got {conf}")
    return errors


def _read(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        out = []
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))  # NaN/Infinity pass here and are rejected by validate_predictions
            except ValueError as e:
                raise SystemExit(f"{path} line {n}: invalid JSON ({e})")
        return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--pred", required=True)
    a = ap.parse_args(argv)
    errors = validate_predictions(_read(a.input), _read(a.pred))
    if errors:
        for e in errors[:50]:
            print("ERROR:", e)
        if len(errors) > 50:
            print(f"... {len(errors) - 50} more")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
