# Data Reference, Baselines & Scoring Guide

> **Corrections 13.11.2026:** numbers re-checked against `data/unified/*.jsonl` and `5_score.py`. Changes are marked ✱ below. Full list: `00_start_here_review_and_fixes.md` §2 and §4.

> **Purpose:** Complete reference for the Project 1 datasets, empirical findings from `EDA.md`, evaluation commands, and how to interpret `5_score.py` JSON outputs.

---

## 1. Dataset Overview & Splits

`2_prepare.py` normalizes raw datasets into `data/unified/dev.jsonl` ($\approx 75\%$) and `data/unified/test_public.jsonl` ($\approx 25\%$) using deterministic hashing on the document group ID (so multi-page documents from the same filing stay in the same split).

| Split           | File Path                             | Docs | Total Fields | Present Fields | Absent (null) Fields | Null Rate | Usage Rule                                                                                     |
|-----------------|---------------------------------------|-----:|-------------:|---------------:|---------------------:|----------:|------------------------------------------------------------------------------------------------|
| **Dev**         | `data/unified/dev.jsonl`              |  540 |       22,115 |          9,372 |               12,743 |     57.6% | Split into `dev_train` + `dev_cal` for prompt tuning, calibration, and selecting $\tau^*$.     |
| **Public Test** | `data/unified/test_public.jsonl`      |  176 |        6,962 |          2,865 |                4,097 |     58.8% ✱ | **Held-out evaluation only.** Record checkpoint scores; never tune on this file.               |
| **Hidden Test** | Provided at grading (`run_hidden.sh`) |    — |            — |              — |                    — |         — | Same format as `dev.jsonl` **without the** `"gold"` **key**. Scored at your declared $\tau^*$. |

*(Optional extra datasets in* `1_download.sh`*:* `invoicebenchmark` *and* `drew_ipp` *can be downloaded via* `bash 1_download.sh --only <name>` *for extra calibration/testing if needed, without polluting* `test_public.jsonl`*.)*

---

## 2. Critical Findings from `EDA.md` (What Affects Accuracy Most)

### A. Two Very Different Document Domains

1. `cuad` **(Legal Contracts — 70.6% of dev fields / 76.0% of public test fields):**
   - 381 dev docs $\times$ 41 legal clause types = 15,621 fields.
   - $67.9\%$ **of fields are** `null`. Most contracts only contain ~13 of the 41 clauses.
   - Scored with `x-normalizer: "span"` using token-level $F_1 \ge 0.8$ (multiple distinct spans in the same contract are joined with `" | "`).
2. `extractbench` **(Forms, Tax Returns, Filings, Invoices — 28.1%** `string` **+ 1.2%** `json`**):**
   - 159 dev docs, 6,494 fields ($32.9\%$ `null`).
   - Includes IRS forms (W-2, K-1, 990-PF), SEC filings (13F, N-PORT), purchase orders, utility bills, vehicle valuations, and deliberately corrupted files (`*_corrupted`).

### B. Five Data Traps That Cause $-100$ Penalties

1. **ExtractBench scalar fields have no `x-normalizer` key ✱.** The scorer treats them as** `"string"` **(NOT** `"amount"` **or** `"date"`**):**
   - `5_score.py` only normalizes case and collapsed whitespace for `"string"` fields.
   - If the PDF prints `"1,234.50"` or `"11/13/2026"` and the LLM reformats it to `"1234.50"` or `"2026-11-13"`, **it is scored WRONG (**$-100$ **penalty)**. Prompts must strictly instruct the model to copy strings verbatim as printed.
   - ✱ **Caveat (checked):** the gold also contains 198 floats, 123 ints and 99 `m/d/y` dates, and the schema descriptions sometimes say "thousands comma removed". For numeric and date fields, follow the schema description. Verbatim copying applies to text.
2. **Empty Checkboxes Are** `"false"`**, Not** `null`**:**
   - `2_prepare.py` encodes boolean checkboxes as `"true"` or `"false"`. ✱ Checked: the schema type is `boolean`, but the gold is the string (1,066 values: 777 `"false"`, 289 `"true"`, 136 `null`). Emit the same string form. An unchecked box on a visible form section has gold `"false"`, whereas a missing/inapplicable section has `null`.
3. **28.6% of Contracts Exceed** `MAX_CHARS = 60,000`**:** ✱
   - ✱ **109** out of 381 CUAD contracts in `dev.jsonl` are truncated at 60,000 characters in `4_extract_example.py`, hiding clauses near the end of long agreements.
4. **40% of ExtractBench PDFs Have Zero Extractable Text:**
   - 64 out of 159 ExtractBench dev PDFs return `None` from `pdftotext`/`pypdf` (image-only scans; tags P2 57, P3 17, P1 7). ✱ The 7 `*_corrupted` PDFs are **all among these 64**. They have no text either, they are not "garbled".
5. **Nested** `json` **Fields (**$1.2\%$ **of dev fields) Are Scored All-or-Nothing:**
   - A single wrong number inside a 30-row holdings or line-items table triggers the full $-100$ penalty. Consider abstaining (`confidence = 0.0`) on complex `json` array fields unless multi-sample agreement is $100\%$.
6. ✱ **Windows paths in the data (bug C1):** every `pages` entry (540 of 540 dev records) uses `\`, e.g. `raw\extractbench\docs\short\....pdf`. On Linux/macOS these paths do not resolve, and the extractor writes all-null for those docs. Normalise separators before building the path.

---

## 3. Commands to Run & Save Checkpoints

Always run from inside `Project_1/` with `.venv` active. Save predictions to `results/<name>.jsonl` (git-ignored) and score reports to `results/<name>_score.json` (tracked in Git).

### Offline No-AI Baselines (Already Run)

```bash
cd Project_1
mkdir -p results

# 1. Never answer (floor: 0% saving, 0 errors)
python3 3_baseline.py --train data/unified/dev.jsonl --target data/unified/test_public.jsonl --out results/base_never.jsonl --mode never
python3 5_score.py --gold data/unified/test_public.jsonl --pred results/base_never.jsonl --threshold 0.95 --json results/base_never_score.json

# 2. Most common training value per field
python3 3_baseline.py --train data/unified/dev.jsonl --target data/unified/test_public.jsonl --out results/base_common.jsonl --mode common
python3 5_score.py --gold data/unified/test_public.jsonl --pred results/base_common.jsonl --threshold 0.95 --json results/base_common_score.json

# 3. Starter offline regex/keyword rules
python3 4_extract_example.py --data data/unified/test_public.jsonl --out results/base_offline.jsonl --mode offline
python3 5_score.py --gold data/unified/test_public.jsonl --pred results/base_offline.jsonl --threshold 0.95 --json results/base_offline_score.json
```

### Standard Command Pattern for Future Checkpoints

> ✱ **Warning (bug C3):** `5_score.py` iterates over the **gold** file. Docs that are missing from the predictions count as all-null. If you run `--limit 10` and score against the full `dev.jsonl`, the net saving, coverage and recall are wrong. Always score against a gold subset with the same doc ids (`head -n 10 data/unified/dev.jsonl > results/dev10_gold.jsonl`).

```bash
# Step A: Tune/calibrate ONLY on dev.jsonl
python3 your_extractor.py --data data/unified/dev.jsonl --out results/<run_name>_dev.jsonl
python3 5_score.py --gold data/unified/dev.jsonl --pred results/<run_name>_dev.jsonl --json results/<run_name>_dev_score.json

# Step B: Pick optimal threshold tau* from dev_cal (not test_public!)

# Step C: Evaluate once on held-out test_public.jsonl at your declared tau*
python3 your_extractor.py --data data/unified/test_public.jsonl --out results/<run_name>_test.jsonl
python3 5_score.py --gold data/unified/test_public.jsonl --pred results/<run_name>_test.jsonl --threshold <tau*> --json results/<run_name>_test_score.json
```

---

## 4. Understanding `5_score.py` JSON Output

Each `results/*_score.json` file contains the following keys:

- `declared` *(present when* `--threshold <tau>` *is passed — this is your official competition result)*:
  - `threshold`: Your declared confidence cutoff $\tau^*$.
  - `precision`: $\text{correct} / \text{accepted}$. Must exceed $(E-1)/E$ for positive savings: $99\%$ for $E = 100$ ✱ (the old "$99.01\%$" was wrong).
  - `coverage`: $(\text{correct} + \text{wrong}) / \text{gold\_present}$ — fraction of truly present fields your system attempts to auto-book.
  - `hallucination_rate`: $\text{hallucinated} / \text{gold\_null}$ — fraction of absent fields where your system wrongly booked a value.
  - `accepted`, `wrong`, `hallucinated`: Raw field counts auto-booked at $\ge \tau^*$.
  - `band`: Highest precision tier reached (`0.99`, `0.95`, `0.90`, `0.80`, or `null` if below $80\%$).
  - `net_saving_pct`: Headline KPI:

    $$
    \text{net\_saving\_pct} = \frac{\text{accepted} - 100 \times (\text{wrong} + \text{hallucinated})}{N_{\text{fields}}}
    
    $$
- ✱ `at_threshold`: all counters at your declared τ (`accepted`, `correct`, `wrong`, `hallucinated`, `missed`, `true_null`, `precision`, `recall`, `coverage`, `hallucination_rate`). Present only when `--threshold` is passed.
- `at_threshold_0`: Performance if every non-null prediction were accepted ($\tau = 0.0$). Useful for measuring raw extraction recall/precision before abstention.
- `headline` **&** `coverage_at_precision`: Oracle sweep over all thresholds on that file showing maximum coverage achievable at $99\%$, $95\%$, $90\%$, and $80\%$ precision. **Use this sweep on** `dev.jsonl` **only** to pick $\tau^*$.
- `business`: Oracle best net saving across all thresholds on that file (`review_cost = 1.0`, `error_cost = 100.0`).
- `schema_validity`: Share of documents whose non-null predicted values pass `jsonschema.validate(...)`.
- `by_source` **&** `by_condition`: Breakdown at $\tau = 0.0$ across `cuad` vs. `extractbench` and across capture quality tags (`perception:P1` clean digital, `perception:P2` medium scan, `perception:P3` degraded/handwritten). ✱ `by_condition` can also contain `damage:`, `severity:` and `difficulty:` tags when they are present in the data.
- `curve`: Full list of operating points across every unique confidence score, used to plot your **Accuracy–Rejection (Precision vs. Coverage) Curve** in the slides.

---

## 5. Recorded Baseline Benchmark Table (`test_public.jsonl`, $N = 6,962$ fields)

| System                                | Threshold $\tau$ | Accepted | Correct | Wrong | Hallucinated | Precision | Coverage |  Net Saving | Schema Validity |
|---------------------------------------|-----------------:|---------:|--------:|------:|-------------:|----------:|---------:|------------:|----------------:|
| `3_baseline.py --mode never`          |             0.95 |        0 |       0 |     0 |            0 |       n/a |     0.0% |    **0.0%** |           89.2% |
| `3_baseline.py --mode common`         |             0.95 |      319 |     192 |   125 |            2 |     60.2% |    11.1% | **-177.8%** |           73.9% |
| `4_extract_example.py --mode offline` |             0.95 |        0 |       0 |     0 |            0 |       n/a |     0.0% |    **0.0%** |           89.2% |
| `4_extract_example.py --mode offline` |             0.00 |      732 |      76 |   550 |          106 |     10.4% |    21.8% | **-931.7%** ✱ |           89.2% |
