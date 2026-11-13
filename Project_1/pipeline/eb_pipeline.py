"""ExtractBench vision pipeline (T06): native PDF (or page images) to field observations, per model view.

    run_views(rec, routed, ctx) -> list[ViewResult]
    extract_document(rec, routed, ctx) -> {"fields", "diagnostics", "job_failures", "samples"}   (4_extract.py contract)

ViewResult = {"view_id", "model", "input_kind", "fields": {name: obs}, "complete", "errors", "attempts", ...}
`obs` is the merge v2 format ({"status", "value", "model_confidence", "complete", "evidence", "reason"}), so the
aggregation (T09, until then uncertainty.single_view) consumes it like a text-pipeline sample.

Views (a view is `<role>-<kind>`; role A = LLM_MODEL_A, B = LLM_MODEL_B):

| route            | A-pdf | B-pdf | A-text (legacy prompt on the text layer) |
|------------------|:-----:|:-----:|:----------------------------------------:|
| pdf_text_good    |  yes  |  yes  |  yes                                     |
| pdf_text_damaged |  yes  |  yes  |  no (text layer untrusted)               |
| pdf_no_text      |  yes  |  yes  |  no                                      |
| pdf_corrupted    |  PNG render only (if it renders), else unreadable        |

A "pdf" view sends the native PDF when the model supports it (models.json), else rendered PNG pages. A rejected request
(HTTP 400/413, e.g. a size limit) falls back to PNG at a lower DPI. PDFs with more than `max_pages` pages are rendered
(first `max_pages` pages) instead of sent whole. One request per batch of at most `batch_size` fields.

ctx needs `.cfg`, `.cache`, `.state` (transport objects) and optionally `.eb` (dict, see DEFAULT_EB).
Gold is never read.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline import models as model_registry
from pipeline import router
from pipeline.messages import pdf_messages, png_messages
from pipeline.merge import merge_sample_v2
from pipeline.prompts_eb import EB_BATCH_SIZE, EB_PROMPT_VERSION, build_prompt as build_eb_prompt, eb_jobs
from pipeline.render import render_pages
from pipeline.requests import PROMPT_VERSION as TEXT_PROMPT_VERSION
from pipeline.requests import build_jobs as build_text_jobs
from pipeline.requests import build_prompt as build_text_prompt
from pipeline.transport import execute_job

logging.getLogger("pypdf").setLevel(logging.ERROR)

DEFAULT_MODEL_A = "vertex_ai/gemini-3.7-flash"
DEFAULT_MODEL_B = "vertex_ai/claude-sonnet-5.5"
VIEW_KINDS = ("pdf", "text")
ROUTE_VIEWS = {
    "pdf_text_good": ("A-pdf", "B-pdf", "A-text"),
    "pdf_text_damaged": ("A-pdf", "B-pdf"),
    "pdf_no_text": ("A-pdf", "B-pdf"),
    "pdf_corrupted": ("A-pdf",),
}
VISION_ROUTES = tuple(ROUTE_VIEWS)
FALLBACK_ERRORS = ("http:400", "http:413")     # request rejected: usually a size limit -> next attempt
DEFAULT_EB = {
    "views": ["A-pdf"],        # until T09 consumes several views only view A feeds the prediction ("full" = the table)
    "model_a": None, "model_b": None,
    "batch_size": EB_BATCH_SIZE, "dpi": 150, "lower_dpi": 100, "max_pages": 10,
    "max_pdf_bytes": 15 * 1024 * 1024, "temperature": 0.0, "workers": 1,
    "text_chunk_chars": 45000, "text_overlap_chars": 3000, "text_batch_size": 10,
}
KIND_OF_ATTEMPT = {"pdf_file": "pdf", "pdf_image_url": "pdf", "png": "png"}


# ---------------------------------------------------------------- configuration

def eb_models(env: dict | None = None) -> dict[str, str]:
    """Model per role. LLM_MODEL_A (else LLM_MODEL, else the default) and LLM_MODEL_B (else the default)."""
    roles = model_registry.model_roles(env)
    return {"A": roles.get("A") or DEFAULT_MODEL_A, "B": roles.get("B") or DEFAULT_MODEL_B}


def resolve_eb(overrides: dict | None = None, env: dict | None = None) -> dict:
    """Complete eb configuration: DEFAULT_EB, then explicit models from the environment, then overrides."""
    eb = {**DEFAULT_EB, **(overrides or {})}
    models = eb_models(env)
    eb["model_a"] = eb.get("model_a") or models["A"]
    eb["model_b"] = eb.get("model_b") or models["B"]
    eb["views"] = list(eb["views"])
    return eb


def parse_view_id(view_id: str) -> tuple[str, str]:
    """'A-pdf' -> ('A', 'pdf'). Raises ValueError for anything else."""
    role, _, kind = str(view_id).partition("-")
    if role not in ("A", "B") or kind not in VIEW_KINDS:
        raise ValueError(f"unknown view {view_id!r}; use <A|B>-<pdf|text>, e.g. A-pdf")
    return role, kind


def parse_views(spec: str | list[str] | None) -> list[str]:
    """CLI value to a view list: 'A' (default, view A only), 'full' (the per-route table), or 'A-pdf,B-pdf'."""
    if spec is None:
        return list(DEFAULT_EB["views"])
    items = [s.strip() for s in (spec.split(",") if isinstance(spec, str) else spec) if s.strip()]
    if items == ["A"]:
        return ["A-pdf"]
    if items == ["full"]:
        return ["full"]
    for v in items:
        parse_view_id(v)
    return items


def views_for_route(route_name: str, requested: list[str]) -> list[str]:
    """The views that run on a route: 'full' = the route's table, otherwise the requested views the route allows."""
    allowed = ROUTE_VIEWS.get(route_name, ())
    if requested == ["full"]:
        return list(allowed)
    return [v for v in requested if v in allowed]


# ---------------------------------------------------------------- document inputs

def _pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


class Document:
    """Lazy access to the files of one record: PDF bytes, page count, rendered pages."""

    def __init__(self, rec: dict, data_dir: Path | None, eb: dict):
        self.rec, self.data_dir, self.eb = rec, data_dir, eb
        self.error: str | None = None
        self.paths: list[Path] = []
        try:
            self.paths = [router.page_path(p, data_dir) for p in rec.get("pages") or []]
        except (FileNotFoundError, ValueError) as e:
            self.error = f"missing_file:{type(e).__name__}"
        if not self.paths and not self.error:
            self.error = "no_pages"
        self.is_pdf = bool(self.paths) and self.paths[0].suffix.lower() == ".pdf"
        self._bytes: bytes | None = None
        self._n_pages: int | None | bool = False
        self._png: dict[int, list] = {}

    @property
    def pdf_bytes(self) -> bytes | None:
        if self._bytes is None and self.is_pdf:
            try:
                self._bytes = self.paths[0].read_bytes()
            except OSError:
                self.error = "unreadable_file"
        return self._bytes

    @property
    def n_pages(self) -> int | None:
        if self._n_pages is False:
            self._n_pages = _pdf_pages(self.paths[0]) if self.is_pdf else len(self.paths)
        return self._n_pages  # type: ignore[return-value]

    def pngs(self, dpi: int) -> list:
        """PNG pages as bytes (at most max_pages). [] when nothing can be rendered."""
        if dpi not in self._png:
            try:
                if self.is_pdf:
                    files = render_pages(self.paths[0], dpi=dpi, max_pages=self.eb["max_pages"])
                else:
                    files = [p for p in self.paths if p.suffix.lower() == ".png"][: self.eb["max_pages"]]
                self._png[dpi] = [f.read_bytes() for f in files]
            except OSError:
                self._png[dpi] = []
        return self._png[dpi]


def plan_attempts(model: str, doc: Document, eb: dict, *, force_png: bool = False) -> list[dict]:
    """Input attempts for one pdf view, best first: native PDF (model-supported mode), then PNG at the normal DPI when
    the model has no PDF support, then PNG at the lower DPI. Each: {"kind", "mode", "dpi"}."""
    available = ["png"] if force_png or not doc.is_pdf else ["pdf_file", "pdf_image_url", "png"]
    order = model_registry.fallback_order(model, available)
    attempts: list[dict] = []
    native = next((k for k in order if k in ("pdf_file", "pdf_image_url")), None)
    size_ok = doc.is_pdf and (len(doc.pdf_bytes or b"") <= eb["max_pdf_bytes"])
    pages_ok = doc.n_pages is not None and doc.n_pages <= eb["max_pages"]
    if native and size_ok and pages_ok and not force_png:
        attempts.append({"kind": native, "mode": "file" if native == "pdf_file" else "image_url", "dpi": None})
    if "png" in order:
        dpis = [eb["dpi"], eb["lower_dpi"]] if not attempts else [eb["lower_dpi"]]
        attempts += [{"kind": "png", "mode": None, "dpi": d} for d in dict.fromkeys(dpis)]
    return attempts


# ---------------------------------------------------------------- one view

def _run_jobs(jobs: list[dict], ctx, *, model: str, prompt_version: str, build_messages, temperature: float) -> list[dict]:
    results = []
    for job in jobs:
        results.append(execute_job(job, cfg=ctx.cfg, cache=ctx.cache, state=ctx.state, temperature=temperature,
                                   prompt_version=prompt_version, build_messages=build_messages,
                                   sampling="identical", model=model))
    return results


def _view_result(view_id: str, model: str, input_kind: str | None, results: list[dict], jobs: list[dict],
                 schema: dict, attempts: list[dict], **extra) -> dict:
    sample = merge_sample_v2(results, schema, 0, planned_jobs=jobs)
    errors = sorted({r["error"] for r in results if not r["ok"]})
    return {"view_id": view_id, "model": model, "input_kind": input_kind, "fields": sample["fields"],
            "complete": sample["complete"], "errors": errors, "n_requests": len(jobs), "attempts": attempts, **extra}


def _failed_view(view_id: str, model: str, schema: dict, reason: str, attempts: list[dict] | None = None) -> dict:
    fields = {n: {"status": "error", "value": None, "model_confidence": None, "complete": False, "evidence": [],
                  "reason": reason} for n in schema.get("properties", {})}
    return {"view_id": view_id, "model": model, "input_kind": None, "fields": fields, "complete": False,
            "errors": [reason], "n_requests": 0, "attempts": attempts or []}


def run_pdf_view(view_id: str, model: str, rec: dict, doc: Document, ctx, eb: dict, *, force_png: bool = False) -> dict:
    schema = rec["schema"]
    if doc.error:
        return _failed_view(view_id, model, schema, doc.error)
    attempts = plan_attempts(model, doc, eb, force_png=force_png)
    if not attempts:
        return _failed_view(view_id, model, schema,
                            "no_supported_input" if not model_registry.supported_kinds(model) else "no_input_available")
    jobs = eb_jobs(schema, eb["batch_size"])
    log: list[dict] = []
    last: dict | None = None
    for att in attempts:
        kind, source = att["kind"], ("png" if att["kind"] == "png" else "pdf")
        pages = None
        if kind == "png":
            pages = doc.pngs(att["dpi"])
            if not pages:
                log.append({**att, "ok": False, "error": "render_failed"})
                continue
            size = sum(len(p) for p in pages)
        else:
            size = len(doc.pdf_bytes or b"")

        def build(job, _source=source, _pages=pages, _mode=att["mode"]):
            prompt = build_eb_prompt(job["schema"], _source)
            if _source == "png":
                return png_messages(prompt, _pages)
            return pdf_messages(prompt, doc.pdf_bytes, _mode)

        results = _run_jobs(jobs, ctx, model=model, prompt_version=EB_PROMPT_VERSION, build_messages=build,
                            temperature=eb["temperature"])
        failed = [r["error"] for r in results if not r["ok"]]
        log.append({**att, "ok": not failed, "bytes": size, "n_pages": doc.n_pages, "error": failed[0] if failed else None})
        last = _view_result(view_id, model, kind, results, jobs, schema, log, request_bytes=size,
                            n_pages=doc.n_pages, prompt_version=EB_PROMPT_VERSION)
        if not failed or not any(e.startswith(FALLBACK_ERRORS) for e in failed):
            break  # success, or an error that another input kind will not fix (timeout, parse, rate limit)
    if last is None:
        return _failed_view(view_id, model, schema, "render_failed", log)
    last["attempts"] = log
    return last


def run_text_view(view_id: str, model: str, rec: dict, text: str, ctx, eb: dict) -> dict:
    """View C: the text layer through the legacy chunked text prompt (cache-compatible with the text pipeline)."""
    schema = rec["schema"]
    jobs = build_text_jobs(text, schema, chunk_chars=eb["text_chunk_chars"], overlap_chars=eb["text_overlap_chars"],
                           batch_size=eb["text_batch_size"], samples=1)

    def build(job):
        prompt = build_text_prompt(job["schema"], job["text"], chunk_no=job["chunk_id"] + 1, n_chunks=job["n_chunks"])
        return [{"role": "user", "content": prompt}]

    results = _run_jobs(jobs, ctx, model=model, prompt_version=TEXT_PROMPT_VERSION, build_messages=build,
                        temperature=eb["temperature"])
    return _view_result(view_id, model, "text", results, jobs, schema, [{"kind": "text", "ok": all(r["ok"] for r in results)}],
                        n_chars=len(text), prompt_version=TEXT_PROMPT_VERSION)


# ---------------------------------------------------------------- all views of one document

def _eb_of(ctx) -> dict:
    eb = getattr(ctx, "eb", None)
    return eb if eb and eb.get("model_a") else resolve_eb(eb)


def run_views(rec: dict, routed: dict | str, ctx, *, data_dir: Path | None = None) -> list[dict]:
    """All views of the document's route. `routed` is a router.route() result (or just the route name).
    Never raises: a failing view returns error observations."""
    info = routed if isinstance(routed, dict) else {"route": routed, "text": None}
    route_name = info["route"]
    eb = _eb_of(ctx)
    view_ids = views_for_route(route_name, eb["views"])
    if not view_ids:
        return []
    doc = Document(rec, data_dir, eb)
    text = info.get("text")

    def run_one(view_id: str) -> dict:
        role, kind = parse_view_id(view_id)
        model = eb["model_a"] if role == "A" else eb["model_b"]
        try:
            if kind == "text":
                if not text or not str(text).strip():
                    return _failed_view(view_id, model, rec["schema"], "no_text_layer")
                return run_text_view(view_id, model, rec, text, ctx, eb)
            return run_pdf_view(view_id, model, rec, doc, ctx, eb, force_png=(route_name == "pdf_corrupted"))
        except Exception as e:  # a bug in one view must not kill the document
            return _failed_view(view_id, model, rec["schema"], f"internal:{type(e).__name__}")

    workers = max(1, min(int(eb.get("workers") or 1), len(view_ids)))
    if workers == 1:
        return [run_one(v) for v in view_ids]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_one, view_ids))


# ---------------------------------------------------------------- document result (4_extract.py contract)

def view_samples(views: list[dict]) -> list[dict]:
    """Views as samples.jsonl rows (contract v2 sample + view metadata, no document text)."""
    from uncertainty.contracts import CONTRACT_VERSION
    return [{"contract_version": CONTRACT_VERSION, "sample_idx": i, "complete": v["complete"], "fields": v["fields"],
             "view_id": v["view_id"], "model": v["model"], "input_kind": v["input_kind"]}
            for i, v in enumerate(views)]


def extract_document(rec: dict, routed: dict, ctx, *, data_dir: Path | None = None) -> dict:
    """Route -> views -> temporary single-view aggregation -> k1_grounded prediction.
    Returns {"fields", "diagnostics", "job_failures", "samples"}."""
    from uncertainty.decision import make_prediction
    from uncertainty.single_view import aggregate_single_view

    schema = rec["schema"]
    route_info = {"route": routed["route"], "text_source": routed.get("text_source"), "quality": routed.get("quality"),
                  "quality_features": routed.get("quality_features")}
    eb = _eb_of(ctx)
    views = run_views(rec, routed, ctx, data_dir=data_dir)
    if not views:
        raise ValueError(f"no eb view applies to route {routed['route']} with views {eb['views']}")
    primary = views[0]
    agg = aggregate_single_view(primary, schema, routed.get("text"), route=routed["route"])
    fields = make_prediction(agg, schema, method="k1_grounded")
    failures = sorted({e for v in views for e in v["errors"]})
    diag = dict(agg["diagnostics"])
    diag.update({"complete": all(v["complete"] for v in views), "uq_method": "k1_grounded", "uq_called": False,
                 "pipeline": "eb-vision", "prompt_version": EB_PROMPT_VERSION, "job_failures": failures,
                 "views": [{k: v.get(k) for k in ("view_id", "model", "input_kind", "complete", "errors", "n_requests",
                                                  "request_bytes", "n_pages", "attempts")} for v in views],
                 **route_info})
    return {"fields": fields, "diagnostics": diag, "job_failures": failures, "samples": view_samples(views)}
