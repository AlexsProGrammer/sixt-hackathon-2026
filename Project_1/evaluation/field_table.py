"""Field table (T03): one row per (document, gold field) of a run, with features and labels. Productionised
`analyse_fields.py`. Every selection and calibration decision is made from this table.

    python -m evaluation.field_table RUN_ID_OR_DIR [--out fields.jsonl]

Reads from the run folder: gold.jsonl, preds.jsonl, and when present diagnostics.jsonl and samples.jsonl.
Writes RUN/fields.jsonl (git-ignored) and records `fields_contract_version` in run.json.

Row schema (FIELDS_CONTRACT_VERSION = 1; later subplans may add keys, never rename or drop):
    ids         doc_id, group, source, family, perception, field, kind, normalizer, route
    prediction  pred_value, pred_present, conf_out (confidence written to preds.jsonl, null when abstained),
                model_conf (lowest model confidence over the present samples, null without samples.jsonl),
                n_views, agreement, entropy_norm (diagnostics.jsonl, null when absent)
    evidence    grounded_text (value is a token-bounded span of the text layer), grounded_ocr (null until T08),
                cross_view_agree (true when >= 2 views agree completely, null for a single view; T09),
                value_len, text_quality (T05 score, 0 without text), text_source, has_text
    label       gold_present, match, outcome in {correct, wrong, hallucinated, missed, true_null}

Labels come only from 5_score.collect / values_match, so they cannot drift from the official scorer: at
threshold 0 the outcome counts equal score.json's at_threshold_0.

Gold is read to label dev predictions offline. It never enters a prompt, a cache key or an extraction input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import docs, registry  # noqa: E402
from pipeline import router  # noqa: E402
from evaluation.partitions import group_of  # noqa: E402
from uncertainty.grounding import field_kind, is_grounded  # noqa: E402

FIELDS_CONTRACT_VERSION = 1
FIELDS_NAME = "fields.jsonl"
OUTCOMES = ("correct", "wrong", "hallucinated", "missed", "true_null")


def outcome_of(pred_present: bool, gold_present: bool, match: bool) -> str:
    if pred_present and gold_present:
        return "correct" if match else "wrong"
    if pred_present:
        return "hallucinated"
    return "missed" if gold_present else "true_null"


def _by_doc(path: Path, key: str) -> dict:
    out = {}
    if path.exists():
        for row in registry.read_jsonl(path):
            out[row["doc_id"]] = row.get(key)
    return out


def _model_conf(samples: list[dict] | None, field: str) -> float | None:
    confs = []
    for s in samples or []:
        f = (s.get("fields") or {}).get(field) or {}
        c = f.get("model_confidence")
        if f.get("status") == "present" and isinstance(c, (int, float)) and not isinstance(c, bool):
            confs.append(float(c))
    return min(confs) if confs else None


def doc_rows(rec: dict, preds: dict, scorer, *, diag: dict | None = None, samples: list | None = None,
             text: str | None = None) -> list[dict]:
    """Field-table rows of one document. `text` is the document text layer (None = no text)."""
    props = rec.get("schema", {}).get("properties", {})
    family = docs.family_of(rec)
    routed = router.route(rec, text=text)       # T05: route and text-layer quality of the layer the caller holds
    quality, route = routed["quality"], routed["route"]
    group = group_of(rec["doc_id"])
    per_field = (diag or {}).get("per_field") or {}
    rows = []
    for r in scorer.collect([rec], preds):
        name = r["field"]
        spec = props.get(name, {})
        value = (preds.get(rec["doc_id"], {}).get(name) or {}).get("value")
        pf = per_field.get(name) or {}
        n_views = pf.get("k_valid") if pf else None
        agreement = pf.get("agreement") if pf else None
        pred_present = bool(r["pred_present"])
        rows.append({
            "doc_id": rec["doc_id"], "group": group, "source": r["source"], "family": family,
            "perception": docs.perception_of(rec), "field": name, "kind": field_kind(spec),
            "normalizer": spec.get("x-normalizer", "string"), "route": route,
            "pred_value": value if pred_present else None, "pred_present": pred_present,
            "conf_out": float(r["conf"]) if pred_present else None,
            "model_conf": _model_conf(samples, name),
            "n_views": n_views, "agreement": agreement, "entropy_norm": pf.get("entropy_norm") if pf else None,
            "grounded_text": bool(pred_present and is_grounded(value, text, spec)),
            "grounded_ocr": None,
            "cross_view_agree": (bool(agreement == 1.0) if (n_views or 0) >= 2 and agreement is not None else None),
            "value_len": len(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) if pred_present else 0,
            "text_quality": quality, "text_source": routed["text_source"], "has_text": text is not None,
            "gold_present": bool(r["gold_present"]), "match": bool(r["match"]),
            "outcome": outcome_of(pred_present, bool(r["gold_present"]), bool(r["match"])),
        })
    return rows


def build_field_table(run_dir: Path, *, text_fn: Callable[[dict], str | None] | None = None,
                      write: bool = True) -> list[dict]:
    """Build (and by default write) RUN/fields.jsonl. Only documents present in both preds and gold are used."""
    run_dir = Path(run_dir)
    scorer = registry.load_scorer()
    gold_path, preds_path = run_dir / "gold.jsonl", run_dir / "preds.jsonl"
    if not gold_path.exists() or not preds_path.exists():
        raise FileNotFoundError(f"{run_dir.name}: field table needs gold.jsonl and preds.jsonl")
    preds = scorer.load_preds(preds_path)
    diag = _by_doc(run_dir / "diagnostics.jsonl", "diagnostics")
    samples = _by_doc(run_dir / "samples.jsonl", "samples")
    text_fn = text_fn or docs.doc_text
    rows: list[dict] = []
    for rec in scorer.read_jsonl(gold_path):
        if rec["doc_id"] not in preds:
            continue
        rows.extend(doc_rows(rec, preds, scorer, diag=diag.get(rec["doc_id"]), samples=samples.get(rec["doc_id"]),
                             text=text_fn(rec)))
    if write:
        registry.write_jsonl(run_dir / FIELDS_NAME, rows)
        registry.update_run(run_dir, fields_contract_version=FIELDS_CONTRACT_VERSION, n_field_rows=len(rows))
    return rows


def load_field_table(run_dir: Path, rebuild: bool = False) -> list[dict]:
    run_dir = Path(run_dir)
    path = run_dir / FIELDS_NAME
    if rebuild or not path.exists():
        return build_field_table(run_dir)
    return registry.read_jsonl(path)


def outcome_counts(rows: list[dict]) -> dict:
    out = {o: 0 for o in OUTCOMES}
    for r in rows:
        out[r["outcome"]] += 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="run id, unambiguous name fragment, or run folder path")
    a = ap.parse_args(argv)
    run_dir = registry.resolve_run(a.run)
    rows = build_field_table(run_dir)
    print(f"{run_dir.name}: {len(rows)} rows -> {run_dir / FIELDS_NAME}")
    print(json.dumps(outcome_counts(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
