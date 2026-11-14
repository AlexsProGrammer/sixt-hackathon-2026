#!/usr/bin/env python3
"""Extractor CLI: thin wrapper around pipeline.extractor (T11).

    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode llm --samples 3 --uq-method k_entropy
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode llm --on-error abstain --decision submission/decision.json
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --abstain-all      # no API call, no credentials needed
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode offline     # keyword rules, baseline only

Writes OUT.jsonl (doc_id, fields), OUT.diagnostics.jsonl (doc_id, diagnostics), OUT.samples.jsonl (doc_id,
per-sample field observations for offline ablation; contains document text, keep local), OUT.manifest.json.
Records need only schema.properties. The extractor never reads "gold".
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pipeline import extractor as _ext
from pipeline import router
from pipeline.extractor import (
    CODE_FILES,
    CONTRACT_VERSION,
    DECISION_CONTRACT_VERSIONS,
    DEFAULTS,
    LLM_VARS,
    PATTERNS,
    SAMPLING_MODES,
    UQ_METHODS,
    Config,
    Ctx,
    build_messages,
    check_existing,
    code_sha256,
    extract_document,
    llm_config,
    load_config,
    load_decision,
    load_env,
    null_fields,
    probly_version,
    read_jsonl,
    run_file,
    run_fingerprint,
    run_jobs,
    sha256_bytes,
    sha256_obj,
    sidecar_paths,
)

DATA = Path(os.environ["EXTRACT_DATA_DIR"]) if os.environ.get("EXTRACT_DATA_DIR") else Path(__file__).parent / "data"


def page_path(stored: str) -> Path:
    return _ext.page_path(stored, DATA)


def pdf_text(path: Path) -> str | None:
    return _ext.pdf_text(path)


def load_cuad() -> dict:
    return _ext.load_cuad(DATA)


def full_text(rec: dict) -> str | None:
    return _ext.full_text(rec, DATA)


def offline_extract(rec: dict) -> dict:
    return _ext.offline_extract(rec, data_dir=DATA)


def extract_llm(rec: dict, ctx: Ctx) -> dict:
    return _ext.extract_llm(rec, ctx, data_dir=DATA, text_fn=full_text)


def main(argv=None) -> int:
    return _ext.cli_main(argv, data_dir=DATA)


if __name__ == "__main__":
    sys.exit(main())
