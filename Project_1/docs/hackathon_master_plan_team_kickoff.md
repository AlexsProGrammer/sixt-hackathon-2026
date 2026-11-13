# Project 1 Master Plan: Teach a Machine to Say "I Don't Know"

> **Corrections 13.11.2026:** This plan was checked against the code and data. Start with `00_start_here_review_and_fixes.md` (verified facts, bugs C1–C7, day plan). Where this file differs, that file is right.

> **Audience:** Human teammates & AI coding agents working inside `Project_1/`.  
> **Guiding Principle:** *"Just make it exist first, you can make it good later."* Keep the pipeline working end-to-end at every step, measure every change against `5_score.py`, and stay adaptable to whatever API models or hardware are announced at kick-off.

---

## 1. Mission & Core Business Constraint

SIXT currently relies on manual human entry to transcribe contracts, forms, and scans into internal systems. Automated extraction saves human review time, **but a single confidently wrong value booked into the system of record costs $100\times$ more than a human review**:

- **Human review cost (`review_cost`):** $1$ per field sent to a human (`value: null` or `confidence < threshold`).
- **Silent error cost (`error_cost`):** $100$ per field auto-booked (`value != null` and `confidence >= threshold`) that is wrong or hallucinated on an absent field.
- **Break-even precision:** A correct auto-booked field saves $1$. A wrong one costs $100$ instead of $1$, so it is $99$ worse. Break-even is $p = (E-1)/E = 99\%$ for $E = 100$ (not $100/101$). **Auto-booked predictions must be right more than $99\%$ of the time.** At $E = 20$ this is $95\%$, at $E = 500$ it is $99.8\%$.

### Hard Constraints & Final Deliverables (Deadline: Friday 13 Nov 2026, 16:45)
All final artifacts must be pushed to the public team GitHub repository under `Project_1/` (and `submission/`):
1. `Project_1/` source code with `Project_1/run_hidden.sh` updated to invoke your final extractor at your declared confidence threshold $\tau^*$.
2. `Project_1/SUBMISSION.md` (copied from `../SUBMISSION_TEMPLATE.md`) containing your approach, model comparison table, cost/latency per document, held-out metrics, and **your declared threshold $\tau^*$**.
3. `Project_1/EDA.md` (already generated from `data/unified/dev.jsonl`).
4. `submission/slides.pdf` (max 5 slides) **or** `submission/demo.mp4` (max 1 min, $< 50\text{ MB}$).
5. **Strict Disqualification Rules:** Never commit `.env` or API keys. Never commit `data/` or real SIXT/customer/personal data. Never tune hyperparameters or thresholds on `data/unified/test_public.jsonl`.

---

## 2. Environment Setup & Requirements

- **Python Version:** Python `3.12+` (`3.12.10` verified in `.venv`). Required because `probly` targets Python `3.12+` while `Project_1` requires `3.11+`.
- **Virtual Environment & Dependencies:**
  ```bash
  cd Project_1
  python3 -m venv .venv
  source .venv/bin/activate        # Windows (PowerShell/cmd): .venv\Scripts\activate
  pip install --upgrade pip
  pip install -r requirements.txt
  pip install probly
  ```
- **API Credentials (`.env`):** Copy `.env.example` to `.env` (git-ignored) and fill in the credentials provided at kick-off:
  ```env
  LLM_BASE_URL=<provided-openai-compatible-url>
  LLM_API_KEY=<provided-api-key>
  LLM_MODEL=<provided-model-name>
  ```
  *(Note: Keep track of any additional model names listed in the kick-off email so you can compare cheap vs. strong models or build a multi-model ensemble.)*
  **Important (bug C2):** nothing in the code loads `.env` yet. Export the three variables in your shell, or add a loader first. Otherwise `--mode auto` silently runs the offline rules. Never print the key.

---

## 3. Team Kickoff Agenda (09:30 Morning Sync — 15 Minutes)

Before writing code at 09:30, align on these 5 points as a 3-person team:

1. **Confirm Registration & Repo Access:** Verify that your public GitHub fork URL is registered in the Team + Topic Registration form (closes 09:30) and all 3 teammates have push access.
2. **Inspect Provided Resources:** Check the SIXT kick-off email for:
   - Which LLM endpoints/models are available (text-only vs. vision-capable, rate limits, token limits).
   - Whether any GPU compute is available or if all inference runs via the provided API + local laptops.
3. **Review `EDA.md` & Baseline Numbers Together (3 mins):** Share the key findings already documented in `Project_1/EDA.md` ($57.6\%$ null rate, `string` normalizer on ExtractBench, $109$ CUAD contracts $> 60\text{k}$ chars, $64$ PDFs without text) so everyone understands why naive prompting fails.
4. **Assign Clear Ownership (3-Person Split):**
   - **Person A — Extraction & Grounding Lead:** Fixes starter extractor issues (full-document chunking, batched schema prompts, vision/OCR handling for scans, normalizer-aware grounding checks, corrupted PDF detection).
   - **Person B — Uncertainty & `probly` Lead:** Implements multi-sample/multi-prompt/multi-model wrapper, `probly` uncertainty representations (`CategoricalDistribution` / `CredalSet`), post-hoc calibration on `dev_train`, and conformal threshold selection ($\tau^*$) on `dev_cal`.
   - **Person C — Pipeline, Caching, Evaluation & Story Lead:** Builds the disk LLM response cache (`cache/`), runs benchmark checkpoints on `test_public.jsonl`, tracks cost/latency per document, updates `run_hidden.sh`, and builds `SUBMISSION.md` + `submission/slides.pdf`.
5. **Agree on Git & Storage Discipline:**
   - Work on short-lived feature branches (`feat/extractor`, `feat/probly-uq`, `feat/eval-slides`) and merge into `main` frequently once `test_score.py` passes.
   - Keep `data/`, `cache/`, and raw `*.jsonl` prediction dumps out of Git (use Nextcloud/shared drive if sharing cached API responses across laptops).

---

## 4. Phased Execution Roadmap & Benchmark Checkpoints

Every major engineering milestone ends with a **Checkpoint** where you score against `test_public.jsonl` and save `results/<checkpoint>_score.json` for your final comparison table.

| Phase | Time Window | Objective | Deliverable / Checkpoint |
| :--- | :--- | :--- | :--- |
| **Phase 0: Prep** | Pre-Hack | Setup `.venv`, install `probly`, generate `EDA.md`, run 3 offline no-AI baselines. | `EDA.md` + `results/base_{never,common,offline}_score.json` |
| **Phase 1: API Smoke Test & Raw LLM Baseline** | 09:30 – 10:15 | Add API key (export it, see C2). Run unmodified `4_extract_example.py --mode llm` on a 10–30-doc dev slice, then `test_public.jsonl`. Score the slice against a **matching gold subset** (bug C3). | **CHECKPOINT 1:** `results/llm_starter_score.json` (uncalibrated single-pass baseline) |
| **Phase 2: Fix extractor bugs (C1–C7)** | 10:15 – 11:30 | **First C1 (Windows paths in data) and C2 (`.env`)**, they block everything. Then fix 60k char truncation, batch large schemas, fix `grounded()` normalizer mismatch, handle scanned PDFs/checkboxes, add parallel requests + response `cache/`. | **CHECKPOINT 2:** `results/llm_refactored_score.json` (proves extraction/grounding gains before `probly`) |
| **Phase 3: `probly` UQ, Calibration & Abstention** | 11:30 – 14:30 | Split `dev.jsonl` into `dev_train` (70%) and `dev_cal` (30%), **grouped by document id without the `-pNNNN` suffix** (not by row, otherwise pages of one filing leak across the split). Choose τ\* by the rule in `00_start_here_review_and_fixes.md` §5. Run $K$-sample / multi-prompt / multi-model extraction, compute `probly` uncertainty, calibrate on `dev_train`, select $\tau^*$ on `dev_cal`. | **CHECKPOINT 3:** `results/probly_calibrated_score.json` at $\tau^*$ (headline result) |
| **Phase 4: Error Analysis & Sensitivity** | 14:30 – 15:30 | Inspect remaining errors on `dev_cal`. Run `--error-cost 20` and `--error-cost 500` sensitivity checks + ablation table for `SUBMISSION.md`. | **CHECKPOINT 4:** Final ablation table & risk-coverage plot |
| **Phase 5: Freeze & Final Packaging** | 15:30 – 16:45 | Update `run_hidden.sh` with $\tau^*$, test `run_hidden.sh` on a mock gold-free input from a **Linux shell** (C1), finalize `SUBMISSION.md` and `submission/slides.pdf` ($\le 5$ slides), push to `main`. | Clean repo pushed before **16:45** |

---

## 5. Instructions & Guardrails for AI Coding Agents

If you are an LLM or AI coding assistant reading this repository to help write code:
1. **Stay Flexible:** Do not assume a specific LLM provider, context window, vision support, or GPU availability until `.env` and kick-off details are confirmed. Keep model endpoints, concurrency limits, sample counts ($K$), and threshold $\tau^*$ configurable via CLI flags / environment variables with sensible defaults.
2. **Prevent Data Leakage:** Never read `data/unified/test_public.jsonl` when designing prompts, selecting features, fitting calibration models, or choosing $\tau^*$. Use `data/unified/dev.jsonl` (split into `dev_train` and `dev_cal`) for all tuning and calibration.
3. **Preserve `run_hidden.sh` Compatibility:** The hidden evaluation harness runs `bash run_hidden.sh <input.jsonl> <output.jsonl>` from inside `Project_1/`. Input records in the hidden test **do not contain a `"gold"` key**—always iterate over `rec["schema"]["properties"]`, never `rec["gold"]`.
4. **Always Emit Valid Confidence Scores:** In `5_score.py`, a missing `"confidence"` defaults to `1.0` (auto-accepted!). Every non-null field prediction **must** explicitly include `"confidence": <float in [0.0, 1.0]>`.
5. **Respect `.gitignore`:** Never commit `.env`, `data/`, `cache/`, or large prediction `.jsonl` files. Keep small summary JSONs (`results/*_score.json`) and Markdown reports tracked.
6. **Paths in data are Windows paths:** every `pages` entry contains `\`. Resolve them through one helper that normalises the separator (bug C1). Do not use the raw string.
7. **Never print `.env` values** or the API key in logs, commits, or docs.