"""Extractor library (T11): route -> views -> aggregation -> selector, configured by decision or CLI.

Public library API:
    load_config(source=None, **overrides) -> Config
    extract_document(rec, config, ctx) -> {"fields", "diagnostics", "views", "route", ...}
    run_file(input_path, out_path, config, *, run_dir=None, run_name=None, limit=None, progress=None) -> dict

`4_extract.py` is a thin CLI wrapper around this module. Gold is never read by the extractor.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import math
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlparse

from pipeline import cuad_pipeline, eb_pipeline, router
from pipeline.merge import merge_sample_v2
from pipeline.requests import PROMPT_VERSION, build_jobs, build_prompt
from pipeline.transport import ReplyCache, RunState, execute_job

HERE = Path(__file__).resolve().parent.parent
# EXTRACT_DATA_DIR overrides the data folder (used by tests with synthetic data). Normal runs use data/.
DATA = Path(os.environ["EXTRACT_DATA_DIR"]) if os.environ.get("EXTRACT_DATA_DIR") else HERE / "data"
LLM_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
CONTRACT_VERSION = 1          # run manifest and decision file v1
DECISION_CONTRACT_VERSIONS = (1, 2)
UQ_METHODS = ("k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy", "selector")
SAMPLING_MODES = ("mixed", "identical")
DEFAULTS = {
    "workers": 1, "samples": 1, "temperature": 0.7, "chunk_chars": 45000,
    "overlap_chars": 3000, "batch_size": 10, "uq_method": None, "sampling": "mixed",
}
PATTERNS = {
    "amount": r"-?\d[\d.,]*\d|\d",
    "date": r"\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]{2,8}\.? \d{4}",
    "id": r"[A-Za-z0-9][A-Za-z0-9\-/]{3,}",
}

ALLOWED_V1_DECISION_KEYS = frozenset({
    "contract_version", "run_id", "threshold", "abstain_all", "method", "pipeline", "pipeline_sha256",
    "error_cost", "n_docs", "n_fields", "accepted", "wrong", "hallucinated", "net_saving_pct",
    "n_abstained_after_errors", "measurement",
})
ALLOWED_V2_DECISION_KEYS = frozenset({
    "contract_version", "abstain_all", "threshold", "method", "run_id", "error_cost", "measurement",
    "pipeline", "pipeline_sha256", "routes", "models", "selector", "selector_path", "selector_sha256",
    "cascade", "allow_model_env_override",
})
ALLOWED_V2_ROUTES = frozenset({
    "cuad", "pdf_text_good", "pdf_text_damaged", "pdf_no_text", "pdf_corrupted", "legacy_text",
})
ALLOWED_ROUTE_KEYS = frozenset({
    "pipeline", "views", "prompt", "samples", "temperature", "chunk_chars", "overlap_chars",
    "batch_size", "uq_method", "sampling", "aggregator", "cascade", "view_priority",
    "candidate_cells", "dpi", "lower_dpi", "max_pages",
})
ALLOWED_MODEL_ROLES = frozenset({"A", "B", "C", "OCR", "default"})


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

def page_path(stored: str, data_dir: Path | None = None) -> Path:
    """Map a record's page path to a local file (implementation: pipeline.router)."""
    return router.page_path(stored, data_dir or DATA)


def pdf_text(path: Path) -> str | None:
    """Text of all pages (pdftotext, pypdf fallback). Implementation: pipeline.router."""
    return router.pdf_text(path)


def load_cuad(data_dir: Path | None = None) -> dict:
    """CUAD texts, loaded once. Call before any worker pool starts."""
    return router.load_cuad(data_dir or DATA)


def full_text(rec: dict, data_dir: Path | None = None) -> str | None:
    """Complete document text, never truncated. None means no text layer (scan or unreadable PDF)."""
    return router.full_text(rec, data_dir or DATA)


def null_fields(schema: dict) -> dict:
    return {name: {"value": None, "confidence": 0.0} for name in schema.get("properties", {})}


# ---------------------------------------------------------------- offline baseline (unchanged rules)

def offline_extract(rec: dict, *, data_dir: Path | None = None) -> dict:
    text = full_text(rec, data_dir)
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
    """Everything one run needs."""

    def __init__(self, cfg, cache, state, pipeline, on_error, eb=None, cuad=None, selector=None, data_dir=None):
        self.cfg = cfg
        self.cache = cache
        self.state = state
        self.pipeline = pipeline
        self.on_error = on_error
        self.eb = eb          # None = text pipeline only; else the resolved ExtractBench vision config (T06)
        self.cuad = cuad      # None = text pipeline only; else the resolved CUAD long-context config (T07)
        self.selector = selector  # Loaded selector.json for method='selector' (T10)
        self.data_dir = data_dir


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


def _extract_text_pipeline(rec: dict, routed: dict, text: str | None, ctx: Ctx, pipeline_cfg: dict | None = None) -> dict:
    from uncertainty.decision import make_prediction
    from uncertainty.uq_probly import aggregate_v2

    schema = rec["schema"]
    p = pipeline_cfg or ctx.pipeline
    route_info = {"route": routed["route"], "text_source": routed["text_source"], "quality": routed["quality"],
                  "quality_features": routed["quality_features"]}
    if text is None or not text.strip():
        per_field = {n: {"eligible": False, "reason": "unreadable", "agreement": None, "entropy_nats": None,
                         "n_clusters": 0, "grounded": False} for n in schema.get("properties", {})}
        return {"fields": null_fields(schema),
                "diagnostics": {"n_samples": 0, "expected_k": p["samples"], "complete": False,
                                "method": "unreadable_document", "uq_called": False, "per_field": per_field,
                                **route_info},
                "job_failures": [], "samples": [], "views": [], "route": routed["route"]}
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
    if p["uq_method"] == "selector":
        from evaluation.docs import family_of
        fields = make_prediction(
            agg,
            schema,
            method="selector",
            selector=ctx.selector,
            record_meta={"source": rec.get("source_dataset"), "family": family_of(rec)},
        )
    else:
        fields = make_prediction(agg, schema, method=p["uq_method"])
    failures = sorted({r["error"] for r in results if not r["ok"]})
    diag = dict(agg["diagnostics"])
    diag.update({"complete": all(s["complete"] for s in samples), "uq_method": p["uq_method"],
                 "uq_called": True, "probly_version": probly_version(), "job_failures": failures,
                 "pipeline": "legacy_text", "prompt_version": PROMPT_VERSION,
                 **route_info})
    return {"fields": fields, "diagnostics": diag, "job_failures": failures, "samples": samples,
            "views": [], "route": routed["route"]}


def extract_llm(rec: dict, ctx: Ctx, *, data_dir: Path | None = None, text_fn=None) -> dict:
    """One document (legacy Ctx interface). Returns {"fields", "diagnostics", "job_failures", "samples"}."""
    d_dir = data_dir or ctx.data_dir or DATA
    text = text_fn(rec) if text_fn is not None else full_text(rec, d_dir)
    routed = router.route(rec, d_dir, text=text)
    if ctx.eb and routed["route"] in eb_pipeline.VISION_ROUTES and eb_pipeline.views_for_route(routed["route"], ctx.eb["views"]):
        res = eb_pipeline.extract_document(rec, routed, ctx, data_dir=d_dir)
        res.setdefault("views", res.get("diagnostics", {}).get("views", []))
        res.setdefault("route", routed["route"])
        return res
    if ctx.cuad and routed["route"] == "cuad" and ctx.cuad.get("views"):
        res = cuad_pipeline.extract_document(rec, routed, ctx)
        res.setdefault("views", res.get("diagnostics", {}).get("views", []))
        res.setdefault("route", routed["route"])
        return res
    return _extract_text_pipeline(rec, routed, text, ctx)


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


CODE_FILES = (
    "4_extract.py", "pipeline/extractor.py", "pipeline/router.py", "pipeline/requests.py",
    "pipeline/transport.py", "pipeline/merge.py", "pipeline/cuad_pipeline.py",
    "pipeline/eb_pipeline.py", "pipeline/prompts_eb.py", "pipeline/messages.py",
    "pipeline/models.py", "uncertainty/single_view.py", "uncertainty/contracts.py",
    "uncertainty/grounding.py", "uncertainty/policy.py", "uncertainty/schema_check.py",
    "uncertainty/uq_probly.py", "uncertainty/decision.py",
)


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

def _resolve_selector_path(raw_path: str, decision_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    cand_rel = Path(decision_path).resolve().parent / p
    if cand_rel.exists():
        return cand_rel
    cand_here = HERE / p
    if cand_here.exists():
        return cand_here
    return p


def _validate_v2_routes(routes: object, path: str) -> None:
    if not isinstance(routes, dict) or not routes:
        raise SystemExit(f"ERROR: decision file v2 {path} 'routes' must be a non-empty object.")
    unknown_routes = sorted(set(routes) - ALLOWED_V2_ROUTES)
    if unknown_routes:
        raise SystemExit(f"ERROR: decision file v2 {path} has unknown route(s): {', '.join(unknown_routes)}.")
    for rname, rspec in routes.items():
        if not isinstance(rspec, dict):
            raise SystemExit(f"ERROR: decision file v2 {path} route {rname!r} must be an object.")
        unknown_rkeys = sorted(set(rspec) - ALLOWED_ROUTE_KEYS)
        if unknown_rkeys:
            raise SystemExit(f"ERROR: decision file v2 {path} route {rname!r} has unknown key(s): {', '.join(unknown_rkeys)}.")
        pipe_kind = rspec.get("pipeline")
        if pipe_kind not in ("cuad", "eb", "legacy_text", "abstain"):
            raise SystemExit(f"ERROR: decision file v2 {path} route {rname!r} has invalid pipeline {pipe_kind!r}.")


def _validate_v2_models(models: object, path: str) -> None:
    if not isinstance(models, dict) or not models:
        raise SystemExit(f"ERROR: decision file v2 {path} 'models' must be a non-empty object.")
    unknown_roles = sorted(set(models) - ALLOWED_MODEL_ROLES)
    if unknown_roles:
        raise SystemExit(f"ERROR: decision file v2 {path} has unknown model role(s): {', '.join(unknown_roles)}.")
    for role, mname in models.items():
        if not isinstance(mname, str) or not mname.strip():
            raise SystemExit(f"ERROR: decision file v2 {path} model for role {role!r} must be a non-empty string.")


def _load_and_verify_selector(sel_raw: str, sel_sha: str, decision_path: str) -> dict:
    sel_file = _resolve_selector_path(sel_raw, decision_path)
    try:
        sel_bytes = sel_file.read_bytes()
    except OSError as e:
        raise SystemExit(f"ERROR: cannot read selector file {sel_file}: {type(e).__name__}")
    if sha256_bytes(sel_bytes) != sel_sha:
        raise SystemExit("ERROR: decision file selector_sha256 does not match the selector file.")
    try:
        sel_obj = json.loads(sel_bytes.decode("utf-8"))
    except ValueError as e:
        raise SystemExit(f"ERROR: selector file {sel_file} is not valid JSON: {type(e).__name__}")
    if not isinstance(sel_obj, dict) or sel_obj.get("selector_version") != 1:
        raise SystemExit(f"ERROR: selector file {sel_file} has an unknown selector_version.")
    return sel_obj


def load_decision(path: str | Path) -> dict:
    """Strict: version (1 or 2), boolean abstain_all, finite threshold in [0, 1], unknown keys rejected,
    complete pipeline or routes block for an active decision, pipeline_sha256 and selector_sha256 must match."""
    path_str = str(path)
    try:
        dec = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"ERROR: cannot read decision file {path_str}: {type(e).__name__}")
    if not isinstance(dec, dict) or dec.get("contract_version") not in DECISION_CONTRACT_VERSIONS:
        raise SystemExit(f"ERROR: decision file {path_str} has an unknown contract_version.")
    ver = dec["contract_version"]
    allowed_keys = ALLOWED_V1_DECISION_KEYS if ver == 1 else ALLOWED_V2_DECISION_KEYS
    unknown = sorted(set(dec) - allowed_keys)
    if unknown:
        raise SystemExit(f"ERROR: decision file {path_str} has unknown key(s): {', '.join(unknown)}.")
    if not isinstance(dec.get("abstain_all"), bool):
        raise SystemExit(f"ERROR: decision file {path_str} lacks a boolean abstain_all.")
    thr = dec.get("threshold")
    if not isinstance(thr, (int, float)) or isinstance(thr, bool) or not math.isfinite(float(thr)) \
            or not 0.0 <= float(thr) <= 1.0:
        raise SystemExit(f"ERROR: decision file {path_str} needs a finite numeric threshold in [0, 1].")
    if "allow_model_env_override" in dec and not isinstance(dec["allow_model_env_override"], bool):
        raise SystemExit(f"ERROR: decision file {path_str} allow_model_env_override must be boolean.")
    if "cascade" in dec and not isinstance(dec["cascade"], bool):
        raise SystemExit(f"ERROR: decision file {path_str} cascade must be boolean.")

    if not dec["abstain_all"]:
        pipe = dec.get("pipeline")
        routes = dec.get("routes") if ver == 2 else None
        if pipe is None and routes is None:
            raise SystemExit(f"ERROR: decision file {path_str} lacks the pipeline or routes block.")
        if pipe is not None:
            if not isinstance(pipe, dict):
                raise SystemExit(f"ERROR: decision file {path_str} lacks a valid pipeline block.")
            missing = [k for k in DEFAULTS if k not in pipe]
            if missing:
                raise SystemExit(f"ERROR: decision file pipeline block lacks: {', '.join(missing)}.")
            if "pipeline_sha256" in dec and dec["pipeline_sha256"] != sha256_obj(pipe):
                raise SystemExit("ERROR: decision file pipeline_sha256 does not match its pipeline block.")
        if ver == 2:
            if routes is not None:
                _validate_v2_routes(routes, path_str)
            if "models" in dec and dec["models"] is not None:
                _validate_v2_models(dec["models"], path_str)
            sel_block = dec.get("selector")
            sel_raw = dec.get("selector_path")
            sel_sha = dec.get("selector_sha256")
            if sel_block is not None:
                if not isinstance(sel_block, dict) or set(sel_block) != {"path", "sha256"}:
                    raise SystemExit(f"ERROR: decision file v2 {path_str} selector must have exactly 'path' and 'sha256'.")
                sel_raw = sel_block["path"]
                sel_sha = sel_block["sha256"]
            uses_selector = (
                (isinstance(pipe, dict) and pipe.get("uq_method") == "selector")
                or dec.get("method") == "selector"
                or sel_block is not None
                or sel_raw is not None
                or sel_sha is not None
            )
            if uses_selector:
                if not isinstance(sel_raw, str) or not sel_raw or not isinstance(sel_sha, str) or not sel_sha:
                    raise SystemExit(f"ERROR: decision file v2 {path_str} lacks selector path or sha256.")
                dec["_selector"] = _load_and_verify_selector(sel_raw, sel_sha, path_str)
                dec["_selector_sha256"] = sel_sha
    return dec


# ---------------------------------------------------------------- Config & load_config

@dataclass
class Config:
    mode: str
    on_error: str
    pipeline: dict
    cfg: dict | None = None
    decision: dict | None = None
    decision_path: str | None = None
    eb: dict | None = None
    cuad: dict | None = None
    routes: dict | None = None
    models: dict | None = None
    cascade: bool = False
    selector: dict | None = None
    allow_model_env_override: bool = False
    cache_dir: Path | None = None
    no_cache: bool = False
    resume: bool = False
    data_dir: Path = field(default_factory=lambda: DATA)


def _normalize_route_views(pipe_kind: str, views: list[str] | None) -> list[str]:
    if not views:
        return ["A-pdf"] if pipe_kind == "eb" else ["A-text"]
    out = []
    for v in views:
        if pipe_kind == "cuad" and v in ("A", "B"):
            out.append(f"{v}-text")
        elif pipe_kind == "eb" and v in ("A", "B"):
            out.append(f"{v}-pdf")
        else:
            out.append(v)
    return out


def _effective_data_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    env_dir = os.environ.get("EXTRACT_DATA_DIR", "").strip()
    return Path(env_dir) if env_dir else DATA


def load_config(source: str | Path | argparse.Namespace | dict | None = None, **overrides: Any) -> Config:
    """Resolve a Config from a decision file path, parsed CLI args, or an options dict."""
    if isinstance(source, (str, Path)):
        opts: dict[str, Any] = {"decision": str(source)}
    elif isinstance(source, argparse.Namespace):
        opts = vars(source).copy()
    elif isinstance(source, dict):
        opts = dict(source)
    elif source is None:
        opts = {}
    else:
        raise TypeError(f"unsupported config source: {type(source).__name__}")
    opts.update(overrides)

    decision_path = opts.get("decision")
    dec = load_decision(decision_path) if decision_path else None
    abstain_all_flag = bool(opts.get("abstain_all", False))
    req_mode = opts.get("mode")

    if abstain_all_flag and req_mode == "llm":
        raise SystemExit("ERROR: --abstain-all contradicts --mode llm.")
    if dec is not None and dec["abstain_all"]:
        mode = "abstain_all"
        if req_mode == "llm":
            print("NOTE: decision file is all-abstain; --mode llm is accepted, no API request is made.", file=sys.stderr)
    elif abstain_all_flag:
        mode = "abstain_all"
    elif dec is not None:
        mode = "llm"
        dec_pipe = dec.get("pipeline") or {}
        if dec.get("pipeline"):
            conflicts = [k for k in DEFAULTS if opts.get(k) is not None and opts.get(k) != dec_pipe.get(k)]
        else:
            conflicts = []
        if conflicts or (req_mode not in (None, "llm")):
            raise SystemExit(f"ERROR: options contradict the decision file: {', '.join(conflicts) or '--mode'}.")
    else:
        mode = req_mode or "auto"

    if dec is not None and not dec["abstain_all"]:
        base = dec.get("pipeline") or {}
        pipeline_values = {k: base.get(k, DEFAULTS[k]) for k in DEFAULTS}
        if dec.get("method") == "selector" and "uq_method" not in base:
            pipeline_values["uq_method"] = "selector"
    else:
        env_chunk = os.environ.get("LLM_CHUNK_CHARS", "").strip()
        defaults = {**DEFAULTS, "chunk_chars": int(env_chunk)} if env_chunk else DEFAULTS
        pipeline_values = {k: (opts.get(k) if opts.get(k) is not None else defaults[k]) for k in DEFAULTS}

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

    dec_pipe = (dec.get("pipeline") or {}) if dec is not None else {}
    dec_models = (dec.get("models") or {}) if dec is not None else {}
    allow_env_override = bool(opts.get("allow_model_env_override") or (dec and dec.get("allow_model_env_override")))

    if dec is not None and mode == "llm" and dec_pipe.get("prompt_version") not in (None, PROMPT_VERSION):
        raise SystemExit("ERROR: decision file was made with another prompt_version.")

    expected_primary_model = dec_pipe.get("model") or dec_models.get("A") or dec_models.get("default")
    if dec is not None and mode == "llm" and cfg and expected_primary_model not in (None, cfg["LLM_MODEL"]):
        if allow_env_override:
            pass
        else:
            raise SystemExit("ERROR: decision file was made with another model than LLM_MODEL.")

    if pipeline_values["overlap_chars"] >= pipeline_values["chunk_chars"]:
        raise SystemExit("ERROR: overlap_chars must be smaller than chunk_chars.")
    if pipeline_values["uq_method"] is None:
        pipeline_values["uq_method"] = "k1_grounded" if pipeline_values["samples"] == 1 else "k_agreement_conf"
    if pipeline_values["uq_method"] not in UQ_METHODS or pipeline_values["sampling"] not in SAMPLING_MODES:
        raise SystemExit("ERROR: unknown --uq-method or --sampling value.")
    if mode == "llm":
        k = pipeline_values["samples"]
        if pipeline_values["uq_method"] == "k1_grounded" and k != 1:
            raise SystemExit("ERROR: --uq-method k1_grounded needs --samples 1.")
        if pipeline_values["uq_method"] not in ("k1_grounded", "selector") and k < 2:
            raise SystemExit(f"ERROR: --uq-method {pipeline_values['uq_method']} needs --samples 2 or more.")
        if pipeline_values["uq_method"] == "selector" and not (dec and dec.get("_selector")):
            raise SystemExit("ERROR: --uq-method selector needs a v2 --decision file with a selector.")

    pipeline = {
        **pipeline_values,
        "model": cfg["LLM_MODEL"] if cfg else None,
        "prompt_version": PROMPT_VERSION if mode == "llm" else None,
    }
    agg_mode = opts.get("aggregator") or (dec_pipe.get("aggregator") if dec is not None and not dec["abstain_all"] else None)
    if agg_mode is not None:
        pipeline["aggregator"] = agg_mode

    eb_cfg = None
    eb_views_arg = opts.get("eb_views")
    dec_eb = dec_pipe.get("eb") if dec is not None and not dec["abstain_all"] else None
    if mode == "llm" and (eb_views_arg or dec_eb):
        try:
            if eb_views_arg and dec_eb and eb_pipeline.parse_views(eb_views_arg) != dec_eb.get("views"):
                raise SystemExit("ERROR: --eb-views contradicts the decision file.")
            eb_overrides = {**(dec_eb or {})}
            if eb_views_arg:
                eb_overrides["views"] = eb_pipeline.parse_views(eb_views_arg)
            if dec_models and not allow_env_override:
                if dec_models.get("A"):
                    eb_overrides.setdefault("model_a", dec_models["A"])
                if dec_models.get("B"):
                    eb_overrides.setdefault("model_b", dec_models["B"])
            eb_cfg = eb_pipeline.resolve_eb(eb_overrides)
        except ValueError as e:
            raise SystemExit(f"ERROR: {e}")
        pipeline["eb"] = {k: eb_cfg[k] for k in ("views", "model_a", "model_b", "batch_size", "dpi", "lower_dpi",
                                                 "max_pages", "temperature")}
        pipeline["eb"]["prompt_version"] = eb_pipeline.EB_PROMPT_VERSION
    elif eb_views_arg and mode != "llm":
        print("WARNING: --eb-views is ignored outside the llm mode.", file=sys.stderr)

    cuad_cfg = None
    cuad_views_arg = opts.get("cuad_views")
    dec_cuad = dec_pipe.get("cuad") if dec is not None and not dec["abstain_all"] else None
    if mode == "llm" and (cuad_views_arg or dec_cuad):
        try:
            if cuad_views_arg and dec_cuad and cuad_pipeline.parse_views(cuad_views_arg) != dec_cuad.get("views"):
                raise SystemExit("ERROR: --cuad-views contradicts the decision file.")
            cuad_overrides = {**(dec_cuad or {})}
            if cuad_views_arg:
                cuad_overrides["views"] = cuad_pipeline.parse_views(cuad_views_arg)
            if dec_models and not allow_env_override:
                if dec_models.get("A"):
                    cuad_overrides.setdefault("model_a", dec_models["A"])
                if dec_models.get("B"):
                    cuad_overrides.setdefault("model_b", dec_models["B"])
            cuad_cfg = cuad_pipeline.resolve_cuad(cuad_overrides)
        except ValueError as e:
            raise SystemExit(f"ERROR: {e}")
        pipeline["cuad"] = {k: cuad_cfg[k] for k in ("views", "model_a", "model_b", "chunk_chars", "overlap_chars",
                                                     "temperature")}
        pipeline["cuad"]["prompt_version"] = cuad_pipeline.CUAD_PROMPT_VERSION
    elif cuad_views_arg and mode != "llm":
        print("WARNING: --cuad-views is ignored outside the llm mode.", file=sys.stderr)

    routes = dec.get("routes") if dec is not None and not dec["abstain_all"] else None
    cascade = bool(dec.get("cascade", False)) if dec is not None else False
    if routes is not None:
        pipeline["routes"] = routes
        pipeline["cascade"] = cascade
    if dec_models:
        pipeline["models"] = dict(dec_models)

    cache_dir_raw = opts.get("cache_dir")
    cache_dir = Path(cache_dir_raw) if cache_dir_raw is not None else HERE / "cache"
    return Config(
        mode=mode,
        on_error=opts.get("on_error") or "fail",
        pipeline=pipeline,
        cfg=cfg,
        decision=dec,
        decision_path=str(decision_path) if decision_path else None,
        eb=eb_cfg,
        cuad=cuad_cfg,
        routes=routes,
        models=dict(dec_models) if dec_models else None,
        cascade=cascade,
        selector=dec.get("_selector") if dec else None,
        allow_model_env_override=allow_env_override,
        cache_dir=cache_dir,
        no_cache=bool(opts.get("no_cache", False)),
        resume=bool(opts.get("resume", False)),
        data_dir=_effective_data_dir(opts.get("data_dir")),
    )


# ---------------------------------------------------------------- document API

def _route_eb_config(route_spec: dict, config: Config) -> dict:
    overrides: dict[str, Any] = {
        "views": _normalize_route_views("eb", route_spec.get("views")),
        "cascade": route_spec.get("cascade", config.cascade),
    }
    for k in ("batch_size", "dpi", "lower_dpi", "max_pages", "temperature", "aggregator",
              "uq_method", "view_priority", "candidate_cells"):
        if k in route_spec:
            overrides[k] = route_spec[k]
    if "uq_method" not in overrides and config.pipeline.get("uq_method"):
        overrides["uq_method"] = config.pipeline["uq_method"]
    if config.models and not config.allow_model_env_override:
        if config.models.get("A"):
            overrides["model_a"] = config.models["A"]
        if config.models.get("B"):
            overrides["model_b"] = config.models["B"]
    return eb_pipeline.resolve_eb(overrides)


def _route_cuad_config(route_spec: dict, config: Config) -> dict:
    overrides: dict[str, Any] = {
        "views": _normalize_route_views("cuad", route_spec.get("views")),
        "cascade": route_spec.get("cascade", config.cascade),
    }
    for k in ("chunk_chars", "overlap_chars", "temperature", "aggregator",
              "uq_method", "view_priority", "candidate_cells"):
        if k in route_spec:
            overrides[k] = route_spec[k]
    if "uq_method" not in overrides and config.pipeline.get("uq_method"):
        overrides["uq_method"] = config.pipeline["uq_method"]
    if config.models and not config.allow_model_env_override:
        if config.models.get("A"):
            overrides["model_a"] = config.models["A"]
        if config.models.get("B"):
            overrides["model_b"] = config.models["B"]
    return cuad_pipeline.resolve_cuad(overrides)


def extract_document(rec: dict, config: Config, ctx: Ctx | None = None) -> dict:
    """Route -> views -> aggregation -> selector.
    Returns {"fields", "diagnostics", "views", "route", "job_failures", "samples"}."""
    schema = rec["schema"]
    if config.mode == "abstain_all":
        return {
            "fields": null_fields(schema),
            "diagnostics": {
                "n_samples": 0, "complete": False, "method": "abstain_all", "uq_called": False,
                "per_field": {n: {"eligible": False, "reason": "abstain_all"} for n in schema.get("properties", {})},
            },
            "views": [],
            "route": "abstain_all",
            "job_failures": [],
            "samples": [],
        }
    if config.mode == "offline":
        row = offline_extract(rec, data_dir=config.data_dir)
        return {
            "fields": row["fields"],
            "diagnostics": None,
            "views": [],
            "route": "offline",
            "job_failures": [],
            "samples": [],
        }
    if ctx is None:
        raise ValueError("extract_document in llm mode requires a Ctx")

    d_dir = config.data_dir
    text = full_text(rec, d_dir)
    routed = router.route(rec, d_dir, text=text)
    route_name = routed["route"]

    if config.routes is not None:
        rspec = config.routes.get(route_name) or config.routes.get("legacy_text")
        if rspec is None or rspec.get("pipeline") == "abstain":
            return {
                "fields": null_fields(schema),
                "diagnostics": {
                    "n_samples": 0, "complete": False, "method": "route_abstain", "uq_called": False,
                    "route": route_name, "text_source": routed["text_source"],
                    "quality": routed["quality"], "quality_features": routed["quality_features"],
                    "per_field": {n: {"eligible": False, "reason": "route_abstain"} for n in schema.get("properties", {})},
                },
                "views": [],
                "route": route_name,
                "job_failures": [],
                "samples": [],
            }
        pipe_kind = rspec["pipeline"]
        if pipe_kind == "eb":
            eb_cfg = _route_eb_config(rspec, config)
            route_ctx = Ctx(ctx.cfg, ctx.cache, ctx.state, ctx.pipeline, ctx.on_error,
                            eb=eb_cfg, cuad=ctx.cuad, selector=ctx.selector, data_dir=d_dir)
            res = eb_pipeline.extract_document(rec, routed, route_ctx, data_dir=d_dir)
            res.setdefault("views", res.get("diagnostics", {}).get("views", []))
            res["route"] = route_name
            return res
        if pipe_kind == "cuad":
            cuad_cfg = _route_cuad_config(rspec, config)
            route_ctx = Ctx(ctx.cfg, ctx.cache, ctx.state, ctx.pipeline, ctx.on_error,
                            eb=ctx.eb, cuad=cuad_cfg, selector=ctx.selector, data_dir=d_dir)
            res = cuad_pipeline.extract_document(rec, routed, route_ctx)
            res.setdefault("views", res.get("diagnostics", {}).get("views", []))
            res["route"] = route_name
            return res
        if pipe_kind == "legacy_text":
            p_cfg = {**ctx.pipeline, **{k: rspec[k] for k in ("samples", "temperature", "chunk_chars",
                                                              "overlap_chars", "batch_size", "uq_method",
                                                              "sampling", "aggregator") if k in rspec}}
            return _extract_text_pipeline(rec, routed, text, ctx, pipeline_cfg=p_cfg)
        raise ValueError(f"unknown route pipeline: {pipe_kind!r}")

    return extract_llm(rec, ctx, data_dir=d_dir)


# ---------------------------------------------------------------- run_file & registry

def _register_run(run_dir: Path, input_path: Path, run_name: str | None, limit: int | None,
                  recs: list[dict], config: Config) -> Any:
    from evaluation import registry
    splits = sorted({str(r.get("split")) for r in recs if r.get("split")})
    registry.init_run_dir(run_dir, name=run_name, split=splits[0] if len(splits) == 1 else "mixed" if splits else "unknown")
    registry.write_inputs(run_dir, recs, input_ref=str(input_path) if not limit else None,
                          input_sha256=sha256_bytes(input_path.read_bytes()) if not limit else None)
    models = [config.pipeline["model"]] if config.pipeline.get("model") else []
    if config.pipeline.get("eb"):
        models += [m for m in (config.pipeline["eb"]["model_a"], config.pipeline["eb"]["model_b"]) if m not in models]
    if config.models:
        models += [m for m in config.models.values() if m and m not in models]
    extra: dict[str, Any] = {"status": "running", "mode": config.mode, "models": models, "n_requested": len(recs)}
    if run_name:
        extra["name"] = run_name
    if config.decision_path is not None:
        extra["decision_sha256"] = sha256_bytes(Path(config.decision_path).read_bytes())
    registry.update_run(run_dir, **extra)
    return registry


def _finish_registered_run(registry, run_dir: Path, config: Config, run_complete: bool, n_written: int) -> None:
    status = "complete" if run_complete else ("failed" if n_written == 0 else "incomplete")
    try:
        registry.finish_run(run_dir, status, n_written=n_written)
        if (run_dir / "gold.jsonl").exists() and n_written:
            threshold = float(config.decision["threshold"]) if config.decision is not None else registry.DEFAULT_THRESHOLD
            s = registry.score_run(run_dir, threshold)
            print(f"scored {s['n_docs']} docs at threshold {threshold}: accepted={s['accepted']} wrong={s['wrong']} "
                  f"hallucinated={s['hallucinated']} net_saving_e100={s['net_saving_pct_e100']:.2%}", file=sys.stderr)
        registry.append_index(run_dir)
        print(f"run folder: {run_dir}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: run registry update failed: {type(e).__name__}: {e}", file=sys.stderr)


def run_file(
    input_path: str | Path,
    out_path: str | Path,
    config: Config,
    *,
    run_dir: str | Path | None = None,
    run_name: str | None = None,
    limit: int | None = None,
    progress: Callable[[int, int, str, dict], None] | None = None,
) -> dict:
    """Execute extraction on input_path and write out_path + sidecar files.
    Returns {"manifest": dict, "exit_code": int}."""
    in_p = Path(input_path)
    out = Path(out_path)
    r_dir = Path(run_dir) if run_dir is not None else None
    if r_dir is not None and out.resolve().parent != r_dir.resolve():
        raise SystemExit("ERROR: with --run-dir, --out must be inside the run folder.")

    with open(in_p, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    recs = recs[:limit] if limit else recs
    diag_path, man_path, samples_path = sidecar_paths(out, r_dir)
    fingerprint = run_fingerprint(in_p, config.pipeline, config.cfg)
    done = check_existing(out, diag_path, man_path, samples_path, config.pipeline, config.resume, fingerprint)
    previous_segments = []
    if config.resume and man_path.exists():
        previous_segments = json.loads(man_path.read_text(encoding="utf-8")).get("segments", [])
    out.parent.mkdir(parents=True, exist_ok=True)
    registry = None
    if r_dir is not None:
        registry = _register_run(r_dir, in_p, run_name, limit, recs, config)

    state = RunState()
    cache = ReplyCache(None if config.no_cache else config.cache_dir, state)
    ctx = Ctx(config.cfg, cache, state, config.pipeline, config.on_error,
              config.eb, config.cuad, selector=config.selector, data_dir=config.data_dir)
    if config.mode == "llm" and any(r["source_dataset"] == "cuad" for r in recs):
        load_cuad(config.data_dir)

    run_id = uuid.uuid4().hex[:12]
    started = time.time()
    failed: list[str] = []
    degraded: list[str] = []
    skipped = 0
    routes_used: dict[str, int] = {}
    text_sources: dict[str, int] = {}
    models_used: set[str] = set()
    input_kinds_used: set[str] = set()
    prompt_versions_used: set[str] = set()
    if config.mode == "llm" and config.cfg and config.cfg.get("LLM_MODEL"):
        models_used.add(config.cfg["LLM_MODEL"])

    with open(out, "a", encoding="utf-8") as fout, open(diag_path, "a", encoding="utf-8") as fdiag, \
            open(samples_path, "a", encoding="utf-8") as fsamp:
        for i, rec in enumerate(recs):
            if rec["doc_id"] in done:
                skipped += 1
                continue
            try:
                res = extract_document(rec, config, ctx)
            except Exception as e:
                print(f"[{i}] {rec['doc_id']}: FAILED {type(e).__name__}", file=sys.stderr)
                if config.mode == "llm" and config.on_error == "abstain":
                    res = {
                        "fields": null_fields(rec["schema"]),
                        "diagnostics": {"n_samples": 0, "complete": False, "method": "document_error",
                                        "uq_called": False, "per_field": {}, "job_failures": [type(e).__name__]},
                        "job_failures": [type(e).__name__], "samples": [], "views": [], "route": "error",
                    }
                    fout.write(json.dumps({"doc_id": rec["doc_id"], "fields": res["fields"]}, ensure_ascii=False) + "\n")
                    fdiag.write(json.dumps({"doc_id": rec["doc_id"], "diagnostics": res["diagnostics"]}, ensure_ascii=False) + "\n")
                    degraded.append(rec["doc_id"])
                    if progress is not None:
                        progress(i + 1, len(recs), rec["doc_id"], res)
                else:
                    failed.append(rec["doc_id"])
                continue

            if res["job_failures"] and config.mode == "llm" and config.on_error == "fail":
                print(f"[{i}] {rec['doc_id']}: FAILED jobs {', '.join(res['job_failures'])} (not written)", file=sys.stderr)
                failed.append(rec["doc_id"])
                continue
            if res["job_failures"]:
                print(f"[{i}] {rec['doc_id']}: fields with failed jobs set to null after errors "
                      f"{', '.join(res['job_failures'])}", file=sys.stderr)
                degraded.append(rec["doc_id"])

            diag = res.get("diagnostics") or {}
            r_name = res.get("route") or diag.get("route")
            if r_name:
                routes_used[r_name] = routes_used.get(r_name, 0) + 1
            ts = diag.get("text_source")
            if ts:
                text_sources[ts] = text_sources.get(ts, 0) + 1
            pv = diag.get("prompt_version")
            if pv:
                prompt_versions_used.add(pv)
            for v in res.get("views") or diag.get("views") or []:
                if isinstance(v, dict):
                    if v.get("model"):
                        models_used.add(v["model"])
                    if v.get("input_kind"):
                        input_kinds_used.add(v["input_kind"])
            if not (res.get("views") or diag.get("views")) and config.mode == "llm" and r_name != "abstain_all":
                if diag.get("method") not in ("unreadable_document", "route_abstain", "abstain_all"):
                    input_kinds_used.add("text")

            fout.write(json.dumps({"doc_id": rec["doc_id"], "fields": res["fields"]}, ensure_ascii=False) + "\n")
            if res["diagnostics"] is not None:
                fdiag.write(json.dumps({"doc_id": rec["doc_id"], "diagnostics": res["diagnostics"]}, ensure_ascii=False) + "\n")
            if res.get("samples"):
                fsamp.write(json.dumps({"doc_id": rec["doc_id"], "samples": res["samples"]}, ensure_ascii=False) + "\n")
            fout.flush()
            fdiag.flush()
            fsamp.flush()
            if progress is not None:
                progress(i + 1, len(recs), rec["doc_id"], res)
            print(f"[{i}] {rec['doc_id']}", file=sys.stderr)

    n_written = len(read_jsonl(out)) if out.exists() else 0
    n_requested_total = len(recs)
    run_complete = (not failed and not degraded and not state.stop.is_set() and n_written == len(recs))
    manifest = {
        "contract_version": CONTRACT_VERSION, "field_contract_version": 2, "run_id": run_id, "mode": config.mode,
        "pipeline": config.pipeline,
        "uq": {"method": config.pipeline["uq_method"], "expected_k": config.pipeline["samples"],
               "probly_version": probly_version() if config.mode == "llm" else None},
        "fingerprint": fingerprint,
        "segments": previous_segments + [{"run_id": run_id, "n_requested": n_requested_total,
                                          "requests": state.requests, "resumed_from_disk": skipped}],
        "n_requested": n_requested_total, "n_written": n_written,
        "n_skipped_resumed": skipped, "n_failed": len(failed), "failed_doc_ids": failed[:50],
        "n_abstained_after_errors": len(degraded), "abstained_after_error_doc_ids": degraded[:50],
        "run_complete": bool(run_complete),
        "requests": state.requests, "cache_hits": state.cache_hits,
        "requests_by_model": dict(state.requests_by_model),
        "cache_hits_by_model": dict(state.cache_hits_by_model),
        "routes_used": routes_used,
        "text_sources": text_sources,
        "models_used": sorted(models_used),
        "input_kinds": sorted(input_kinds_used),
        "prompt_versions": sorted(prompt_versions_used),
        "selector_sha256": config.decision.get("_selector_sha256") if config.decision else None,
        "elapsed_seconds": round(time.time() - started, 2), "stopped_429": state.stop.is_set(),
        "on_error": config.on_error, "warnings": state.warnings[:20],
    }
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"done: requested={len(recs)} written={n_written} failed={len(failed)} requests={state.requests} "
          f"cache_hits={state.cache_hits} run_id={run_id}", file=sys.stderr)
    if registry is not None:
        _finish_registered_run(registry, r_dir, config, run_complete, n_written)
    if failed and config.on_error == "fail":
        shown = ", ".join(failed[:5]) + (" ..." if len(failed) > 5 else "")
        print(f"ERROR: {len(failed)} document(s) not written. Rerun with --resume to retry them: {shown}", file=sys.stderr)
        return {"manifest": manifest, "exit_code": 1}
    return {"manifest": manifest, "exit_code": 0}


# ---------------------------------------------------------------- CLI

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Extractor CLI", formatter_class=argparse.RawDescriptionHelpFormatter)
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
                    help="decision rule: k1_grounded (K=1), k_agreement_only (K>1), k_agreement_conf (K>1), k_entropy (K>1), selector")
    ap.add_argument("--eb-views", default=None, metavar="VIEWS",
                    help="ExtractBench vision pipeline (T06) on the native PDF instead of the text layer.")
    ap.add_argument("--cuad-views", default=None, metavar="VIEWS",
                    help="CUAD long-context pipeline (T07): 'A' = A-text only, 'full' = A-text,B-text. Off by default.")
    ap.add_argument("--chunk-chars", type=int, default=None, help="default 45000")
    ap.add_argument("--overlap-chars", type=int, default=None, help="default 3000")
    ap.add_argument("--batch-size", type=int, default=None, help="fields per request, default 10")
    ap.add_argument("--aggregator", choices=["v2", "multiview"], default=None, help="default v2")
    ap.add_argument("--on-error", choices=["fail", "abstain"], default="fail",
                    help="fail: documents with failed jobs are not written, exit 1. abstain: write null/0 for affected fields.")
    ap.add_argument("--abstain-all", action="store_true", help="write null/0 for every document, no API call")
    ap.add_argument("--decision", help="submission/decision.json: loads the frozen pipeline configuration")
    ap.add_argument("--resume", action="store_true", help="continue an existing run with an identical pipeline")
    ap.add_argument("--cache-dir", default=str(HERE / "cache"))
    ap.add_argument("--no-cache", action="store_true")
    return ap


def cli_main(argv=None, *, data_dir: Path | None = None) -> int:
    ap = build_arg_parser()
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir) if a.run_dir else None
    if run_dir is not None and not a.out:
        a.out = str(run_dir / "preds.jsonl")
    if not a.out:
        raise SystemExit("ERROR: --out is required (or --run-dir, which defaults it to RUN_DIR/preds.jsonl).")

    if os.environ.get("EXTRACT_SKIP_DOTENV") != "1":
        loaded = load_env()
        if loaded:
            print(f"loaded from .env (names only): {', '.join(loaded)}", file=sys.stderr)

    overrides = {"data_dir": data_dir} if data_dir is not None else {}
    config = load_config(a, **overrides)
    print(f"mode: {config.mode}", file=sys.stderr)
    out = run_file(a.data, a.out, config, run_dir=run_dir, run_name=a.run_name, limit=a.limit)
    return int(out["exit_code"])
