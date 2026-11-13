#!/usr/bin/env python3
"""
Compares all probly versions (probly, probly2..probly5) alongside LLM & non-AI baselines
on identical doc_id intersections, highlighting the newest run (e.g. probly5).
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

PALETTE = ["#78909c", "#42a5f5", "#ffa726", "#ab47bc", "#26a69a", "#ef5350", "#1b5e20"]


def load_gold_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["doc_id"]: r for r in S.read_jsonl(path)}


def discover_pred_files(results_dir: Path) -> list[Path]:
    files = []
    for p in sorted(results_dir.rglob("*.jsonl")):
        if any(part in ("split", "plots") for part in p.parts):
            continue
        if p.name.endswith((".diagnostics.jsonl", ".samples.jsonl")) or p.name.startswith(("release_", "final_dev_input")):
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


def find_newest_probly(names: list[str]) -> str | None:
    probly_names = [n for n in names if "probly" in n.lower()]
    return sorted(probly_names)[-1] if probly_names else None


def align_all_runs(runs: dict[str, dict], gold_map: dict[str, dict]) -> tuple[set[str], dict[str, dict]]:
    """Aligns all runs on the exact shared doc_ids of the newest probly run (or all runs)."""
    if not runs:
        return set(), {}
    newest = find_newest_probly(list(runs.keys()))
    target_ids = set(runs[newest].keys()) & set(gold_map.keys()) if newest else set(gold_map.keys())

    # Keep all runs that cover at least those target_ids; otherwise intersect across all runs
    covering = {k: v for k, v in runs.items() if target_ids.issubset(v.keys())}
    if len(covering) >= 2:
        aligned = {k: {did: v[did] for did in target_ids} for k, v in covering.items()}
        return target_ids, aligned

    shared = set(gold_map.keys())
    for v in runs.values():
        shared &= set(v.keys())
    aligned = {k: {did: v[did] for did in shared} for k, v in runs.items()}
    return shared, aligned


def score_all(gold_subset: list[dict], aligned_runs: dict[str, dict], threshold: float) -> dict[str, dict]:
    out = {}
    for name in sorted(aligned_runs.keys()):
        preds = aligned_runs[name]
        out[name] = {
            "e100": S.score(gold_subset, preds, threshold=threshold, error_cost=100.0),
            "e20": S.score(gold_subset, preds, threshold=threshold, error_cost=20.0),
            "e500": S.score(gold_subset, preds, threshold=threshold, error_cost=500.0),
        }
    return out


def print_table(title: str, n_docs: int, scored: dict[str, dict], threshold: float, newest: str | None):
    print(f"\n## {title} ({n_docs} shared docs, threshold = {threshold:.2f})\n")
    print("| Method | Accepted | Correct | Wrong | Halluc. | Precision | Coverage | Saving (100x) | Saving (20x) | Saving (500x) |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name, bundle in scored.items():
        res = bundle["e100"]
        d = res["declared"]
        prec = f"{d['precision']*100:.1f}%" if d["accepted"] > 0 else "n/a"
        label = f"**{name} (LATEST)**" if name == newest else f"`{name}`"
        print(
            f"| {label} | {d['accepted']} | {res['at_threshold']['correct']} | {d['wrong']} | "
            f"{d['hallucinated']} | {prec} | {d['coverage']*100:.1f}% | "
            f"**{d['net_saving_pct']*100:.1f}%** | {bundle['e20']['declared']['net_saving_pct']*100:.1f}% | "
            f"{bundle['e500']['declared']['net_saving_pct']*100:.1f}% |"
        )


def plot_precision_coverage(scored: dict[str, dict], title: str, out_path: Path, threshold: float, newest: str | None):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.8, 5.0), dpi=180)
    for i, (name, bundle) in enumerate(scored.items()):
        res = bundle["e100"]
        is_latest = name == newest
        color = "#1b5e20" if is_latest else PALETTE[i % (len(PALETTE) - 1)]
        lw = 3.0 if is_latest else 1.7
        alpha = 1.0 if is_latest else 0.78
        label = f"{name} (LATEST)" if is_latest else name

        pts = [p for p in res["curve"] if p["accepted"] > 0]
        if not pts:
            ax.scatter([0.0], [100.0], color=color, s=75, marker="s", label=f"{label} (0% auto)")
            continue
        cov = [p["coverage"] * 100 for p in pts]
        prec = [p["precision"] * 100 for p in pts]
        ax.plot(cov, prec, marker="o", markersize=4 if is_latest else 2.8, linewidth=lw, alpha=alpha, color=color, label=label, zorder=5 if is_latest else 3)

        d = res["declared"]
        if d["accepted"] > 0:
            ax.scatter([d["coverage"] * 100], [d["precision"] * 100], color=color, edgecolor="black", s=105 if is_latest else 65, zorder=7)

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


def plot_net_saving(scored: dict[str, dict], title: str, out_path: Path, newest: str | None):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.6, 4.5), dpi=180)
    names = list(scored.keys())
    labels = [f"{n}\n(LATEST)" if n == newest else n for n in names]
    vals = [scored[n]["e100"]["declared"]["net_saving_pct"] * 100 for n in names]
    colors = ["#2e7d32" if v > 0 else ("#607d8b" if abs(v) < 1e-9 else "#c62828") for v in vals]

    bars = ax.bar(labels, vals, color=colors, width=0.52, edgecolor="#222222", linewidth=0.7)
    ax.axhline(0, color="#111111", linewidth=1.1)

    lo, hi = min(vals + [0.0]), max(vals + [0.0])
    span = max(hi - lo, 20.0)
    ax.set_ylim(lo - 0.18 * span, hi + 0.18 * span)

    for bar, v in zip(bars, vals):
        offset = 0.03 * span if v >= 0 else -0.03 * span
        va = "bottom" if v >= 0 else "top"
        ax.text(bar.get_x() + bar.get_width() / 2, v + offset, f"{v:.1f}%", ha="center", va=va, fontsize=8.8, fontweight="bold")

    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=10)
    ax.set_ylabel("Net Saving vs. Manual Review (%)", fontsize=10)
    plt.xticks(rotation=18, ha="right", fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def plot_cost_sensitivity(scored: dict[str, dict], title: str, out_path: Path, newest: str | None):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(8.8, 4.6), dpi=180)
    names = list(scored.keys())
    labels = [f"{n}*" if n == newest else n for n in names]
    x = np.arange(len(names))
    w = 0.25

    v20 = [scored[n]["e20"]["declared"]["net_saving_pct"] * 100 for n in names]
    v100 = [scored[n]["e100"]["declared"]["net_saving_pct"] * 100 for n in names]
    v500 = [scored[n]["e500"]["declared"]["net_saving_pct"] * 100 for n in names]

    clip_min = -250.0
    ax.bar(x - w, [max(v, clip_min) for v in v20], width=w, color="#42a5f5", label="Error Cost = 20x (95.2% break-even)")
    ax.bar(x, [max(v, clip_min) for v in v100], width=w, color="#ef5350", label="Error Cost = 100x (99.0% break-even)")
    ax.bar(x + w, [max(v, clip_min) for v in v500], width=w, color="#8e24aa", label="Error Cost = 500x (99.8% break-even)")

    ax.axhline(0, color="#111111", linewidth=1.1)
    ax.set_ylim(clip_min - 35, max(max(v20 + v100 + v500 + [10.0]) + 25, 30))
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=9)
    ax.set_ylabel("Net Saving % (clipped at -250%)", fontsize=9.5)
    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=True, fontsize=8.2)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()
    threshold = resolve_threshold(a.threshold)

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
        key = path.stem if path.parent == RESULTS_DIR else f"{path.parent.name}/{path.stem}"
        if ids.issubset(test_gold.keys()):
            test_runs[key] = preds
        elif ids.issubset(dev_gold.keys()):
            dev_runs[key] = preds

    print(f"Found dev runs: {list(dev_runs.keys())}")
    print(f"Found test_public runs: {list(test_runs.keys())}")

    # 1. test_public comparison (all versions aligned to newest probly run)
    t_ids, t_aligned = align_all_runs(test_runs, test_gold)
    if t_ids:
        newest_t = find_newest_probly(list(t_aligned.keys()))
        t_gold_sub = [test_gold[did] for did in sorted(t_ids)]
        t_scored = score_all(t_gold_sub, t_aligned, threshold)
        print_table("Held-Out test_public Comparison (All Versions)", len(t_ids), t_scored, threshold, newest_t)

        plot_precision_coverage(
            t_scored,
            f"1. Precision vs. Coverage — test_public ({len(t_ids)} shared docs, dot = @{threshold:.2f})",
            PLOTS_DIR / "1_test_precision_coverage.png",
            threshold,
            newest_t,
        )
        plot_net_saving(
            t_scored,
            f"2. Net Saving vs. Manual Review — test_public ({len(t_ids)} docs, @{threshold:.2f})",
            PLOTS_DIR / "2_test_net_saving.png",
            newest_t,
        )
        plot_cost_sensitivity(
            t_scored,
            f"3. Error-Cost Sensitivity (20x / 100x / 500x) — test_public ({len(t_ids)} docs, @{threshold:.2f})",
            PLOTS_DIR / "3_test_error_cost_sensitivity.png",
            newest_t,
        )

    # 2. dev comparison (all probly / llm versions aligned to newest probly run)
    d_ids, d_aligned = align_all_runs(dev_runs, dev_gold)
    if d_ids:
        newest_d = find_newest_probly(list(d_aligned.keys()))
        d_gold_sub = [dev_gold[did] for did in sorted(d_ids)]
        d_scored = score_all(d_gold_sub, d_aligned, threshold)
        print_table("Dev Set Progression (probly1..probly5)", len(d_ids), d_scored, threshold, newest_d)

        plot_precision_coverage(
            d_scored,
            f"4. Dev Progression: Precision vs. Coverage ({len(d_ids)} shared docs, dot = @{threshold:.2f})",
            PLOTS_DIR / "4_dev_precision_coverage.png",
            threshold,
            newest_d,
        )

    print("\nSaved 4 clean plots in results/plots/:")
    for p in sorted(PLOTS_DIR.glob("*.png")):
        print(" -", p)


if __name__ == "__main__":
    main()
