# Project 2: Mileage Forecasting & Erroneous Mileage Detection

**Project owners:** Julian Hackinger, Ernest Quintana

**Questions before the hackathon:** email the project owners directly: julian.hackinger@sixt.com, ernest.quintana@sixt.com. On the day, technical support is available on site and domain expertise remotely; the on-site team will coordinate.

## Problem
**A. Mileage prediction / nowcasting / forecasting.** For long-term rentals we only get an odometer reading when the vehicle is returned, which can lag up to four weeks for customers on monthly reporting. Current mileage is needed for valuation and defleet decisions. We need to **nowcast** current mileage and **forecast** future mileage.

**B. Erroneous mileage detection.** Reported mileage is sometimes wrong (on purpose or by accident). Using the same features, we want a model or rule set that flags reports that don't match a vehicle's expected usage pattern.

The two are linked: a good mileage predictor gives an expected value, and a report that deviates sharply from it is a natural candidate to flag. A single team can reasonably attempt both in one day if scoped as "build the predictor, then flag residual outliers". They could also be separated.

## Approach
- **A.** Nowcast the current mileage using information on the current rental status. Forecast future mileage using historical driving patterns.
- **B.** There is no ready-made "this report was wrong" label in the data. Two workable approaches for a one-day scope:
  - **Residual-based flagging:** train the predictor, then flag reports whose actual value deviates from the prediction beyond a threshold (e.g. z-score or quantile cutoff on residuals). Unsupervised, no labels needed.
  - **Rule-based proxy labels:** build weak labels from physically implausible cases (e.g. mileage decreasing between readings, daily mileage rate above a plausible maximum) to sanity-check or lightly supervise the flagging.

## Data
A small example file, [example_file.csv](example_file.csv) (57 rows, one vehicle, same columns as below), is in this folder so you can try things now. The full datasets will be provided for the teams that choose this topic. Do not use real data outside the provided sample. Identifiers are anonymized or salt-hashed.

Schema (one row per status update):
- `vhcl_anon_id`: anonymized internal vehicle ID (vehicle number is also salt-hashed)
- `acriss_code_anonymized`: anonymized ACRISS code ([LINK](https://www.sixt.de/mietwagenleitfaden/acriss-code/))
- `vehicle_level`: vehicle category (size, cost, power and luxury; e.g. Standard, Intermediate, Full Size)
- `vehicle_type`: two-character vehicle type and body style (doors, wagon, SUV; e.g. Off Road, Limousine)
- `model_year`: model year of the vehicle
- `driven_wheels`: drivetrain configuration (4x4, AWD, FWD, RWD)
- `power_ps`: horse power
- `cubic_capacity_liter`: cubic capacity in liters
- `status_code_anonymized`: 1 = new vehicle, 2 = active vehicle, 3 = vehicle in defleet process, 4 = sold vehicle
- `vhcl_fct_taken_datm`: status taken timestamp (does not always have a new mileage)
- `vhcl_current_mileage`: mileage at `vhcl_fct_taken_datm`
- `repair_status`: whether the vehicle is currently on repair
- `on_rent_status`: whether the vehicle is currently on rent
- `rental_product`: if on rent, which type of product
- `one_way_flg`: if on rent, whether on a one-way rental
- `rntl_handover_date`: rental handover (start of rental)
- `rntl_return_date`: rental return (end of rental)
- `vhcl_max_mileage`: maximum mileage set in the system
- `brnc_code`: salt-hashed branch code (individual SIXT branch)
- `brnc_pool_code`: salt-hashed pool code (a pool of branches; e.g. all branches within one city)
- `brnc_region_code`: salt-hashed region code (a US sub-region; e.g. Northern California)
- `brnc_state_code`: salt-hashed state code (a US state)
- `uti_plan`: utilization projected/planned for that month

## Expected outcome
- **A.** A model that nowcasts and forecasts mileage of a vehicle fleet.
- **B.** A model or rule set that flags mileage reports that deviate from expected usage.

**Results are judged on:** error on held-out vehicles / periods (e.g. MAE, MAPE) for nowcast and forecast, compared to a naive baseline; and how plausible the flagged reports are.

## Setup

<img src="../assets/time-quick-setup.svg" alt="Under 5 minutes" width="360">

**Quick setup (under 5 min):** `bash setup.sh` in this folder. It makes a virtual environment and runs `starter.py` (a naive baseline and simple flags to beat) on the small `example_file.csv`, or on the organizers' CSV once you put it in `data/` (git-ignored). Python is our starting point; any language is fine.
Do this **before the hackathon day** (repo is shared on 12 Nov).

- `git` and **Python 3.11+**, with a virtual environment (`python -m venv .venv` or `uv venv`).
- Your own LLM coding agent, so you can work with the tool you are most comfortable with. SIXT provides LLM API keys for tasks that need one.
- Create `requirements.txt` / `pyproject.toml` in this folder for your own dependencies. Never commit secrets (use `.env`).
- Data: try the small `example_file.csv` now; the full datasets will be added by the organizers for teams that choose this topic in their repos
- Check: you can clone or fork the repo and run `python --version` in your environment.

## Submission
Code, a `SUBMISSION.md` in this folder (approach, results, how to run) and evaluation results.
Also **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides) in your project folder, included in your repo.
