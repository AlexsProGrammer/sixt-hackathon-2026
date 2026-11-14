#!/usr/bin/env python3
"""Extractor: full text -> chunk/batch jobs -> HTTP (cache, retries) -> sample merge (contract v2)
-> probly aggregation -> decision rule -> prediction.

    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode llm --samples 3 --uq-method k_entropy
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode llm --on-error abstain --decision submission/decision.json
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --abstain-all      # no API call, no credentials needed
    python 4_extract.py --data INPUT.jsonl --out OUT.jsonl --mode offline     # keyword rules, baseline only

Writes OUT.jsonl (doc_id, fields), OUT.diagnostics.jsonl (doc_id, diagnostics), OUT.samples.jsonl (doc_id,
per-sample field observations for offline ablation; contains document text, keep local), OUT.manifest.json.
Records need only schema.properties. The extractor never reads "gold".
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import math
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
from urllib.parse import urlparse

from pipeline import cuad_pipeline, eb_pipeline, router
from pipeline.merge import merge_sample_v2
from pipeline.requests import PROMPT_VERSION, build_jobs, build_prompt
from pipeline.transport import ReplyCache, RunState, execute_job

HERE = Path(__file__).parent
# EXTRACT_DATA_DIR overrides the data folder (used by the tests with synthetic data). Normal runs use data/.
DATA = Path(os.environ["EXTRACT_DATA_DIR"]) if os.environ.get("EXTRACT_DATA_DIR") else HERE / "data"
LLM_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
CONTRACT_VERSION = 1          # run manifest and decision file
UQ_METHODS = ("k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy")
SAMPLING_MODES = ("mixed", "identical")
DEFAULTS = {"workers": 1, "samples": 1, "temperature": 0.7, "chunk_chars": 45000,
            "overlap_chars": 3000, "batch_size": 10, "uq_method": None, "sampling": "mixed"}
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
    """The default LLM settings plus optional per-role (A, B, C, OCR) URL/key overrides.
    Raises RuntimeError naming the missing variables, never their values."""
    cfg = {k: (os.environ.get(k, "").strip() or os.environ.get(f"{k}_DEFAULT", "").strip()) for k in LLM_VARS}
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise RuntimeError("LLM config missing: " + ", ".join(missing)
                           + " (set in the environment or in Project_1/.env)")
    if not cfg["LLM_BASE_URL"].lower().startswith(("https://", "http://")):
        raise RuntimeError("LLM_BASE_URL has no http:// or https:// scheme (fix the value in Project_1/.env)")
    endpoints = {}
    for role in ("A", "B", "C", "OCR"):
        m = os.environ.get(f"LLM_MODEL_{role}", "").strip()
        u = os.environ.get(f"LLM_BASE_URL_{role}", "").strip()
        k = os.environ.get(f"LLM_API_KEY_{role}", "").strip()
        if u and not u.lower().startswith(("https://", "http://")):
            raise RuntimeError(f"LLM_BASE_URL_{role} has no http:// or https:// scheme (fix the value in Project_1/.env)")
        if m and (u or k):
            endpoints[m] = {"LLM_BASE_URL": u or cfg["LLM_BASE_URL"], "LLM_API_KEY": k or cfg["LLM_API_KEY"]}
    if endpoints:
        cfg["endpoints"] = endpoints
    return cfg


def probly_version() -> str:
    try:
        return importlib_metadata.version("probly")
    except importlib_metadata.PackageNotFoundError:
        return "not installed"


# ---------------------------------------------------------------- documents

def page_path(stored: str) -> Path:
    """Map a record's page path to a local file (implementation: pipeline.router). Uses this module's DATA."""
    return router.page_path(stored, DATA)


def pdf_text(path: Path) -> str | None:
    """Text of all pages (pdftotext, pypdf fallback). Implementation: pipeline.router."""
    return router.pdf_text(path)


def load_cuad() -> dict:
    """CUAD texts, loaded once. Call before any worker pool starts."""
    return router.load_cuad(DATA)


def full_text(rec: dict) -> str | None:
    """Complete document text, never truncated. None means no text layer (scan or unreadable PDF)."""
    return router.full_text(rec, DATA)


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


# ---------------------------------------------------------------- LLM pipeline (contract v2)

class Ctx:
    """Everything one run needs. Built once in main()."""

    def __init__(self, cfg, cache, state, pipeline, on_error, eb=None, cuad=None):
        self.cfg = cfg
        self.cache = cache
        self.state = state
        self.pipeline = pipeline
        self.on_error = on_error
        self.eb = eb          # None = text pipeline only; else the resolved ExtractBench vision config (T06)
        self.cuad = cuad      # None = text pipeline only; else the resolved CUAD long-context config (T07)


def build_messages(job: dict) -> list[dict]:
    prompt = build_prompt(job["schema"], job["text"], chunk_no=job["chunk_id"] + 1, n_chunks=job["n_chunks"])
    return [{"role": "user", "content": prompt}]


def run_jobs(jobs: list[dict], ctx: Ctx) -> list[dict]:
    p = ctx.pipeline
    fn = partial(execute_job, cfg=ctx.cfg, cache=ctx.cache, state=ctx.state, temperature=p["temperature"],
                 prompt_version=PROMPT_VERSION, build_messages=build_messages, sampling=p["sampling"])
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
    """One document. Returns {"fields", "diagnostics", "job_failures", "samples"}. Job errors never raise."""
    from uncertainty.decision import make_prediction  # imported here: all-abstain and offline need no probly
    from uncertainty.uq_probly import aggregate_v2

    schema = rec["schema"]
    text = full_text(rec)
    routed = router.route(rec, DATA, text=text)
    if ctx.eb and routed["route"] in eb_pipeline.VISION_ROUTES and eb_pipeline.views_for_route(routed["route"], ctx.eb["views"]):
        return eb_pipeline.extract_document(rec, routed, ctx, data_dir=DATA)   # ExtractBench on the native PDF (T06)
    if ctx.cuad and routed["route"] == "cuad" and ctx.cuad.get("views"):
        return cuad_pipeline.extract_document(rec, routed, ctx)               # CUAD long-context pipeline (T07)
    route_info = {"route": routed["route"], "text_source": routed["text_source"], "quality": routed["quality"],
                  "quality_features": routed["quality_features"]}
    if text is None or not text.strip():
        per_field = {n: {"eligible": False, "reason": "unreadable", "agreement": None, "entropy_nats": None,
                         "n_clusters": 0, "grounded": False} for n in schema.get("properties", {})}
        return {"fields": null_fields(schema),
                "diagnostics": {"n_samples": 0, "expected_k": ctx.pipeline["samples"], "complete": False,
                                "method": "unreadable_document", "uq_called": False, "per_field": per_field,
                                **route_info},
                "job_failures": [], "samples": []}
    p = ctx.pipeline
    jobs = build_jobs(text, schema, chunk_chars=p["chunk_chars"], overlap_chars=p["overlap_chars"],
                      batch_size=p["batch_size"], samples=p["samples"])
    results = run_jobs(jobs, ctx) if jobs else []
    samples = [merge_sample_v2(results, schema, s, planned_jobs=jobs) for s in range(p["samples"])]
    if p.get("aggregator") == "multiview":
        from uncertainty.multiview import aggregate_views
        view_list = [
            {"view_id": f"sample-{s['sample_idx']}", "model": ctx.cfg["LLM_MODEL"],
             "input_kind": "text", "fields": s["fields"], "complete": s["complete"]}
            for s in samples
        ]
        agg = aggregate_views(view_list, schema, {"text": text, "ocr": None})
    else:
        agg = aggregate_v2(samples, schema, text, expected_k=p["samples"])
    fields = make_prediction(agg, schema, method=p["uq_method"])
    failures = sorted({r["error"] for r in results if not r["ok"]})
    diag = dict(agg["diagnostics"])
    diag.update({"complete": all(s["complete"] for s in samples), "uq_method": p["uq_method"],
                 "uq_called": True, "probly_version": probly_version(), "job_failures": failures,
                 **route_info})
    return {"fields": fields, "diagnostics": diag, "job_failures": failures, "samples": samples}


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


def sidecar_paths(out: Path, run_dir: Path | None = None) -> tuple[Path, Path, Path]:
    """diagnostics, manifest, samples. In a run folder they have fixed names next to preds.jsonl."""
    if run_dir is not None:
        return run_dir / "diagnostics.jsonl", run_dir / "manifest.json", run_dir / "samples.jsonl"
    return (out.with_name(out.stem + ".diagnostics.jsonl"), out.with_name(out.stem + ".manifest.json"),
            out.with_name(out.stem + ".samples.jsonl"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_obj(obj: object) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8"))


CODE_FILES = ("4_extract.py", "pipeline/router.py", "pipeline/requests.py", "pipeline/transport.py", "pipeline/merge.py",
              "pipeline/cuad_pipeline.py", "pipeline/eb_pipeline.py", "pipeline/prompts_eb.py", "pipeline/messages.py", "pipeline/models.py",
              "uncertainty/single_view.py", "uncertainty/contracts.py", "uncertainty/grounding.py", "uncertainty/policy.py",
              "uncertainty/schema_check.py",
              "uncertainty/uq_probly.py", "uncertainty/decision.py")


def code_sha256() -> str:
    """Hash of the modules that decide prediction values. Changes here make earlier results non-comparable."""
    parts = []
    for rel in CODE_FILES:
        p = HERE / rel
        parts.append(rel + "\0" + (sha256_bytes(p.read_bytes()) if p.exists() else "missing"))
    return sha256_bytes("\n".join(parts).encode("utf-8"))


def run_fingerprint(input_path: Path, pipeline: dict, cfg: dict | None) -> dict:
    """Provenance of a run. Contains no credentials: the endpoint is recorded as host name only."""
    fp = {"input_sha256": sha256_bytes(input_path.read_bytes()), "pipeline_sha256": sha256_obj(pipeline),
          "endpoint_host": urlparse(cfg["LLM_BASE_URL"]).netloc if cfg else None,
          "code_sha256": code_sha256(), "prompt_version": PROMPT_VERSION}
    fp["fingerprint_sha256"] = sha256_obj(fp)
    return fp


def check_existing(out: Path, diag: Path, manifest: Path, samples: Path, pipeline: dict, resume: bool,
                   fingerprint: dict) -> set[str]:
    """Refuse to mix runs. Returns doc_ids already written by an identical run (resume only)."""
    existing = out.exists() and out.stat().st_size > 0
    if not existing:
        if diag.exists() or manifest.exists() or samples.exists():
            raise SystemExit(f"ERROR: stale sidecar files next to a missing {out.name}. Use a fresh --out.")
        return set()
    if not resume:
        raise SystemExit(f"ERROR: {out} already exists. Use --resume to continue an identical run, or a fresh --out.")
    if not manifest.exists() or not diag.exists():
        raise SystemExit("ERROR: cannot resume: manifest or diagnostics file is missing.")
    man = json.loads(manifest.read_text(encoding="utf-8"))
    if man.get("pipeline") != pipeline:
        raise SystemExit("ERROR: cannot resume: pipeline configuration differs from the existing run.")
    if man.get("fingerprint", {}).get("fingerprint_sha256") != fingerprint["fingerprint_sha256"]:
        raise SystemExit("ERROR: cannot resume: input file, code version or endpoint differs from the existing run.")
    rows = read_jsonl(out)
    ids = [r.get("doc_id") for r in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit("ERROR: cannot resume: duplicate doc_id in existing output.")
    return set(ids)


# ---------------------------------------------------------------- decision file

def load_decision(path: str) -> dict:
    """Strict: version, boolean abstain_all, finite threshold in [0, 1], complete pipeline block for an active
    decision, and pipeline_sha256 (when present) must match the pipeline block. No silent defaults."""
    try:
        dec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"ERROR: cannot read decision file {path}: {type(e).__name__}")
    if not isinstance(dec, dict) or dec.get("contract_version") != CONTRACT_VERSION:
        raise SystemExit(f"ERROR: decision file {path} has an unknown contract_version.")
    if not isinstance(dec.get("abstain_all"), bool):
        raise SystemExit(f"ERROR: decision file {path} lacks a boolean abstain_all.")
    thr = dec.get("threshold")
    if not isinstance(thr, (int, float)) or isinstance(thr, bool) or not math.isfinite(float(thr)) \
            or not 0.0 <= float(thr) <= 1.0:
        raise SystemExit(f"ERROR: decision file {path} needs a finite numeric threshold in [0, 1].")
    if not dec["abstain_all"]:
        pipe = dec.get("pipeline")
        if not isinstance(pipe, dict):
            raise SystemExit(f"ERROR: decision file {path} lacks the pipeline block.")
        missing = [k for k in DEFAULTS if k not in pipe]
        if missing:
            raise SystemExit(f"ERROR: decision file pipeline block lacks: {', '.join(missing)}.")
        if "pipeline_sha256" in dec and dec["pipeline_sha256"] != sha256_obj(pipe):
            raise SystemExit("ERROR: decision file pipeline_sha256 does not match its pipeline block.")
    return dec


# ---------------------------------------------------------------- run registry (only with --run-dir)

def _register_run(run_dir: Path, a, recs: list[dict], mode: str, pipeline: dict, dec: dict | None):
    """Create/refresh the run folder: run.json, gold-free input copy, gold subset. Returns the registry module."""
    from evaluation import registry
    splits = sorted({str(r.get("split")) for r in recs if r.get("split")})
    registry.init_run_dir(run_dir, name=a.run_name, split=splits[0] if len(splits) == 1 else "mixed" if splits else "unknown")
    input_path = Path(a.data)
    registry.write_inputs(run_dir, recs, input_ref=str(input_path) if not a.limit else None,
                          input_sha256=sha256_bytes(input_path.read_bytes()) if not a.limit else None)
    models = [pipeline["model"]] if pipeline.get("model") else []
    if pipeline.get("eb"):
        models += [m for m in (pipeline["eb"]["model_a"], pipeline["eb"]["model_b"]) if m not in models]
    extra = {"status": "running", "mode": mode, "models": models,
             "n_requested": len(recs)}
    if a.run_name:
        extra["name"] = a.run_name
    if dec is not None:
        extra["decision_sha256"] = sha256_bytes(Path(a.decision).read_bytes())
    registry.update_run(run_dir, **extra)
    return registry


def _finish_registered_run(registry, run_dir: Path, a, dec: dict | None, run_complete: bool, n_written: int,
                           n_requested: int) -> None:
    """Close the run folder: status, score (when gold exists) and index row. Never changes the exit code."""
    status = "complete" if run_complete else ("failed" if n_written == 0 else "incomplete")
    try:
        registry.finish_run(run_dir, status, n_written=n_written)
        if (run_dir / "gold.jsonl").exists() and n_written:
            threshold = float(dec["threshold"]) if dec is not None else registry.DEFAULT_THRESHOLD
            s = registry.score_run(run_dir, threshold)
            print(f"scored {s['n_docs']} docs at threshold {threshold}: accepted={s['accepted']} wrong={s['wrong']} "
                  f"hallucinated={s['hallucinated']} net_saving_e100={s['net_saving_pct_e100']:.2%}", file=sys.stderr)
        registry.append_index(run_dir)
        print(f"run folder: {run_dir}", file=sys.stderr)
    except Exception as e:  # registry problems must not hide a finished extraction
        print(f"WARNING: run registry update failed: {type(e).__name__}: {e}", file=sys.stderr)


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="e.g. data/unified/dev.jsonl (no gold needed)")
    ap.add_argument("--out", help="predictions file; with --run-dir defaults to RUN_DIR/preds.jsonl")
    ap.add_argument("--run-dir", help="register this run in a self-contained folder (results/runs/<run_id>/): "
                                      "preds, diagnostics, samples, manifest, input/gold copy, score, index row")
    ap.add_argument("--run-name", help="display name of the run (default: the run folder name)")
    ap.add_argument("--limit", type=int, help="only the first N documents (LLM calls cost money)")
    ap.add_argument("--mode", choices=["auto", "llm", "offline"], default=None,
                    help="llm: fail loudly if config is missing or an API call fails. "
                         "auto (default): LLM if config is complete, else offline rules with a warning.")
    ap.add_argument("--workers", type=int, default=None, help="parallel jobs per document (default 1)")
    ap.add_argument("--samples", type=int, default=None, help="K samples (default 1)")
    ap.add_argument("--temperature", type=float, default=None, help="temperature of sampled answers (default 0.7)")
    ap.add_argument("--sampling", choices=SAMPLING_MODES, default=None,
                    help="mixed (default): sample 0 at temperature 0, others at --temperature. "
                         "identical: every sample at --temperature.")
    ap.add_argument("--uq-method", choices=UQ_METHODS, default=None,
                    help="decision rule: k1_grounded (K=1, default for K=1), k_agreement_only (K>1), k_agreement_conf (K>1, default for K>1), k_entropy (K>1, probly)")
    ap.add_argument("--eb-views", default=None, metavar="VIEWS",
                    help="ExtractBench vision pipeline (T06) on the native PDF instead of the text layer. "
                         "'A' = view A only, 'full' = the per-route table (A-pdf, B-pdf, A-text), or a list such as "
                         "A-pdf,B-pdf. Models: LLM_MODEL_A (default LLM_MODEL) and LLM_MODEL_B. Off by default. "
                         "Only view A feeds the prediction until the multi-view aggregation (T09) exists.")
    ap.add_argument("--cuad-views", default=None, metavar="VIEWS",
                    help="CUAD long-context pipeline (T07): 'A' = A-text only, 'full' = A-text,B-text. Off by default.")
    ap.add_argument("--chunk-chars", type=int, default=None, help="default 45000")
    ap.add_argument("--overlap-chars", type=int, default=None, help="default 3000")
    ap.add_argument("--batch-size", type=int, default=None, help="fields per request, default 10")
    ap.add_argument("--aggregator", choices=["v2", "multiview"], default=None, help="default v2")
    ap.add_argument("--on-error", choices=["fail", "abstain"], default="fail",
                    help="fail: documents with failed jobs are not written, exit 1. abstain: write null/0 for the "
                         "affected fields plus diagnosis; complete fields are kept.")
    ap.add_argument("--abstain-all", action="store_true", help="write null/0 for every document, no API call")
    ap.add_argument("--decision", help="submission/decision.json: loads the frozen pipeline configuration")
    ap.add_argument("--resume", action="store_true", help="continue an existing run with an identical pipeline")
    ap.add_argument("--cache-dir", default=str(HERE / "cache"))
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir) if a.run_dir else None
    if run_dir is not None and not a.out:
        a.out = str(run_dir / "preds.jsonl")
    if not a.out:
        raise SystemExit("ERROR: --out is required (or --run-dir, which defaults it to RUN_DIR/preds.jsonl).")
    if run_dir is not None and Path(a.out).resolve().parent != run_dir.resolve():
        raise SystemExit("ERROR: with --run-dir, --out must be inside the run folder.")

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
        env_chunk = os.environ.get("LLM_CHUNK_CHARS", "").strip()
        defaults = {**DEFAULTS, "chunk_chars": int(env_chunk)} if env_chunk else DEFAULTS
        pipeline_values = {k: (cli_pipeline[k] if cli_pipeline[k] is not None else defaults[k]) for k in DEFAULTS}

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
    if pipeline_values["uq_method"] is None:  # default depends on K: one sample has no variation to measure
        pipeline_values["uq_method"] = "k1_grounded" if pipeline_values["samples"] == 1 else "k_agreement_conf"
    if pipeline_values["uq_method"] not in UQ_METHODS or pipeline_values["sampling"] not in SAMPLING_MODES:
        raise SystemExit("ERROR: unknown --uq-method or --sampling value.")
    if mode == "llm":
        k = pipeline_values["samples"]
        if pipeline_values["uq_method"] == "k1_grounded" and k != 1:
            raise SystemExit("ERROR: --uq-method k1_grounded needs --samples 1.")
        if pipeline_values["uq_method"] != "k1_grounded" and k < 2:
            raise SystemExit(f"ERROR: --uq-method {pipeline_values['uq_method']} needs --samples 2 or more.")
    pipeline = {**pipeline_values, "model": cfg["LLM_MODEL"] if cfg else None,
                "prompt_version": PROMPT_VERSION if mode == "llm" else None}
    agg_mode = a.aggregator or (dec["pipeline"].get("aggregator") if dec is not None and not dec["abstain_all"] else None)
    if agg_mode is not None:
        pipeline["aggregator"] = agg_mode
    eb_cfg = None
    dec_eb = dec["pipeline"].get("eb") if dec is not None and not dec["abstain_all"] else None
    if mode == "llm" and (a.eb_views or dec_eb):
        try:
            if a.eb_views and dec_eb and eb_pipeline.parse_views(a.eb_views) != dec_eb.get("views"):
                raise SystemExit("ERROR: --eb-views contradicts the decision file.")
            eb_cfg = eb_pipeline.resolve_eb({**(dec_eb or {}), **({"views": eb_pipeline.parse_views(a.eb_views)}
                                                                  if a.eb_views else {})})
        except ValueError as e:
            raise SystemExit(f"ERROR: {e}")
        pipeline["eb"] = {k: eb_cfg[k] for k in ("views", "model_a", "model_b", "batch_size", "dpi", "lower_dpi",
                                                 "max_pages", "temperature")}
        pipeline["eb"]["prompt_version"] = eb_pipeline.EB_PROMPT_VERSION
    elif a.eb_views and mode != "llm":
        print("WARNING: --eb-views is ignored outside the llm mode.", file=sys.stderr)
    cuad_cfg = None
    dec_cuad = dec["pipeline"].get("cuad") if dec is not None and not dec["abstain_all"] else None
    if mode == "llm" and (a.cuad_views or dec_cuad):
        try:
            if a.cuad_views and dec_cuad and cuad_pipeline.parse_views(a.cuad_views) != dec_cuad.get("views"):
                raise SystemExit("ERROR: --cuad-views contradicts the decision file.")
            cuad_cfg = cuad_pipeline.resolve_cuad({**(dec_cuad or {}), **({"views": cuad_pipeline.parse_views(a.cuad_views)}
                                                                        if a.cuad_views else {})})
        except ValueError as e:
            raise SystemExit(f"ERROR: {e}")
        pipeline["cuad"] = {k: cuad_cfg[k] for k in ("views", "model_a", "model_b", "chunk_chars", "overlap_chars",
                                                     "temperature")}
        pipeline["cuad"]["prompt_version"] = cuad_pipeline.CUAD_PROMPT_VERSION
    elif a.cuad_views and mode != "llm":
        print("WARNING: --cuad-views is ignored outside the llm mode.", file=sys.stderr)
    print(f"mode: {mode}", file=sys.stderr)

    # ----- input and output files
    recs = [json.loads(line) for line in open(a.data, encoding="utf-8") if line.strip()]
    recs = recs[: a.limit] if a.limit else recs
    out = Path(a.out)
    diag_path, man_path, samples_path = sidecar_paths(out, run_dir)
    fingerprint = run_fingerprint(Path(a.data), pipeline, cfg)
    done = check_existing(out, diag_path, man_path, samples_path, pipeline, a.resume, fingerprint)
    previous_segments = []
    if a.resume and man_path.exists():
        previous_segments = json.loads(man_path.read_text(encoding="utf-8")).get("segments", [])
    out.parent.mkdir(parents=True, exist_ok=True)
    registry = None
    if run_dir is not None:
        registry = _register_run(run_dir, a, recs, mode, pipeline, dec)

    state = RunState()
    cache = ReplyCache(None if a.no_cache else Path(a.cache_dir), state)
    ctx = Ctx(cfg, cache, state, pipeline, a.on_error, eb_cfg, cuad_cfg)
    if mode == "llm" and any(r["source_dataset"] == "cuad" for r in recs):
        load_cuad()  # once, before any worker pool starts

    run_id = uuid.uuid4().hex[:12]
    started = time.time()
    failed: list[str] = []      # not written (fail mode): rerun with --resume to retry
    degraded: list[str] = []    # written with affected fields null/0 after job errors: NOT a measured prediction
    skipped = 0
    with open(out, "a", encoding="utf-8") as fout, open(diag_path, "a", encoding="utf-8") as fdiag, \
            open(samples_path, "a", encoding="utf-8") as fsamp:
        for i, rec in enumerate(recs):
            if rec["doc_id"] in done:
                skipped += 1
                continue
            try:
                if mode == "abstain_all":
                    res = {"fields": null_fields(rec["schema"]),
                           "diagnostics": {"n_samples": 0, "complete": False, "method": "abstain_all",
                                           "uq_called": False,
                                           "per_field": {n: {"eligible": False, "reason": "abstain_all"}
                                                         for n in rec["schema"]["properties"]}},
                           "job_failures": [], "samples": []}
                elif mode == "offline":
                    row = offline_extract(rec)
                    res = {"fields": row["fields"], "diagnostics": None, "job_failures": [], "samples": []}
                else:
                    res = extract_llm(rec, ctx)
            except Exception as e:  # document-level error: reported, never silently written as a success
                print(f"[{i}] {rec['doc_id']}: FAILED {type(e).__name__}", file=sys.stderr)
                if mode == "llm" and a.on_error == "abstain":
                    res = {"fields": null_fields(rec["schema"]),
                           "diagnostics": {"n_samples": 0, "complete": False, "method": "document_error",
                                           "uq_called": False, "per_field": {}, "job_failures": [type(e).__name__]},
                           "job_failures": [type(e).__name__], "samples": []}
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
                print(f"[{i}] {rec['doc_id']}: fields with failed jobs set to null after errors "
                      f"{', '.join(res['job_failures'])}", file=sys.stderr)
                degraded.append(rec["doc_id"])
            fout.write(json.dumps({"doc_id": rec["doc_id"], "fields": res["fields"]}, ensure_ascii=False) + "\n")
            if res["diagnostics"] is not None:
                fdiag.write(json.dumps({"doc_id": rec["doc_id"], "diagnostics": res["diagnostics"]}, ensure_ascii=False) + "\n")
            if res.get("samples"):
                fsamp.write(json.dumps({"doc_id": rec["doc_id"], "samples": res["samples"]}, ensure_ascii=False) + "\n")
            fout.flush()
            fdiag.flush()
            fsamp.flush()
            print(f"[{i}] {rec['doc_id']}", file=sys.stderr)

    n_written = len(read_jsonl(out)) if out.exists() else 0
    n_requested_total = len(recs)
    # complete: every requested document is in the output, none failed or was abstained after an error,
    # and the run was not stopped by the rate limit. Incomplete runs must not be used for calibration.
    run_complete = (not failed and not degraded and not state.stop.is_set() and n_written == len(recs))
    manifest = {
        "contract_version": CONTRACT_VERSION, "field_contract_version": 2, "run_id": run_id, "mode": mode,
        "pipeline": pipeline, "uq": {"method": pipeline["uq_method"], "expected_k": pipeline["samples"],
                                     "probly_version": probly_version() if mode == "llm" else None},
        "fingerprint": fingerprint,
        "segments": previous_segments + [{"run_id": run_id, "n_requested": n_requested_total,
                                          "requests": state.requests, "resumed_from_disk": skipped}],
        "n_requested": n_requested_total, "n_written": n_written,
        "n_skipped_resumed": skipped, "n_failed": len(failed), "failed_doc_ids": failed[:50],
        "n_abstained_after_errors": len(degraded), "abstained_after_error_doc_ids": degraded[:50],
        "run_complete": bool(run_complete),
        "requests": state.requests, "cache_hits": state.cache_hits,
        "elapsed_seconds": round(time.time() - started, 2), "stopped_429": state.stop.is_set(),
        "on_error": a.on_error, "warnings": state.warnings[:20],
    }
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"done: requested={len(recs)} written={n_written} failed={len(failed)} requests={state.requests} "
          f"cache_hits={state.cache_hits} run_id={run_id}", file=sys.stderr)
    if registry is not None:
        _finish_registered_run(registry, run_dir, a, dec, run_complete, n_written, len(recs))
    if failed and a.on_error == "fail":
        shown = ", ".join(failed[:5]) + (" ..." if len(failed) > 5 else "")
        print(f"ERROR: {len(failed)} document(s) not written. Rerun with --resume to retry them: {shown}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
