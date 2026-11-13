#!/usr/bin/env python3
"""Offline tuning of the text-layer quality gate (T05). Writes pipeline/router_config.json.

    python tools/tune_quality.py --data data/splits/fit.jsonl [--write] [--min-family-docs 3]

Target (offline only): for every ExtractBench document with a text layer, the gold-hit rate = share of its gold
string values that occur in the text layer as a token-bounded span (uncertainty.grounding.is_grounded). A document
with hit rate < 50% has a damaged or unusable layer. The quality score (no gold) must separate these documents.

Gold is read here and only here. The result is three numbers (tau_q and two weights) and a list of damaged
families (schema titles). None of them contains a gold value; the router uses them at inference without gold.

Selection: grid over (w_clipped, tau_q); maximise recall of low-hit documents subject to flagging at most
--max-false-rate of the good ones, ties broken by balanced accuracy. Families whose documents are mostly low-hit
although the score does not catch them (single dropped glyphs, e.g. the K-1 1065 forms) are listed in
`damaged_families` when they have >= --min-family-docs documents in the split.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import router, text_quality  # noqa: E402
from uncertainty.grounding import field_kind, is_grounded  # noqa: E402

LOW_HIT = 0.5
MIN_VALUES = 3          # documents with fewer gold string values have no reliable hit rate


def gold_hit_rate(rec: dict, text: str) -> tuple[float | None, int]:
    props = (rec.get("schema") or {}).get("properties", {})
    n = hit = 0
    for name, value in (rec.get("gold") or {}).items():
        spec = props.get(name, {})
        if not isinstance(value, str) or not value.strip() or value.strip().lower() in ("true", "false"):
            continue
        if field_kind(spec) not in ("string", "span"):
            continue
        n += 1
        hit += bool(is_grounded(value, text, spec))
    return (hit / n if n >= MIN_VALUES else None), n


def collect(path: Path, data_dir: Path | None = None) -> list[dict]:
    rows = []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("source_dataset") == "cuad":
            continue
        try:
            page = router.page_path(rec["pages"][0], data_dir)
            if page.suffix.lower() != ".pdf":
                continue
            eng = router._engines(page)
            text, source = router._pick(eng)
        except Exception:
            continue
        if not text:
            continue
        other = eng["pypdf" if source == "pdftotext" else "pdftotext"][0]
        feats = text_quality.features(text[: router.QUALITY_SAMPLE_CHARS],
                                      other[: router.QUALITY_SAMPLE_CHARS] if other else None)
        hit, n = gold_hit_rate(rec, text)
        rows.append({"doc_id": rec["doc_id"], "family": router.family_of(rec), "feats": feats, "hit": hit, "n_values": n})
    return rows


def evaluate(rows: list[dict], tau: float, wc: float, wo: float) -> dict:
    tp = fn = fp = tn = 0
    for r in rows:
        if r["hit"] is None:
            continue
        flagged = text_quality.score(r["feats"], wc, wo) < tau
        low = r["hit"] < LOW_HIT
        tp += flagged and low
        fn += (not flagged) and low
        fp += flagged and (not low)
        tn += (not flagged) and (not low)
    rec = tp / (tp + fn) if tp + fn else 0.0
    far = fp / (fp + tn) if fp + tn else 0.0
    return {"tau_q": tau, "w_clipped": wc, "w_odd": wo, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "recall_low_hit": round(rec, 4), "false_flag_rate": round(far, 4),
            "balanced_accuracy": round((rec + 1 - far) / 2, 4)}


def tune(rows: list[dict], max_false_rate: float = 0.15) -> dict:
    grid = [evaluate(rows, round(t / 100, 2), wc, 2.0) for wc in (0.0, 1.0, 2.0, 4.0, 8.0) for t in range(30, 96, 1)]
    ok = [g for g in grid if g["false_flag_rate"] <= max_false_rate] or grid
    # highest recall, then best balanced accuracy, then the lowest threshold (flags less), then the smallest weight
    return max(ok, key=lambda g: (g["recall_low_hit"], g["balanced_accuracy"], -g["tau_q"], -g["w_clipped"]))


def damaged_families(rows: list[dict], best: dict, min_docs: int) -> list[str]:
    """Families with >= min_docs scored documents whose median hit rate is < 50% and that the score alone
    misses for at least half of their low-hit documents."""
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["family"] and r["hit"] is not None:
            by_family[r["family"]].append(r)
    out = []
    for fam, rs in by_family.items():
        if len(rs) < min_docs or statistics.median(r["hit"] for r in rs) >= LOW_HIT:
            continue
        missed = [r for r in rs if r["hit"] < LOW_HIT
                  and text_quality.score(r["feats"], best["w_clipped"], best["w_odd"]) >= best["tau_q"]]
        low = [r for r in rs if r["hit"] < LOW_HIT]
        if len(missed) * 2 >= len(low):
            out.append(fam)
    return sorted(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data/splits/fit.jsonl"))
    ap.add_argument("--max-false-rate", type=float, default=0.15)
    ap.add_argument("--min-family-docs", type=int, default=3)
    ap.add_argument("--write", action="store_true", help="write pipeline/router_config.json")
    a = ap.parse_args(argv)
    rows = collect(Path(a.data))
    scored = [r for r in rows if r["hit"] is not None]
    n_low = sum(r["hit"] < LOW_HIT for r in scored)
    print(f"{len(rows)} documents with text, {len(scored)} with >= {MIN_VALUES} gold string values, {n_low} with hit rate < {LOW_HIT:.0%}")
    best = tune(rows, a.max_false_rate)
    fams = damaged_families(rows, best, a.min_family_docs)
    print("score only :", json.dumps(best))
    caught_by_family = [r for r in scored if r["hit"] < LOW_HIT and (
        text_quality.score(r["feats"], best["w_clipped"], best["w_odd"]) < best["tau_q"] or r["family"] in fams)]
    recall = len(caught_by_family) / n_low if n_low else 0.0
    print(f"damaged families ({len(fams)}): {fams}")
    print(f"flagged damaged (score or family): {len(caught_by_family)}/{n_low} = {recall:.1%} of low-hit documents")
    cfg = {"version": 1, "tau_q": best["tau_q"], "w_clipped": best["w_clipped"], "w_odd": best["w_odd"],
           "damaged_families": fams,
           "tuned_on": {"file": Path(a.data).name, "n_docs": len(scored), "n_low_hit": n_low,
                        "recall_low_hit_score_only": best["recall_low_hit"],
                        "recall_low_hit_with_families": round(recall, 4),
                        "false_flag_rate_score_only": best["false_flag_rate"], "low_hit_threshold": LOW_HIT}}
    if a.write:
        router.CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {router.CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
