"""Project 2 starter: a naive nowcast baseline and simple flags. Beat it, then flag residual outliers.

Usage: python starter.py [file.csv]   (default: first CSV in data/, else example_file.csv)
Baseline: predict each reading as the previous reading + the vehicle's average daily rate so far.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
found = sorted((HERE / "data").glob("*.csv")) or [HERE / "example_file.csv"]
path = Path(sys.argv[1]) if len(sys.argv) > 1 else found[0]
df = pd.read_csv(path, parse_dates=["vhcl_fct_taken_datm"])
df = df.dropna(subset=["vhcl_current_mileage"]).sort_values(["vhcl_anon_id", "vhcl_fct_taken_datm"])
print(f"{path.name}: {len(df)} readings, {df.vhcl_anon_id.nunique()} vehicles")

g = df.groupby("vhcl_anon_id")
df["prev_km"] = g.vhcl_current_mileage.shift()
df["days"] = g.vhcl_fct_taken_datm.diff().dt.days
df["rate"] = (df.vhcl_current_mileage - df.prev_km) / df.days.replace(0, np.nan)
df["rate_before"] = g.rate.transform(lambda s: s.shift().expanding().mean())  # only earlier readings: no leakage
df["pred"] = df.prev_km + df.rate_before * df.days
ev = df.dropna(subset=["pred"])
if len(ev):
    print(f"Naive nowcast on {len(ev)} readings: MAE = {(ev.pred - ev.vhcl_current_mileage).abs().mean():.0f} km")
else:
    print("Not enough history per vehicle to evaluate the baseline.")

# simple flags: mileage going down, or an implausible rate (here > 1000 km/day)
flags = df[(df.vhcl_current_mileage < df.prev_km) | (df.rate > 1000)]
print(f"Rule-based flags: {len(flags)} of {len(df)} readings")
