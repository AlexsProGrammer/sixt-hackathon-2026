# Submission: Project 1, Teach a machine to say "I don't know"

## Authors
**Team name:** A-Team
**Project:** Project 1: Teach a machine to say "I don't know" (structured extraction with abstention)

## Problem and approach
A wrong booked value costs 100, a human review costs 1. So automation pays only above **99 % precision on the booked fields**. The task is not "extract everything" but "know which answers you can prove".

What we learned the hard way: model confidence and repeated sampling do **not** tell you that.

- At confidence 1.00 the model is still wrong in ~10 % of cases.
- Three samples of the same model agreed on the same wrong table and were booked at 0.99.

Our approach therefore moves trust from the model to **measured field cells** (full architecture in [`docs/architecture.md`](docs/architecture.md)):

1. **Route** each document (`pipeline/router.py`, `pipeline/text_quality.py`): `cuad` (contracts) / `pdf_text_good` / `pdf_text_damaged` / `pdf_no_text` / `pdf_corrupted`.
2. **Several views** (`pipeline/eb_pipeline.py`, `pipeline/cuad_pipeline.py`): different model families on different inputs (Gemini on the PDF, Claude on the PDF, Gemini on the text). On a damaged K-1 scan both vision views read *Pine Harbour Water Utilities LLC* correctly. The text layer gave *ine Harbour Water Utillties*.
3. **Evidence** (`uncertainty/evidence.py`, `uncertainty/schema_check.py`): schema check (types, keys) and type-aware grounding of the value in the document (`grounded_text`, `grounded_ocr`).
4. **probly** (`uncertainty/multiview.py`, `uncertainty/uq_probly.py`): the views' answers form a categorical distribution. Its entropy measures disagreement.
5. **Selector** (`evaluation/train_selector.py`, `uncertainty/decision.py`): book a field only if its cell (document family × field) had **zero errors over several independent document groups on `fit`**, and the evidence holds. Everything else goes to a human, pre-filled.

Assumptions:
- The hidden test comes from the same document families (organiser statement).
- Dev gold is used only to score and to label dev predictions for the selector. It never goes into a prompt.

## Models and why
Probed via `tools/probe_models.py` (`results/model_probe.json`, `models.json`):

| Model | Open / closed | Where | Input kinds & main finding | Probe / doc speed | Chosen? |
|---|---|---|---|---|---|
| `vertex_ai/gemini-3.7-flash` | closed | organiser endpoint | `text`, `pdf_file`, `pdf_image_url`, `png` all supported; 307 dev docs text: 88.6% precision; reads K-1 scan via PDF/PNG | ~2.5–3.7 s probe; ~30 s/doc (K=1, text) | **yes**, view A |
| `vertex_ai/claude-sonnet-5.5` | closed | organiser endpoint | `text`, `pdf_file`, `png` supported (`pdf_image_url` HTTP 400); correct on damaged K-1 scan via PDF/PNG | ~1.9 s probe (PDF) | **yes**, view B (independent family) |
| `gpt-5.6-sol` | closed | organiser endpoint | `text`, `png` supported (`pdf_file` & `pdf_image_url` HTTP 400); correct on K-1 scan via PNG | ~2.1 s probe (PNG) | PNG-only fallback |
| `vertex_ai/gemini-3.5-flash-lite` | closed | organiser endpoint | `text`, `pdf_file`, `pdf_image_url`, `png` all supported; correct on K-1 scan | ~1.1–1.4 s probe | optional fast view |
| `mistral-ocr-4` | closed | organiser endpoint (`POST /ocr`) | 404 on `/chat/completions`; works via `POST /ocr` for `grounded_ocr` | – | OCR grounding |
| `vertex_ai/gemini-3.8-flash` | closed | organiser endpoint | K=3 audit: 3 identical wrong samples booked | ~4 min/doc (K=3) | no: same-model sampling is not a correctness signal |

**Declared threshold:** 0.99. The current `submission/decision.json` is **all-abstain** (`abstain_all: true`) until the selector passes its frozen `audit` gate (see Results).

## Results
Net saving = (booked − 100 × errors) / all fields, from the unchanged `5_score.py` (run IDs from `results/runs/index.jsonl`). The human baseline (`never`) scores **0.0 %**.

| System | Run ID / Source | Data | Booked | Errors | Precision | Net saving (E=100) |
|---|---|---|---:|---:|---:|---:|
| `never` (all to human) | `20261112-213433-base_never-068683` | test_public (176 docs) | 0 | 0 | – | **0.0 %** |
| most common value | `20261112-213505-base_common-3b0b8d` | test_public (176 docs) | 319 | 127 | 60.2 % | −177.8 % |
| LLM, model confidence ≥ 0.99 | `20261113-143133-llm_dev-76e2d4` (legacy) | dev (307 docs, 12,562 fields) | 2,970 | 339 | 88.6 % | −246.2 % |
| probly K-sample pipeline, 0.99 | `20261113-153153-probly_dev-c4fc6c` (legacy) | dev (78 docs, 4,410 fields) | 132 | 4 | 97.0 % | −6.1 % |
| probly5 K-sample pipeline, 0.99 | `20261113-205136-probly5_dev-7c5d2d` (legacy) | dev (100 docs, 5,262 fields) | 230 | 7 | 97.0 % | −8.9 % |
| **Field-cell selector** (leave-one-group-out simulation) | `tools/analyse_fields.py results/llm_dev.jsonl` | dev (307 docs, 12,562 fields) | **378** | **0** | **100 %** | **+3.01 %** |

Note: earlier snapshots scored `llm_dev` and `probly_dev` against all 22,115 dev fields (−30.9 % and −1.2 %, shown on the slides); `results/runs/index.jsonl` scores each run against its own document subset. At E=20 / E=500, `base_common` scores −31.9 % / −907.5 %.

What this shows:
- Confidence-based and same-model-agreement systems stay below the human baseline at every threshold we tried.
- The field-cell selector is the first rule that beats it, even with the weakest pipeline (text only, no vision).

Honest limits:
- The +3.01 % is a simulation on stored legacy dev answers (`llm_dev.jsonl`). The new reproducible pipeline (`pipeline/`, `evaluation/run_batch.py`), router (`pipeline/router.py`), vision/multi-view (`pipeline/eb_pipeline.py`), CUAD long-context (`pipeline/cuad_pipeline.py`), selector (`evaluation/train_selector.py`), and dashboard (`dashboard/app.py`) are implemented and unit-tested, but the full frozen `fit` → `select` → `audit` run has not yet completed; `submission/decision.json` therefore stays `abstain_all: true`.
- 0 errors in 378 bookings gives a Wilson-95 upper error bound of ~1 %, right at break-even. More bookings (from vision and contracts) are needed for a solid margin.
- Most of the bookings come from a few form families (e.g. RRC H-5 well tests). Contracts (70.6 % of dev fields) remain mostly unbookable (see `results/cuad_analysis.json`: 405 missing passages, 243 subset matches).

## How to run
Python 3.12, from `Project_1/`:
```bash
python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
bash 1_download.sh --accept-licenses && .venv/bin/python 2_prepare.py
bash run_hidden.sh <input.jsonl> <output.jsonl>        # submitted configuration
```
Environment variables (only for active LLM runs): `LLM_BASE_URL`, `LLM_API_KEY`, optional `LLM_MODEL`, `LLM_MODEL_A`, `LLM_MODEL_B`, `LLM_MODEL_OCR`.

Reproduce the analysis, batch runs, and dashboard:
```bash
.venv/bin/python 5_score.py --gold data/unified/dev.jsonl --pred results/llm_dev.jsonl --threshold 0.99
.venv/bin/python tools/analyse_fields.py results/llm_dev.jsonl      # per-field table + selector simulation
.venv/bin/python -m evaluation.run_batch --help                    # reproducible run registry + splits
.venv/bin/python -m pip install -r requirements-dashboard.txt && .venv/bin/streamlit run dashboard/app.py
.venv/bin/python submission/make_slides.py                         # slides.pdf
```
More commands: [`README.md`](README.md) and [`docs/architecture.md`](docs/architecture.md).

## Demo
`submission/slides.pdf` (5 slides: problem, insight, architecture, first proof, vision/rollout).

## Next steps
1. Run the full frozen `fit` → `select` → `audit` evaluation via `evaluation/run_batch.py` across the implemented router, vision/multi-view, and CUAD pipelines.
2. Train `submission/selector.json` (`evaluation/train_selector.py`) and flip `abstain_all` to `false` in `submission/decision.json` once the frozen `audit` split is positive at E=100.

**How SIXT could use it:** start in *suggest mode*. Every field is pre-filled with its evidence and a human confirms. Each confirmation becomes a label. A field cell is switched to automatic booking only after it has proven itself. Trust grows per field, measured and reversible.
