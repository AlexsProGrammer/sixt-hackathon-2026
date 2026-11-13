# Submission: Project 1, teach a machine to say "I don't know"

**Team name:** not provided in this workspace (fill in)

**Project:** Project 1: Teach a machine to say "I don't know" (structured extraction with abstention)

**Status in one paragraph.** The declared decision is **all-abstain** (threshold 1.0, `abstain_all = true`, see `submission/decision.json`). No value is auto-booked. The only independent development measurement with a frozen choice (method `k_agreement_conf`, threshold 0.99, K=3) was run on a small dev set: 7 documents, 130 audit fields. It produced 4 accepted fields, 1 of them wrong, and a negative net saving. After that audit we found a schema error (a table with wrong key names and currency text was accepted). Re-analysing the same stored samples with the corrected validation removes that wrong field (3 accepted, all correct), but this is post-hoc analysis on data already seen. The prompt correction has **not** been measured with the API. The decision stays all-abstain until a new, unused dev measurement supports a release.

## Problem and approach

SIXT enters contracts, forms and scans by hand. A wrong booked value costs 100 times more than a human review (review cost 1, error cost 100). Automation pays only if the accepted values are right more than 99% of the time. In general the break-even precision is (E-1)/E, that is 99.0% for E = 100, 95% for E = 20 and 99.8% for E = 500.

Pipeline (`4_extract.py` with the packages `pipeline/`, `uncertainty/`, `evaluation/`):

1. **Full text.** CUAD contracts and the PDF text layer are used whole, not truncated. A PDF without text (scan) or a broken PDF gets null/0 with the diagnosis `unreadable`, and no request is made.
2. **Jobs.** Chunks of 45,000 characters with 3,000 overlap. Fields in batches of at most 10. Every chunk gets every batch, for every sample.
3. **Prompt (version v3).** The complete field schema, including all referenced `$defs`, is sent as JSON. Numeric fields must be JSON numbers, keys must match the schema names exactly.
4. **Transport.** At most one retry, a shared wait budget of 60 s per run, a run stop on HTTP 429, and a SHA-256 reply cache. Strict parsing: invalid JSON is a visible error.
5. **Merge per sample** (contract version 2). Each field keeps its status (`present`, `absent`, `invalid`, `missing`, `error`, `unsupported`, `unreadable`) and its evidence (chunk offsets). A field is complete only if all its own jobs succeeded. A failed batch does not discard fields of other batches. A missing answer is never treated as an explicit null.
6. **Validation, in two separate steps.** (a) *Schema validity* (`uncertainty/schema_check.py`): jsonschema against the field schema and its `$defs`, strict types (a bool is not a number, a currency text is not a number), and a closed key set for objects. (b) *Textual evidence* (`uncertainty/grounding.py`): the normalised value must occur in the document as a contiguous, token-bounded span. A schema-invalid value is `invalid` and is never accepted, even if it occurs in the text.
7. **probly aggregation** (`uncertainty/uq_probly.py`). Only valid observations vote. All K observations of a field must be valid. The cluster frequencies form a probly categorical distribution, and its entropy in nats (normalised by log K) is a diagnostic.
8. **Decision rules** (`uncertainty/decision.py`), each with its own name:
   - `k1_grounded`: the model confidence of sample 0 (K=1 baseline).
   - `k_agreement_only`: the winner share only.
   - `k_agreement_conf`: min(winner share, lowest model confidence among the winner's observations). This is the earlier combination, renamed so the two definitions cannot be mixed up.
   - `k_entropy`: 1 − H/log K, with H from probly.
9. **Freeze and audit** (`evaluation/select_threshold.py`). Method and threshold are chosen on `dev_select` with the official scorer `5_score.py` (unchanged). They are frozen before the audit and applied once to `dev_audit` without re-optimisation. A release needs: complete runs on both sets, identical pipeline except for the method, an independent audit run, a frozen candidate, at least 30 accepted audit fields (see the note below) and a positive net saving on the audit. The Wilson 95% upper bound of the error rate is reported as a named diagnostic. It is not a release gate, and its assumption is stated in the report.

Assumptions and limits: the model confidence is uncalibrated. Grounding proves that a value occurs in the document, not that it belongs to the field.

## Error analysis (confirmed causes)

The audit showed a wrong accepted table field `labor_categories` in `extractbench:short/gsa_mas_it_labor_0020`. The stored prediction used the keys `labor_category` and `year_1` and the text `"$241.81"`, while the schema requires `labor_category_title`, `year_1_rate` and a number. Two causes were confirmed in the code:

1. **The prompt omitted `$defs`.** `build_prompt()` listed only the top-level fields by name, type and description. The definition `LaborRow` with the real key names was never sent to the model, so it invented keys. Fixed in prompt version v3, which sends the full schema including `$defs`.
2. **Nested values were checked only for text occurrence.** `_grounded_json()` checked that each leaf value occurs in the text, but not the keys, the types or the structure. A key name or a currency text could pass, as long as the number occurred somewhere in the text. Fixed by the schema validation in step 6 above.

Further defect found in review, also fixed: in the key check, a `null` alternative of `anyOf` accepted any object, because it has no declared properties. Now only the alternatives whose JSON type fits the value are considered.

**Extraction rule beyond JSON Schema (documented, deliberate).** JSON Schema allows undeclared keys unless `additionalProperties` is `false`. For extraction, undeclared keys are rejected when the schema declares properties, unless `patternProperties` matches or `additionalProperties` is a schema. Reason: the model must reproduce the declared key names of each table row. This rule is switched off by `strict_keys=False`. Keys allowed by the schema through `additionalProperties` (as a schema) or `patternProperties` are accepted and checked against their schema.

## Models and why

| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| `vertex_ai/gemini-3.8-flash` (the `LLM_MODEL` value of the organiser endpoint) | closed (API) | organiser's OpenAI-compatible endpoint | see Results | about 1,454 to 1,678 s for 7 documents with K=3 (60 and 57 requests); token cost not measured | yes, as the only model we ran. Not compared with other models. |

No other model was tried. The model choice is a default, not a result of comparison.

## Results

All numbers are fractions of the scorer, formatted here as percentages. Net saving is computed as (accepted − 100 × (wrong + hallucinated)) / N, where N is the number of fields in the set. This matches the official scorer for error cost 100. Earlier drafts contained a factor-100 error in the audit comparison (values such as −7.5 were read as −7.5 %, they are −750 %). The corrected values are below.

### A. Historical measurements (prompt v2, before the fixes)

| Set | Documents / fields | Method, threshold | Accepted | Correct | Wrong | Hallucinated | Precision | Coverage | Net saving |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| A: 6 dev_cal documents, K=1 | 6 / 199 | model, threshold 0.95 | 2 | 1 | 1 | 0 | 50.0% | 3.4% | −49.2% (error cost 100); −9.0% (20); −250.3% (500) |
| B: dev_select, K=3 | 7 / 164 | `k_agreement_conf`, 0.99 (frozen) | 14 | 14 | 0 | 0 | 100% | 18.9% | +8.5% |
| C: dev_audit, K=3 | 7 / 130 | `k_agreement_conf`, 0.99 (frozen) | 4 | 3 | 1 | 0 | 75.0% | 9.1% | −73.8% (error cost 20: −12.3%; 500: −381.5%) |

Set A is the earlier functional test: 4 of its 6 documents were abstained after a shared-quota HTTP 429. Set A is not a representative measurement.

Set C is the audit that did not support an active decision. The frozen choice was not changed after the audit.

### B. Dev_audit comparison at threshold 0.95 (historical, prompt v2)

| Method | Accepted | Correct | Wrong | Hallucinated | Precision | Net saving |
|---|---:|---:|---:|---:|---:|---:|
| k1_grounded | 31 | 17 | 14 | 0 | 54.8% | −1053.1% |
| k_agreement_only | 34 | 15 | 18 | 1 | 44.1% | −1435.4% |
| k_agreement_conf | 25 | 15 | 10 | 0 | 60.0% | −750.0% |
| k_entropy | 34 | 15 | 18 | 1 | 44.1% | −1435.4% |

No method has a positive net saving on the audit, not even at threshold 0.95.

### C. Post-hoc re-analysis with the corrected validation (no new API calls)

The stored samples of runs B and C were re-classified with the corrected schema validation (`results/post_schema_v3/`). **These are post-hoc results on data already known and used for the selection and audit. They do not measure prompt v3, because the stored answers were produced by prompt v2.**

| Set | Method, threshold | Accepted | Correct | Wrong | Hallucinated | Precision | Coverage | Net saving | Change against A/B |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| dev_select | `k_agreement_conf`, 0.99 | 14 | 14 | 0 | 0 | 100% | 18.9% | +8.5% | none |
| dev_audit | `k_agreement_conf`, 0.99 | 3 | 3 | 0 | 0 | 100% | 6.8% | +2.3% | `labor_categories` (wrong) is now `invalid` |
| dev_audit | `k_agreement_conf`, 0.95 | 22 | 15 | 7 | 0 | 68.2% | not recomputed | −521.5% | was 25 accepted, 10 wrong |

For the dev_audit set at 0.99 the net saving is 3/130 = +2.3 %. This is a sample of 3 correct accepted fields, which is far too few for any conclusion. The result shows only that the wrong table value is no longer accepted.

The other methods on the audit at 0.95 after re-analysis: `k1_grounded` 28 accepted, 11 wrong, net −824.6 %; `k_agreement_only` 31 accepted, 15 wrong, 1 hallucinated, net −1206.9 %; `k_entropy` 31 accepted, 15 wrong, 1 hallucinated, net −1206.9 %. No method is positive.

### D. Sample size, and the origin of the 30-field rule

The release rule "at least 30 accepted audit fields" is a **heuristic of this project** (the coding agent chose the value as a minimum for a visible audit signal). It is not derived from a power or error-bound calculation, and the team should confirm or replace it. The statistical diagnostic is separate. With 0 errors among n accepted fields, the 95% Wilson upper bound is about 3.8/n. To reach an upper bound of 1% with 0 errors, about 384 accepted fields are needed. The sets here have 3 to 14 accepted fields, so no error rate can be claimed from them.

### E. Baselines (team table, `docs/data_reference_baselines_scoring_guide.md`)

Measured earlier on `test_public`, which was not used for tuning: never-answer 0.0%; most-common-value −177.8% at threshold 0.95; offline keyword rules −931.7% at threshold 0.00. Those are the team's numbers and were not recomputed here.

### F. Run counts (real API, from the manifests)

| Run | Documents | Requests (actual, planned) | Retries | Cache hits | Failures | 429 stop | Run complete | Elapsed |
|---|---|---|---|---|---|---|---|---|
| A (K=1) | 6 | 10 (21 planned for K=1 on this set) | not recorded separately (manifest predates the field) | 0 | 4 abstained after 429 | yes | no | about 203 s |
| B (select, K=3) | 7 | 60 (60) | 0 | 0 | 0 | no | yes | 1,679 s |
| C (audit, K=3) | 7 | 57 (57) | 0 | 0 | 0 | no | yes | 1,455 s |

The planned counts exclude cache hits and retries, and the actual requests exclude retries that are not counted in the manifest. Retries were 0 in runs B and C.

## How to run

Python 3.12 is required (`probly==0.9.1`). From a fresh clone, in the folder `Project_1`:

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Data: place the provided dataset under `data/` (not committed). The extractor reads `data/raw/` for CUAD and PDFs.

Configuration (names only): `LLM_BASE_URL` (must start with `https://`), `LLM_API_KEY`, `LLM_MODEL`. They come from the environment or from a local `.env` file. Variables already set in the environment take precedence. Never commit `.env`.

Checks:

```
.venv\Scripts\python.exe test_score.py
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.venv\Scripts\python.exe -m evaluation.partitions --data data\unified\dev.jsonl --out-dir results\partitions_v1 --seed 20260113
.venv\Scripts\python.exe -m evaluation.preflight --input <input.jsonl> --samples 3 --dry-run
.venv\Scripts\python.exe submission\make_slides.py
```

Current decision (no API call):

```
bash run_hidden.sh <input.jsonl> <fresh-output.jsonl>
```

`run_hidden.sh` selects `.venv/bin/python` or `.venv/Scripts/python.exe`, then runs `4_extract.py --mode llm --on-error abstain --decision submission/decision.json`. It refuses an existing output path.

Active measurement with the same tools: `4_extract.py --data ... --out ... --mode llm --samples 3 --on-error abstain`, then `evaluation.ablation` on the stored samples, then `evaluation.select_threshold freeze` on `dev_select`, `audit` on `dev_audit` and `decide`.

## Demo

`submission/slides.pdf` (5 slides, generated by `submission/make_slides.py` from the stored score and decision files). The slides show the historical numbers, the error cause, the post-hoc re-analysis and the limits.

## External data flow

The text of each document part and the field prompts are sent to the organiser's LLM endpoint. The responses are cached locally in `cache/`, and the samples are kept in `results/*.samples.jsonl`. Both contain document text. They are git-ignored and stay on the team's machines.

## Limits

- No positive decision is supported. The only frozen choice was negative on the independent audit.
- The dev measurements are very small: 14 and 4 accepted fields. They are a limited development measurement, not a quality result.
- Dev_select and dev_audit were chosen with preference for short CUAD contracts (3 per set) and small ExtractBench documents (4 per set). Large contracts and long forms are not represented.
- Prompt v3 has not been measured with the API. The post-hoc analysis uses prompt v2 answers.
- Confidence is an uncalibrated score. Entropy and agreement are diagnostics, not calibrated probabilities.
- A document with one incomplete sample loses its failed fields (field-wise completeness now applies, but a failed sample still reduces K for that field).
- Grounding shows that text occurs in the document, not that the value belongs to the field. Example: `Liquidated Damages` was accepted with a grounded value that the gold leaves null.
- Strict span grounding costs recall. A shortened span is counted wrong by the scorer's token F1 (for example `March 27, 2020` against gold `March 27, 2020.`).
- Native boolean fields are never accepted. JSON objects are accepted only if the schema, the keys and every non-null leaf value are validated. A leaf number can match elsewhere in the text, so leaf evidence is weaker than span evidence.
- The 30-field release rule is a heuristic (see D).
- Calibration: **not implemented** (no trained predictor; `make_prediction(..., method="calibrated")` raises an error) and **no training data** (no K=3 predictions on `dev_fit`, and several hundred labelled candidates would be needed).

## Not tested

- Linux: no Linux Python environment was available. `run_hidden.sh` is verified on Windows with Git Bash only.
- Prompt v3 and the new schema validation on real API responses: not measured.
- `test_public`: not used, and the full dev evaluation was not run.

## Next steps

1. Run the new prompt v3 with K=3 on a set of dev documents that have not been used before, for example from `dev_fit` or the unused `dev_select` documents. Freeze the method and threshold before running (`evaluation.partitions` and `evaluation.preflight` give the splits and the planned request count).
2. Repeat the freeze, audit and decide steps on that new set. Use new output files for prompt v3. Only a positive, independent result with enough accepted fields may change the decision.
3. Confirm or replace the 30-field rule with the team.
4. Decide whether to add a calibrator on `dev_fit` once enough labelled candidates exist.
5. For SIXT, the conservative decision stays in place: the system abstains on everything it cannot verify, and the diagnostics show which fields a human should review first.
