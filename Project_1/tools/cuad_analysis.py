#!/usr/bin/env python3
"""Offline CUAD error analysis on dev gold + legacy llm_dev run (T07 Phase A, no API calls).

    python tools/cuad_analysis.py \
        --gold data/unified/dev.jsonl \
        --pred results/llm_dev.jsonl \
        --splits-manifest data/splits/manifest.json \
        --out-md docs/cuad_analysis.md \
        --out-json results/cuad_analysis.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import router  # noqa: E402
from uncertainty.grounding import SPAN_SEPARATOR, is_grounded, normalise  # noqa: E402

_spec = importlib.util.spec_from_file_location("scorer", ROOT / "5_score.py")
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)

SPAN_SCHEMA = {"type": "string", "x-normalizer": "span"}
F1_BINS = ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8")
FAILURE_MODES = ("subset", "superset", "missing_passages", "other_location", "paraphrase")


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def split_passages(text: str) -> list[str]:
    return [p.strip() for p in str(text).split(SPAN_SEPARATOR) if p.strip()]


def token_count(text: str) -> int:
    return len(scorer.norm_string(text).split())


def f1_bin(f1: float) -> str:
    if f1 < 0.2:
        return "0.0-0.2"
    if f1 < 0.4:
        return "0.2-0.4"
    if f1 < 0.6:
        return "0.4-0.6"
    return "0.6-0.8"


def classify_wrong(pred: str, gold: str, doc_text: str) -> str:
    """Classify a wrong span prediction into one of the 5 T07 failure modes."""
    if not doc_text or not is_grounded(pred, doc_text, SPAN_SCHEMA):
        return "paraphrase"
    gold_passages = split_passages(gold)
    pred_passages = split_passages(pred)
    ng = normalise(gold)
    np = normalise(pred)

    if len(gold_passages) > 1 and len(pred_passages) < len(gold_passages):
        for pp in pred_passages:
            npp = normalise(pp)
            for gp in gold_passages:
                ngp = normalise(gp)
                if scorer.span_f1(pp, gp) >= scorer.SPAN_F1_THRESHOLD or npp in ngp or ngp in npp:
                    return "missing_passages"

    if np in ng or (pred_passages and all(normalise(pp) in ng for pp in pred_passages)):
        return "subset"
    if ng in np or (gold_passages and all(normalise(gp) in np for gp in gold_passages)):
        return "superset"
    return "other_location"


def load_fit_ids(manifest_path: Path | None) -> set[str]:
    if not manifest_path or not manifest_path.exists():
        return set()
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    return set(man.get("splits", {}).get("fit", {}).get("doc_ids", []))


def analyze(gold_records: list[dict], pred_records: list[dict], cuad_texts: dict[str, str],
            fit_ids: set[str]) -> dict:
    cuad_gold = [r for r in gold_records if r.get("source_dataset") == "cuad"]
    preds_by_id = {r["doc_id"]: r.get("fields", {}) for r in pred_records}
    categories = list(cuad_gold[0]["schema"]["properties"].keys()) if cuad_gold else []

    # Learn per-category gold medians & single-passage rates on `fit` (fallback to all dev if fit_ids empty)
    fit_recs = [r for r in cuad_gold if r["doc_id"] in fit_ids] if fit_ids else cuad_gold
    fit_stats: dict[str, dict] = {}
    for cat in categories:
        lens = []
        n_passages = []
        for r in fit_recs:
            g = r["gold"].get(cat)
            if scorer.is_present(g):
                lens.append(token_count(g))
                n_passages.append(len(split_passages(g)))
        med_len = statistics.median(lens) if lens else 0.0
        single_rate = (sum(1 for n in n_passages if n == 1) / len(n_passages)) if n_passages else 0.0
        fit_stats[cat] = {
            "n_fit_present": len(lens),
            "median_tokens_fit": med_len,
            "single_passage_rate_fit": single_rate,
        }

    # Full dev gold stats + prediction error analysis on docs present in pred_records
    cat_gold_present = Counter()
    cat_gold_passages: dict[str, list[int]] = defaultdict(list)
    cat_gold_tokens: dict[str, list[int]] = defaultdict(list)

    cat_correct = Counter()
    cat_wrong = Counter()
    cat_hallucinated = Counter()
    cat_abstained_present = Counter()
    cat_f1_hist: dict[str, Counter] = defaultdict(Counter)
    cat_modes: dict[str, Counter] = defaultdict(Counter)

    overall_f1_hist = Counter()
    overall_modes = Counter()

    # Simulation on predicted CUAD docs (also track non-fit subset to avoid leakage)
    sim_rows = []
    n_pred_cuad_docs = 0

    for r in cuad_gold:
        doc_id = r["doc_id"]
        doc_text = cuad_texts.get(doc_id) or cuad_texts.get(doc_id.removeprefix("cuad:"), "")
        for cat in categories:
            g = r["gold"].get(cat)
            if scorer.is_present(g):
                cat_gold_present[cat] += 1
                cat_gold_passages[cat].append(len(split_passages(g)))
                cat_gold_tokens[cat].append(token_count(g))

        if doc_id not in preds_by_id:
            continue
        n_pred_cuad_docs += 1
        pfields = preds_by_id[doc_id]
        in_fit = doc_id in fit_ids

        for cat in categories:
            g = r["gold"].get(cat)
            entry = pfields.get(cat) or {}
            pv = entry.get("value")
            p_present = scorer.is_present(pv)
            g_present = scorer.is_present(g)

            if not p_present:
                if g_present:
                    cat_abstained_present[cat] += 1
                continue

            if not g_present:
                cat_hallucinated[cat] += 1
                sim_rows.append({
                    "doc_id": doc_id, "category": cat, "in_fit": in_fit,
                    "outcome": "hallucinated", "pred_tokens": token_count(pv),
                    "pred_passages": len(split_passages(pv)),
                    "grounded": bool(doc_text and is_grounded(str(pv), doc_text, SPAN_SCHEMA)),
                })
                continue

            f1 = scorer.span_f1(str(pv), str(g))
            correct = f1 >= scorer.SPAN_F1_THRESHOLD
            if correct:
                cat_correct[cat] += 1
                outcome = "correct"
            else:
                cat_wrong[cat] += 1
                outcome = "wrong"
                b = f1_bin(f1)
                cat_f1_hist[cat][b] += 1
                overall_f1_hist[b] += 1
                mode = classify_wrong(str(pv), str(g), doc_text)
                cat_modes[cat][mode] += 1
                overall_modes[mode] += 1

            sim_rows.append({
                "doc_id": doc_id, "category": cat, "in_fit": in_fit,
                "outcome": outcome, "pred_tokens": token_count(pv),
                "pred_passages": len(split_passages(pv)),
                "grounded": bool(doc_text and is_grounded(str(pv), doc_text, SPAN_SCHEMA)),
            })

    # Per-category summary
    per_cat = {}
    for cat in categories:
        n_pres = cat_gold_present[cat]
        passages = cat_gold_passages[cat]
        toks = cat_gold_tokens[cat]
        c = cat_correct[cat]
        w = cat_wrong[cat]
        h = cat_hallucinated[cat]
        tot_pred = c + w + h
        per_cat[cat] = {
            "gold_present_count": n_pres,
            "gold_present_share": round(n_pres / len(cuad_gold), 4) if cuad_gold else 0.0,
            "gold_passages_mean": round(statistics.mean(passages), 2) if passages else 0.0,
            "gold_passages_median": statistics.median(passages) if passages else 0.0,
            "gold_passages_max": max(passages) if passages else 0,
            "gold_single_passage_share": round(sum(1 for x in passages if x == 1) / len(passages), 4) if passages else 0.0,
            "gold_median_tokens": statistics.median(toks) if toks else 0.0,
            "pred_total": tot_pred,
            "pred_correct": c,
            "pred_wrong": w,
            "pred_hallucinated": h,
            "pred_abstained_when_gold_present": cat_abstained_present[cat],
            "precision": round(c / tot_pred, 4) if tot_pred else None,
            "f1_hist": {b: cat_f1_hist[cat][b] for b in F1_BINS},
            "failure_modes": {m: cat_modes[cat][m] for m in FAILURE_MODES},
            "fit_stats": fit_stats[cat],
        }

    # Offline rule simulations (evaluated on all predicted CUAD docs AND non-fit docs)
    def eval_sim(rows_subset: list[dict]) -> dict:
        def score_rows(rs: list[dict]) -> dict:
            c = sum(1 for x in rs if x["outcome"] == "correct")
            w = sum(1 for x in rs if x["outcome"] == "wrong")
            h = sum(1 for x in rs if x["outcome"] == "hallucinated")
            e = w + h
            tot = c + e
            return {
                "booked": tot, "correct": c, "wrong": w, "hallucinated": h,
                "errors": e, "precision": round(c / tot, 4) if tot else None,
                "net_e100": c - 100 * e,
            }

        def len_ok(x: dict) -> bool:
            med = fit_stats[x["category"]]["median_tokens_fit"]
            return med > 0 and (0.5 * med <= x["pred_tokens"] <= 2.0 * med)

        def single_gold_cat_ok(x: dict) -> bool:
            return fit_stats[x["category"]]["single_passage_rate_fit"] >= 0.8

        def single_pred_ok(x: dict) -> bool:
            return x["pred_passages"] == 1

        return {
            "baseline_all_predicted": score_rows(rows_subset),
            "grounded_only": score_rows([x for x in rows_subset if x["grounded"]]),
            "rule_single_passage_cat": score_rows([x for x in rows_subset if single_gold_cat_ok(x)]),
            "rule_single_passage_cat_and_pred": score_rows([x for x in rows_subset if single_gold_cat_ok(x) and single_pred_ok(x)]),
            "rule_length_0.5_2x": score_rows([x for x in rows_subset if len_ok(x)]),
            "rule_both_and_grounded": score_rows([
                x for x in rows_subset if x["grounded"] and single_gold_cat_ok(x) and single_pred_ok(x) and len_ok(x)
            ]),
        }

    sim_all = eval_sim(sim_rows)
    non_fit_rows = [x for x in sim_rows if not x["in_fit"]]
    sim_non_fit = eval_sim(non_fit_rows)

    # Candidate categories: rank by precision and gold presence, identify top failure mode
    candidates = []
    for cat, st in per_cat.items():
        if st["pred_total"] == 0:
            continue
        top_mode = max(FAILURE_MODES, key=lambda m: st["failure_modes"][m])
        top_mode_count = st["failure_modes"][top_mode]
        if st["pred_hallucinated"] > top_mode_count and st["pred_hallucinated"] > st["pred_wrong"]:
            primary_issue = f"hallucination ({st['pred_hallucinated']})"
        elif top_mode_count > 0:
            primary_issue = f"{top_mode} ({top_mode_count}/{st['pred_wrong']})"
        else:
            primary_issue = "none"
        candidates.append({
            "category": cat,
            "precision": st["precision"] or 0.0,
            "pred_correct": st["pred_correct"],
            "pred_wrong": st["pred_wrong"],
            "pred_hallucinated": st["pred_hallucinated"],
            "single_passage_share": st["gold_single_passage_share"],
            "median_tokens": st["gold_median_tokens"],
            "primary_issue": primary_issue,
        })
    candidates.sort(key=lambda x: (-x["precision"], -x["pred_correct"], x["category"]))

    return {
        "summary": {
            "n_dev_cuad_docs": len(cuad_gold),
            "n_pred_cuad_docs": n_pred_cuad_docs,
            "n_fit_cuad_docs": len(fit_recs),
            "n_categories": len(categories),
            "total_correct": sum(cat_correct.values()),
            "total_wrong": sum(cat_wrong.values()),
            "total_hallucinated": sum(cat_hallucinated.values()),
            "overall_f1_hist": {b: overall_f1_hist[b] for b in F1_BINS},
            "overall_failure_modes": {m: overall_modes[m] for m in FAILURE_MODES},
        },
        "simulations": {"all_pred_cuad": sim_all, "non_fit_pred_cuad": sim_non_fit},
        "per_category": per_cat,
        "candidates": candidates,
    }


def render_markdown(rep: dict) -> str:
    s = rep["summary"]
    lines = [
        "# T07 Phase A: CUAD Offline Error Analysis",
        "",
        "Generated by `tools/cuad_analysis.py` on `data/unified/dev.jsonl` and `results/llm_dev.jsonl`.",
        "",
        "## 1. Overall Summary",
        f"- Dev CUAD docs: **{s['n_dev_cuad_docs']}** (predicted in `llm_dev`: **{s['n_pred_cuad_docs']}**, `fit` CUAD docs: **{s['n_fit_cuad_docs']}**)",
        f"- Categories: **{s['n_categories']}**",
        f"- Predictions: **{s['total_correct']}** correct / **{s['total_wrong']}** wrong / **{s['total_hallucinated']}** hallucinated",
        "",
        "### Wrong Prediction Token-F1 Histogram",
        "| F1 bin | Count |",
        "|---|---:|",
    ]
    for b in F1_BINS:
        lines.append(f"| {b} | {s['overall_f1_hist'][b]} |")

    lines += [
        "",
        "### Wrong Prediction Failure Modes",
        "| Mode | Count | Description |",
        "|---|---:|---|",
        f"| `subset` | {s['overall_failure_modes']['subset']} | Grounded pred is a substring/subset of gold (truncated clause) |",
        f"| `superset` | {s['overall_failure_modes']['superset']} | Grounded pred contains gold plus extra surrounding text |",
        f"| `missing_passages` | {s['overall_failure_modes']['missing_passages']} | Multi-passage gold where pred matched at least one passage but missed others |",
        f"| `other_location` | {s['overall_failure_modes']['other_location']} | Grounded in document, does not match gold location |",
        f"| `paraphrase` | {s['overall_failure_modes']['paraphrase']} | Not grounded in document text (reworded/altered) |",
        "",
        "## 2. Offline Rule Simulations (Legacy `llm_dev`)",
        "Medians and single-passage rates (`>= 0.80`) learned on `fit`.",
        "",
        "### Non-`fit` Predicted CUAD Docs (out-of-sample)",
        "| Rule | Booked | Correct | Wrong | Hallucinated | Precision | Net (E=100) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, st in rep["simulations"]["non_fit_pred_cuad"].items():
        prec = f"{st['precision']:.3f}" if st["precision"] is not None else "n/a"
        lines.append(f"| `{name}` | {st['booked']} | {st['correct']} | {st['wrong']} | {st['hallucinated']} | {prec} | {st['net_e100']} |")

    lines += [
        "",
        "### All Predicted CUAD Docs",
        "| Rule | Booked | Correct | Wrong | Hallucinated | Precision | Net (E=100) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, st in rep["simulations"]["all_pred_cuad"].items():
        prec = f"{st['precision']:.3f}" if st["precision"] is not None else "n/a"
        lines.append(f"| `{name}` | {st['booked']} | {st['correct']} | {st['wrong']} | {st['hallucinated']} | {prec} | {st['net_e100']} |")

    lines += [
        "",
        "## 3. Per-Category Statistics & Failure Modes",
        "| Category | Gold % | Passages (mean/max/1-pass%) | Med Tok | Correct | Wrong | Halluc | Prec | Top Failure Mode |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for c in rep["candidates"]:
        cat = c["category"]
        st = rep["per_category"][cat]
        p_str = f"{st['gold_passages_mean']:.2f}/{st['gold_passages_max']}/{st['gold_single_passage_share']*100:.0f}%"
        prec = f"{st['precision']:.3f}" if st["precision"] is not None else "n/a"
        lines.append(
            f"| {cat} | {st['gold_present_share']*100:.1f}% | {p_str} | {st['gold_median_tokens']:.0f} | "
            f"{st['pred_correct']} | {st['pred_wrong']} | {st['pred_hallucinated']} | {prec} | {c['primary_issue']} |"
        )

    lines += [
        "",
        "## 4. Candidate Categories & Prompt Fixes for Phase B (`cuad-v1`)",
        "Top categories by legacy precision / single-passage suitability and the prompt rules needed:",
        "",
    ]
    for c in rep["candidates"][:15]:
        lines.append(
            f"- **{c['category']}** (prec={c['precision']:.3f}, 1-pass={c['single_passage_share']*100:.0f}%, "
            f"med_tok={c['median_tokens']:.0f}): primary issue `{c['primary_issue']}`"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", default=str(ROOT / "data/unified/dev.jsonl"))
    ap.add_argument("--pred", default=str(ROOT / "results/llm_dev.jsonl"))
    ap.add_argument("--splits-manifest", default=str(ROOT / "data/splits/manifest.json"))
    ap.add_argument("--out-md", default=str(ROOT / "docs/cuad_analysis.md"))
    ap.add_argument("--out-json", default=str(ROOT / "results/cuad_analysis.json"))
    a = ap.parse_args(argv)

    gold_records = read_jsonl(Path(a.gold))
    pred_records = read_jsonl(Path(a.pred))
    cuad_texts = router.load_cuad(ROOT / "data")
    fit_ids = load_fit_ids(Path(a.splits_manifest) if a.splits_manifest else None)

    rep = analyze(gold_records, pred_records, cuad_texts, fit_ids)
    md = render_markdown(rep)

    out_md = Path(a.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")

    if a.out_json:
        out_json = Path(a.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    s = rep["summary"]
    print(f"Wrote {out_md} ({s['total_correct']} correct / {s['total_wrong']} wrong / {s['total_hallucinated']} hallucinated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
