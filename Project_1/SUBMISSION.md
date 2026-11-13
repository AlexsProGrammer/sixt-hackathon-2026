# Submission: Project 1, Teach a machine to say "I don't know"

## Authors
**Team name:** A-Team
**Project:** Project 1: Teach a machine to say "I don't know" (structured extraction with abstention)

## Problem and approach
A wrong booked value costs 100, a human review costs 1. So automation pays only above **99 % precision on the booked fields**. The task is not "extract everything" but "know which answers you can prove".

What we learned the hard way: model confidence and repeated sampling do **not** tell you that.

- At confidence 1.00 the model is still wrong in ~10 % of cases.
- Three samples of the same model agreed on the same wrong table and were booked at 0.99.

Our approach therefore moves trust from the model to **measured field cells**:

1. **Route** each document: contract / form with a good text layer / scan or damaged text layer.
2. **Several views**: different model families on different inputs (Gemini on the PDF, Claude on the PDF, Gemini on the text). On a damaged K-1 scan both vision views read *Pine Harbour Water Utilities LLC* correctly. The text layer gave *ine Harbour Water Utillties*.
3. **Evidence**: schema check (types, keys) and grounding of the value in the document.
4. **probly**: the views' answers form a categorical distribution. Its entropy measures disagreement.
5. **Selector**: book a field only if its cell (document family × field) had **zero errors over several independent document groups on dev**, and the evidence holds. Everything else goes to a human, pre-filled.

Assumptions:
- The hidden test comes from the same document families (organiser statement).
- Dev gold is used only to score and to label dev predictions for the selector. It never goes into a prompt.

## Models and why
| Model | Open / closed | Where | Main finding | Cost / time | Chosen? |
|---|---|---|---|---|---|
| `vertex_ai/gemini-3.7-flash` | closed | organiser endpoint | text pipeline on 307 dev docs: 81 % raw precision; reads native PDF (`image_url` and `file`) | ~30 s/doc (K=1, text) | **yes**, view A |
| `vertex_ai/claude-sonnet-5.5` | closed | organiser endpoint | reads native PDF via `file`; correct on the damaged K-1 scan | not measured | **yes**, view B (independent family) |
| `gpt-5.6-sol` | closed | organiser endpoint | rejected PDF input (HTTP 400); page images untested | – | no (for now) |
| `vertex_ai/gemini-3.8-flash` | closed | organiser endpoint | K=3 audit: 3 identical wrong samples booked | ~4 min/doc (K=3) | no: same-model sampling is not a correctness signal |

**Declared threshold:** 0.99. The current `submission/decision.json` is **all-abstain** until the selector passes its audit (see Results).

## Results
Net saving = (booked − 100 × errors) / all fields, from the unchanged `5_score.py`. The human baseline (`never`) scores **0.0 %**.

| System | Data | Booked | Errors | Precision | Net saving |
|---|---|---:|---:|---:|---:|
| `never` (all to human) | test_public | 0 | 0 | – | **0.0 %** |
| most common value | test_public | 319 | 127 | 60.2 % | −177.8 % |
| LLM, model confidence ≥ 0.99 | dev, 307 docs | 976 | 78 | 92.0 % | −30.9 % |
| probly K-sample pipeline, 0.99 | dev, 78 docs | 132 | 4 | 97.0 % | −1.2 % |
| **Field-cell selector** (stored answers, leave-one-group-out) | dev, 307 docs | **378** | **0** | **100 %** | **+3.0 %** |

What this shows:
- Confidence-based and same-model-agreement systems stay below the human baseline at every threshold we tried.
- The field-cell selector is the first rule that beats it, with the weakest pipeline (text only, no vision).

Honest limits:
- The +3.0 % is a simulation on stored dev answers. It still needs a reproducible run plus a frozen audit split (milestone M1).
- 0 errors in 378 bookings gives a 95 % upper error bound of ~1 %, right at break-even. More bookings (from vision and contracts) are needed for a solid margin.
- Most of the bookings come from a few form families (e.g. RRC H-5 well tests). Contracts (70 % of the fields) are not yet bookable.
- Not yet built: the vision, multi-view and contract pipelines. They are planned and tested only with a probe.

## How to run
Python 3.12, from `Project_1/`:
```bash
python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
bash 1_download.sh --accept-licenses && .venv/bin/python 2_prepare.py
bash run_hidden.sh <input.jsonl> <output.jsonl>        # submitted configuration
```
Environment variables (only for active LLM runs): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

Reproduce the analysis:
```bash
.venv/bin/python 5_score.py --gold data/unified/dev.jsonl --pred results/llm_dev.jsonl --threshold 0.99
.venv/bin/python analyse_fields.py results/llm_dev.jsonl      # per-field table + selector simulation
.venv/bin/python submission/make_slides.py                    # slides.pdf
```
More commands: [`README.md`](README.md).

## Demo
`submission/slides.pdf` (5 slides: problem, idea, pipelines, evidence, rollout).

## Next steps
1. **M1**: a reproducible full dev run, then train the selector on `fit`, choose on `select`, audit once on `audit`. Switch from all-abstain only if the audit is positive.
2. **M2**: router + text-quality gate, vision and 2-model views for forms (more bookable cells, including checkboxes).
3. **M3**: long-context contract pipeline; book only clause types with a single short passage.
4. **M4**: review dashboard: PDF next to value, gold and confidence, with accept/decline. Human decisions become new labels.

**How SIXT could use it:** start in *suggest mode*. Every field is pre-filled with its evidence and a human confirms. Each confirmation becomes a label. A field cell is switched to automatic booking only after it has proven itself. Trust grows per field, measured and reversible.
