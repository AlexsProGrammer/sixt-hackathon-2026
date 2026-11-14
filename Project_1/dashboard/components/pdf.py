"""Document viewer component: PDF (ExtractBench / upload) and highlighted contract text (CUAD)."""
from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Iterable

import streamlit as st

from dashboard import data
from pipeline import render


def resolve_pdf_path(rec: dict, data_dir: Path | None = None) -> Path | None:
    """Resolve the first PDF path on `rec['pages']` if present on disk."""
    ddir = Path(data_dir) if data_dir else data.DATA_DIR
    pages = rec.get("pages") or []
    for raw in pages:
        p = Path(str(raw))
        candidates = [p, ddir / p, data.ROOT / p]
        for c in candidates:
            if c.is_file() and c.suffix.lower() == ".pdf":
                return c
    return None


def render_pdf_bytes_or_path(pdf_path: Path | None = None, pdf_bytes: bytes | None = None) -> None:
    """Display a PDF via `st.pdf`, falling back to base64 `<iframe>` and `pdftoppm` PNGs."""
    if pdf_bytes is None and pdf_path is not None and pdf_path.is_file():
        pdf_bytes = pdf_path.read_bytes()
    if pdf_bytes is None:
        st.info("No PDF file available for this document.")
        return

    if hasattr(st, "pdf"):
        try:
            st.pdf(pdf_bytes, height=720)
            return
        except Exception:
            pass

    if len(pdf_bytes) <= 8 * 1024 * 1024:
        b64 = base64.b64encode(pdf_bytes).decode("ascii")
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="720" type="application/pdf"></iframe>',
            unsafe_allow_html=True,
        )
        return

    if pdf_path is not None and pdf_path.is_file():
        imgs = render.render_pages(pdf_path, dpi=150, max_pages=10)
        if imgs:
            for img in imgs:
                st.image(str(img), use_container_width=True)
            return

    st.warning("Could not render PDF inline.")


def _find_span_ranges(text: str, values: Iterable[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    lower_text = text.lower()
    for val in values:
        s = str(val or "").strip()
        if len(s) < 4:
            continue
        idx = lower_text.find(s.lower())
        if idx >= 0:
            ranges.append((idx, idx + len(s)))
    return ranges


def annotate_contract_html(text: str, pred_spans: Iterable[str], gold_spans: Iterable[str]) -> str:
    """Return escaped HTML with predicted spans highlighted (<mark>) and gold spans underlined (<u>)."""
    pred_ranges = _find_span_ranges(text, pred_spans)
    gold_ranges = _find_span_ranges(text, gold_spans)
    if not pred_ranges and not gold_ranges:
        return f"<pre style='white-space:pre-wrap;font-size:13px;line-height:1.45;'>{html.escape(text)}</pre>"

    events: set[int] = {0, len(text)}
    for a, b in pred_ranges + gold_ranges:
        events.add(a)
        events.add(b)
    cuts = sorted(events)

    parts: list[str] = ["<div style='white-space:pre-wrap;font-family:monospace;font-size:13px;line-height:1.45;'>"]
    for i in range(len(cuts) - 1):
        start, end = cuts[i], cuts[i + 1]
        if start == end:
            continue
        chunk = html.escape(text[start:end])
        in_pred = any(a <= start and end <= b for a, b in pred_ranges)
        in_gold = any(a <= start and end <= b for a, b in gold_ranges)
        if in_pred and in_gold:
            parts.append(f"<mark style='background:#fde68a;border-bottom:2px solid #16a34a;'><u>{chunk}</u></mark>")
        elif in_pred:
            parts.append(f"<mark style='background:#fde68a;'>{chunk}</mark>")
        elif in_gold:
            parts.append(f"<u style='text-decoration-color:#16a34a;text-decoration-thickness:2px;'>{chunk}</u>")
        else:
            parts.append(chunk)
    parts.append("</div>")
    return "".join(parts)


def render_document_pane(rec: dict, field_rows: list[dict], *, data_dir: Path | None = None) -> None:
    """Render the left-hand document pane (PDF for ExtractBench/uploads, highlighted text for CUAD)."""
    pdf_path = resolve_pdf_path(rec, data_dir=data_dir)
    if pdf_path is not None:
        render_pdf_bytes_or_path(pdf_path=pdf_path)
        return

    from pipeline import extractor
    text = extractor.full_text(rec, data_dir=Path(data_dir) if data_dir else data.DATA_DIR)
    if not text:
        st.info("No PDF or text layer available for this document.")
        return

    pred_spans: list[str] = []
    gold_spans: list[str] = []
    for r in field_rows:
        if r.get("value") not in (None, "", []):
            if isinstance(r["value"], list):
                pred_spans.extend(str(x) for x in r["value"])
            else:
                pred_spans.append(str(r["value"]))
        if r.get("gold") not in (None, "", []):
            if isinstance(r["gold"], list):
                gold_spans.extend(str(x) for x in r["gold"])
            else:
                gold_spans.append(str(r["gold"]))

    st.caption("Highlighted = predicted span · Underlined = gold span")
    rendered = annotate_contract_html(text[:120_000], pred_spans, gold_spans)
    with st.container(height=700, border=True):
        st.markdown(rendered, unsafe_allow_html=True)
