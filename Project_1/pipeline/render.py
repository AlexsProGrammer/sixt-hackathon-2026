"""Render PDF pages to PNG with pdftoppm. Cached under cache/render/<pdf_sha256>/<dpi>/page-N.png."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"
_PAGE_RE = re.compile(r"-(\d+)\.png$")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cached(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[1])) if out_dir.is_dir() else []


def render_pages(pdf_path: Path | str, dpi: int = 150, max_pages: int = 10, *,
                 cache_root: Path | None = None, timeout: float = 120.0) -> list[Path]:
    """Render up to max_pages pages. Returns the PNG paths in page order, or [] on any failure (missing pdftoppm,
    corrupted PDF, timeout). A cached render is reused only if it has at least min(max_pages, rendered) pages."""
    pdf = Path(pdf_path)
    exe = shutil.which("pdftoppm")
    if exe is None or not pdf.is_file():
        return []
    try:
        sha = file_sha256(pdf)
    except OSError:
        return []
    out_dir = Path(cache_root or CACHE_ROOT) / "render" / sha / str(dpi)
    have = _cached(out_dir)
    if have and (len(have) >= max_pages or (out_dir / ".complete").exists()):
        return have[:max_pages]
    tmp_parent = out_dir.parent
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=tmp_parent, prefix=f".{dpi}-"))
    try:
        proc = subprocess.run([exe, "-r", str(dpi), "-png", "-f", "1", "-l", str(max_pages), str(pdf), str(tmp / "page")],
                              capture_output=True, timeout=timeout)
        if proc.returncode != 0:
            return []
        pages = []
        for p in tmp.glob("page-*.png"):
            m = _PAGE_RE.search(p.name)
            if m:
                pages.append((int(m.group(1)), p))
        if not pages:
            return []
        pages.sort()
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        for n, p in pages:
            p.replace(out_dir / f"page-{n}.png")
        if len(pages) < max_pages:
            (out_dir / ".complete").touch()  # the document has fewer pages than max_pages
        return _cached(out_dir)
    except (subprocess.TimeoutExpired, OSError):
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
