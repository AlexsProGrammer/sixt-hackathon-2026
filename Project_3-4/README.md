# Project 3-4: Turnaround Prediction (Action Time and Tasks)

Projects 3 and 4 run as one topic for now. This may change after we hear from the project owner.

**Project owner:** Iulia Pasov

**Questions before the hackathon:** email the project owner directly: iulia.pasov@sixt.com. On the day, ask on site.

## Part A: Predict Turnaround Action Time

### Problem
A turnaround consists of multiple actions (e.g. refueling, charging, special cleaning). We know the total turnaround time but not the time spent on each task.

### Approach
Analyse what impacts each task using only the total turnaround duration. Predict either per task (if it can be extracted) or the total turnaround time for different combinations of actions.

**Results are judged on:** error on total turnaround time (e.g. MAE) and feature importance that makes sense.

## Part B: Predict Turnaround Tasks

### Problem
We would like to know which tasks will be done at turnaround. Those tasks are decided at check-in, but we want to know them before the vehicle is dropped off. This tells us when we expect the car to be ready.

### Approach
EDA plus an ML model. Example: a long-term rental or a child seat implies special cleaning.

**Results are judged on:** precision / recall / F1 per task and feature importance.

## Data
A random sample is feasible. A sample dataset will be provided.

## Expected outcome
ML model(s) and feature importance. You may tackle Part A, Part B, or both.

## Setup
Do this **before the hackathon day** (repo is shared on 12 Nov).

- `git` and **Python 3.11+**, with a virtual environment (`python -m venv .venv` or `uv venv`).
- Your own LLM coding agent, so you can work with the tool you are most comfortable with. SIXT provides LLM API keys for tasks that need one.
- Create `requirements.txt` / `pyproject.toml` in this folder for your own dependencies. Never commit secrets (use `.env`).
- Data: a sample dataset will be added by the organizers. _[TBD: location]_
- Check: you can clone or fork the repo and run `python --version` in your environment.

## Submission
Code, a `SUBMISSION.md` in this folder (approach, results, how to run) and evaluation results.
Also **either** a **1-minute demo video** (`submission/demo.mp4`, under 50 MB) **or** a **small set of slides** (`submission/slides.pdf`, max 5 slides) in your project folder, included in your repo.
