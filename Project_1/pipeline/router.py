"""Document router (T05): assigns every record to one route before extraction.

    route(rec) -> {"route", "text", "text_source", "quality", "quality_features"}

| route              | condition                                                                       |
|--------------------|---------------------------------------------------------------------------------|
| cuad               | source_dataset == "cuad"                                                        |
| pdf_text_good      | ExtractBench, text layer present, quality >= tau_q                              |
| pdf_text_damaged   | ExtractBench, text layer present, quality <  tau_q                              |
| pdf_no_text        | ExtractBench, no text layer (scan, image page)                                  |
| pdf_corrupted      | every available text engine failed AND the first page cannot be rendered         |

The text-layer readers (`pdf_text`, `full_text`, `page_path`, `load_cuad`) live here; 4_extract.py re-imports them.
The router never reads gold and never raises: any problem with a document becomes route `pdf_corrupted`.

    python -m pipeline.router --data data/splits/fit.jsonl --summary
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):                      # `python pipeline/router.py` works as well
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import text_quality  # noqa: E402

logging.getLogger("pypdf").setLevel(logging.ERROR)   # damaged PDFs are routed, not reported line by line

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "router_config.json"
ROUTES = ("cuad", "pdf_text_good", "pdf_text_damaged", "pdf_no_text", "pdf_corrupted")
FAMILY_TITLE_CHARS = 45           # same truncation as evaluation.docs.family_of
QUALITY_SAMPLE_CHARS = 100_000    # quality of very long texts is measured on the first 100k characters
CUAD_QUALITY_CHARS = 20_000       # CUAD texts are clean; a short sample keeps routing cheap
DEFAULT_CONFIG = {"version": 1, "tau_q": 0.6, "w_clipped": text_quality.W_CLIPPED, "w_odd": text_quality.W_ODD,
                  "damaged_families": []}
_UNSET = object()


# ---------------------------------------------------------------- configuration

def default_data_dir() -> Path:
    """EXTRACT_DATA_DIR overrides the data folder (tests with synthetic data). Read on every call."""
    env = os.environ.get("EXTRACT_DATA_DIR")
    return Path(env) if env else ROOT / "data"


@lru_cache(maxsize=4)
def _load_config(path: str) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_CONFIG)
    return {**DEFAULT_CONFIG, **cfg} if isinstance(cfg, dict) else dict(DEFAULT_CONFIG)


def load_config(path: Path | str | None = None) -> dict:
    return _load_config(str(path or CONFIG_PATH))


def family_of(rec: dict) -> str | None:
    """schema.title cut to 45 characters, the same family key as evaluation.docs.family_of (None without title)."""
    title = (rec.get("schema") or {}).get("title")
    return str(title)[:FAMILY_TITLE_CHARS] if title else None


# ---------------------------------------------------------------- document paths and CUAD text

def page_path(stored: str, data_dir: Path | None = None) -> Path:
    """Map a record's page path to a local file. Records store Windows separators; normalise them
    so one record resolves the same way on Windows, Linux and macOS."""
    data = Path(data_dir) if data_dir is not None else default_data_dir()
    parts = [p for p in stored.replace("\\", "/").split("/") if p and p != "."]
    if not parts or ".." in parts:
        raise ValueError(f"unsafe page path in record: {stored!r}")
    path = data.joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"document not found: data/{'/'.join(parts)}")
    return path


_cuad: dict[str, dict] = {}


def load_cuad(data_dir: Path | None = None) -> dict:
    """CUAD texts, loaded once per data folder. Call before any worker pool starts."""
    data = Path(data_dir) if data_dir is not None else default_data_dir()
    key = str(data)
    if key not in _cuad:
        raw = json.loads((data / "raw/cuad/CUADv1.json").read_text(encoding="utf-8"))["data"]
        _cuad[key] = {d["title"]: "\n".join(p["context"] for p in d["paragraphs"]) for d in raw}
    return _cuad[key]


# ---------------------------------------------------------------- PDF text engines

def _signature(path: Path) -> tuple[str, int, int]:
    st = path.stat()
    return str(path), st.st_mtime_ns, st.st_size


@lru_cache(maxsize=64)
def _pdftotext(sig: tuple, available: bool) -> tuple[str | None, bool | None]:
    """(text, ok). ok is None when the engine is not installed, False on an error, True otherwise."""
    if not available:
        return None, None
    try:
        r = subprocess.run(["pdftotext", "-layout", sig[0], "-"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None, False
    if r.returncode != 0:
        return None, False
    return r.stdout, True


@lru_cache(maxsize=64)
def _pypdf(sig: tuple) -> tuple[str | None, bool | None]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, None
    try:
        return "\n".join(p.extract_text() or "" for p in PdfReader(sig[0]).pages), True
    except Exception:  # broken or image-only PDF
        return None, False


def _engines(path: Path) -> dict:
    sig = _signature(path)
    return {"pdftotext": _pdftotext(sig, shutil.which("pdftotext") is not None), "pypdf": _pypdf(sig)}


def _pick(engines: dict) -> tuple[str | None, str | None]:
    """First engine with non-blank text: pdftotext, then pypdf. Returns (text, source)."""
    for name in ("pdftotext", "pypdf"):
        text = engines[name][0]
        if text and text.strip():
            return text, name
    return None, None


def pdf_text(path: Path) -> str | None:
    """Text of all pages (pdftotext reads the whole file; pypdf fallback reads every page).
    pypdf is only read when pdftotext is missing, failed or found no text."""
    sig = _signature(Path(path))
    text, ok = _pdftotext(sig, shutil.which("pdftotext") is not None)
    if text and text.strip():
        return text
    text, ok = _pypdf(sig)
    return text if text and text.strip() else None


def full_text(rec: dict, data_dir: Path | None = None) -> str | None:
    """Complete document text, never truncated. None means no text layer (scan or unreadable PDF)."""
    if rec["source_dataset"] == "cuad":
        return load_cuad(data_dir)[rec["doc_id"].split(":", 1)[1]]
    page = page_path(rec["pages"][0], data_dir)
    if page.suffix.lower() != ".pdf":
        return None
    return pdf_text(page)


def can_render_first_page(path: Path) -> bool:
    """True when pdftoppm renders page 1 (a file that renders is a scan, not a corrupted file)."""
    exe = shutil.which("pdftoppm")
    if exe is None:
        return False
    with tempfile.TemporaryDirectory(prefix="router-render-") as tmp:
        try:
            r = subprocess.run([exe, "-r", "30", "-png", "-f", "1", "-l", "1", str(path), str(Path(tmp) / "p")],
                               capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and any(Path(tmp).glob("p-*.png"))


# ---------------------------------------------------------------- routing

def _result(route_name: str, text: str | None = None, source: str | None = None, quality: float = 0.0,
            feats: dict | None = None) -> dict:
    return {"route": route_name, "text": text, "text_source": source, "quality": quality,
            "quality_features": feats or {}}


def _score(text: str, other: str | None, rec: dict, cfg: dict) -> tuple[float, dict]:
    fam = family_of(rec)
    flagged = bool(fam and fam in set(cfg.get("damaged_families") or []))
    feats = text_quality.features(text[:QUALITY_SAMPLE_CHARS], other[:QUALITY_SAMPLE_CHARS] if other else None)
    feats["family_flagged"] = flagged
    return text_quality.score(feats, cfg.get("w_clipped"), cfg.get("w_odd")), feats


def _verdict(q: float, feats: dict, cfg: dict) -> str:
    """Damaged when the score is below tau_q, or when the document belongs to a family whose text layer was
    found damaged offline (tools/tune_quality.py): single dropped glyphs are invisible to the dictionary score."""
    return "pdf_text_damaged" if (q < cfg["tau_q"] or feats.get("family_flagged")) else "pdf_text_good"


def route(rec: dict, data_dir: Path | None = None, text=_UNSET, config: dict | None = None) -> dict:
    """Route one record. `text` (a string or None) bypasses file reading: the router classifies a text layer
    that the caller already holds (field table, tests). Never raises."""
    try:
        return _route(rec, data_dir, text, config or load_config())
    except Exception:  # a document the router cannot even open must still get a route
        return _result("pdf_corrupted")


def _route(rec: dict, data_dir: Path | None, given, cfg: dict) -> dict:
    if rec.get("source_dataset") == "cuad":
        try:
            body = load_cuad(data_dir)[rec["doc_id"].split(":", 1)[1]] if given is _UNSET else given
        except Exception:
            body = None
        if not body:
            return _result("cuad", None, "cuad")
        q, feats = _score(body[:CUAD_QUALITY_CHARS], None, rec, cfg)
        return _result("cuad", body, "cuad", q, feats)

    try:
        page = page_path(rec["pages"][0], data_dir)
    except (FileNotFoundError, ValueError, KeyError, IndexError):
        if given is _UNSET:
            raise
        page = None   # the caller holds the text of a file we cannot open: classify the text only
    if given is not _UNSET and given and given.strip():
        text, source, other = given, "given", None
        if page is not None and page.suffix.lower() == ".pdf":
            eng = _engines(page)
            picked, name = _pick(eng)
            if picked == given:       # the given text is the engine output: record which one and cross-check
                source, other = name, eng["pypdf" if name == "pdftotext" else "pdftotext"][0]
        q, feats = _score(text, other, rec, cfg)
        return _result(_verdict(q, feats, cfg), text, source, q, feats)
    if page is None or page.suffix.lower() != ".pdf":
        return _result("pdf_no_text")
    engines = _engines(page)
    text, source = _pick(engines) if given is _UNSET else (None, None)   # a blank given text is authoritative
    if text is None:
        available = [name for name, (_, ok) in engines.items() if ok is not None]
        failed = all(engines[name][1] is False for name in available)   # also true when no engine is installed
        if failed and not can_render_first_page(page):
            return _result("pdf_corrupted")
        return _result("pdf_no_text")
    other_name = "pypdf" if source == "pdftotext" else "pdftotext"
    q, feats = _score(text, engines[other_name][0], rec, cfg)
    return _result(_verdict(q, feats, cfg), text, source, q, feats)


def route_name(rec: dict, **kw) -> str:
    return route(rec, **kw)["route"]


# ---------------------------------------------------------------- command line

def summarise(recs: list[dict], data_dir: Path | None = None) -> dict:
    counts: Counter = Counter()
    by_family: dict[str, Counter] = {}
    for rec in recs:
        r = route(rec, data_dir)
        counts[r["route"]] += 1
        by_family.setdefault(family_of(rec) or rec.get("source_dataset", "?"), Counter())[r["route"]] += 1
    return {"n": len(recs), "routes": dict(counts), "by_family": {k: dict(v) for k, v in sorted(by_family.items())}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="records file, e.g. data/splits/fit.jsonl (gold is never read)")
    ap.add_argument("--summary", action="store_true", help="route counts, overall and per family")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    recs = [json.loads(line) for line in open(a.data, encoding="utf-8") if line.strip()]
    recs = recs[: a.limit] if a.limit else recs
    if a.summary:
        s = summarise(recs)
        print(f"{s['n']} documents, tau_q={load_config()['tau_q']}")
        for name in ROUTES:
            print(f"  {name:<18} {s['routes'].get(name, 0):>5}")
        print("per family:")
        for fam, c in s["by_family"].items():
            print(f"  {fam[:46]:<46} " + " ".join(f"{k}={v}" for k, v in sorted(c.items())))
        return 0
    for rec in recs:
        r = route(rec)
        print(json.dumps({"doc_id": rec["doc_id"], "route": r["route"], "text_source": r["text_source"],
                          "quality": r["quality"], "quality_features": r["quality_features"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
