#!/usr/bin/env python3
"""Reply cache statistics per model / prompt version, and purge. Stdlib only.

  python tools/cache_stats.py
  python tools/cache_stats.py --purge vertex_ai/gemini-3.7-flash [--prompt-version v2] --yes
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from pipeline.transport import model_slug  # noqa: E402


def collect(root: Path) -> list[tuple[str, str, int, int]]:
    rows = []
    base = root / "replies"
    if not base.is_dir():
        return rows
    for m in sorted(p for p in base.iterdir() if p.is_dir()):
        for pv in sorted(p for p in m.iterdir() if p.is_dir()):
            files = [f for f in pv.rglob("*.json")]
            rows.append((m.name, pv.name, len(files), sum(f.stat().st_size for f in files)))
    return rows


def legacy_count(root: Path) -> int:
    n = 0
    for d in root.iterdir() if root.is_dir() else []:
        if d.is_dir() and len(d.name) == 2:
            n += len(list(d.glob("*.json")))
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", default=str(HERE.parent / "cache"))
    ap.add_argument("--purge", metavar="MODEL", help="model name or slug to delete")
    ap.add_argument("--prompt-version", help="restrict --purge to one prompt version")
    ap.add_argument("--yes", action="store_true", help="confirm the purge (otherwise only prints what would go)")
    a = ap.parse_args(argv)
    root = Path(a.cache_dir)

    if a.purge:
        slug = model_slug(a.purge) if ("/" in a.purge or ":" in a.purge) else a.purge
        target = root / "replies" / slug
        if a.prompt_version:
            target = target / a.prompt_version
        if not target.is_dir():
            print(f"nothing to purge: {target} does not exist", file=sys.stderr)
            return 1
        n = sum(1 for _ in target.rglob("*.json"))
        if not a.yes:
            print(f"would delete {n} entries under {target} (add --yes to confirm)")
            return 0
        shutil.rmtree(target)
        print(f"deleted {n} entries under {target}")
        return 0

    rows = collect(root)
    print(f"{'model':40s} {'prompt':8s} {'entries':>8s} {'MB':>8s}")
    for m, pv, n, size in rows:
        print(f"{m:40s} {pv:8s} {n:8d} {size / 1e6:8.2f}")
    print(f"{'total':40s} {'':8s} {sum(r[2] for r in rows):8d} {sum(r[3] for r in rows) / 1e6:8.2f}")
    legacy = legacy_count(root)
    if legacy:
        print(f"legacy flat entries not yet migrated: {legacy} (run tools/migrate_cache.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
