#!/usr/bin/env python3
"""Probe which input kinds each endpoint model accepts (replaces vision_probe.py).

For every model and each of pdf_file / pdf_image_url / png / text, one request is sent on one fixed PDF and the answer
is compared with a known value. Results go to results/model_probe.json; with --write the accepted/rejected
capabilities are stored in models.json (only definitive outcomes: HTTP 200 or 4xx; timeouts and 5xx stay untested).

  python tools/probe_models.py --pdf data/raw/extractbench/docs/short/07021-2016-p0014.pdf \
      --models vertex_ai/gemini-3.7-flash vertex_ai/claude-sonnet-5.5 gpt-5.6-sol --write

Models whose name contains "ocr" are additionally probed on the dedicated /ocr endpoint (recorded as ocr_endpoint,
never written to models.json).
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from pipeline.messages import pdf_messages, png_messages, text_messages  # noqa: E402
from pipeline.models import load_models, update_supports  # noqa: E402
from pipeline.render import render_pages  # noqa: E402
from pipeline.transport import RunState, TransportError, call_model, redact  # noqa: E402

QUESTION = "What is the partnership name printed in item B (partnership's name)? Reply with the exact text only."
EXPECTED = "Pine Harbour Water Utilities LLC"
KINDS = ("pdf_file", "pdf_image_url", "png", "text")
DEFINITIVE = (400, 404, 405, 413, 415, 422)


def load_extract():
    spec = importlib.util.spec_from_file_location("extract4", HERE / "4_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def build(kind: str, pdf: Path, prompt: str):
    if kind == "pdf_file":
        return pdf_messages(prompt, pdf.read_bytes(), "file")
    if kind == "pdf_image_url":
        return pdf_messages(prompt, pdf.read_bytes(), "image_url")
    if kind == "png":
        pngs = render_pages(pdf, dpi=150, max_pages=1)
        if not pngs:
            raise RuntimeError("render failed (pdftoppm missing or PDF unreadable)")
        return png_messages(prompt, pngs)
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=60)
    return text_messages(prompt, out.stdout)


def probe_one(cfg: dict, model: str, kind: str, pdf: Path, expected: str, timeout: float) -> dict:
    row = {"model": model, "kind": kind, "ok": False, "status": None, "answer": None, "correct": None,
           "error": None, "elapsed_s": None, "usage": None}
    try:
        messages, _, _ = build(kind, pdf, QUESTION)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"build:{type(e).__name__}: {e}"[:200]
        return row
    state = RunState(wait_budget=10.0)
    try:
        res = call_model(cfg, model, messages, 0.0, state, timeout=timeout)
        row.update(ok=True, status=200, answer=(res["text"] or "").strip()[:200], elapsed_s=res["elapsed_s"],
                   usage=res["usage"])
        row["correct"] = norm(expected) in norm(row["answer"])
    except TransportError as e:
        row.update(status=e.status, error=redact(str(e), [cfg["LLM_API_KEY"]])[:240])
    return row


def probe_ocr_endpoint(cfg: dict, model: str, pdf: Path, timeout: float) -> dict:
    """POST <base>/ocr with the PDF as data URI (Mistral OCR API shape). Records reachability only."""
    uri = "data:application/pdf;base64," + base64.b64encode(pdf.read_bytes()).decode("ascii")
    body = json.dumps({"model": model, "document": {"type": "document_url", "document_url": uri}}).encode()
    req = urllib.request.Request(cfg["LLM_BASE_URL"].rstrip("/") + "/ocr", body,
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {cfg['LLM_API_KEY']}"})
    row = {"model": model, "kind": "ocr_endpoint", "ok": False, "status": None, "error": None, "pages": None,
           "correct": None}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
        pages = payload.get("pages") if isinstance(payload, dict) else None
        text = "\n".join(p.get("markdown", "") for p in pages or [] if isinstance(p, dict))
        row.update(ok=True, status=200, pages=len(pages or []), correct=norm(EXPECTED) in norm(text))
    except urllib.error.HTTPError as e:
        detail = redact(e.read(300).decode("utf-8", "replace"), [cfg["LLM_API_KEY"]]).strip()[:200]
        row.update(status=e.code, error=f"HTTP {e.code}: {detail}")
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}"[:120]
    return row


def matrix(rows: list[dict]) -> str:
    models = list(dict.fromkeys(r["model"] for r in rows))
    kinds = list(KINDS) + (["ocr_endpoint"] if any(r["kind"] == "ocr_endpoint" for r in rows) else [])
    by = {(r["model"], r["kind"]): r for r in rows}
    w = max(len(m) for m in models) if models else 5
    lines = ["model".ljust(w) + "  " + "  ".join(k.ljust(13) for k in kinds)]
    for m in models:
        cells = []
        for k in kinds:
            r = by.get((m, k))
            if r is None:
                cells.append("-")
            elif r["ok"]:
                cells.append("ok" + (" (value ok)" if r.get("correct") else " (wrong)"))
            else:
                cells.append(f"fail {r['status'] or r['error'] or ''}"[:13])
        lines.append(m.ljust(w) + "  " + "  ".join(c.ljust(13) for c in cells))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--models", nargs="+", default=None, help="default: all models in models.json")
    ap.add_argument("--expected", default=EXPECTED, help="known value expected in the answer")
    ap.add_argument("--out", type=Path, default=HERE / "results" / "model_probe.json")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--write", action="store_true", help="update models.json with definitive outcomes")
    a = ap.parse_args()

    X = load_extract()
    X.load_env()
    cfg = {k: __import__("os").environ.get(k, "").strip() for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")}
    if not cfg["LLM_BASE_URL"] or not cfg["LLM_API_KEY"]:
        sys.exit("LLM_BASE_URL and LLM_API_KEY are required (environment or Project_1/.env)")
    models = a.models or list(load_models())
    if not a.pdf.is_file():
        sys.exit(f"PDF not found: {a.pdf}")

    tasks = [(m, k) for m in models for k in KINDS]
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        futs = [pool.submit(probe_one, cfg, m, k, a.pdf, a.expected, a.timeout) for m, k in tasks]
        rows = [f.result() for f in futs]
        ocr_models = [m for m in models if "ocr" in m.lower()]
        rows += [f.result() for f in [pool.submit(probe_ocr_endpoint, cfg, m, a.pdf, a.timeout) for m in ocr_models]]

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = {"probed_at": now, "pdf": str(a.pdf), "expected": a.expected, "question": QUESTION, "results": rows}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(matrix(rows))
    print(f"\nwrote {a.out}")

    if a.write:
        updates: dict[str, dict[str, bool]] = {}
        for r in rows:
            if r["kind"] not in KINDS:
                continue
            if r["ok"]:
                updates.setdefault(r["model"], {})[r["kind"]] = True
            elif r["status"] in DEFINITIVE:
                updates.setdefault(r["model"], {})[r["kind"]] = False
        update_supports(updates, probed_at=now)
        print(f"updated models.json for {len(updates)} model(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
