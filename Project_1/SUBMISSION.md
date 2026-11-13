# Submission: Project 1, teach a machine to say "I don't know"

## Authors

**Team name:** not provided in this workspace (fill in)

**Project:** Project 1: Teach a machine to say "I don't know" (structured extraction with abstention)

## Summary: what we submit, and the honest result

**Declared decision: all-abstain** (`submission/decision.json`: `abstain_all = true`, declared threshold 1.0). The submitted system books no value automatically. Every field goes to a human. Its net saving is exactly **0.0%**, the same as the `never` baseline.

We built a full extraction pipeline with probly-based uncertainty. We do not switch it on, for three measured reasons:

1. **Coverage is low.** At our conservative threshold 0.99 the pipeline accepts 1.4% of the fields that have a value on dev, and 7.2% on test_public. For CUAD contracts it accepts nothing.
2. **Precision is high but not high enough.** The best active variant reaches 97.0% precision. The cost rule (review 1, error 100) needs more than 99%.
3. **So every active variant is below the human-review baseline.** The best one is at −1.2% net saving (dev) and −15.7% (test_public). `never` is at 0.0%. One wrong booked value removes the gain of 100 correct ones.

Under the 1:100 cost rule, all-abstain is therefore the rational submission. An active submission would lose money. The pipeline, the measurements and the five last fixes show how far we are from break-even and what is needed to pass it (see "Improvement levers").

## Problem and approach

SIXT enters contracts, forms and scans by hand. A human review costs 1 per field. A wrong booked value costs 100. Automation pays only if accepted values are right more than 99% of the time. In general the break-even precision is (E−1)/E: 95.0% for E = 20, 99.0% for E = 100, 99.8% for E = 500.

Net saving = (accepted − E × (wrong + hallucinated)) / all fields. This is the formula of the official scorer `5_score.py`, which we use unchanged.

Pipeline (`4_extract.py` with the packages `pipeline/`, `uncertainty/`, `evaluation/`):

1. **Full text.** CUAD contracts and the PDF text layer are used whole, not truncated. A PDF without text (scan) or a broken PDF gets null/0 with the diagnosis `unreadable`. No request is made for it.
2. **Jobs.** Chunks of 45,000 characters with 3,000 overlap. Fields in batches of at most 10. Every chunk gets every batch, for every sample.
3. **Prompt (version v4).** The complete field schema including all `$defs` is sent as JSON. Numbers must be JSON numbers, keys must match the schema exactly, booleans are JSON `true`/`false`, and several span passages are joined with ` | `.
4. **Transport.** At most one retry, a shared wait budget of 60 s per run, a run stop on HTTP 429, and a SHA-256 reply cache keyed by the prompt version. Parsing is strict about structure; line breaks and tabs inside string values are accepted.
5. **Merge per sample.** Each field keeps a status (`present`, `absent`, `invalid`, `missing`, `error`, `unsupported`, `unreadable`). A failed batch does not discard the fields of other batches. A missing answer is never treated as an explicit null.
6. **Validation in two separate steps.** (a) Schema validity (`uncertainty/schema_check.py`): types, closed key sets, `$defs`. (b) Text grounding (`uncertainty/grounding.py`): the normalised value must occur in the document as a contiguous, token-bounded span. A value that fails either check is never accepted.
7. **probly aggregation** (`uncertainty/uq_probly.py`). The K valid answers of a field are clustered by exact normalised value. The cluster frequencies form a probly categorical distribution. Its entropy (nats, normalised by log K) is a diagnostic and the score of the method `k_entropy`. Per field the diagnostics also hold the `status_counts`.
8. **Decision rules** (`uncertainty/decision.py`): `k1_grounded` (model confidence, K=1), `k_agreement_only` (winner share), `k_agreement_conf` (min of winner share and lowest model confidence), `k_entropy` (1 − H/log K, with H from probly). A value with score 0 becomes null.
9. **Freeze and audit** (`evaluation/select_threshold.py`). Method and threshold are chosen on `dev_select`, frozen, and applied once to `dev_audit`. Only a positive audit may switch the system on. The audit was negative, so the decision is all-abstain.

Assumptions and limits: the model confidence is uncalibrated. Grounding proves that a value occurs in the document, not that it belongs to the field.

## Models and why

| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| `vertex_ai/gemini-3.8-flash` | closed (API) | organiser's OpenAI-compatible endpoint | dev_audit, K=3, threshold 0.99: precision 75.0%, coverage 9.1%, net −73.8% | about 210 to 240 s per document with K=3 (57 to 60 requests for 7 documents); token cost not measured | used for the K=3 select and audit runs |
| `vertex_ai/gemini-3.7-flash` | closed (API) | same endpoint | 10 dev documents, K=1, threshold 0.99: 14 accepted, 0 wrong | about 30 s per document with K=1 (48 requests for 10 documents) | used for the K=1 run with a stored manifest |
| no model (all-abstain) | n/a | local, no API call | net 0.0%, coverage 0%, hallucination rate 0% | 0 requests, under 1 s per document | **yes, this is the submitted configuration** |

The two Gemini versions were the `LLM_MODEL` values of the organiser endpoint at the time of each run. They were **not compared on the same documents**, so we make no claim about which one is better. The model choice is a default, not the result of a comparison.

**Declared confidence threshold: 1.0 with `abstain_all = true`** (no value is accepted). The threshold we would use for an active system, and the one used in the analysis below, is **0.99**.

## Results

All percentages are net saving as a share of all fields in the scored split, from the official scorer. Stored score files are in `results/`.

### A. Baselines (test_public, 176 documents, 6,962 fields, threshold 0.95)

| Baseline | Accepted | Correct | Wrong | Hallucinated | Precision | Coverage | Net saving (E=100) | E=20 | E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `never` (human reviews everything) | 0 | 0 | 0 | 0 | n/a | 0.0% | **0.0%** | 0.0% | 0.0% |
| `common` (most common value) | 319 | 192 | 125 | 2 | 60.2% | 11.1% | **−177.8%** | −31.9% | −907.5% |
| `offline` (keyword rules) | 0 at 0.95 (732 at threshold 0) | 76 at threshold 0 | 550 | 106 | 10.4% at threshold 0 | 0.0% | 0.0% at 0.95 (−931.7% at threshold 0) | | |

`never` at 0.0% is the bar. A system is useful only if it is above 0.0%. `common` shows how expensive a careless system is.

### B. Method comparison on the large runs

These runs cover a part of each split (document counts below). The scorer was run against the whole split, and a document without a prediction counts as abstained. The percentages are therefore diluted: on the processed documents alone, the losses per field are larger. Counts (accepted, wrong) are not affected. The manifests of these runs are not in the repository, except for the 10-document run (K=1, `k1_grounded`, prompt v2).

**dev (540 documents, 22,115 fields)**

| Run | Documents processed | Threshold | Accepted | Correct | Wrong | Halluc. | Precision | Coverage | Net (E=100) | E=20 | E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `never` | all | any | 0 | 0 | 0 | 0 | n/a | 0.0% | **0.0%** | 0.0% | 0.0% |
| LLM, model confidence only | 307 | 0.95 | 1,220 | 1,055 | 159 | 6 | 86.5% | 13.0% | −69.1% | −9.4% | −367.5% |
| LLM, model confidence only | 307 | 0.99 | 976 | 898 | 78 | 0 | 92.0% | 10.4% | −30.9% | −2.6% | −171.9% |
| probly pipeline (grounding + policy) | 78 | 0.95 | 230 | 181 | 46 | 3 | 78.7% | 2.4% | −21.1% | −3.4% | −109.7% |
| probly pipeline | 78 | 0.98 | 143 | 138 | 4 | 1 | 96.5% | 1.5% | −1.6% | +0.2% | −10.7% |
| **probly pipeline** | 78 | **0.99** | 132 | 128 | 3 | 1 | **97.0%** | **1.4%** | **−1.2%** | +0.2% | −8.4% |
| probly pipeline | 78 | 1.00 | 81 | 78 | 3 | 0 | 96.3% | 0.9% | −1.0% | +0.1% | −6.4% |
| probly pipeline, 10 documents | 10 | 0.99 | 14 | 14 | 0 | 0 | 100% | 0.15% | +0.06% | +0.06% | +0.06% |

**test_public (176 documents, 6,962 fields). Scored for reporting only. No prompt, method or threshold was derived from it.**

| Run | Documents processed | Threshold | Accepted | Correct | Wrong | Halluc. | Precision | Coverage | Net (E=100) | E=20 | E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `never` | all | any | 0 | 0 | 0 | 0 | n/a | 0.0% | **0.0%** | 0.0% | 0.0% |
| `common` | all | 0.95 | 319 | 192 | 125 | 2 | 60.2% | 11.1% | −177.8% | −31.9% | −907.5% |
| LLM, model confidence only | 75 | 0.95 | 1,195 | 927 | 243 | 25 | 77.6% | 40.8% | −367.8% | −59.8% | −1,907.6% |
| LLM, model confidence only | 75 | 0.99 | 892 | 793 | 94 | 5 | 88.9% | 31.0% | −129.4% | −15.6% | −698.2% |
| probly pipeline | 40 | 0.95 | 237 | 213 | 24 | 0 | 89.9% | 8.3% | −31.1% | −3.5% | −169.0% |
| **probly pipeline** | 40 | **0.99** | 205 | 192 | 13 | 0 | **93.7%** | **7.2%** | **−15.7%** | −0.8% | −90.4% |
| probly pipeline | 40 | 1.00 | 167 | 158 | 9 | 0 | 94.6% | 5.8% | −10.5% | −0.2% | −62.2% |

What these runs show:

- **The probly pipeline removes most of the loss.** On dev at 0.99 the loss goes from −30.9% to −1.2%. On test_public from −129.4% to −15.7%. Hallucinated values fall to 0 or 1.
- **It is still below `never`.** No row with more than 14 accepted fields is positive at E = 100. The 10-document run is positive, but 14 accepted fields prove nothing (see D).
- **The price is coverage.** The pipeline accepts 132 fields where the plain LLM run accepts 976.
- **CUAD coverage is zero.** In every probly run the number of accepted CUAD fields is 0. All accepted fields come from ExtractBench. In the plain LLM run on dev, CUAD precision is 39.6% (101 accepted, 40 correct), so accepting CUAD spans without a better check would be far worse.
- **The model confidence is not calibrated.** At confidence 1.00 the plain LLM run is still wrong in 63 of 660 fields (9.5%).

### C. Select and audit with probly (K=3, prompt v2, `gemini-3.8-flash`)

Method and threshold were chosen on `dev_select`, frozen, then applied once to `dev_audit`.

| Set | Documents / fields | Method, threshold | Accepted | Correct | Wrong | Halluc. | Precision | Coverage | Net (E=100) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| dev_select | 7 / 164 | `k_agreement_conf`, 0.99 (chosen here) | 14 | 14 | 0 | 0 | 100% | 18.9% | +8.5% |
| dev_audit | 7 / 130 | `k_agreement_conf`, 0.99 (frozen) | 4 | 3 | 1 | 0 | 75.0% | 9.1% | **−73.8%** (E=20: −12.3%; E=500: −381.5%) |

The audit did not confirm the selection result. One wrong field among four turned +8.5% into −73.8%. The frozen choice was not changed afterwards.

All four methods on dev_audit at threshold 0.95 (same stored samples):

| Method | Accepted | Correct | Wrong | Halluc. | Precision | Net (E=100) |
|---|---:|---:|---:|---:|---:|---:|
| `k1_grounded` | 31 | 17 | 14 | 0 | 54.8% | −1,053.1% |
| `k_agreement_only` | 34 | 15 | 18 | 1 | 44.1% | −1,435.4% |
| `k_agreement_conf` | 25 | 15 | 10 | 0 | 60.0% | −750.0% |
| `k_entropy` (probly entropy) | 34 | 15 | 18 | 1 | 44.1% | −1,435.4% |

**probly entropy alone does not solve the problem.** `k_entropy` and `k_agreement_only` ignore the model confidence, so three identical answers score 1.0 even when all three are wrong. The model repeats the same mistake consistently. Agreement measures consistency, not correctness. The combination with the model confidence (`k_agreement_conf`) is the best of the four, and it is still negative.

**Post-hoc re-analysis** (`results/post_schema_v3/`, same stored samples, no new API call): with the corrected schema validation the wrong audit field becomes `invalid`. dev_audit at 0.99 is then 3 accepted, 3 correct, net +2.3%. At 0.95 `k_agreement_conf` is 22 accepted, 7 wrong, net −521.5%. This is analysis on data we had already seen. It is not an independent result, and 3 accepted fields are no evidence.

### D. Why small positive numbers are not evidence

With 0 errors among n accepted fields, the 95% Wilson upper bound of the error rate is about 3.8/n. To claim an error rate below 1%, about 384 accepted fields without any error are needed. Our positive results have 3 to 14 accepted fields. The largest run has 132 accepted fields and 4 errors (3.0%). No measurement supports the claim "above 99% precision".

### E. Cost sensitivity (20 / 100 / 500)

| Variant at threshold 0.99 | Precision | E=20 (needs > 95.0%) | E=100 (needs > 99.0%) | E=500 (needs > 99.8%) |
|---|---:|---:|---:|---:|
| `never` / all-abstain (submitted) | n/a | 0.0% | 0.0% | 0.0% |
| probly pipeline, dev (78 documents) | 97.0% | **+0.2%** | −1.2% | −8.4% |
| probly pipeline, test_public (40 documents) | 93.7% | −0.8% | −15.7% | −90.4% |
| LLM, model confidence only, dev (307 documents) | 92.0% | −2.6% | −30.9% | −171.9% |
| probly `k_agreement_conf`, dev_audit (7 documents) | 75.0% | −12.3% | −73.8% | −381.5% |
| `common`, test_public (threshold 0.95) | 60.2% | −31.9% | −177.8% | −907.5% |

At error cost 20 the probly pipeline is slightly positive on dev (+0.2%) but not on test_public. At 100 and 500 every active variant is negative. All-abstain is the only variant that is never negative, at any error cost.

### F. Why coverage is low

Coverage is low on purpose and by limitation. The causes, in order of size:

1. **CUAD span rejections.** 70.6% of all dev fields are CUAD span fields. Before the last fixes the pipeline accepted none of them: the model answered multi-part clauses as lists or with other separators, curly apostrophes did not match straight ones in the grounding check, and long clauses with line breaks failed JSON parsing.
2. **Strict text grounding.** A value is accepted only if it occurs in the text as a contiguous, token-bounded span. Paraphrased, reformatted or shortened values are rejected. Booleans are never accepted, because no evidence rule exists for them.
3. **Scan abstention.** About 40% of the ExtractBench PDFs have no text layer. The pipeline abstains on the whole document.
4. **The conservative threshold 0.99.** Raising the threshold from 0.95 to 0.99 removes 43% of the accepted fields on dev (230 to 132).
5. **Document-level and K-level abstention.** With K=3 a field needs three valid observations. One failed request removes the field.

### G. The five last fixes (code and regression tests done, effect on the API not measured)

| # | File | Defect | Fix | Expected effect |
|---|---|---|---|---|
| a | `pipeline/transport.py` | A reply with a literal line break or tab inside a string was rejected as invalid JSON. Long CUAD clauses were lost. | `json.loads(..., strict=False)`. Broken structure is still an error. | fewer lost CUAD answers, more coverage |
| b | `pipeline/requests.py` (prompt v4) | Booleans were requested as the strings `"true"`/`"false"`, which fail a `boolean` schema. Multi-part spans had no stated format. | Booleans as JSON `true`/`false`. Several passages in one string, joined with ` | ` (the scorer's separator). | fewer `invalid` values, span answers in the scored format |
| c | `uncertainty/grounding.py` | `Supplier’s` in the text did not match `Supplier's` in the answer. The same for curly quotes, dashes and non-breaking spaces. | The glyph variants are unified before comparison. Words, numbers and punctuation stay exact. | fewer false rejections of correct CUAD spans |
| d | `uncertainty/decision.py` | A non-null value with confidence 0.0 was written out. At threshold 0 the scorer accepts it. | Such a value becomes null. | no accepted value without confidence |
| e | `uncertainty/uq_probly.py` | The per-field diagnostics did not show why a field was rejected. | `status_counts` (present, absent, unsupported, invalid, error) in the diagnostics. | error analysis per field, basis for field-wise abstention |

These fixes are covered by `tests/test_final_regressions.py` (32 tests). **Prompt v4 and the fixes have not been run against the API.** Their effect on coverage and precision is unknown until a new dev measurement is made. This is the second reason for all-abstain: we do not submit an unmeasured configuration.

### H. Confirmed error cause from the audit (concrete example)

Document `extractbench:short/gsa_mas_it_labor_0020`, field `labor_categories` (a table). The schema requires rows with the keys `labor_category_title` and `year_1_rate` (a number). The model returned `labor_category`, `year_1` and the text `"$241.81"`. All three samples agreed, every cell value occurred in the document, and the field was accepted with confidence 0.99. It was wrong, and it alone cost 100.

Two causes, both fixed: the prompt (v2) did not send the `$defs`, so the model never saw the real key names; and nested values were checked only for text occurrence, not for keys and types. Since prompt v3 the full schema is sent, and `schema_check.py` rejects the value as `invalid`.

### I. Run counts (real API, from the manifests)

| Run | Model | Documents | Requests | Retries | Failures | 429 stop | Elapsed |
|---|---|---:|---:|---:|---|---|---:|
| dev_cal subset, K=1 | `gemini-3.8-flash` | 6 | 10 of 21 planned | not recorded | 4 documents abstained after 429 | yes | about 203 s |
| dev_select, K=3 | `gemini-3.8-flash` | 7 | 60 | 0 | 0 | no | 1,679 s |
| dev_audit, K=3 | `gemini-3.8-flash` | 7 | 57 | 0 | 0 | no | 1,455 s |
| 10 dev documents, K=1 | `gemini-3.7-flash` | 10 | 48 | not recorded | 0 | no | 303 s |

The dev_cal subset run is the measurement stored in `submission/decision.json`: 2 accepted fields, 1 wrong, net −49.2% at threshold 0.95 (E=20: −9.0%; E=500: −250.3%). It is a functional test, not a representative measurement.

## Configuration

| Setting | Where | Default | Submitted value |
|---|---|---|---|
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | environment or `.env` (names only, never committed) | none | not used: all-abstain makes no request |
| Decision file | `--decision submission/decision.json` | none | `abstain_all: true`, threshold 1.0 |
| K samples | `--samples` | 1 | n/a |
| Decision rule | `--uq-method` | `k1_grounded` (K=1), `k_agreement_conf` (K>1) | n/a |
| Temperature, sampling | `--temperature`, `--sampling` | 0.7, `mixed` (sample 0 is greedy) | n/a |
| Chunking | `--chunk-chars`, `--overlap-chars`, `--batch-size` | 45,000 / 3,000 / 10 | n/a |
| Workers | `--workers` | 1 | n/a |
| Error handling | `--on-error fail|abstain` | `fail` | `abstain` |
| Cache | `--cache-dir`, `--no-cache` | `cache/` | not used |

With `abstain_all: true` the extractor needs no API key, no network and no probly import. It writes null with confidence 0.0 for every schema field of every input document.

## How to run

Python 3.12 is required (`probly==0.9.1`). From a fresh clone, in the folder `Project_1`:

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On Linux or macOS: `python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.

Data: `bash 1_download.sh --accept-licenses` and `python 2_prepare.py` create `data/` (not committed).

**Hidden test (the submitted configuration, no API call):**

```
bash run_hidden.sh <input.jsonl> <output.jsonl>
```

`run_hidden.sh` picks `.venv/bin/python`, `.venv/Scripts/python.exe` or `python3` and runs
`4_extract.py --data "$1" --out "$2" --mode llm --on-error abstain --decision submission/decision.json`.
The exit code of the extractor is passed on (0 on success, 2 for wrong arguments, 1 for any error). **The output path must not exist yet**: the extractor refuses to overwrite a file.

Check a prediction file without gold:

```
.venv\Scripts\python.exe -m evaluation.validate --input <input.jsonl> --pred <output.jsonl>
```

Tests (no API call):

```
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.venv\Scripts\python.exe test_score.py
```

Score and reproduce the tables:

```
.venv\Scripts\python.exe 5_score.py --gold data/unified/dev.jsonl --pred results/<run>.jsonl --threshold 0.99 --json results/<run>_score.json
.venv\Scripts\python.exe compare_results.py --threshold 0.99
.venv\Scripts\python.exe submission\make_slides.py
```

Active measurement (needs the API; not part of the submission): `4_extract.py --data ... --out ... --mode llm --samples 3 --on-error abstain`, then `evaluation.ablation` on the stored samples, then `evaluation.select_threshold freeze` on `dev_select`, `audit` on `dev_audit`, and `decide`.

## Demo

`submission/slides.pdf` (5 slides, built by `submission/make_slides.py` from the stored score files): 1. problem and the 1:100 cost trap, 2. architecture and probly pipeline, 3. method comparison, low coverage and the `never` baseline, 4. a concrete error and the five fixes, 5. limits and improvement levers.

## External data flow

In an active run the text of each document part and the field prompts are sent to the organiser's LLM endpoint. Replies are cached in `cache/`, samples are kept in `results/*.samples.jsonl`. Both contain document text, are git-ignored and stay on the team's machines. The submitted all-abstain configuration sends nothing.

## Limits

- **The submitted system saves nothing.** It is exactly as good as full human review (0.0%). It only avoids losing money.
- **Coverage of the active pipeline is low** (1.4% on dev, 7.2% on test_public at 0.99) and zero for CUAD.
- **No active variant reaches 99% precision.** The best is 97.0% (132 accepted, 4 errors).
- **Prompt v4 and the five last fixes are not measured on the API.**
- **The large runs cover only a part of the splits** (78 and 307 of 540 dev documents; 40 and 75 of 176 test_public documents). Their percentages are diluted by the unprocessed documents, and their manifests are not in the repository. The plain LLM run and the probly run cover different documents, so their rows are not a paired comparison.
- **Two model versions** (`gemini-3.7-flash`, `gemini-3.8-flash`) were used in different runs and never compared on the same documents.
- The select and audit sets are tiny (7 documents each) and prefer short documents.
- The confidence is an uncalibrated score. `make_prediction(..., method="calibrated")` raises an error: no calibrator is implemented.
- Grounding shows that the text occurs in the document, not that it belongs to the field. Example: `Liquidated Damages` was accepted with a grounded value where the gold is null.
- Scans and corrupted PDFs are always abstained. No OCR, no vision model.
- Booleans are never accepted. JSON tables are accepted only if schema, keys and every leaf value pass.
- `run_hidden.sh` was run on Windows with Git Bash only. No Linux environment was available.
- test_public was scored for reporting. We did not tune on it, but we have seen its numbers, so it is no longer a blind set for us.

## Improvement levers: how to get above the human baseline

The gap is concrete. At 0.99 on dev the pipeline has 132 accepted fields and 4 errors. With at most 1 error it would be positive. Two things are needed at once: fewer errors among the accepted fields, and more accepted fields.

1. **Measure prompt v4 and the five fixes.** One K=3 run on unused `dev_fit` documents, with method and threshold frozen first. Expected: CUAD span fields become acceptable for the first time (fixes a, b, c), and schema-invalid booleans and tables disappear (fix b plus schema validation). This is the largest coverage lever, because 70.6% of the fields are CUAD spans.
2. **Vision or OCR for image-only scans.** About 40% of the ExtractBench PDFs have no text layer. Send page images to a vision model, or add OCR and ground against the OCR text. Scans need their own, stricter threshold.
3. **Calibrate the probability on a larger dev set.** The raw confidence is wrong in 9.5% of the cases where it says 1.00. Fit an isotonic or Venn-Abers calibrator (probly `calibrator`) per normalizer type on several hundred labelled candidates from `dev_fit`. Features: model confidence, agreement, probly entropy, `status_counts`, field type, grounding. Then choose the threshold with a conformal risk bound instead of a fixed 0.99.
4. **Field-specific instead of document-wide abstention.** Accept only field types with proven precision (for example printed ExtractBench strings and numbers) and keep abstaining on risky ones (tables, clauses, booleans). The `status_counts` diagnostics (fix e) and the per-source score give the data for this. A per-field-type threshold raises coverage without raising the error rate.
5. **A second check for span fields.** Grounding does not show that a clause belongs to the category. A verification prompt ("does this passage answer this field, yes or no") on the accepted candidates would target exactly the remaining errors.
6. **Release rule.** Switch the system on only after an independent audit with several hundred accepted fields and a positive net saving. Until then all-abstain stays.

How SIXT could use this today: the pipeline can run in "suggest" mode. It books nothing, but it pre-fills the fields it can verify and shows the evidence span and the diagnostics, so the human review is faster. That gives a benefit without the 100-point risk.
