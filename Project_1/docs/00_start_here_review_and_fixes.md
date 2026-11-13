# START HERE: verified state, bugs, corrections, day plan

> Updated 13.11.2026 after checking the docs against `4_extract_example.py`, `5_score.py`, `2_prepare.py`, `make_eda.py`, `test_score.py`, the data in `data/unified/`, and `probly` 0.9.1 (Python 3.12.10, `.venv`).
> **Read this file first.** Where it conflicts with the other docs in this folder, this file wins. The other docs have been corrected to match.

---

## 1. What we build today (5 points)

1. **One extractor** that returns `{"value", "confidence"}` for every schema field. CUAD contracts have 41 `span` fields each. ExtractBench forms and scans have `string`, `json` and boolean fields, plus numeric fields with no normalizer.
2. **Fix the starter** (section 3): full documents, field batching, correct grounding, scanned PDFs, retries, cache, and no silent fallbacks.
3. **Estimate uncertainty per field** with K samples, prompts or models. Cluster the answers with the scorer's own `values_match`, then turn the cluster frequencies into a `probly` distribution or credal set. Combine with grounding signals.
4. **Calibrate and choose τ\*.** Fit the calibrator on `dev_train` (group-aware split). Choose τ\* on `dev_cal`, and only there. Never use `test_public` for any decision.
5. **Package by 16:45:** `run_hidden.sh` with τ\*, `SUBMISSION.md` with the declared τ\*, metrics, and sensitivity at error cost 20 and 500. Plus `slides.pdf` or `demo.mp4`.

---

## 2. Verified facts (dev and test, checked 13.11.2026)

| Claim | Verified value | Notes |
|---|---|---|
| dev docs | **540** (381 CUAD, 159 ExtractBench) | ✅ |
| dev fields | 22,115; present 9,372; null 12,743; **null rate 57.6%** | ✅ |
| test_public | 176 docs, 6,962 fields, present 2,865, **null rate 58.8%** | ❌ was 58.9% in the docs |
| CUAD contracts > 60,000 chars | **109 of 381 (28.6%)** | ❌ docs say 110. See note A. |
| ExtractBench PDFs without text | **64 of 159 (40.3%)**: perception P2 57, P3 17, P1 7 | ✅ no pdftotext/pypdf exceptions |
| `*_corrupted` PDFs | 7, **all 7 without text** and tagged P1 | ❌ docs say "garbled text" and P2/P3 |
| Gold types, ExtractBench scalars | str 3,766; float 198; int 123; null 2,136 | Numbers are not all strings |
| Boolean-typed fields | 1,066 gold values as **strings** `"true"` (289) / `"false"` (777); 136 null | Schema says `boolean`, gold says string |
| Dates in gold | `m/d/y` 99×, ISO `YYYY-MM-DD` 16× | Dates are not all printed one way |
| Scalar fields with `x-normalizer` | **none** (6,223 fields have no key) | Scorer falls back to `string` |
| `span` / `json` fields | span 15,621 (CUAD only); json 271 (ExtractBench) | ✅ |
| Gold keys = schema keys | true for all 540 docs | ✅ |
| CUAD present clauses per doc | mean 13.2 of 41 | ✅ |
| Gold spans joined with `" \| "` | 1,956 gold values | ✅ |
| **Page paths** | **all 540 records store Windows paths**, e.g. `raw\extractbench\docs\short\...pdf` | ❗ see bug C1 |
| Offline baseline net saving at τ=0 | **−931.7%** (docs said −930.0%) | ❌ arithmetic: (732 − 65,600) / 6,962 |
| `test_score.py` | 19 tests, all pass | ✅ |

**Note A (110 vs 109):** `make_eda.py` counts every document whose text length is ≥ 60,000. The one extra document is an ExtractBench PDF with more than 60,000 characters of text. "110 CUAD contracts" is therefore wrong. The correct figure is **109 CUAD contracts**.

**Note B (break-even):** A correct accepted field saves 1 (review cost avoided). A wrong or hallucinated accepted field costs `E` instead of 1, so it is `E − 1` worse. Break-even precision is `p = (E − 1) / E`:
- E = 100 → **99.0%** (the docs said 99.01%, which is wrong)
- E = 20 → 95.0%
- E = 500 → 99.8%

---

## 3. Bugs to fix first (ordered by damage)

| ID | Bug | Where | Effect | Fix |
|---|---|---|---|---|
| **C1** | **Windows paths in data.** Every `pages` entry contains `\`. On Linux/macOS, `Path("raw\\...pdf")` is one filename and does not resolve. | `data/unified/*.jsonl` field `pages`; `4_extract_example.py` `build_content` and `doc_text` use `DATA / rec["pages"][0]` | Every ExtractBench doc fails on Linux, prints an error to stderr, and is written as all-null. **The hidden test probably runs on Linux, so this could zero the whole ExtractBench part.** | One helper that replaces `\` with `/` before building the path. Use it everywhere. Check on a Linux shell or in WSL. |
| **C2** | **`.env` is never loaded.** Nothing calls dotenv. Keys are read only from `os.environ` (`call_llm`, and the mode check in `main`). | `4_extract_example.py` `call_llm`, `main` | Without exported variables, `--mode auto` (the default that `run_hidden.sh` uses) silently falls back to offline rules. It prints only one stderr line. | Load `.env` at startup with a small parser (no new dependency). Make `run_hidden.sh` pass `--mode llm`, so missing keys fail loudly. |
| **C3** | **Scorer mis-scores partial runs.** `5_score.py` `collect()` iterates over the **gold** file. Docs missing from the predictions count as all-null. | `5_score.py` `collect` | The CLAUDE.md command `4_extract_example.py --limit 10` followed by `5_score.py --gold dev.jsonl` gives wrong net saving, recall and coverage, because 530 unpredicted docs count as predicted-null. Precision is not affected. | Score against a gold subset that matches the predictions, e.g. `head -n 10 data/unified/dev.jsonl > results/dev10_gold.jsonl`. Or add a `--only-predicted` flag to the scorer. |
| **C4** | **Malformed LLM reply → whole doc silently null.** `parse_json` returns `{}` on any error. No retry, no log. | `4_extract_example.py` `parse_json`, `extract` | Expensive (every field goes to a human) but not dangerous. Hides a rate problem. | Retry once at temperature 0, count parse failures per run, print them. |
| **C5** | **Confidence default is 0.5.** If the model omits `confidence`, the starter uses 0.5. This is an invented number. (It avoids the scorer's 1.0 trap, but is still wrong.) | `extract`: `a.get("confidence", 0.5)` | With τ ≤ 0.5 these values auto-book. | Default to **0.0**. |
| **C6** | **Grounding is too lenient and only halves confidence.** `squash()` removes commas on both sides, so `"1,234.50"` matches `"1234.50"` in the text. The scorer treats them as different strings, so this is exactly the trap. Also `len > 80` and dict/list values are never checked. Ungrounded values are multiplied by 0.5, which can still be above τ. | `grounded()` and `extract` (`conf *= 0.5`) | Hallucinated or reformatted values get booked. | Ungrounded → confidence **0.0** (abstain). For `string` fields, compare with the scorer's `norm_string` and keep commas. For `span`, use token overlap, not substring. |
| **C7** | **Lazy global `_cuad` load.** `cuad_text` loads the JSON on first use. With a thread pool, several threads may load it at once. | `cuad_text` | Slow and wasteful, not wrong. | Load once in `main` before the pool starts. |

**Smaller issues**
- `describe()` cuts descriptions at 300 characters and gives no type information for `json` or boolean fields. ExtractBench descriptions are long and contain the rules, so the cut-off matters.
- `main()` writes `{"value": None}` with no confidence on exceptions. That is safe (null). Do not change it to a non-null default.
- `run_hidden.sh` calls `python3`. On Windows (Git Bash) `python3` may be a Store alias. Check before relying on it.
- `probly` calibration helpers may need packages that are not installed here (`scikit-learn` is missing). Test the import before the calibration step.
- PyMuPDF (`fitz`) is not installed. It is only needed if we render PDF pages to images.

---

## 4. Corrections to the other docs in this folder

| File | Old text | Correct |
|---|---|---|
| `hackathon_master_plan_team_kickoff.md` §1 | break-even ≈ 99.01% (100/101) | **99.0%** = (E−1)/E, see Note B |
| `hackathon_master_plan_team_kickoff.md` §2 | Python 3.12.3 verified; `source .venv/bin/activate` only | 3.12.10 verified; Windows: `.venv\Scripts\activate` |
| `hackathon_master_plan_team_kickoff.md` §3 | "110 contracts > 60k chars" | **109 CUAD** |
| `hackathon_master_plan_team_kickoff.md` §4 | Phase 3: "conformal threshold selection" | There is no ready-made τ selection for our cost. We implement it ourselves (section 5 of this file). |
| `data_reference_baselines_scoring_guide.md` §1 | test_public null 58.9% | **58.8%** |
| `data_reference_baselines_scoring_guide.md` §2B.1 | "all ExtractBench scalar fields use `string`" | Scorer **defaults** to `string`; no schema field has the key. Numbers and dates appear as float/int/`m/d/y` in gold, so "copy verbatim" is not always right. Follow the schema description. |
| `data_reference_baselines_scoring_guide.md` §2B.2 | checkbox gold `"false"` | ✅ gold is the **string** `"false"`/`"true"`; the schema says `boolean` |
| `data_reference_baselines_scoring_guide.md` §2B.3 | "110 out of 381" | **109 out of 381** |
| `data_reference_baselines_scoring_guide.md` §2B.4 | corrupted files "garbled" | The 7 corrupted files **have no text**, tag P1 |
| `data_reference_baselines_scoring_guide.md` §4 | list of JSON keys | Add `at_threshold` (all counters at τ). `by_condition` also has `damage:`, `severity:`, `difficulty:` tags. |
| `data_reference_baselines_scoring_guide.md` §5 | Offline τ=0 net saving −930.0% | **−931.7%** |
| `engineering_roadmap_refactoring_llm_cache.md` §1.1 | "cuts off 110 contracts" | **109** |
| `engineering_roadmap_refactoring_llm_cache.md` §1.3 | "`grounded()` penalizes valid normalized matches" | Not what the code does. The real problem is that it is too lenient for commas (C6). |
| `engineering_roadmap_refactoring_llm_cache.md` §1.6 | "rules are missing" | Rules for verbatim copy and null already exist in `PROMPT`. Missing: checkbox rule and number rule. |
| `engineering_roadmap_refactoring_llm_cache.md` §1.4 | corrupted files: "garbled text / `�`" | They have **no text**. Route them to "no text". |
| `probly_integration_uncertainty_quantification_guide.md` Step 4 | `probly.decision` | Module is **`probly.decider`** |
| same, Step 3 | calibration methods in `probly.calibrator` | `probly.calibrator` has only `Calibrator` and `calibrate`. The methods are in **`probly.method.calibration`** (`platt_scaling`, `isotonic_regression`, `temperature_scaling`, `vector_scaling`). |
| same, Step 2 | `CategoricalDistribution` as a class to instantiate | It is **abstract**. Use `create_categorical_distribution(probs)`. Credal set: `create_probability_intervals(...)` or `create_probability_intervals_from_bounds(...)`. |
| same, Step 4 | "conformal threshold controls false acceptance at α = 0.01" | `probly.method.conformal` contains **conformal set predictors** (LAC, APS, RAPS, …), not a risk-controlled threshold for our cost. We need our own rule (section 5). |
| same, §3 | `examples/llm/semantic_entropy.py` | Not in the installed package. Do not plan on it. |
| `CLAUDE.md`, commands | `4_extract_example.py --limit 10`, then score on the full `dev.jsonl` | Wrong, see **C3** |

---

## 5. How to choose τ\* (the decision that matters most)

**Split (once, group-aware):** `2_prepare.py` groups documents by the id without the `-pNNNN` page suffix. Split `dev.jsonl` by that group, not by row, so pages of the same filing do not end up in both `dev_train` and `dev_cal`. Save the split as a file and do not change it afterwards.

**Rules:**
1. Fit calibration and any aggregation on `dev_train` only.
2. Choose τ\* on `dev_cal` only.
3. Evaluate once on `test_public` at the declared τ\*. Never choose τ\* after looking at test.

**Choosing τ\* with the cost:** Break-even is 99.0% precision. For a usable decision you also need statistical margin:
- **Rule of three:** with 0 errors in n accepted fields, the 95% upper bound on the error rate is about 3/n. To claim error ≤ 1%, you need **n ≥ 300 accepted fields with 0 errors** on `dev_cal`. Otherwise the precision estimate is too noisy.
- Pick τ\* as the value that maximises `net_saving` on `dev_cal`, **subject to** the 95% upper bound of the error rate among accepted fields being ≤ 1%. Report it with the bound.
- Check that τ\* still gives positive saving at E = 20 and E = 500 (sensitivity). If it only works at E = 100, it is fragile.

**Expected size of `dev_cal`:** about 30% of 540 docs ≈ 160 docs ≈ 6,600 fields. Only about 40% of fields are present, so the number of accepted fields depends on how many the model answers confidently. Check early whether there are enough.

---

## 6. Day plan (13.11.2026, deadline 16:45)

| Time | Step | Done when |
|---|---|---|
| now | Fix **C1** (paths) and **C2** (.env). Run `test_score.py`. | A Linux/WSL run on 3 ExtractBench docs gives non-empty values. |
| +20 min | Run the scorer on the offline baselines. | Net saving −931.7% at τ=0 reproduced. |
| +30 min | **C3**: gold-subset helper. LLM smoke test on 10 docs (`--mode llm`). | Scored correctly against a matching gold subset. |
| +60 min | **C4–C7** fixes. Re-run the smoke test. | `results/llm_refactored_dev_score.json` exists. |
| after lunch | K samples, clustering, calibration on `dev_train`, τ\* on `dev_cal`. | `results/probly_calibrated_dev_cal_score.json` with the bound. |
| 15:30 | Freeze τ\*. Put it in `run_hidden.sh`. Test `run_hidden.sh` with a gold-free input from a **Linux shell**. | No gold-key errors, no all-null ExtractBench docs. |
| 16:00 | `SUBMISSION.md`, slides or demo. | Pushed to `main` before 16:45. |

**Cost control:** API cost is per call. Run `--limit 10` before any full run. Cache everything in `cache/` (git-ignored).

---

## 7. Open questions for the team (decide early)

1. Which models does the endpoint offer? Is any of them vision-capable? This decides whether scanned PDFs can be answered at all.
2. What are the rate limits? This decides the number of workers and K.
3. Who owns C1 and C2? They block everyone. Suggestion: Person C, first 30 minutes.
