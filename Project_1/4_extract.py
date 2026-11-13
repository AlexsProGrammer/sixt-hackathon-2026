#!/usr/bin/env python3
"""Extractor: full text -> chunk/batch jobs -> HTTP (cache, retries) -> sample merge -> probly aggregation -> prediction.

    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode llm --on-error abstain --decision submission/decision.json
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --abstain-all      # no API call, no credentials needed
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode offline     # keyword rules, baseline only

Writes OUT.jsonl (doc_id, fields), OUT.diagnostics.jsonl (doc_id, diagnostics) and OUT.manifest.json.
Records need only schema.properties. The extractor never reads "gold".
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path

from pipeline.merge import merge_sample
from pipeline.requests import PROMPT_VERSION, build_jobs, build_prompt
from pipeline.transport import ReplyCache, RunState, execute_job

HERE = Path(__file__).parent
# EXTRACT_DATA_DIR overrides the data folder (used by the tests with synthetic data). Normal runs use data/.
DATA = Path(os.environ["EXTRACT_DATA_DIR"]) if os.environ.get("EXTRACT_DATA_DIR") else HERE / "data"
LLM_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
CONTRACT_VERSION = 1
DEFAULTS = {"workers": 1, "samples": 1, "temperature": 0.7, "chunk_chars": 45000,
            "overlap_chars": 3000, "batch_size": 10}
PATTERNS = {
    "amount": r"-?\d[\d.,]*\d|\d",
    "date": r"\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]{2,8}\.? \d{4}",
    "id": r"[A-Za-z0-9][A-Za-z0-9\-/]{3,}",
}


# ---------------------------------------------------------------- configuration

def load_env(path: Path = HERE / ".env") -> list[str]:
    """Load KEY=VALUE lines from .env. Variables already set to a non-empty value are never overwritten.
    Returns the names that were loaded (never the values)."""
    loaded = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()  # also handles CRLF
    except FileNotFoundError:
        return loaded
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if sep and key and val and not os.environ.get(key, "").strip():
            os.environ[key] = val
            loaded.append(key)
    return loaded


def llm_config() -> dict:
    """The three LLM settings. Raises RuntimeError naming the missing variables, never their values."""
    cfg = {k: os.environ.get(k, "").strip() for k in LLM_VARS}
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise RuntimeError("LLM config missing: " + ", ".join(missing)
                           + " (set in the environment or in Project_1/.env)")
    if not cfg["LLM_BASE_URL"].lower().startswith(("https://", "http://")):
        raise RuntimeError("LLM_BASE_URL has no http:// or https:// scheme (fix the value in Project_1/.env)")
    return cfg


# ---------------------------------------------------------------- documents

def page_path(stored: str) -> Path:
    """Map a record's page path to a local file. Records store Windows separators; normalise them
    so one record resolves the same way on Windows, Linux and macOS."""
    parts = [p for p in stored.replace("\\", "/").split("/") if p and p != "."]
    if not parts or ".." in parts:
        raise ValueError(f"unsafe page path in record: {stored!r}")
    path = DATA.joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"document not found: data/{'/'.join(parts)}")
    return path


def pdf_text(path: Path) -> str | None:
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    try:
        from pypdf import PdfReader
        text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
        return text if text.strip() else None
    except ImportError:
        return None
    except Exception:  # broken or image-only PDF: treated as "no text layer" -> unreadable, not a crash
        return None


_cuad: dict | None = None


def load_cuad() -> dict:
    """CUAD texts, loaded once. Call before any worker pool starts."""
    global _cuad
    if _cuad is None:
        raw = json.loads((DATA / "raw/cuad/CUADv1.json").read_text(encoding="utf-8"))["data"]
        _cuad = {d["title"]: "\n".join(p["context"] for p in d["paragraphs"]) for d in raw}
    return _cuad


def full_text(rec: dict) -> str | None:
    """Complete document text, never truncated. None means no text layer (scan or unreadable PDF)."""
    if rec["source_dataset"] == "cuad":
        return load_cuad()[rec["doc_id"].split(":", 1)[1]]
    page = page_path(rec["pages"][0])
    if page.suffix.lower() != ".pdf":
        return None
    return pdf_text(page)


def null_fields(schema: dict) -> dict:
    return {name: {"value": None, "confidence": 0.0} for name in schema.get("properties", {})}


# ---------------------------------------------------------------- offline baseline (unchanged rules)

def offline_extract(rec: dict) -> dict:
    text = full_text(rec)
    fields = {}
    for name, spec in rec["schema"]["properties"].items():
        kind = spec.get("x-normalizer")
        words = [w for w in re.split(r"[\W_]+", name.lower()) if len(w) > 2]
        value, conf = None, 0.0
        if text and words:
            if kind == "span":
                for sent in re.split(r"(?<=[.;])\s+", text):
                    if all(w in sent.lower() for w in words) and 20 < len(sent) < 600:
                        value, conf = " ".join(sent.split()), 0.3
                        break
            elif kind in PATTERNS:
                for line in text.splitlines():
                    low = line.lower()
                    if all(w in low for w in words):
                        tail = line[low.rindex(words[-1]) + len(words[-1]):]
                        m = re.search(PATTERNS[kind], tail)
                        if m:
                            value, conf = m.group(0).strip(), 0.5
                            break
        fields[name] = {"value": value, "confidence": conf}
    return {"doc_id": rec["doc_id"], "fields": fields}


# ---------------------------------------------------------------- LLM pipeline

class Ctx:
    """Everything one run needs. Built once in main()."""

    def __init__(self, cfg, cache, state, pipeline, on_error):
        self.cfg = cfg
        self.cache = cache
        self.state = state
        self.pipeline = pipeline
        self.on_error = on_error


def build_messages(job: dict) -> list[dict]:
    prompt = build_prompt(job["schema"], job["text"], chunk_no=job["chunk_id"] + 1, n_chunks=job["n_chunks"])
    return [{"role": "user", "content": prompt}]


def run_jobs(jobs: list[dict], ctx: Ctx) -> list[dict]:
    p = ctx.pipeline
    fn = partial(execute_job, cfg=ctx.cfg, cache=ctx.cache, state=ctx.state, temperature=p["temperature"],
                 prompt_version=PROMPT_VERSION, build_messages=build_messages)
    results: list[dict | None] = [None] * len(jobs)
    window = max(1, 2 * p["workers"])  # bounded submission: never queue the whole document at once
    with ThreadPoolExecutor(max_workers=p["workers"]) as pool:
        for lo in range(0, len(jobs), window):
            idxs = list(range(lo, min(lo + window, len(jobs))))
            futures = {pool.submit(fn, jobs[i]): i for i in idxs}
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()
    return results  # type: ignore[return-value]


def extract_llm(rec: dict, ctx: Ctx) -> dict:
    """Returns {"fields", "diagnostics", "job_failures"} for one document. Never raises for job errors."""
    schema = rec["schema"]
    text = full_text(rec)
    if text is None or not text.strip():
        per_field = {n: {"agreement": 0.0, "entropy": None, "n_clusters": 0, "grounded": False,
                         "reason": "unreadable"} for n in schema.get("properties", {})}
        return {"fields": null_fields(schema),
                "diagnostics": {"n_samples": 0, "complete": False, "method": "unreadable_document",
                                "per_field": per_field},
                "job_failures": []}
    from uncertainty.uq_probly import aggregate_samples  # imported here: all-abstain and offline need no probly
    p = ctx.pipeline
    jobs = build_jobs(text, schema, chunk_chars=p["chunk_chars"], overlap_chars=p["overlap_chars"],
                      batch_size=p["batch_size"], samples=p["samples"])
    results = run_jobs(jobs, ctx) if jobs else []
    samples = [merge_sample(results, schema, s) for s in range(p["samples"])]
    agg = aggregate_samples(samples, schema, text)
    diag = dict(agg["diagnostics"])
    failures = sorted({r["error"] for r in results if not r["ok"]})
    diag["job_failures"] = failures
    return {"fields": agg["fields"], "diagnostics": diag, "job_failures": failures}


# ---------------------------------------------------------------- files and resume

def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                raise SystemExit(f"ERROR: {path} line {n} is not valid JSON (damaged output). Use a fresh --out.")
    return rows


def sidecar_paths(out: Path) -> tuple[Path, Path]:
    return out.with_name(out.stem + ".diagnostics.jsonl"), out.with_name(out.stem + ".manifest.json")


def check_existing(out: Path, diag: Path, manifest: Path, pipeline: dict, resume: bool) -> set[str]:
    """Refuse to mix runs. Returns doc_ids already written by an identical pipeline (resume only)."""
    existing = out.exists() and out.stat().st_size > 0
    if not existing:
        if diag.exists() or manifest.exists():
            raise SystemExit(f"ERROR: stale {diag.name}/{manifest.name} next to a missing {out.name}. Use a fresh --out.")
        return set()
    if not resume:
        raise SystemExit(f"ERROR: {out} already exists. Use --resume to continue an identical run, or a fresh --out.")
    if not manifest.exists() or not diag.exists():
        raise SystemExit("ERROR: cannot resume: manifest or diagnostics file is missing.")
    man = json.loads(manifest.read_text(encoding="utf-8"))
    if man.get("pipeline") != pipeline:
        raise SystemExit("ERROR: cannot resume: pipeline configuration differs from the existing run.")
    rows = read_jsonl(out)
    ids = [r.get("doc_id") for r in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit("ERROR: cannot resume: duplicate doc_id in existing output.")
    return set(ids)


# ---------------------------------------------------------------- decision file

def load_decision(path: str) -> dict:
    try:
        dec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"ERROR: cannot read decision file {path}: {type(e).__name__}")
    if not isinstance(dec, dict) or dec.get("contract_version") != CONTRACT_VERSION:
        raise SystemExit(f"ERROR: decision file {path} has an unknown contract_version.")
    if not isinstance(dec.get("abstain_all"), bool):
        raise SystemExit(f"ERROR: decision file {path} lacks a boolean abstain_all.")
    if not dec["abstain_all"] and not isinstance(dec.get("pipeline"), dict):
        raise SystemExit(f"ERROR: decision file {path} lacks the pipeline block.")
    return dec


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="e.g. data/unified/dev.jsonl (no gold needed)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, help="only the first N documents (LLM calls cost money)")
    ap.add_argument("--mode", choices=["auto", "llm", "offline"], default=None,
                    help="llm: fail loudly if config is missing or an API call fails. "
                         "auto (default): LLM if config is complete, else offline rules with a warning.")
    ap.add_argument("--workers", type=int, default=None, help="parallel jobs per document (default 1)")
    ap.add_argument("--samples", type=int, default=None, help="K samples (default 1)")
    ap.add_argument("--temperature", type=float, default=None, help="temperature of samples 1..K-1 (default 0.7)")
    ap.add_argument("--chunk-chars", type=int, default=None, help="default 45000")
    ap.add_argument("--overlap-chars", type=int, default=None, help="default 3000")
    ap.add_argument("--batch-size", type=int, default=None, help="fields per request, default 10")
    ap.add_argument("--on-error", choices=["fail", "abstain"], default="fail",
                    help="fail: documents with failed jobs are not written, exit 1. abstain: write null/0 plus diagnosis.")
    ap.add_argument("--abstain-all", action="store_true", help="write null/0 for every document, no API call")
    ap.add_argument("--decision", help="submission/decision.json: loads the frozen pipeline configuration")
    ap.add_argument("--resume", action="store_true", help="continue an existing run with an identical pipeline")
    ap.add_argument("--cache-dir", default=str(HERE / "cache"))
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)

    if os.environ.get("EXTRACT_SKIP_DOTENV") != "1":  # tests set this so they never load the real .env
        loaded = load_env()
        if loaded:
            print(f"loaded from .env (names only): {', '.join(loaded)}", file=sys.stderr)

    # ----- decide the mode and the pipeline configuration
    cli_pipeline = {k: getattr(a, k) for k in DEFAULTS}
    dec = load_decision(a.decision) if a.decision else None
    if a.abstain_all and a.mode == "llm":
        raise SystemExit("ERROR: --abstain-all contradicts --mode llm.")
    if dec is not None and dec["abstain_all"]:
        mode = "abstain_all"
        if a.mode == "llm":
            print("NOTE: decision file is all-abstain; --mode llm is accepted, no API request is made.", file=sys.stderr)
    elif a.abstain_all:
        mode = "abstain_all"
    elif dec is not None:
        mode = "llm"
        conflicts = [k for k in DEFAULTS if cli_pipeline[k] is not None and cli_pipeline[k] != dec["pipeline"].get(k)]
        if conflicts or (a.mode not in (None, "llm")):
            raise SystemExit(f"ERROR: options contradict the decision file: {', '.join(conflicts) or '--mode'}.")
    else:
        mode = a.mode or "auto"

    if dec is not None and not dec["abstain_all"]:
        base = dec["pipeline"]
        pipeline_values = {k: base.get(k, DEFAULTS[k]) for k in DEFAULTS}
    else:
        pipeline_values = {k: (cli_pipeline[k] if cli_pipeline[k] is not None else DEFAULTS[k]) for k in DEFAULTS}

    cfg = None
    if mode in ("llm", "auto"):
        try:
            cfg = llm_config()
            mode = "llm"
        except RuntimeError as e:
            if mode == "llm":
                raise SystemExit(f"ERROR: {e}. Nothing was written.")
            print(f"WARNING: {e}. --mode auto is using OFFLINE rules (use --mode llm to fail instead).", file=sys.stderr)
            mode = "offline"

    if dec is not None and mode == "llm" and dec["pipeline"].get("prompt_version") not in (None, PROMPT_VERSION):
        raise SystemExit("ERROR: decision file was made with another prompt_version.")
    if dec is not None and mode == "llm" and cfg and dec["pipeline"].get("model") not in (None, cfg["LLM_MODEL"]):
        raise SystemExit("ERROR: decision file was made with another model than LLM_MODEL.")
    if pipeline_values["overlap_chars"] >= pipeline_values["chunk_chars"]:
        raise SystemExit("ERROR: overlap_chars must be smaller than chunk_chars.")
    pipeline = {**pipeline_values, "model": cfg["LLM_MODEL"] if cfg else None,
                "prompt_version": PROMPT_VERSION if mode == "llm" else None}
    print(f"mode: {mode}", file=sys.stderr)

    # ----- input and output files
    recs = [json.loads(line) for line in open(a.data, encoding="utf-8") if line.strip()]
    recs = recs[: a.limit] if a.limit else recs
    out = Path(a.out)
    diag_path, man_path = sidecar_paths(out)
    done = check_existing(out, diag_path, man_path, pipeline, a.resume)
    out.parent.mkdir(parents=True, exist_ok=True)

    state = RunState()
    cache = ReplyCache(None if a.no_cache else Path(a.cache_dir), state)
    ctx = Ctx(cfg, cache, state, pipeline, a.on_error)
    if mode == "llm" and any(r["source_dataset"] == "cuad" for r in recs):
        load_cuad()  # once, before any worker pool starts

    run_id = uuid.uuid4().hex[:12]
    started = time.time()
    failed: list[str] = []      # not written (fail mode): rerun with --resume to retry
    degraded: list[str] = []    # written as null/0 after job errors (abstain mode): NOT a measured prediction
    skipped = 0
    with open(out, "a", encoding="utf-8") as fout, open(diag_path, "a", encoding="utf-8") as fdiag:
        for i, rec in enumerate(recs):
            if rec["doc_id"] in done:
                skipped += 1
                continue
            try:
                if mode == "abstain_all":
                    res = {"fields": null_fields(rec["schema"]),
                           "diagnostics": {"n_samples": 0, "complete": False, "method": "abstain_all",
                                           "per_field": {n: {"agreement": 0.0, "entropy": None, "n_clusters": 0,
                                                             "grounded": False, "reason": "abstain_all"}
                                                         for n in rec["schema"]["properties"]}},
                           "job_failures": []}
                elif mode == "offline":
                    row = offline_extract(rec)
                    res = {"fields": row["fields"], "diagnostics": None, "job_failures": []}
                else:
                    res = extract_llm(rec, ctx)
            except Exception as e:  # document-level error: reported, never silently written as a success
                print(f"[{i}] {rec['doc_id']}: FAILED {type(e).__name__}", file=sys.stderr)
                if mode == "llm" and a.on_error == "abstain":
                    res = {"fields": null_fields(rec["schema"]),
                           "diagnostics": {"n_samples": 0, "complete": False, "method": "document_error",
                                           "per_field": {}, "job_failures": [type(e).__name__]},
                           "job_failures": [type(e).__name__]}
                    fout.write(json.dumps({"doc_id": rec["doc_id"], "fields": res["fields"]}, ensure_ascii=False) + "\n")
                    fdiag.write(json.dumps({"doc_id": rec["doc_id"], "diagnostics": res["diagnostics"]}, ensure_ascii=False) + "\n")
                    degraded.append(rec["doc_id"])
                else:
                    failed.append(rec["doc_id"])
                continue

            if res["job_failures"] and mode == "llm" and a.on_error == "fail":
                print(f"[{i}] {rec['doc_id']}: FAILED jobs {', '.join(res['job_failures'])} (not written)", file=sys.stderr)
                failed.append(rec["doc_id"])
                continue
            if res["job_failures"]:
                print(f"[{i}] {rec['doc_id']}: abstained after job errors {', '.join(res['job_failures'])}", file=sys.stderr)
                degraded.append(rec["doc_id"])
            fout.write(json.dumps({"doc_id": rec["doc_id"], "fields": res["fields"]}, ensure_ascii=False) + "\n")
            if res["diagnostics"] is not None:
                fdiag.write(json.dumps({"doc_id": rec["doc_id"], "diagnostics": res["diagnostics"]}, ensure_ascii=False) + "\n")
            fout.flush()
            fdiag.flush()
            print(f"[{i}] {rec['doc_id']}", file=sys.stderr)

    n_written = len(read_jsonl(out)) if out.exists() else 0
    manifest = {
        "contract_version": CONTRACT_VERSION, "run_id": run_id, "mode": mode,
        "pipeline": pipeline, "n_requested": len(recs), "n_written": n_written,
        "n_skipped_resumed": skipped, "n_failed": len(failed), "failed_doc_ids": failed[:50],
        "n_abstained_after_errors": len(degraded), "abstained_after_error_doc_ids": degraded[:50],
        "requests": state.requests, "cache_hits": state.cache_hits,
        "elapsed_seconds": round(time.time() - started, 2), "stopped_429": state.stop.is_set(),
        "on_error": a.on_error, "warnings": state.warnings[:20],
    }
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"done: requested={len(recs)} written={n_written} failed={len(failed)} requests={state.requests} "
          f"cache_hits={state.cache_hits} run_id={run_id}", file=sys.stderr)
    if failed and a.on_error == "fail":
        shown = ", ".join(failed[:5]) + (" ..." if len(failed) > 5 else "")
        print(f"ERROR: {len(failed)} document(s) not written. Rerun with --resume to retry them: {shown}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
