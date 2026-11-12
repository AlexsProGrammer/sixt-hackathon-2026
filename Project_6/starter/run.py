"""Run a solution. Organizers use the same script on the hidden test set.

    python run.py                                   # fit on data/train.csv, predict data/validation.csv
    python run.py --solution solution.py --test ../data/validation.csv --out predictions.csv
    python run.py --repeat                          # run twice and check the values are identical
    python run.py --compare submitted_predictions.csv   # check the re-run matches the submitted file

Then score:  python evaluate.py predictions.csv ../data/validation_labels.csv \\
                 --task-truth ../data/validation_labels.csv --flags ../data/validation.csv
"""
import argparse, importlib.util, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TASKS = ["quick_exterior_cleaning", "normal_exterior_cleaning", "special_cleaning", "interior_cleaning",
         "damage_check", "refuel", "electric_charging", "quick_damage_repair", "tyre_check"]
ap = argparse.ArgumentParser()
ap.add_argument("--solution", default=str(HERE / "solution.py"))
ap.add_argument("--data", default=str(HERE.parent / "data"))
ap.add_argument("--test", default=None, help="turnarounds to predict (default: <data>/validation.csv)")
ap.add_argument("--out", default="predictions.csv")
ap.add_argument("--repeat", action="store_true", help="run twice and compare")
ap.add_argument("--compare", default=None, help="a previously submitted predictions.csv to compare against")
ap.add_argument("--tol", type=float, default=1e-6)
a = ap.parse_args()

data = Path(a.data)
train = pd.read_csv(data / "train.csv", parse_dates=["return_ts"])
branches = pd.read_csv(data / "branch_data.csv")
test = pd.read_csv(a.test or data / "validation.csv", parse_dates=["return_ts"])


def run_once():
    spec = importlib.util.spec_from_file_location("solution", a.solution)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    t0 = time.time()
    model = mod.fit(train.copy(), branches.copy())
    pred = mod.predict(model, test.copy(), branches.copy())
    print(f"ran in {time.time() - t0:.0f}s")
    assert list(pred.turnaround_id) == list(test.turnaround_id), "predictions must be in the same order as the input"
    assert {"turnaround_id", "total_turnaround_min"} <= set(pred.columns), "missing columns"
    missing = [f"dur_{t}" for t in TASKS if f"dur_{t}" not in pred.columns]
    assert not missing, f"missing per-task estimates (required): {missing}"
    return pred


def same(p, q):
    cols = [c for c in p.columns if c != "turnaround_id" and c in q.columns]
    d = float(np.nanmax(np.abs(p[cols].values.astype(float) - q[cols].values.astype(float)))) if cols else 0.0
    return d <= a.tol, d


pred = run_once()
pred.to_csv(a.out, index=False)
print(f"wrote {a.out} ({len(pred)} rows)")
if a.repeat:
    ok, d = same(pred, run_once())
    print("run twice:", "IDENTICAL" if ok else f"DIFFERENT (max abs difference {d:.4g})")
if a.compare:
    ok, d = same(pred, pd.read_csv(a.compare))
    print("matches submitted predictions:", "YES" if ok else f"NO (max abs difference {d:.4g})")
