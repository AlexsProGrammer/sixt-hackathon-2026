"""Starter script: load the data, look at it, make the baseline plan and write it.

Run it cell by cell (the `# %%` markers work in most editors) or as a whole: `python starter.py`.
Python 3.14 or newer.
"""

# %% Imports
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fleetkit import baseline_plan, load_instance, write_plan  # noqa: E402

# %% Load and validate all data files
instance = load_instance(data_dir=HERE / "data")
print("Horizon:", instance.horizon.iloc[0].to_dict())
print("Stations:", len(instance.stations))
print("Vehicles in the snapshot:", len(instance.fleet_snapshot))
print("Reservations per group:")
print(instance.reservations["status"].value_counts().to_string())

# %% Look at the costs and the caps
print(instance.categories.to_string(index=False))
print(instance.transfer_costs.to_string(index=False))

# %% Make the baseline plan and write it in the submission format
df_baseline = baseline_plan(instance=instance)
write_plan(df_plan=df_baseline, path=HERE / "plans" / "baseline.csv")
print(f"Baseline plan: {len(df_baseline)} rows, {df_baseline['cars'].sum()} cars added.")

# %% A small model with PuLP 4 and CBC (toy numbers, not the challenge data)
# PuLP 4 differs from older tutorials: create variables with model.add_variable(...) or
# model.add_variable_dict(...), and read the status from the object that solve() returns.
import pulp  # noqa: E402

toy_stations = ["X", "Y", "Z"]
# (car-days in the bucket, marginal revenue per car-day), best bucket first
toy_buckets = {"X": [(5, 60.0), (5, 30.0)], "Y": [(3, 80.0), (6, 20.0)], "Z": [(8, 40.0)]}
toy_holding_cost = 25.0
toy_spare_cars = 10

model = pulp.LpProblem("toy", pulp.LpMaximize)
cars = model.add_variable_dict("cars_%s", toy_stations, lowBound=0, cat="Integer")
served = {
    (s, b): model.add_variable(f"served_{s}_{b}", lowBound=0, upBound=size)
    for s in toy_stations
    for b, (size, _) in enumerate(toy_buckets[s])
}
model += pulp.lpSum(
    margin * served[s, b] for s in toy_stations for b, (_, margin) in enumerate(toy_buckets[s])
) - toy_holding_cost * pulp.lpSum(cars.values())
for s in toy_stations:
    model += pulp.lpSum(served[s, b] for b in range(len(toy_buckets[s]))) <= cars[s]
model += pulp.lpSum(cars.values()) <= toy_spare_cars

stats = model.solve(pulp.COIN_CMD(msg=False, timeLimit=60, gapRel=0.01))
# TimeLimit or GapLimit with a solution is a usable result; only "no solution" is a failure.
if not stats.has_solution:
    raise RuntimeError(f"No solution: {stats.status}")
print("Status:", stats.status.name, "objective:", stats.objective)
print({s: round(cars[s].value()) for s in toy_stations})

# %% How to submit
# 1. Write your plan with write_plan(df_plan=..., path=...). It checks the format, not the feasibility.
# 2. Copy the CSV into your team folder in the shared folder, under a new file name.
# 3. After a short time a file with the same name and the ending .result.md appears next to it.
# 4. Put your final plan into your team folder as final.csv before the deadline.
