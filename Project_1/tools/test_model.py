#!/usr/bin/env python3
"""Test configured LLM roles (default, A, B, C, OCR) against their endpoints.

Verifies that each configured model ID is valid, responds to /chat/completions,
and returns valid structured JSON parseable by pipeline.transport.parse_reply.

Examples:
    .venv/bin/python tools/test_model.py --role default
    .venv/bin/python tools/test_model.py --role a
    .venv/bin/python tools/test_model.py --role b
    .venv/bin/python tools/test_model.py --role ocr
    .venv/bin/python tools/test_model.py --role all
    .venv/bin/python tools/test_model.py --list-free
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from pipeline.extractor import llm_config, load_env  # noqa: E402
from pipeline.models import model_roles  # noqa: E402
from pipeline.transport import (  # noqa: E402
    ParseError,
    TransportError,
    last_call_meta,
    parse_reply,
    post_chat,
    redact,
    resolve_endpoint,
)

ROLE_CHOICES = ("default", "a", "b", "c", "ocr", "all")

TEST_PROMPT = (
    "Extract the fields below from the text and return ONLY a JSON object with keys "
    '"company", "total", and "currency".\n\n'
    "Text:\n"
    "Invoice from Acme Corp. Total amount due: 42.50 EUR."
)
EXPECTED = {"company": "Acme Corp", "total": 42.5, "currency": "EUR"}


def _canonical_role(role: str) -> str:
    r = role.strip().lower()
    if r in ("default", "ocr"):
        return r
    return r.upper()


def _fetch_models_catalog(base_url: str, api_key: str, timeout: float = 15.0) -> list[dict] | None:
    """Best-effort GET /models returning raw model objects."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return None
        return [item for item in data if isinstance(item, dict) and item.get("id")]
    except Exception:  # noqa: BLE001
        return None


def _fetch_available_models(base_url: str, api_key: str, timeout: float = 15.0) -> list[str] | None:
    """Best-effort GET /models to suggest valid IDs when a model ID is rejected."""
    data = _fetch_models_catalog(base_url, api_key, timeout=timeout)
    return [str(item["id"]) for item in data] if data is not None else None


def _is_free_model(item: dict) -> bool:
    mid = str(item.get("id", "")).strip()
    return mid.endswith(":free")


def _suggest_models(available: list[str], target: str, limit: int = 8) -> list[str]:
    tokens = [t for t in target.lower().replace("/", " ").replace(":", " ").replace("-", " ").split() if len(t) > 2]
    scored: list[tuple[int, int, str]] = []
    for mid in available:
        low = mid.lower()
        hits = sum(1 for t in tokens if t in low)
        is_free = 1 if ":free" in low else 0
        if hits > 0 or (":free" in target.lower() and is_free):
            scored.append((hits, is_free, mid))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [m for _, _, m in scored[:limit]]


def test_role(cfg: dict, role: str, model: str | None, *, timeout: float = 60.0,
              json_mode: bool | None = None, suggest: bool = True) -> dict:
    """Run a single JSON extraction probe for one role."""
    if not model:
        return {"role": role, "status": "skip", "reason": "not configured in .env"}

    base_url, api_key, resolved_model = resolve_endpoint(cfg, model)
    host = urlparse(base_url).netloc or base_url
    row: dict = {
        "role": role,
        "model": resolved_model,
        "endpoint": host,
        "status": "fail",
        "json_ok": False,
        "values_ok": False,
        "elapsed_s": None,
        "usage": None,
        "error": None,
        "suggestions": [],
    }
    messages = [{"role": "user", "content": TEST_PROMPT}]
    try:
        reply = post_chat(cfg, messages, 0.0, model=resolved_model, timeout=timeout, json_mode=json_mode)
    except TransportError as e:
        row["error"] = redact(f"{e.kind}: {e}", [api_key])
        if suggest and e.status == 400 and "not a valid model" in str(e).lower():
            avail = _fetch_available_models(base_url, api_key)
            if avail:
                row["suggestions"] = _suggest_models(avail, resolved_model)
        return row

    meta = last_call_meta()
    row["elapsed_s"] = meta.get("elapsed_s")
    row["usage"] = meta.get("usage")

    try:
        parsed = parse_reply(reply)
    except ParseError as e:
        row["status"] = "parse_error"
        row["error"] = f"{e}; raw={reply[:160]!r}"
        return row

    row["json_ok"] = True
    company_ok = str(parsed.get("company", "")).strip().lower().startswith("acme")
    try:
        total_ok = abs(float(parsed.get("total")) - EXPECTED["total"]) < 1e-6
    except (TypeError, ValueError):
        total_ok = False
    currency_ok = str(parsed.get("currency", "")).strip().upper() == EXPECTED["currency"]
    row["values_ok"] = company_ok and total_ok and currency_ok
    row["parsed"] = parsed
    row["status"] = "ok" if row["values_ok"] else "warn"
    if not row["values_ok"]:
        row["error"] = f"unexpected values: {parsed}"
    return row


def _print_result(r: dict) -> None:
    role = r["role"]
    if r["status"] == "skip":
        print(f"[{role}] SKIP: {r['reason']}")
        return
    tag = {"ok": "PASS", "warn": "WARN", "parse_error": "FAIL(JSON)", "fail": "FAIL"}.get(r["status"], "FAIL")
    elapsed = f"{r['elapsed_s']:.2f}s" if r["elapsed_s"] is not None else "-"
    print(f"[{role}] {tag}  model={r['model']}  host={r['endpoint']}  time={elapsed}")
    if r["status"] == "ok":
        print(f"       json=ok  values=ok  parsed={json.dumps(r['parsed'], ensure_ascii=False)}")
    elif r["status"] == "warn":
        print(f"       json=ok  values=mismatch  {r['error']}")
    else:
        print(f"       error: {r['error']}")
    if r.get("suggestions"):
        print("       valid model suggestions: " + ", ".join(r["suggestions"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", default="all", type=str.lower, choices=ROLE_CHOICES,
                    help="which model role to test (default: all configured)")
    ap.add_argument("--list-free", action="store_true",
                    help="list all free models on LLM_BASE_URL (/models) and test each for JSON usability")
    ap.add_argument("--no-probe", action="store_true",
                    help="with --list-free, only list free model IDs without sending test requests")
    ap.add_argument("--timeout", type=float, default=60.0, help="per-request timeout in seconds")
    ap.add_argument("--no-json-mode", action="store_true", help="disable response_format=json_object")
    ap.add_argument("--no-suggest", action="store_true", help="do not query /models on invalid model ID")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON summary")
    args = ap.parse_args(argv)

    if os.environ.get("EXTRACT_SKIP_DOTENV") != "1":
        load_env()
    try:
        cfg = llm_config()
    except RuntimeError as e:
        sys.exit(f"Config error: {e}")

    json_mode = False if args.no_json_mode else None

    if args.list_free:
        catalog = _fetch_models_catalog(cfg["LLM_BASE_URL"], cfg["LLM_API_KEY"])
        if catalog is None:
            sys.exit(f"Failed to query {cfg['LLM_BASE_URL'].rstrip('/')}/models")
        free_ids = sorted({str(item["id"]) for item in catalog if _is_free_model(item)})
        if args.no_probe:
            if args.json:
                print(json.dumps({"total_models": len(catalog), "free_models": free_ids}, indent=2))
            else:
                print(f"Total models: {len(catalog)}, free models: {len(free_ids)}")
                for mid in free_ids:
                    print(f"  {mid}")
            return 0 if free_ids else 1
        results = [
            test_role(cfg, f"free:{i}", mid, timeout=args.timeout, json_mode=json_mode, suggest=False)
            for i, mid in enumerate(free_ids, 1)
        ]
        if args.json:
            print(json.dumps({"total_models": len(catalog), "free_models": free_ids, "results": results},
                             indent=2, ensure_ascii=False))
        else:
            print(f"Found {len(free_ids)} free model(s) out of {len(catalog)} total on {urlparse(cfg['LLM_BASE_URL']).netloc}:")
            for r in results:
                _print_result(r)
        return 0 if any(r["status"] in ("ok", "warn") for r in results) else 1

    roles = model_roles()
    selected = ["default", "A", "B", "C", "ocr"] if args.role == "all" else [_canonical_role(args.role)]

    results = [
        test_role(cfg, r, roles.get(r), timeout=args.timeout, json_mode=json_mode, suggest=not args.no_suggest)
        for r in selected
    ]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            _print_result(r)

    tested = [r for r in results if r["status"] != "skip"]
    if not tested:
        return 1
    return 0 if all(r["status"] in ("ok", "warn") for r in tested) else 1


if __name__ == "__main__":
    sys.exit(main())
