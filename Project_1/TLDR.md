# TL;DR — Essential Commands

Run everything from `Project_1/`:

```bash
cd Project_1
```

---

## 1. Test Models & Endpoints

```bash
# Test all configured .env roles (default, A, B, C, ocr) for valid ID + JSON output
.venv/bin/python tools/test_model.py --role all

# Test a single role: default | a | b | c | ocr
.venv/bin/python tools/test_model.py --role default

# Discover all :free models on LLM_BASE_URL and test each for JSON usability
.venv/bin/python tools/test_model.py --list-free

# Only list :free model IDs (no API calls)
.venv/bin/python tools/test_model.py --list-free --no-probe

# Probe PDF/image/text input support and update models.json
.venv/bin/python tools/probe_models.py \
  --pdf data/raw/extractbench/docs/short/07021-2016-p0014.pdf \
  --models <model_1> <model_2> --write
```

---

## 2. Run Extraction (`evaluation.run_batch`)

```bash
# Smoke split (12 docs) — single-pass LLM
.venv/bin/python -m evaluation.run_batch --split smoke --name v2_smoke --mode llm --workers 4 --tag v2

# Dev / test_public split with K=3 samples + entropy UQ
.venv/bin/python -m evaluation.run_batch \
  --split dev --name probly_dev --mode llm \
  --samples 3 --temperature 0.7 --sampling mixed --uq-method k_entropy \
  --workers 4 --on-error abstain

# Run using frozen decision config
.venv/bin/python -m evaluation.run_batch \
  --split test_public --name final_pub --mode llm \
  --on-error abstain --decision submission/decision.json

# Offline preflight check (no API calls)
.venv/bin/python -m evaluation.preflight --input data/splits/smoke.jsonl --samples 1 --dry-run
```

---

## 3. Resume & Re-score an Incomplete Run

`evaluation.run_batch` always creates a new folder. To resume an existing run folder, call `4_extract.py` with the same `--run-dir` and `--resume`:

```bash
# 1. Resume only failed/unwritten docs in the same run folder
.venv/bin/python 4_extract.py \
  --data data/splits/smoke.jsonl \
  --run-dir results/runs/<RUN_DIR_NAME> \
  --run-name <RUN_NAME> \
  --mode llm --workers 4 --resume

# 2. Re-score the run folder and update results/runs/index.jsonl
.venv/bin/python -m evaluation.registry score <RUN_DIR_NAME>
```

---

## 4. Graphs, Tables & Analysis

```bash
# Generate comparison tables & plots from all registered runs (results/runs/index.jsonl)
.venv/bin/python tools/compare_results.py --threshold 0.99

# List all registered runs
.venv/bin/python -m evaluation.registry list

# Rebuild results/runs/index.jsonl from disk
.venv/bin/python -m evaluation.registry rebuild

# Per-field error analysis on a prediction file (no API calls)
.venv/bin/python tools/analyse_fields.py results/runs/<RUN_DIR_NAME>/preds.jsonl

# Regenerate EDA.md
.venv/bin/python tools/make_eda.py

# Check reply cache size / hits per model
.venv/bin/python tools/cache_stats.py
```

---

## 5. Rate-Limit Settings (`.env`)

```ini
LLM_MIN_INTERVAL_S=3    # Min seconds between outbound requests across all workers (3s = 20 RPM)
LLM_MAX_RETRIES=2       # Retries per request on 429/5xx/timeout
LLM_WAIT_BUDGET_S=300   # Total retry-sleep budget (s) for the whole run; 429 beyond this stops the run
LLM_TIMEOUT_S=120       # Per-request HTTP timeout (s)
```
---

## 6. Dashboard

```bash
.venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1
```

---