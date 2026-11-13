#!/usr/bin/env python3
"""
Compares all valid runs in results/*.jsonl on identical doc_id intersections
and generates exactly 4 clean, slide-ready matplotlib plots in results/plots/.
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

_spec = importlib.util.spec_from_file_location("official_score", HERE / "5_score.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

PALETTE = ["#5c6bc0", "#ef5350", "#ffa726", "#26a69a", "#2e7d32", "#8e24aa", "#00838f"]


def load_gold_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["doc_id"]: r for r in S.read_jsonl(path)}


def discover_pred_files(results_dir: Path) -> list[Path]:
    files = []
    for p in sorted(results_dir.glob("*.jsonl")):
        if p.name.endswith((".diagnostics.jsonl", ".samples.jsonl")):
            continue
        if p.stat().st_size == 0:
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


def common_subset(runs: dict[str, dict], gold_map: dict[str, dict], skip_tiny_smoke: bool = True) -> tuple[set[str], dict[str, dict]]:
    filtered = dict(runs)
    if skip_tiny_smoke and len(filtered) > 1:
        non_smoke = {k: v for k, v in filtered.items() if len(v) > 15}
        if non_smoke:
            filtered = non_smoke
    if not filtered:
        return set(), {}
    shared_ids = set(gold_map.keys())
    for preds in filtered.values():
        shared_ids &= set(preds.keys())
    aligned = {name: {did: preds[did] for did in shared_ids} for name, preds in filtered.items()}
    return shared_ids, aligned


def score_all(gold_subset: list[dict], aligned_runs: dict[str, dict], threshold: float) -> dict[str, dict]:
    out = {}
    for name, preds in aligned_runs.items():
        out[name] = {
            "e100": S.score(gold_subset, preds, threshold=threshold, error_cost=100.0),
            "e20": S.score(gold_subset, preds, threshold=threshold, error_cost=20.0),
            "e500": S.score(gold_subset, preds, threshold=threshold, error_cost=500.0),
        }
    return out


def print_table(title: str, n_docs: int, scored: dict[str, dict], threshold: float):
    print(f"\n## {title} ({n_docs} shared docs, threshold = {threshold:.2f})\n")
    print("| Method | Accepted | Correct | Wrong | Halluc. | Precision | Coverage | Saving (100x) | Saving (20x) | Saving (500x) |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name, bundle in scored.items():
        res = bundle["e100"]
        d = res["declared"]
        prec = f"{d['precision']*100:.1f}%" if d["accepted"] > 0 else "n/a"
        print(
            f"| `{name}` | {d['accepted']} | {res['at_threshold']['correct']} | {d['wrong']} | "
            f"{d['hallucinated']} | {prec} | {d['coverage']*100:.1f}% | "
            f"**{d['net_saving_pct']*100:.1f}%** | {bundle['e20']['declared']['net_saving_pct']*100:.1f}% | "
            f"{bundle['e500']['declared']['net_saving_pct']*100:.1f}% |"
        )


def plot_precision_coverage(scored: dict[str, dict], title: str, out_path: Path, threshold: float):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=180)
    for i, (name, bundle) in enumerate(scored.items()):
        res = bundle["e100"]
        color = PALETTE[i % len(PALETTE)]
        pts = [p for p in res["curve"] if p["accepted"] > 0]
        if not pts:
            ax.scatter([0.0], [100.0], color=color, s=70, marker="s", label=f"{name} (0% auto / all human)")
            continue
        cov = [p["coverage"] * 100 for p in pts]
        prec = [p["precision"] * 100 for p in pts]
        ax.plot(cov, prec, marker="o", markersize=3.5, linewidth=2.0, color=color, label=name)
        d = res["declared"]
        if d["accepted"] > 0:
            ax.scatter([d["coverage"] * 100], [d["precision"] * 100], color=color, edgecolor="black", s=85, zorder=6)

    ax.axhline(99.01, color="#c62828", linestyle="--", linewidth=1.4, label="99.01% Break-Even Precision (100:1 cost)")
    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=10)
    ax.set_xlabel("Coverage (% of truly present fields auto-booked)", fontsize=10)
    ax.set_ylabel("Precision (% of auto-booked fields correct)", fontsize=10)
    ax.set_xlim(-2, 102)
    ax.set_ylim(0, 106)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=True, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def plot_net_saving(scored: dict[str, dict], title: str, out_path: Path, threshold: float):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.2, 4.4), dpi=180)
    names = list(scored.keys())
    vals = [scored[n]["e100"]["declared"]["net_saving_pct"] * 100 for n in names]
    colors = ["#2e7d32" if v > 0 else ("#607d8b" if abs(v) < 1e-9 else "#c62828") for v in vals]

    bars = ax.bar(names, vals, color=colors, width=0.52, edgecolor="#222222", linewidth=0.6)
    ax.axhline(0, color="#111111", linewidth=1.1)

    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    span = max(hi - lo, 20.0)
    ax.set_ylim(lo - 0.18 * span, hi + 0.18 * span)

    for bar, v in zip(bars, vals):
        offset = 0.03 * span if v >= 0 else -0.03 * span
        va = "bottom" if v >= 0 else "top"
        ax.text(bar.get_x() + bar.get_width() / 2, v + offset, f"{v:.1f}%", ha="center", va=va, fontsize=9, fontweight="bold")

    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=10)
    ax.set_ylabel("Net Saving vs. Manual Review (%)", fontsize=10)
    plt.xticks(rotation=15, ha="right", fontsize=9.5)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def plot_cost_sensitivity(scored: dict[str, dict], title: str, out_path: Path):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(8.5, 4.5), dpi=180)
    names = list(scored.keys())
    x = np.arange(len(names))
    w = 0.25

    v20 = [scored[n]["e20"]["declared"]["net_saving_pct"] * 100 for n in names]
    v100 = [scored[n]["e100"]["declared"]["net_saving_pct"] * 100 for n in names]
    v500 = [scored[n]["e500"]["declared"]["net_saving_pct"] * 100 for n in names]

    # Clip extreme negative bars at -250% for readability while annotating true values
    clip_min = -250.0
    ax.bar(x - w, [max(v, clip_min) for v in v20], width=w, color="#42a5f5", label="Error Cost = 20x (95.2% break-even)")
    ax.bar(x, [max(v, clip_min) for v in v100], width=w, color="#ef5350", label="Error Cost = 100x (99.0% break-even)")
    ax.bar(x + w, [max(v, clip_min) for v in v500], width=w, color="#8e24aa", label="Error Cost = 500x (99.8% break-even)")

    ax.axhline(0, color="#111111", linewidth=1.1)
    ax.set_ylim(clip_min - 35, max(max(v20 + v100 + v500 + [10.0]) + 25, 30))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right", fontsize=9.5)
    ax.set_ylabel("Net Saving % (clipped at -250%)", fontsize=9.5)
    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=True, fontsize=8.2)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()
    threshold = resolve_threshold(a.threshold)

    # Remove old cluttered plots first
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in PLOTS_DIR.glob("*.png"):
        old.unlink()

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

    # 1. Unified test_public comparison (all methods on exact shared docs -> 3 plots)
    t_ids, t_aligned = common_subset(test_runs, test_gold, skip_tiny_smoke=True)
    if t_ids:
        t_gold_sub = [test_gold[did] for did in sorted(t_ids)]
        t_scored = score_all(t_gold_sub, t_aligned, threshold)
        print_table("Held-Out test_public Comparison (All Methods Aligned)", len(t_ids), t_scored, threshold)

        plot_precision_coverage(
            t_scored,
            f"1. Precision vs. Coverage — test_public ({len(t_ids)} shared docs, dot = @{threshold:.2f})",
            PLOTS_DIR / "1_test_precision_coverage.png",
            threshold,
        )
        plot_net_saving(
            t_scored,
            f"2. Net Saving vs. Manual Review — test_public ({len(t_ids)} docs, @{threshold:.2f})",
            PLOTS_DIR / "2_test_net_saving.png",
            threshold,
        )
        plot_cost_sensitivity(
            t_scored,
            f"3. Error-Cost Sensitivity (20x / 100x / 500x) — test_public ({len(t_ids)} docs, @{threshold:.2f})",
            PLOTS_DIR / "3_test_error_cost_sensitivity.png",
        )

    # 2. Unified dev comparison (llm_dev vs probly_dev on exact shared docs -> 1 plot)
    d_ids, d_aligned = common_subset(dev_runs, dev_gold, skip_tiny_smoke=True)
    if d_ids:
        d_gold_sub = [dev_gold[did] for did in sorted(d_ids)]
        d_scored = score_all(d_gold_sub, d_aligned, threshold)
        print_table("Dev Set Progression (All Methods Aligned)", len(d_ids), d_scored, threshold)

        plot_precision_coverage(
            d_scored,
            f"4. Dev Set Precision vs. Coverage ({len(d_ids)} shared docs, dot = @{threshold:.2f})",
            PLOTS_DIR / "4_dev_precision_coverage.png",
            threshold,
        )

    print("\nGenerated 4 clean plots in results/plots/:")
    for p in sorted(PLOTS_DIR.glob("*.png")):
        print(" -", p)


if __name__ == "__main__":
    main()
