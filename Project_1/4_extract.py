#!/usr/bin/env python3
"""Minimal extractor to start from. Offline keyword rules by default; an LLM if LLM_BASE_URL, LLM_API_KEY, LLM_MODEL are set.
    python 4_extract_example.py --data data/unified/dev.jsonl --out preds.jsonl --limit 10 [--mode llm|offline]
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
MAX_CHARS = 60_000
LLM_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


def load_env(path: Path = HERE / ".env") -> list[str]:
    """Load KEY=VALUE lines from .env into os.environ. Variables that are already set are never overwritten.
    Returns the names that were loaded (never the values)."""
    loaded = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()  # splitlines() also handles CRLF
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
        if sep and key and val and key not in os.environ:
            os.environ[key] = val
            loaded.append(key)
    return loaded



def llm_config() -> dict:
    """The three LLM settings. Raises RuntimeError naming the missing variables (never their values)."""
    cfg = {k: os.environ.get(k, "").strip() for k in LLM_VARS}
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise RuntimeError("LLM config missing: " + ", ".join(missing)
                           + " (set in the environment or in Project_1/.env)")
    if not cfg["LLM_BASE_URL"].lower().startswith(("https://", "http://")):
        raise RuntimeError("LLM_BASE_URL has no http:// or https:// scheme (fix the value in Project_1/.env)")
    return cfg

def page_path(stored: str) -> Path:
    """Map a record's page path to a local file. Records store Windows separators ('raw\\extractbench\\...').
    Normalise them so one record resolves the same way on Windows, Linux and macOS."""
    parts = [p for p in stored.replace("\\", "/").split("/") if p and p != "."]
    if not parts or ".." in parts:
        raise ValueError(f"unsafe page path in record: {stored!r}")
    path = DATA.joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"document not found: data/{'/'.join(parts)}")
    return path

PROMPT = """Extract the fields below from the document. Reply with ONE JSON object and nothing else:
{{"<field>": {{"value": <string, number, JSON for nested fields, or null>, "confidence": <0..1>}}, ...}}
Rules:
- Copy values as printed in the document. Do not guess, infer or compute.
- If a field is not in the document, or you cannot read it, use null. A wrong value costs 100 times more than a null.
- Confidence is how sure you are the value is exactly right.

Fields (name: description):
{fields}
"""


def describe(schema: dict) -> str:
    out = []
    for name, spec in schema["properties"].items():
        desc = spec.get("description") or spec.get("title") or spec.get("type") or ""
        kind = spec.get("x-normalizer")
        out.append(f"- {name}" + (f" [{kind}]" if kind else "") + (f": {str(desc)[:300]}" if desc else ""))
    return "\n".join(out)


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


_cuad = None


def cuad_text(doc_id: str) -> str:
    global _cuad
    if _cuad is None:
        raw = json.loads((DATA / "raw/cuad/CUADv1.json").read_text(encoding="utf-8"))["data"]
        _cuad = {d["title"]: "\n".join(p["context"] for p in d["paragraphs"]) for d in raw}
    return _cuad[doc_id.split(":", 1)[1]]


def build_content(rec: dict) -> tuple[list, str | None]:
    prompt = PROMPT.format(fields=describe(rec["schema"]))
    page = page_path(rec["pages"][0])
    if rec["source_dataset"] == "cuad":
        text = cuad_text(rec["doc_id"])[:MAX_CHARS]
        return [{"type": "text", "text": f"{prompt}\n--- DOCUMENT ---\n{text}"}], text
    if page.suffix.lower() == ".pdf":
        text = pdf_text(page)
        if text:
            text = text[:MAX_CHARS]
            return [{"type": "text", "text": f"{prompt}\n--- DOCUMENT ---\n{text}"}], text
    # no text available: attach the file for a vision-capable model
    mime = mimetypes.guess_type(page.name)[0] or "application/octet-stream"
    url = f"data:{mime};base64,{base64.b64encode(page.read_bytes()).decode()}"
    part = ({"type": "image_url", "image_url": {"url": url}} if mime.startswith("image/")
            else {"type": "file", "file": {"filename": page.name, "file_data": url}})
    return [{"type": "text", "text": prompt}, part], None


def call_llm(content: list) -> str:
    cfg = llm_config()
    key = cfg["LLM_API_KEY"]
    redact = lambda s: str(s).replace(key, "***")
    body = json.dumps({"model": cfg["LLM_MODEL"], "temperature": 0,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request(cfg["LLM_BASE_URL"].rstrip("/") + "/chat/completions", body,
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        detail = redact(e.read(300).decode("utf-8", "replace")).strip()
        raise RuntimeError(f"LLM endpoint returned HTTP {e.code}: {detail[:300]}") from None
    except ValueError:
        raise RuntimeError("LLM endpoint returned a non-JSON body") from None
    except OSError as e:  # URLError, timeouts, connection resets
        raise RuntimeError(f"LLM endpoint unreachable or timed out: {redact(getattr(e, 'reason', e))}") from None
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("unexpected LLM response format: " + redact(str(payload)[:300])) from None


def parse_json(reply: str) -> dict:
    s = reply.strip()
    if s.startswith("```"):
        s = s.strip("`").removeprefix("json").strip()
    try:
        return json.loads(s[s.index("{"): s.rindex("}") + 1])
    except ValueError:
        return {}


def grounded(value, text: str | None) -> bool:
    if text is None or isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 80:
        return True
    squash = lambda s: "".join(str(s).lower().split()).replace(",", "")
    return squash(value) in squash(text)


def doc_text(rec: dict) -> str | None:
    if rec["source_dataset"] == "cuad":
        return cuad_text(rec["doc_id"])[:MAX_CHARS]
    page = page_path(rec["pages"][0])
    return (pdf_text(page) or "")[:MAX_CHARS] or None if page.suffix.lower() == ".pdf" else None


PATTERNS = {
    "amount": r"-?\d[\d.,]*\d|\d",
    "date": r"\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]{2,8}\.? \d{4}",
    "id": r"[A-Za-z0-9][A-Za-z0-9\-/]{3,}",
}


def offline_extract(rec: dict) -> dict:
    text = doc_text(rec)
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


def extract(rec: dict) -> dict:
    content, text = build_content(rec)
    answer = parse_json(call_llm(content))
    fields = {}
    for name in rec["schema"]["properties"]:
        a = answer.get(name)
        a = a if isinstance(a, dict) else {"value": a}
        value, conf = a.get("value"), a.get("confidence", 0.5)
        try:
            conf = min(max(float(conf), 0.0), 1.0)
        except (TypeError, ValueError):
            conf = 0.0
        if value is not None and not grounded(value, text):
            conf *= 0.5
        fields[name] = {"value": value, "confidence": round(conf, 3)}
    return {"doc_id": rec["doc_id"], "fields": fields}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="e.g. data/unified/dev.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, help="only the first N documents (start small: LLM calls cost money)")
    ap.add_argument("--mode", choices=["auto", "llm", "offline"], default="auto",
                    help="llm: fail loudly if config is missing or an API call fails. "
                         "auto: LLM if config is complete, else offline rules with a warning. offline: rules only.")
    a = ap.parse_args()
    loaded = load_env()
    if loaded:
        print(f"loaded from .env (names only): {', '.join(loaded)}", file=sys.stderr)
    if a.mode == "offline":
        use_llm = False
    else:
        try:
            llm_config()
            use_llm = True
        except RuntimeError as e:
            if a.mode == "llm":
                sys.exit(f"ERROR: {e}. Nothing was written.")
            print(f"WARNING: {e}. --mode auto is using OFFLINE rules (use --mode llm to fail instead).", file=sys.stderr)
            use_llm = False
    print(f"mode: {'LLM' if use_llm else 'offline rules (no API key needed)'}", file=sys.stderr)
    run_one = extract if use_llm else offline_extract
    recs = [json.loads(line) for line in open(a.data, encoding="utf-8") if line.strip()]
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(line)["doc_id"] for line in open(a.out, encoding="utf-8") if line.strip()}
    failed = []
    with open(a.out, "a", encoding="utf-8") as fout:
        for i, rec in enumerate(recs[: a.limit]):
            if rec["doc_id"] in done:
                continue
            try:
                row = run_one(rec)
            except Exception as e:
                print(f"[{i}] {rec['doc_id']}: ERROR {type(e).__name__}: {e}", file=sys.stderr)
                if use_llm:
                    failed.append(rec["doc_id"])  # not written, so a rerun retries it
                    continue
                row = {"doc_id": rec["doc_id"], "fields": {f: {"value": None} for f in rec["schema"]["properties"]}}
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{i}] {rec['doc_id']}", file=sys.stderr)
    if failed:
        shown = ", ".join(failed[:5]) + (" ..." if len(failed) > 5 else "")
        print(f"ERROR: {len(failed)} document(s) failed in LLM mode and were NOT written. Rerun to retry: {shown}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
