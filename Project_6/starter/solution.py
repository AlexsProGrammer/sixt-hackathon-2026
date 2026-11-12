"""Your solution. Keep these two functions; everything else is up to you.

fit(train, branches)        -> any object (your trained model / parameters)
predict(model, df, branches) -> DataFrame with columns
    turnaround_id, total_turnaround_min, and one dur_<task> column per task
    (your estimate of the task's duration in minutes; used where the task was performed)

`train` is data/train.csv, `branches` is data/branch_data.csv, `df` is the turnarounds to predict
(same columns as validation.csv). Rules: deterministic (fix every random seed), no network, no files outside this folder
and data/, no hard-coded labels. The code must give the same values every time it runs.
"""
import numpy as np
import pandas as pd

TASKS = ["quick_exterior_cleaning", "normal_exterior_cleaning", "special_cleaning", "interior_cleaning",
         "damage_check", "refuel", "electric_charging", "quick_damage_repair", "tyre_check"]
SEED = 42  # fix seeds if you use randomness (np.random.seed, model random_state, ...)


def _design(df):
    return np.column_stack([np.ones(len(df)), df[TASKS].values.astype(float)])


def fit(train, branches):
    """Baseline: total = intercept + sum of task flags (ordinary least squares)."""
    return np.linalg.lstsq(_design(train), train.total_turnaround_min.values, rcond=None)[0]


def predict(model, df, branches):
    out = pd.DataFrame({"turnaround_id": df.turnaround_id.values, "total_turnaround_min": _design(df) @ model})
    for i, t in enumerate(TASKS):
        out[f"dur_{t}"] = np.clip(model[1 + i], 0, None) * df[t].values
    return out
