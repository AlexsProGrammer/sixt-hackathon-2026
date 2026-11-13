# Submission: Project 1, teach a machine to say "I don't know"

**Team name:** not provided in this workspace (fill in)

**Project:** Project 1: Teach a machine to say "I don't know" (structured extraction with abstention)

**Status in one line:** The pipeline is complete and tested with mocks and synthetic data. The only real API measurement is a 6-document functional test. It produced no positive saving, so the declared decision is **all-abstain** (threshold 1.0). No system is auto-booking values.

## Problem and approach

SIXT enters contracts, forms and scans by hand. A wrong booked value costs 100 times more than a human review (review cost 1, error cost 100). Automation pays only above a **99% precision** break-even at error cost 100 (general break-even (E-1)/E).

Approach (`4_extract.py`, packages `pipeline/`, `uncertainty/`, `evaluation/`):

1. **Full text, never truncated.** CUAD contracts and PDF text layers are used whole. A PDF without a text layer (scan) or a broken PDF gets null/0 and the diagnosis `unreadable`, with no request and no upload.
2. **Jobs.** Chunks of 45,000 characters with 3,000 overlap. Fields in stable batches of at most 10. Every chunk gets every batch, for every sample.
3. **Transport.** One retry at most. A shared wait budget of 60 s per run. A 429 that cannot be retried stops all further requests of the run. A SHA-256 reply cache. Strict parsing: invalid JSON is a visible error.
4. **Merge per sample** (`pipeline/merge.py`). Conflicting scalar values across chunks give null. A null in one chunk never discards a value found in another. Span pieces are deduplicated in source order and joined with ` | `.
5. **Policy per sample** (`uncertainty/policy.py`, `grounding.py`). A value counts only if its normalised form occurs in the full text as a contiguous, token-bounded span. Commas, points and currency are kept, so `1234.50` does not match `1,234.50`. Confidence must be a finite number in [0,1]. Bool, NaN and infinity are rejected. Invalid or ungrounded values become null/0.
6. **probly aggregation** (`uncertainty/uq_probly.py`). The cluster frequencies over the K samples form a `create_categorical_distribution` (probly 0.9.1). Entropy in nats comes from `probly.quantification.entropy`. Tie or null winner gives null/0. Otherwise the score is min(winner share, lowest valid model confidence among the winner's samples). Agreement never raises confidence. K=1 returns exactly the policy output.
7. **Decision** (`evaluation/`). The threshold is chosen on `dev_cal` with the official scorer `5_score.py`, unchanged. If no positive saving exists, the decision is all-abstain, and predictions are set to null/0 before counting.

Assumptions and limits: model confidence is uncalibrated. Grounding proves that a value occurs in the document, not that it belongs to the field.

## Models and why

| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| `vertex_ai/gemini-3.8-flash` (the `LLM_MODEL` value of the organiser endpoint) | closed (API) | organiser's OpenAI-compatible endpoint | precision 50% at threshold 0.95 on 2 accepted fields (6-document subset); coverage 3.4% | about 203 s for 10 requests including waits and a 429 stop; token cost not measured | yes, as the only model we ran. Not compared with other models. |

No other model was tried. A comparison on the same held-out data was not possible within the API quota. The chosen model is therefore a default, not a result of comparison.

Project settings: **declared threshold tau = 1.0 with `abstain_all = true`** (`submission/decision.json`). Pipeline settings in the decision file are `null`, because no positive decision was made. Settings used in the measured run: K=1, chunk 45,000, overlap 3,000, batch 10, one worker.

## Results

All numbers below come from `results/final_dev_score_*.json`, produced by the official `5_score.py` without modification.

**Dev subset used for the measurement:** 6 documents from `dev_cal` (3 CUAD single-chunk contracts, 2 ExtractBench text PDFs, 1 scan), 199 fields. Documents were chosen deterministically from `results/split/dev_cal_gold.jsonl`.

| Variant (same 6 documents) | Error cost 20 | Error cost 100 | Error cost 500 |
| --- | ---: | ---: | ---: |
| Model, K=1, threshold 0.95 | -9.0% | -49.2% | -250.3% |
| All-abstain, threshold 1.0 (declared) | 0.0% | 0.0% | 0.0% |

Model at threshold 0.95: precision 50.0% (2 accepted, 1 wrong), coverage 3.4%, 0 hallucinations.

**What happened in the run (run_id `07f36e261f39`):**
- One document completed fully. The two accepted fields were `Document Name` (correct) and `Agreement Date` (wrong: the model gave `March 27, 2020`, the gold is `March 27, 2020.`; the official scorer's token F1 is 0.67 < 0.8). This is a scorer sensitivity, not a grounding failure.
- Four documents were abstained after the shared API quota returned HTTP 429 (retry, then run stop). They are **not** measured predictions. The manifest of this run predates the separate counter `n_abstained_after_errors` (added afterwards), so the run's manifest shows `n_failed: 0`. The per-document diagnostics show `rate_limited:429, stopped`.
- One scan was abstained by the unreadable-document rule without any request.

**Baselines** (from the team table in `docs/data_reference_baselines_scoring_guide.md`, measured earlier on `test_public`, not used for tuning): never-answer 0.0% net saving; most-common-value -177.8% at threshold 0.95; offline keyword rules -931.7% at threshold 0.00.

**Not measured:** K=3 on real requests (quota), a K=1 versus K=3 comparison, a threshold on a statistically usable calibration set, and `test_public`. A 6-document set can show no coverage or precision claim. The "99% precision" bound needs at least 300 accepted fields with 0 errors on `dev_cal` for an upper bound of 1% (rule of three). We have 2 accepted fields.

**Tests (local, no API):**
- `test_score.py`: OK (official scorer tests, unchanged).
- Unit and integration tests `tests/`: 92 tests, all OK. Breakdown: policy and grounding 29, extraction (chunks, prompts, paths, transport, retry and 429 stop, cache, parsing, merge) 35, CLI integration with a local mock endpoint 13, evaluation 15.
- Integration covers K=1 with evidence beyond character 60,000, K=3 temperatures, broken JSON in fail and abstain modes, 429 stop, missing configuration, all-abstain without credentials, resume rules, cache hits, decision-file checks.

## How to run

Python 3.12 is required (`probly==0.9.1`). From a fresh clone, from the folder `Project_1`:

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Data: place the provided dataset under `data/` (not committed). The extractor reads `data/raw/` for CUAD and PDFs.

Configuration (names only): `LLM_BASE_URL` (must start with `https://`), `LLM_API_KEY`, `LLM_MODEL`. They come from the environment or from a local `.env` file. Variables already set in the environment take precedence. Do not commit `.env`.

Reproduce the checks:

```
.venv\Scripts\python.exe test_score.py
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.venv\Scripts\python.exe -m evaluation.prepare --data data\unified\dev.jsonl --out-dir results\split --seed 42
.venv\Scripts\python.exe submission\make_slides.py
```

Final command (gold-free input, fresh output path, frozen decision, no API call in the current decision):

```
bash run_hidden.sh <input.jsonl> <fresh-output.jsonl>
```

`run_hidden.sh` selects `.venv/bin/python` or `.venv/Scripts/python.exe`, then runs `4_extract.py --mode llm --on-error abstain --decision submission/decision.json`. It refuses an existing output path. The output is validated with:

```
.venv\Scripts\python.exe -m evaluation.validate --input <input.jsonl> --pred <fresh-output.jsonl>
```

A K=3 measurement with the same tools: `4_extract.py --data ... --out ... --mode llm --samples 3 --on-error abstain`, then `evaluation.select_threshold` with the run manifest, then `5_score.py --threshold ... --error-cost 20|100|500`.

## Demo

`submission/slides.pdf` (5 slides, generated by `submission/make_slides.py` from the measured score files).

## External data flow

The text of each document part and the field prompts are sent to the organiser's LLM endpoint. The endpoint's responses are cached locally in `cache/` (git-ignored). Local artefacts (`results/`, `cache/`, `data/`) stay on the team's machines and are git-ignored.

## Limits (summary)

- Only one completed document with real model output. No positive saving was measured, so the declared decision abstains on everything.
- Confidence is an uncalibrated score. Entropy and agreement are diagnostics, not calibrated probabilities or an epistemic decomposition.
- A document with one incomplete sample loses all its fields (document-level abstention).
- Strict span grounding costs recall. Models often shorten spans with `...`, and those are dropped.
- Grounding shows that text occurs in the document, not that the value belongs to the field. Example: `Exclusivity` accepted with a value found elsewhere in the contract while the gold is null.
- Bool, checkbox, JSON and object fields are never accepted (they are not checkable yet).
- The official scorer's token F1 penalises a trailing period in short spans.
- `run_hidden.sh` uses the interpreter from `.venv` if it exists (Linux or Windows layout). Only without `.venv` does it fall back to `python3`, which then needs `probly` installed.

## Not tested

- Linux: no Linux Python environment was available. `run_hidden.sh` and the path handling are verified on Windows (with Git Bash and a Windows venv) only.
- Real K=3 API runs: blocked by the shared team quota (HTTP 429). Mock-verified only.
- The full dev and `test_public` evaluation: not run.

## Next steps

With more quota: run K=1 and K=3 on a larger `dev_cal` subset (around 300 accepted fields), freeze prompt and grounding, then choose the threshold and report the upper bound. Then score `test_public` once. Add a calibrator on `dev_train` only. Consider normalising typographic quotes and dashes in grounding, after agreement with the team. For SIXT, the conservative decision (abstain everything not verifiable) is already usable: it removes manual errors at zero booking risk, and the diagnostics show which fields a human should review first.
