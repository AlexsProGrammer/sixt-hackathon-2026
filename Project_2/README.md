# Project 2: Nowcasting / Forecasting Mileage

**Project owners:** Julian Hackinger, Ernest Quintana

**Questions before the hackathon:** email the project owners directly: julian.hackinger@sixt.com, ernest.quintana@sixt.com. On the day, ask on site.

## Problem
For the majority of the fleet, odometer updates only arrive once vehicles are returned. Mileage information can therefore be very outdated (up to four weeks) for long-term customers who report mileage monthly. Current mileage is needed for valuation and fleet disposal decisions, and future mileage needs to be forecast.

## Approach
- Nowcast the current mileage using information on the current rental status.
- Forecast future mileage using historical driving patterns.

## Data
Ideally based on vehicle status data. A mock or anonymized sample will be provided. Do not use real data outside the provided sample.

## Expected outcome
A model that nowcasts and forecasts mileage of a vehicle fleet.

**Results are judged on:** error on held-out vehicles / periods (e.g. MAE, MAPE) for nowcast and forecast, compared to a naive baseline.

## Setup
Do this **before the hackathon day** (repo is shared on 12 Nov).

- `git` and **Python 3.11+**, with a virtual environment (`python -m venv .venv` or `uv venv`).
- Your own LLM coding agent. No LLM access is provided by SIXT.
- Create `requirements.txt` / `pyproject.toml` in this folder for your own dependencies. Never commit secrets (use `.env`).
- Data: a mock or anonymized sample will be added by the organizers. _[TBD: location]_
- Check: you can clone or fork the repo and run `python --version` in your environment.

## Submission
Code, a `SUBMISSION.md` in this folder (approach, results, how to run) and evaluation results.
Also **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides) in your project folder, included in your repo.
