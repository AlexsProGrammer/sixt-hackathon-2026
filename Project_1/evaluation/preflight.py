"""Offline preflight: input, paths, configuration names and the exact planned request count. No API call.

    python -m evaluation.preflight --input results/x_input.jsonl --samples 3 --dry-run

Prints only counts, ids and names of missing settings. No document text, no key values, no gold.
Request count = sum over documents of chunks x batches x K. Retries are reported as a worst-case bound.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from pipeline.requests import chunk_spans, field_batches
from pipeline.transport import MAX_RETRIES

ROOT = Path(__file__).resolve().parent.parent
LLM_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


def _extractor():
    spec = importlib.util.spec_from_file_location("extract4", ROOT / "4_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(input_path: str, samples: int, *, batch_size: int = 10, chunk_chars: int = 45000,
          overlap_chars: int = 3000, check_env: bool = True) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if samples < 1:
        errors.append("--samples must be at least 1")
    try:
        with open(input_path, encoding="utf-8") as f:
            recs = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError) as e:
        return {"ok": False, "errors": [f"cannot read input: {type(e).__name__}"]}

    ids = [r.get("doc_id") for r in recs]
    if len(set(ids)) != len(ids):
        errors.append("duplicate doc_id in input")
    gold_docs = sum(1 for r in recs if any(k.startswith("gold") for k in r))
    if gold_docs:
        errors.append(f"{gold_docs} record(s) contain gold keys; inference input must be gold-free")

    ex = _extractor()
    planned = 0
    per_doc = {"text": 0, "unreadable": 0, "missing_file": 0}
    for r in recs:
        props = r.get("schema", {}).get("properties")
        if not isinstance(props, dict) or not props:
            errors.append(f"{r.get('doc_id')}: schema.properties missing or empty")
            continue
        try:
            text = ex.full_text(r)
        except FileNotFoundError:
            per_doc["missing_file"] += 1
            errors.append(f"{r.get('doc_id')}: document file not found")
            continue
        except (KeyError, ValueError) as e:
            errors.append(f"{r.get('doc_id')}: {type(e).__name__} while resolving document")
            continue
        if not text or not text.strip():
            per_doc["unreadable"] += 1
            continue
        per_doc["text"] += 1
        chunks = len(chunk_spans(len(text), chunk_chars, overlap_chars))
        batches = len(field_batches(list(props), batch_size))
        planned += chunks * batches * samples

    env: dict = {}
    if check_env:
        if os.environ.get("EXTRACT_SKIP_DOTENV") != "1":
            ex.load_env()
        env = {k: bool(os.environ.get(k, "").strip()) for k in LLM_VARS}
        missing = [k for k, ok in env.items() if not ok]
        if missing:
            warnings.append("missing for an LLM run: " + ", ".join(missing))
        elif not os.environ["LLM_BASE_URL"].strip().lower().startswith(("https://", "http://")):
            warnings.append("LLM_BASE_URL has no http(s) scheme")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "n_documents": len(recs),
        "documents": per_doc,
        "samples": samples,
        "batch_size": batch_size,
        "chunk_chars": chunk_chars,
        "overlap_chars": overlap_chars,
        "planned_requests": planned,
        "worst_case_requests_with_retries": planned * (1 + MAX_RETRIES),
        "config_names_present": env,
        "note": "planned_requests excludes cache hits; the real count is in the run manifest.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--chunk-chars", type=int, default=45000)
    ap.add_argument("--overlap-chars", type=int, default=3000)
    ap.add_argument("--dry-run", action="store_true", help="report only; this tool never contacts the API")
    a = ap.parse_args(argv)
    res = check(a.input, a.samples, batch_size=a.batch_size, chunk_chars=a.chunk_chars, overlap_chars=a.overlap_chars)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
