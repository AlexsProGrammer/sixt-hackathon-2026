# `probly` Integration & Uncertainty Quantification Guide

> **Purpose:** Practical blueprint for integrating the `probly` library into Project 1's structured extraction pipeline—covering both our default CPU-laptop + API setup and an optional GPU-accelerated setup if hardware is provided tomorrow.

---

## 1. Why `probly` Fits Project 1

In uncertainty-aware machine learning, "teaching a machine to say *I don't know*" is **Selective Prediction (learning with abstention)** combined with **Out-of-Distribution (OoD) / Degradation Detection**.

`probly` (developed by Eyke Hüllermeier's group at LMU Munich / MCML) structures uncertainty-aware ML into four composable stages:
$$\text{Transform} \longrightarrow \text{Represent} \longrightarrow \text{Quantify} \longrightarrow \text{Decide}$$

For structured document extraction, we need to distinguish two types of uncertainty on every extracted field:
- **Aleatoric Uncertainty (Data Ambiguity):** Blurry scans (`perception:P3`), handwriting, ambiguous checkbox marks, or missing/corrupted PDF pages where the input itself lacks clear evidence.
- **Epistemic Uncertainty (Model Ignorance):** The LLM guesses or hallucinates a plausible-looking clause or number that is not grounded in the document, causing different prompts, temperatures, or models to disagree.

---

## 2. Scenario A (Default): CPU Laptop + LLM API Keys

On a CPU-only laptop (e.g., 2019 ThinkPad) calling remote OpenAI-compatible LLM endpoints, **do not run local Hugging Face LLMs or local NLI cross-encoders**. Instead, run LLM inference via the API (with disk caching in `cache/`) and run `probly`'s fast NumPy/SciPy representations, quantification, calibration, and conformal abstention locally on CPU.

### Step 1: Transform — Multi-Sample, Multi-Prompt, or Multi-Model Ensembling
Generate $K$ candidate extractions per field (e.g., $K = 3$ or $K = 5$):
- **Option 1 (Stochastic Temperature Sampling):** Run $1$ greedy pass (`temperature = 0.0`) plus $K - 1$ stochastic passes (`temperature = 0.7`).
- **Option 2 (Prompt / Model Perturbation — Credal Ensemble):** Combine outputs from two distinct prompt templates (e.g., a *literal extraction prompt* vs. a *strict verification/skeptical prompt*) or two different API models if SIXT provides multiple models.
- **Cost-Saving Cascade (Two-Stage):** Run a fast/cheap pass first. For fields already predicted `null` with high certainty or trivially verified, keep as `null`; trigger the full $K$-sample ensemble on documents with non-null candidates or low grounding scores.

### Step 2: Represent — Equivalence Clustering & `probly` Distributions
Raw string equality is too strict for `span` fields (where minor punctuation differences still match under `5_score.py`).
1. **Cluster the $K$ predictions per field** using `5_score.py`'s exact `values_match(a, b, kind)` function (`span_f1 >= 0.8` for spans; `norm_string` for ExtractBench strings; `norm_json` for JSON). Include `None` (`null`) as an explicit cluster!
2. **Map cluster frequencies into `probly.representation`:**
   - **Single ensemble / stochastic samples:** Represent the empirical probability vector over clusters $(c_1, \dots, c_m)$ as a `probly` `CategoricalDistribution` (or `DirichletDistribution` / `Sample` of probability vectors).
   - **Multi-prompt or Multi-model ensemble:** Represent each prompt/model's empirical distribution as a separate member of a `probly` **`CredalSet` / `ProbabilityIntervalsCredalSet`**. The width between upper and lower probabilities directly captures **epistemic model disagreement**.

### Step 3: Quantify & Calibrate — Uncertainty Decomposition + Post-Hoc Calibration
1. **Extract `probly.quantification` metrics per field:**
   - **Total Uncertainty (TU):** Shannon entropy of the predictive distribution (or $1 - \max_c p(c)$).
   - **Epistemic Uncertainty (EU):** Mutual information / credal set width across prompt or model variants.
   - **Majority Cluster Probability $p_{\max}$:** Empirical agreement rate on the winning value (note: if `"null"` is the winning cluster, output `value = null`!).
2. **Combine with Deterministic Reliability Signals (`grounding.py`):**
   - `is_grounded`: Does the winning value actually appear in the PDF/contract text?
   - `pdf_quality`: Is the document digital (`P1`), scanned (`P2/P3`), or `*_corrupted`?
   - `field_type`: `span` vs. `string` vs. `json`.
3. **Post-Hoc Calibration (`probly` calibration methods):**
   - Raw LLM agreement rates (e.g., $2/3 = 0.667$) and self-reported LLM confidences are poorly calibrated.
   - Split `data/unified/dev.jsonl` into `dev_train` ($70\%$) and `dev_cal` ($30\%$).
   - Fit a lightweight calibrator (Temperature Scaling, Platt Scaling / Logistic Regression on `[p_max, TU, EU, is_grounded, is_corrupted]`, or Isotonic Regression) on `dev_train` so predicted confidence $\hat{p} \in [0, 1]$ matches true empirical accuracy.

### Step 4: Decide — Conformal Abstention & Threshold Selection ($\tau^*$)
Use `dev_cal` (never `test_public.jsonl`!) to choose the decision rule (`probly.decision`):
1. **Split Conformal Prediction / Conformal Risk Control:**
   - Define the non-conformity score $s_i = 1 - \hat{p}_i$ on candidate non-null extractions in `dev_cal`.
   - Find the conformal quantile / threshold $\tau^*$ that controls the empirical false-acceptance rate below $\alpha = 0.01$ (corresponding to $\ge 99\%$ precision, where `net_saving_pct` is maximized).
2. **Hard Safety Overrides (`probly.decision` policy):**
   - Force `confidence = 0.0` (abstain) if `is_grounded == False` on digital text.
   - Force `confidence = 0.0` on `*_corrupted` or unreadable documents.
   - Optionally abstain on complex nested `json` arrays unless $K/K$ samples agree identically.
3. **Lock In $\tau^*$:** Set $\tau^*$ as the default threshold in `run_pipeline.py` / `run_hidden.sh` and report that exact number in `Project_1/SUBMISSION.md`.

---

## 3. Scenario B (Optional): If GPU Access Is Provided Tomorrow

If SIXT or TUM provides access to cloud/cluster GPUs at kick-off, keep your `cache/` and `uq_probly.py` interfaces unchanged and upgrade the underlying signal generators:

1. **Local Open-Weight Extractor (vLLM / Hugging Face):**
   - Run a strong open-weight model (e.g., Qwen2.5-72B / Llama-3.3-70B / Qwen2.5-VL for scanned PDFs) locally on GPU with `logprobs=True`.
   - Token-level log-probabilities from the open-weight model can be fed directly into `probly` as first-order distributions alongside multi-sample outputs.
2. **Full `probly` Semantic Entropy with Local NLI (`examples/llm/semantic_entropy.py`):**
   - On GPU, you can run a local DeBERTa NLI model (`microsoft/deberta-large-mnli`) to cluster semantically equivalent contract spans via bidirectional entailment, matching `probly`'s exact LLM semantic entropy pipeline.
3. **Local Vision-Language Parsing for Scanned PDFs:**
   - Use a GPU-hosted VLM or layout-aware OCR model (e.g., Surya / Marker / Qwen-VL) on the $64$ image-only ExtractBench PDFs instead of falling back to abstention.

---

## 4. What to Skip (Lessons from `probly` Benchmarks)

- **Skip Evidential Deep Learning (`EDL`, `PostNet`, `NatPN`):** The `probly` benchmark paper shows that evidential methods substantially underperform even single-model baselines on selective prediction and OoD detection, and require custom neural network training.
- **Keep It Modular:** Even if you only have time for $K=3$ API samples + `probly` `CategoricalDistribution` / `CredalSet` + Logistic/Isotonic calibration + Conformal threshold $\tau^*$ on `dev_cal`, that delivers a complete, theoretically grounded `probly` pipeline in under 3 hours on a standard laptop.