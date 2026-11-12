"""Score a predictions file.

    python evaluate.py predictions.csv labels.csv [--task-truth true_task_durations.csv] [--flags ../data/test.csv] [--train-truth ../data/validation_labels.csv]

predictions.csv columns:
  turnaround_id, total_turnaround_min            (required)
  dur_<task>  e.g. dur_refuel, dur_interior_cleaning ...  (optional: your estimate of each task's duration in minutes)
Per-task columns are only scored where the task was performed (flag = 1 in the data).
"""
import argparse
import numpy as np
import pandas as pd

TASKS = ["quick_exterior_cleaning", "normal_exterior_cleaning", "special_cleaning", "interior_cleaning",
         "damage_check", "refuel", "electric_charging", "quick_damage_repair", "tyre_check"]


def evaluate(pred, labels, truth=None, flags=None, train_truth=None):
    out = {}
    m = labels.merge(pred, on="turnaround_id", suffixes=("_true", "_pred"))
    if len(m) != len(labels):
        raise SystemExit(f"predictions cover {len(m)} of {len(labels)} turnarounds")
    err = (m.total_turnaround_min_pred - m.total_turnaround_min_true).abs()
    out["total_MAE_min"] = err.mean()
    out["total_median_AE_min"] = err.median()
    out["share_within_10_min"] = (err <= 10).mean()
    dur_cols = [c for c in pred.columns if c.startswith("dur_")]
    if dur_cols and truth is not None and flags is not None:
        f = flags.set_index("turnaround_id")
        t = truth.set_index("turnaround_id")
        p = pred.set_index("turnaround_id")
        per, skill, neg, abs_sum, true_sum = {}, {}, 0, 0.0, 0.0
        for task in TASKS:
            if f"dur_{task}" not in p:
                continue
            on = f.index[f[task] == 1]
            est = p.loc[on, f"dur_{task}"]
            per[task] = (est - t.loc[on, task]).abs().mean()
            abs_sum += (est - t.loc[on, task]).abs().sum(); true_sum += t.loc[on, task].sum()
            if train_truth is not None:  # skill vs predicting the reference mean duration (validation_labels.csv) for every instance
                tt = train_truth[task][train_truth[task] > 0]
                skill[task] = max(-1.0, 1 - per[task] / (t.loc[on, task] - tt.mean()).abs().mean())  # clipped at -1
            neg += int((est < 0).sum()) + int(est.isna().sum())
        out["per_task_MAE_min"] = per
        out["per_task_MAE_mean"] = float(np.mean(list(per.values())))   # macro: every task counts equally
        out["per_task_WAPE"] = float(abs_sum / true_sum)                 # pooled error / pooled task minutes
        if skill:
            out["per_task_skill_vs_task_mean"] = skill                  # 0 = no better than the mean, 1 = perfect
            out["mean_skill"] = float(np.mean(list(skill.values())))
        out["negative_or_missing_task_estimates"] = neg
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions"); ap.add_argument("labels")
    ap.add_argument("--task-truth"); ap.add_argument("--flags"); ap.add_argument("--train-truth")
    a = ap.parse_args()
    res = evaluate(pd.read_csv(a.predictions), pd.read_csv(a.labels),
                   pd.read_csv(a.task_truth) if a.task_truth else None,
                   pd.read_csv(a.flags) if a.flags else None,
                   pd.read_csv(a.train_truth) if a.train_truth else None)
    for k, v in res.items():
        print(k, v if not isinstance(v, dict) else "")
        if isinstance(v, dict):
            for kk, vv in v.items():
                print(f"   {kk:28s} {vv:6.2f}")
