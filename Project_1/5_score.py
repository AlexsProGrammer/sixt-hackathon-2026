#!/usr/bin/env python3
"""Scores predictions: net saving vs reviewing every field by hand, plus precision, coverage and hallucinations.
    python 5_score.py --gold data/unified/dev.jsonl --pred preds.jsonl [--threshold 0.95] [--error-cost 100] [--json out.json]
Prediction line: {"doc_id": "...", "fields": {"total": {"value": "12.50", "confidence": 0.93}, "po": {"value": null}}}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

CONDITION_PREFIXES = ("perception:", "damage:", "severity:", "difficulty:")
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d",
                "%d-%b-%Y", "%d-%B-%Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y")


# ---------- normalisation ----------

def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def norm_string(v) -> str:
    return _collapse(str(v)).casefold()


def norm_id(v) -> str:
    return re.sub(r"[^0-9a-z]", "", _collapse(str(v)).casefold())


def _fmt_number(x: float) -> str:
    """Canonical number text, 2 to 4 decimals."""
    t = f"{x:.4f}".rstrip("0")
    whole, _, frac = t.partition(".")
    return f"{whole}.{frac.ljust(2, '0')}"


def norm_amount(v) -> str:
    """Money and rates: '1.234,50' = '1,234.50'; '20%' = 0.20."""
    s = _collapse(str(v))
    percent = "%" in s
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return ""
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    try:
        x = float(s)
    except ValueError:
        return s
    return _fmt_number(x / 100 if percent else x)


def norm_date(v) -> str:
    s = _collapse(str(v))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s.casefold()


def norm_json(v) -> str:
    """Nested object/array fields: compare as canonical JSON (all-or-nothing)."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return norm_string(v)
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


SPAN_F1_THRESHOLD = 0.8


def span_f1(a: str, b: str) -> float:
    """Token F1 between two texts, ignoring case and spacing."""
    ta, tb = norm_string(a).split(), norm_string(b).split()
    if not ta or not tb:
        return float(ta == tb)
    common = sum((__import__("collections").Counter(ta) & __import__("collections").Counter(tb)).values())
    if common == 0:
        return 0.0
    p, r = common / len(ta), common / len(tb)
    return 2 * p * r / (p + r)


NORMALIZERS = {"string": norm_string, "id": norm_id, "amount": norm_amount, "date": norm_date, "json": norm_json}


def values_match(pred, gold, kind: str) -> bool:
    if kind == "span":
        return span_f1(str(pred), str(gold)) >= SPAN_F1_THRESHOLD
    return normalize(pred, kind) == normalize(gold, kind)


def normalize(value, kind: str) -> str:
    return NORMALIZERS.get(kind, norm_string)(value)


def is_present(v) -> bool:
    return v is not None and _collapse(str(v)) != ""


# ---------- core ----------

def collect(gold_records, preds) -> list[dict]:
    """One row per (doc, gold field)."""
    rows = []
    for rec in gold_records:
        props = rec.get("schema", {}).get("properties", {})
        doc_preds = preds.get(rec["doc_id"], {})
        for field, gold_val in rec["gold"].items():
            kind = props.get(field, {}).get("x-normalizer", "string")
            p = doc_preds.get(field) or {}
            pv = p.get("value")
            gold_present = is_present(gold_val)
            pred_present = is_present(pv)
            match = pred_present and gold_present and values_match(pv, gold_val, kind)
            rows.append({
                "doc_id": rec["doc_id"], "field": field, "source": rec.get("source_dataset", "?"),
                "tags": rec.get("tags") or [],
                "conf": float(p.get("confidence", 1.0)) if pred_present else -1.0,
                "pred_present": pred_present, "gold_present": gold_present, "match": match,
            })
    return rows


def at_threshold(rows, t: float) -> dict:
    c = w = h = m = tn = 0
    for r in rows:
        accepted = r["pred_present"] and r["conf"] >= t
        if accepted and r["gold_present"]:
            c, w = (c + 1, w) if r["match"] else (c, w + 1)
        elif accepted:
            h += 1
        elif r["gold_present"]:
            m += 1
        else:
            tn += 1
    n = len(rows)
    accepted_n = c + w + h
    gold_present_n = c + w + m
    gold_null_n = h + tn
    return {
        "threshold": t, "n_fields": n, "accepted": accepted_n,
        "correct": c, "wrong": w, "hallucinated": h, "missed": m, "true_null": tn,
        "precision": c / accepted_n if accepted_n else 1.0,
        "recall": c / gold_present_n if gold_present_n else 1.0,
        "coverage": (c + w) / gold_present_n if gold_present_n else 0.0,
        "accepted_rate": accepted_n / n if n else 0.0,
        "hallucination_rate": h / gold_null_n if gold_null_n else 0.0,
    }


def risk_coverage(rows) -> list[dict]:
    ts = sorted({r["conf"] for r in rows if r["pred_present"]})
    return [at_threshold(rows, t) for t in ts] or [at_threshold(rows, 0.0)]


def headline(curve, target: float) -> dict:
    ok = [p for p in curve if p["precision"] >= target and p["accepted"] > 0]
    best = max(ok, key=lambda p: p["coverage"]) if ok else None
    return {
        "target_precision": target,
        "coverage_at_target_precision": best["coverage"] if best else 0.0,
        "threshold_at_target": best["threshold"] if best else None,
        "reached_target": best is not None,
    }


def net_saving(m: dict, review_cost: float, error_cost: float) -> dict:
    """Saving vs all-manual: accepted wrong or hallucinated values cost error_cost, the rest sent to a human cost review_cost."""
    n = m["n_fields"]
    manual = n * review_cost
    system = (n - m["accepted"]) * review_cost + (m["wrong"] + m["hallucinated"]) * error_cost
    return {"threshold": m["threshold"], "saving": manual - system, "saving_pct": (manual - system) / manual if manual else 0.0}


def best_saving(curve, review_cost: float, error_cost: float) -> dict:
    """Best net saving over all thresholds; accepting nothing (0) is always possible."""
    none = {"threshold": None, "saving": 0.0, "saving_pct": 0.0}
    return max([none] + [net_saving(p, review_cost, error_cost) for p in curve], key=lambda x: x["saving"])


def schema_validity(gold_records, preds) -> float | None:
    """Share of docs whose accepted values validate against the schema; None without jsonschema."""
    try:
        import jsonschema
    except ImportError:
        return None
    ok = 0
    for rec in gold_records:
        doc = {f: (v or {}).get("value") for f, v in preds.get(rec["doc_id"], {}).items() if is_present((v or {}).get("value"))}
        try:
            jsonschema.validate(doc, {**rec["schema"], "type": "object"})
            ok += 1
        except jsonschema.ValidationError:
            pass
    return ok / len(gold_records) if gold_records else None


def score(gold_records, preds, target=0.99, threshold=None, review_cost=1.0, error_cost=100.0) -> dict:
    rows = collect(gold_records, preds)
    curve = risk_coverage(rows)
    out = {
        "at_threshold_0": at_threshold(rows, 0.0),
        "headline": headline(curve, target),
        "coverage_at_precision": {str(t): headline(curve, t)["coverage_at_target_precision"] for t in (0.99, 0.95, 0.90, 0.80)},
        "business": {"review_cost": review_cost, "error_cost": error_cost,
                     **best_saving(curve, review_cost, error_cost)},
        "schema_validity": schema_validity(gold_records, preds),
        "by_source": {},
        "by_condition": {},
        "curve": curve,
    }
    if threshold is not None:
        m = at_threshold(rows, threshold)
        out["at_threshold"] = m
        out["declared"] = {"threshold": threshold, **{k: m[k] for k in ("precision", "coverage", "hallucination_rate", "accepted", "wrong", "hallucinated")},
                           "band": next((b for b in (0.99, 0.95, 0.90, 0.80) if m["precision"] >= b and m["accepted"] > 0), None),
                           "net_saving_pct": net_saving(m, review_cost, error_cost)["saving_pct"]}
    for tag in sorted({t for r in rows for t in r["tags"] if t.startswith(CONDITION_PREFIXES)}):
        out["by_condition"][tag] = at_threshold([r for r in rows if tag in r["tags"]], 0.0)
    for src in sorted({r["source"] for r in rows}):
        out["by_source"][src] = at_threshold([r for r in rows if r["source"] == src], 0.0)
    return out


# ---------- io ----------

def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_preds(path) -> dict:
    return {r["doc_id"]: r.get("fields", {}) for r in read_jsonl(path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--target-precision", type=float, default=0.99)
    ap.add_argument("--threshold", type=float, default=None,
                    help="YOUR declared confidence threshold (choose it on dev). This is what the final score uses.")
    ap.add_argument("--review-cost", type=float, default=1.0, help="cost of a human reviewing one field (default 1)")
    ap.add_argument("--error-cost", type=float, default=100.0, help="cost of one wrong value reaching the system (default 100)")
    ap.add_argument("--json", help="write full result (incl. curve) here")
    a = ap.parse_args(argv)

    res = score(read_jsonl(a.gold), load_preds(a.pred), a.target_precision, a.threshold, a.review_cost, a.error_cost)
    if res.get("declared"):
        d = res["declared"]
        band = f"{d['band']:.0%}" if d["band"] else ("nothing accepted" if d["accepted"] == 0 else "below 80%")
        print(f"=== AT YOUR DECLARED THRESHOLD {d['threshold']}: precision {('n/a' if d['accepted'] == 0 else format(d['precision'], '.1%'))} (band: {band})  coverage {d['coverage']:.1%}  "
              f"hallucinations {d['hallucinated']} ({d['hallucination_rate']:.1%} of absent fields)  net saving {d['net_saving_pct']:.1%}")
        print("=== everything below sweeps all thresholds on this file: use it to choose your threshold on dev, not as your result")
    z, h = res["at_threshold_0"], res["headline"]
    print(f"fields={z['n_fields']}  accepted={z['accepted']}  precision={z['precision']:.4f}  recall={z['recall']:.4f}  coverage={z['coverage']:.4f}")
    print(f"wrong={z['wrong']}  hallucinated={z['hallucinated']}  hallucination_rate={z['hallucination_rate']:.4f}  missed={z['missed']}")
    print(f"coverage @ precision>={h['target_precision']}: {h['coverage_at_target_precision']:.4f}"
          + ("" if h["reached_target"] else "  (target NOT reached at any threshold)"))
    print("coverage at precision >= " + "  ".join(f"{t}: {c:.3f}" for t, c in res["coverage_at_precision"].items()))
    b = res["business"]
    print(f"NET SAVING (best threshold) vs all-manual review: {b['saving_pct']:.1%}"
          + (f" at confidence >= {b['threshold']}" if b["threshold"] is not None else " (automation does not pay off)")
          + f"   [review cost {b['review_cost']:g}, wrong-value cost {b['error_cost']:g}]")
    sv = res["schema_validity"]
    print("schema_validity:", "n/a (pip install jsonschema)" if sv is None else f"{sv:.4f}")
    if res["by_condition"]:
        print("by capture condition (precision / coverage at no threshold):")
        for tag, m in res["by_condition"].items():
            print(f"  {tag:28s} fields={m['n_fields']:6d}  precision={m['precision']:.3f}  coverage={m['coverage']:.3f}")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
