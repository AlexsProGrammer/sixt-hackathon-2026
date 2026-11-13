#!/usr/bin/env python3
"""
Compare all prediction runs in results/*.jsonl on identical doc_id subsets.
Prints Markdown tables for SUBMISSION.md and generates matplotlib PNGs for slides.pdf.

Usage (from Project_1/):
    python3 compare_results.py --threshold 0.95
    # Or automatically read threshold from submission/decision.json if present:
    python3 compare_results.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
DEV_GOLD = HERE / "data/unified/dev.jsonl"
TEST_GOLD = HERE / "data/unified/test_public.jsonl"
RESULTS_DIR = HERE / "results"
DECISION_FILE = HERE / "submission/decision.json"
PLOTS_DIR = RESULTS_DIR / "plots"

# Load official scorer (5_score.py) without modifying it
_spec = importlib.util.spec_from_file_location("official_score", HERE / "5_score.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def load_gold_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["doc_id"]: r for r in S.read_jsonl(path)}


def discover_pred_files(results_dir: Path) -> list[Path]:
    files = []
    for p in sorted(results_dir.glob("*.jsonl")):
        if p.name.endswith(".diagnostics.jsonl"):
            continue
        files.append(p)
    return files


def resolve_threshold(cli_threshold: float | None) -> float:
    if cli_threshold is not None:
        return cli_threshold
    if DECISION_FILE.exists():
        d = json.loads(DECISION_FILE.read_text(encoding="utf-8"))
        if d.get("threshold") is not None:
            return float(d["threshold"])
    return 0.95


def evaluate_group(group_name: str, gold_map: dict[str, dict], runs: dict[str, dict], threshold: float):
    if not runs:
        return

    # Find full-split runs vs partial-subset runs (e.g., --limit 10 or --limit 50)
    full_ids = set(gold_map.keys())
    partial_runs = {name: preds for name, preds in runs.items() if set(preds.keys()) != full_ids}
    full_runs = {name: preds for name, preds in runs.items() if set(preds.keys()) == full_ids}

    comparisons = []
    if full_runs:
        comparisons.append((f"{group_name} (Full Split: {len(full_ids)} docs)", full_ids, full_runs))

    # For partial runs (like llm_dev_10 or a 50-doc subset), compare ALL runs on that exact doc_id intersection
    for p_name, p_preds in partial_runs.items():
        sub_ids = set(p_preds.keys()) & full_ids
        if not sub_ids:
            continue
        aligned = {
            name: {did: preds[did] for did in sub_ids if did in preds}
            for name, preds in runs.items()
            if sub_ids.issubset(preds.keys())
        }
        comparisons.append((f"{group_name} Subset matching `{p_name}` ({len(sub_ids)} docs)", sub_ids, aligned))

    for title, doc_ids, aligned_runs in comparisons:
        gold_subset = [gold_map[did] for did in sorted(doc_ids)]
        print(f"\n## {title} — Declared Threshold = {threshold:.2f}\n")
        print("| Run | Docs | Accepted | Correct | Wrong | Halluc. | Precision | Coverage | Net Saving (100x) | Saving (20x) | Saving (500x) | Best Dev Sweep |")
        print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

        scored_runs = {}
        for name, preds in aligned_runs.items():
            res = S.score(gold_subset, preds, threshold=threshold, error_cost=100.0)
            res_20 = S.score(gold_subset, preds, threshold=threshold, error_cost=20.0)
            res_500 = S.score(gold_subset, preds, threshold=threshold, error_cost=500.0)
            scored_runs[name] = res

            d = res["declared"]
            prec_str = f"{d['precision']*100:.1f}%" if d["accepted"] > 0 else "n/a"
            best_b = res["business"]
            best_str = f"{best_b['saving_pct']*100:.1f}% (@{best_b['threshold']})" if best_b["threshold"] is not None else "0.0%"

            print(
                f"| `{name}` | {len(doc_ids)} | {d['accepted']} | {res['at_threshold']['correct']} | "
                f"{d['wrong']} | {d['hallucinated']} | {prec_str} | {d['coverage']*100:.1f}% | "
                f"**{d['net_saving_pct']*100:.1f}%** | {res_20['declared']['net_saving_pct']*100:.1f}% | "
                f"{res_500['declared']['net_saving_pct']*100:.1f}% | {best_str} |"
            )

        # Print CUAD vs ExtractBench breakdown at declared threshold
        print(f"\n### Dataset Breakdown (`cuad` vs. `extractbench`) — {title}\n")
        print("| Run | CUAD Precision | CUAD Coverage | CUAD Saving | ExtractBench Precision | ExtractBench Coverage | ExtractBench Saving |")
        print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for name, preds in aligned_runs.items():
            row_cells = [f"`{name}`"]
            for src in ("cuad", "extractbench"):
                src_gold = [r for r in gold_subset if r.get("source_dataset") == src]
                if not src_gold:
                    row_cells.extend(["n/a", "n/a", "n/a"])
                    continue
                s_res = S.score(src_gold, preds, threshold=threshold)["declared"]
                p_str = f"{s_res['precision']*100:.1f}%" if s_res["accepted"] > 0 else "n/a"
                row_cells.extend([p_str, f"{s_res['coverage']*100:.1f}%", f"{s_res['net_saving_pct']*100:.1f}%"])
            print("| " + " | ".join(row_cells) + " |")

        make_plots(title, scored_runs, threshold)


def make_plots(title: str, scored_runs: dict[str, dict], threshold: float):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[Note] Install matplotlib (`pip install matplotlib`) to generate PNG plots.")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_")

    # 1. Precision-Coverage (Risk-Coverage) Curve
    fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=160)
    for name, res in scored_runs.items():
        pts = [p for p in res["curve"] if p["accepted"] > 0]
        if not pts:
            continue
        cov = [p["coverage"] * 100 for p in pts]
        prec = [p["precision"] * 100 for p in pts]
        ax.plot(cov, prec, marker="o", markersize=3, linewidth=1.8, label=name)
        # Highlight declared threshold point
        d = res["declared"]
        if d["accepted"] > 0:
            ax.scatter([d["coverage"] * 100], [d["precision"] * 100], s=65, zorder=5)

    ax.axhline(99.01, color="#d9534f", linestyle="--", linewidth=1.2, label="99.01% Break-Even Precision (100:1 cost)")
    ax.set_title(f"Precision vs. Coverage — {title}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Coverage (% of truly present fields auto-booked)")
    ax.set_ylabel("Precision (% of auto-booked fields correct)")
    ax.set_ylim(0, 102)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    p1 = PLOTS_DIR / f"{slug}_precision_coverage.png"
    fig.savefig(p1)
    plt.close(fig)

    # 2. Net Saving Bar Chart at Declared Threshold
    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=160)
    names = list(scored_runs.keys())
    savings = [scored_runs[n]["declared"]["net_saving_pct"] * 100 for n in names]
    colors = ["#2e7d32" if s > 0 else ("#757575" if s == 0 else "#c62828") for s in savings]
    bars = ax.bar(names, savings, color=colors, width=0.55)
    ax.axhline(0, color="#111111", linewidth=1.0)
    ax.set_title(f"Net Saving vs. Manual Review (@ threshold={threshold:.2f})", fontsize=11, fontweight="bold")
    ax.set_ylabel("Net Saving (%)")
    plt.xticks(rotation=20, ha="right", fontsize=8.5)
    for bar, val in zip(bars, savings):
        va = "bottom" if val >= 0 else "top"
        ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.1f}%", ha="center", va=va, fontsize=8.5, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    p2 = PLOTS_DIR / f"{slug}_net_saving.png"
    fig.savefig(p2)
    plt.close(fig)
    print(f"\nSaved plots:\n  - {p1}\n  - {p2}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=None, help="Declared confidence threshold (defaults to submission/decision.json or 0.95)")
    a = ap.parse_args()
    threshold = resolve_threshold(a.threshold)

    dev_gold = load_gold_map(DEV_GOLD)
    test_gold = load_gold_map(TEST_GOLD)
    dev_runs, test_runs = {}, {}

    for path in discover_pred_files(RESULTS_DIR):
        preds = S.load_preds(path)
        if not preds:
            continue
        ids = set(preds.keys())
        if ids.issubset(test_gold.keys()):
            test_runs[path.stem] = preds
        elif ids.issubset(dev_gold.keys()):
            dev_runs[path.stem] = preds
        else:
            print(f"[Skip] {path.name}: doc_ids span multiple splits or unknown split.")

    evaluate_group("test_public", test_gold, test_runs, threshold)
    evaluate_group("dev", dev_gold, dev_runs, threshold)


if __name__ == "__main__":
    main()