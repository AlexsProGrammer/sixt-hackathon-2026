"""Document profile helpers shared by the splits, the field table and the reports (T03).

- family_of      CUAD -> "cuad"; ExtractBench -> schema.title[:45]; documents without a title -> "stem:<file prefix>"
- perception_of  "P0" (no perception tag) or the sorted perception tags joined by "+" ("P2", "P2+P3", ...)
- doc_text       the text layer exactly as 4_extract.py reads it (pdftotext / pypdf / CUAD json), None when absent
- text_quality   coarse 0..1 score of a text layer. PLACEHOLDER until T05 provides the real quality gate.
- route_of       route name used in the field table (T05 router when available, else a provisional name)

Gold is never read here.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAMILY_TITLE_CHARS = 45          # same truncation as analyse_fields.py, so old numbers stay comparable
DAMAGED_FAMILY_PREFIXES = ("Schedule K-1",)   # known: the text layer has dropped/garbled glyphs
CUAD_LONG_CHARS = 45000          # = pipeline chunk size: longer documents need several chunks

_extractor = None


def load_extractor():
    """4_extract.py loaded by path (its name is not importable), once. Honours EXTRACT_DATA_DIR."""
    global _extractor
    if _extractor is None:
        spec = importlib.util.spec_from_file_location("extract4_harness", ROOT / "4_extract.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _extractor = mod
    return _extractor


def family_of(rec: dict) -> str:
    if rec.get("source_dataset") == "cuad":
        return "cuad"
    title = (rec.get("schema") or {}).get("title")
    if title:
        return str(title)[:FAMILY_TITLE_CHARS]
    stem = Path(str(rec["doc_id"]).split("/", 1)[-1]).stem
    prefix = stem.split("__", 1)[0] if "__" in stem else "_".join(re.split(r"[_-]", stem)[:2])
    return f"stem:{prefix}"


def perception_of(rec: dict) -> str:
    tags = sorted(t.split(":", 1)[1] for t in rec.get("tags") or [] if t.startswith("perception:"))
    return "+".join(tags) if tags else "P0"


def is_damaged_family(family: str) -> bool:
    return family.startswith(DAMAGED_FAMILY_PREFIXES)


def doc_text(rec: dict) -> str | None:
    """Full text of the document as the extractor sees it. None = no text layer or unreadable."""
    try:
        text = load_extractor().full_text(rec)
    except Exception:
        return None
    return text if text and text.strip() else None


_VOWEL = re.compile(r"[aeiouyAEIOUY]")
_CONSONANT_RUN = re.compile(r"[^aeiouyAEIOUY\W\d_]{6,}")


def text_quality(text: str | None) -> float:
    """Coarse text-layer quality in [0, 1]: share of plausible words (has a vowel, no run of 6 consonants),
    scaled down for very short layers. It cannot see single dropped glyphs ("Utillties"), which is why
    known-damaged families are listed in DAMAGED_FAMILY_PREFIXES. T05 replaces this with the real gate."""
    if not text or not text.strip():
        return 0.0
    words = re.findall(r"[A-Za-z]{3,}", text)
    if not words:
        return 0.0
    ok = sum(1 for w in words if _VOWEL.search(w) and not _CONSONANT_RUN.search(w))
    return round((ok / len(words)) * min(1.0, len(text.strip()) / 200.0), 4)


def provisional_route(rec: dict, text: str | None, quality: float) -> str:
    """Placeholder route names: cuad_text | no_text | text_damaged | text_poor | text_ok."""
    if rec.get("source_dataset") == "cuad":
        return "cuad_text"
    if not text:
        return "no_text"
    if is_damaged_family(family_of(rec)):
        return "text_damaged"
    return "text_ok" if quality >= 0.5 else "text_poor"


def route_of(rec: dict, text: str | None, quality: float) -> str:
    """Route from T05 (`pipeline.router.route`) when it exists, else the provisional name."""
    try:
        from pipeline.router import route  # type: ignore
    except ImportError:
        return provisional_route(rec, text, quality)
    try:
        r = route(rec)
        return str(getattr(r, "name", None) or getattr(r, "route", None) or r)
    except Exception:
        return provisional_route(rec, text, quality)
