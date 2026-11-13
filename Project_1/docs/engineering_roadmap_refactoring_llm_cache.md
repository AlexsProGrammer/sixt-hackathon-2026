# Engineering Roadmap, Refactoring & LLM Response Cache

<<<<<<< HEAD
> **Corrections 13.11.2026:** checked against `4_extract_example.py`. Items marked ✱ changed. The full, ordered bug list with fixes is in `00_start_here_review_and_fixes.md` §3 (IDs C1–C7). Do C1 and C2 before anything else.

=======
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
> **Purpose:** Guide for refactoring `4_extract_example.py` into a clean, fast, modular pipeline with deterministic disk caching before integrating `probly`.

---

## 1. Six Obvious Issues in `4_extract_example.py` to Fix First

Before adding `probly` uncertainty quantification, fix these six issues in the starter extractor and run **Checkpoint 2** so you can measure the exact improvement from better extraction/grounding vs. `probly` calibration:

<<<<<<< HEAD
1. **Silent 60,000-Character Truncation (**`MAX_CHARS = 60_000`**):**
   - *Problem:* `build_content()` slices `cuad_text(...)[:60_000]` and `pdf_text(...)[:60_000]`, cutting off the ends of ✱ $109$ CUAD contracts in `dev.jsonl` (not 110; the 110 in EDA.md includes one ExtractBench PDF).
=======
1. **Silent 60,000-Character Truncation (`MAX_CHARS = 60_000`):**
   - *Problem:* `build_content()` slices `cuad_text(...)[:60_000]` and `pdf_text(...)[:60_000]`, cutting off the ends of $110$ CUAD contracts in `dev.jsonl`.
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
   - *Fix:* Check the context limit of the model SIXT provides. Either raise `MAX_CHARS` to fit full documents (e.g., $128\text{k}+$ tokens $\approx 400\text{k}$ chars) or split long documents into overlapping chunks ($\approx 45\text{k}$ chars with $3\text{k}$ overlap) and merge extracted `span` values using `" | "` deduplication.
2. **All 41 CUAD Clauses (or 50+ Form Fields) in One Prompt:**
   - *Problem:* Asking an LLM to output 41 legal clauses in a single JSON pass causes attention fatigue, missed clauses, and malformed JSON.
   - *Fix:* Split schemas with $> 12$ fields into thematic batches of $8\text{–}12$ fields per LLM call (e.g., grouping CUAD clauses by topic: Parties/Dates, Termination/Renewal, IP/Licenses, Liability/Governing Law, Exclusivity/Non-Compete).
<<<<<<< HEAD
3. **Broken** `grounded()` **Verification Function:**
   - *Problem:* ✱ Verified: `grounded()` returns `True` when `len(str(value)) > 80` (so long CUAD spans are never checked) and for bool, dict and list values. It is also **too lenient**: `squash()` removes commas on both sides, so `1,234.50` matches `1234.50` in the text, which the scorer counts as wrong. Ungrounded values are only halved (`conf *= 0.5`), which can stay above τ. (The earlier claim that it "penalizes valid matches" was not supported by the code.)
=======
3. **Broken `grounded()` Verification Function:**
   - *Problem:* In `4_extract_example.py`, `grounded()` returns `True` without checking if `len(str(value)) > 80` (skipping almost all CUAD legal spans!), and penalizes valid normalized matches.
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
   - *Fix:*
     - For `span` fields: verify that normalized token recall / substring overlap against the source document text is high (e.g., $\ge 0.85$). If a predicted span does not appear in the contract text, treat it as a hallucination (`confidence = 0.0`).
     - For `string` scalar fields: check if the normalized string (or individual tokens for multi-word strings) appears in extracted PDF text when text is available.
4. **Scanned & Corrupted PDF Handling:**
<<<<<<< HEAD
   - *Problem:* When `pdf_text()` returns `None` ($64$ ExtractBench docs), `build_content()` sends raw base64 `.pdf` bytes (`{"type": "file", ...}`), which many OpenAI-compatible endpoints reject (not tested on our endpoint yet). ✱ `*_corrupted` PDFs yield **no text** (checked: all 7 return nothing), so "garbled text" detection is not the main case. The main case is "no text, route to vision or abstain".
=======
   - *Problem:* When `pdf_text()` returns `None` ($64$ ExtractBench docs), `build_content()` sends raw base64 `.pdf` bytes (`{"type": "file", ...}`), which many OpenAI-compatible endpoints reject. Also, `*_corrupted` PDFs may yield garbled text.
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
   - *Fix:*
     - Detect garbled/corrupted PDF text (e.g., high ratio of non-printable/replacement characters `\ufffd` or unusually low alphabetic ratio) and route to vision or mark high epistemic/input uncertainty.
     - If a vision-capable model is available, render PDF pages to PNG images (e.g., via `pymupdf` / `pdf2image` at $150\text{ DPI}$) and pass `{"type": "image_url", ...}`. If no vision model is available, cleanly abstain (`value: null, confidence: 0.0`) on image-only PDFs rather than crashing or hallucinating.
5. **Sequential Synchronous HTTP Calls:**
   - *Problem:* `4_extract_example.py` processes documents one by one synchronously. Multi-sample UQ ($K = 3\text{–}5$ calls per doc) across hundreds of docs will be too slow sequentially.
   - *Fix:* Use `concurrent.futures.ThreadPoolExecutor(max_workers=8)` (configurable via `--workers`) with exponential backoff retries on HTTP `429` / `5xx` errors.
6. **Prompt Rules for Verbatim Strings, Checkboxes & Absent Fields:**
   - *Fix:* Explicitly instruct the model:
     - Copy numbers, dates, currency symbols, and punctuation **character-for-character** as printed (do not reformat dates or strip commas).
     - Use `"true"` / `"false"` for visible checkboxes, and `null` only when a field/section is absent from the document.
     - Never infer or calculate values not explicitly printed.
<<<<<<< HEAD
     - ✱ Checkbox rule (missing today): `"true"`/`"false"` as strings for boolean fields (gold is string). Number and date rule: follow the schema description (the gold contains floats, ints and `m/d/y` dates).
     - ✱ Also check: `call_llm` hardcodes `temperature: 0`, so multi-sample needs a `temperature` parameter first.

7. **✱ Additional bugs found 13.11.2026** (details and fixes in `00_start_here_review_and_fixes.md` §3):
   - **C1** Windows backslash paths in `pages` break every ExtractBench doc on Linux (written as all-null).
   - **C2** `.env` is never loaded; `--mode auto` falls back to offline rules silently.
   - **C3** `5_score.py` counts docs missing from the predictions as nulls, so partial runs are scored wrongly.
   - **C4** `parse_json` returns `{}` on any error, with no retry and no log.
   - **C5** A missing `confidence` defaults to `0.5`. It should default to `0.0`.
   - **C6** `grounded()` is too lenient for commas and only halves confidence (see item 3).
   - **C7** `cuad_text` lazy-loads a global cache, which is not thread-safe with a pool.
=======
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee

---

## 2. Recommended Modular File Layout (`Project_1/`)

Keep the existing numbered scripts intact (`1_download.sh`, `2_prepare.py`, `3_baseline.py`, `5_score.py`, `test_score.py`) and add clean modules inside `Project_1/`:

```text
Project_1/
├── docs/                        # Team & AI agent documentation
├── results/                     # Saved *_score.json reports (and git-ignored *.jsonl preds)
├── cache/                       # Git-ignored deterministic LLM response cache
├── cache.py                     # Disk cache + token/latency usage tracker
├── grounding.py                 # Normalizer-aware text grounding & PDF corruption checks
├── extractor.py                 # Document loader, schema batcher, parallel OpenAI client
├── uq_probly.py                 # probly representation, quantification, calibration & threshold
├── run_pipeline.py              # CLI entrypoint (--data, --out, --samples, --threshold, ...)
└── run_hidden.sh                # Calls: python3 run_pipeline.py --data "$1" --out "$2"
```

---

## 3. Deterministic Disk Cache (`cache/`) Design

Caching raw LLM responses to disk is critical for a 1-day hackathon:
<<<<<<< HEAD

- Once you run $K$ stochastic extraction calls on `dev.jsonl` and `test_public.jsonl`, your teammate can iterate on `probly` representations, calibration models, and conformal thresholds $\tau^*$ **in** $< 2$ **seconds on CPU with zero additional API calls**.
- It automatically logs exact token usage and latency per document, giving you the exact numbers required for the **"Models and why" (**`Cost and time per item`**)** table in `SUBMISSION.md`.

### Cache Key & Storage Schema

=======
- Once you run $K$ stochastic extraction calls on `dev.jsonl` and `test_public.jsonl`, your teammate can iterate on `probly` representations, calibration models, and conformal thresholds $\tau^*$ **in $< 2$ seconds on CPU with zero additional API calls**.
- It automatically logs exact token usage and latency per document, giving you the exact numbers required for the **"Models and why" (`Cost and time per item`)** table in `SUBMISSION.md`.

### Cache Key & Storage Schema
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
Store one JSON file per unique LLM request inside `Project_1/cache/<two_char_prefix>/<sha256>.json`:

- **Cache Key Inputs (SHA-256 hash of canonical JSON):**
  - `doc_id`
  - `batch_id` (e.g., `"batch_0"` or sorted field names in the prompt)
  - `model` (`LLM_MODEL`)
  - `temperature` (e.g., `0.0` or `0.7`)
  - `sample_idx` (`0, 1, ..., K-1` so multiple stochastic samples at `temperature > 0` get distinct cache entries!)
  - `prompt_hash` (SHA-256 of the system/user prompt text and document content)
- **Stored JSON Payload:**
<<<<<<< HEAD

=======
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
  ```json
  {
    "doc_id": "cuad:...",
    "batch_id": "0",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "sample_idx": 0,
    "latency_sec": 1.42,
    "usage": {"prompt_tokens": 4120, "completion_tokens": 185},
    "raw_reply": "{...}",
    "parsed_json": {...}
  }
  ```

### Thread-Safe Atomic Write Pattern (`cache.py`)
<<<<<<< HEAD

=======
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
Because `ThreadPoolExecutor` writes concurrently from multiple threads, always write to a temporary file in the same directory and `os.replace()` atomically:

```python
import hashlib
import json
import os
import tempfile
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"

def make_cache_key(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def cache_get(key: str, cache_dir: Path = CACHE_DIR) -> dict | None:
    path = cache_dir / key[:2] / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None

def cache_put(key: str, record: dict, cache_dir: Path = CACHE_DIR) -> None:
    subdir = cache_dir / key[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    target = subdir / f"{key}.json"
    fd, tmp_path = tempfile.mkstemp(dir=subdir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
```

### Important Rules for `cache/`
<<<<<<< HEAD

1. **Add** `Project_1/cache/` **to** `.gitignore` so cached responses are never committed to Git.
2. **Back up** `cache/` **to Nextcloud** (or a shared USB/folder) after running `dev.jsonl` so all 3 teammates can run `uq_probly.py` offline on their own laptops.
=======
1. **Add `Project_1/cache/` to `.gitignore`** so cached responses are never committed to Git.
2. **Back up `cache/` to Nextcloud** (or a shared USB/folder) after running `dev.jsonl` so all 3 teammates can run `uq_probly.py` offline on their own laptops.
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
3. **Hidden Test Compatibility:** `run_hidden.sh` must work seamlessly even when `cache/` does not exist (cache miss $\rightarrow$ live API call $\rightarrow$ write to `cache/`).

---

## 4. When to Re-Run & Save `results/`

Run `5_score.py` and save a new `results/<stage>_score.json` whenever you cross one of these boundaries:
<<<<<<< HEAD

1. **After Phase 1 (Unmodified** `4_extract_example.py --mode llm`**):** Establishes the raw single-pass LLM baseline before any engineering fixes.
2. **After Phase 2 (Refactored** `extractor.py` **+** `grounding.py`**, single sample** $K=1$**):** Isolates how much chunking, schema batching, and grounding improve extraction quality on their own.
3. **After Phase 3 (**`uq_probly.py` **with** $K$ **samples + calibration + conformal threshold** $\tau^*$**):** Demonstrates the core hackathon contribution—turning raw LLM outputs into calibrated, selective predictions that achieve $> 99\%$ precision and positive net savings.
=======
1. **After Phase 1 (Unmodified `4_extract_example.py --mode llm`):** Establishes the raw single-pass LLM baseline before any engineering fixes.
2. **After Phase 2 (Refactored `extractor.py` + `grounding.py`, single sample $K=1$):** Isolates how much chunking, schema batching, and grounding improve extraction quality on their own.
3. **After Phase 3 (`uq_probly.py` with $K$ samples + calibration + conformal threshold $\tau^*$):** Demonstrates the core hackathon contribution—turning raw LLM outputs into calibrated, selective predictions that achieve $> 99\%$ precision and positive net savings.
>>>>>>> 7cd2fda5fc53c46381bb9d7e7f468fe269e4c0ee
4. **After any major prompt or model change:** Compare two candidate API models on the exact same `dev_cal` split before picking the winner for `SUBMISSION.md`.