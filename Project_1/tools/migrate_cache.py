#!/usr/bin/env python3
"""Migrate the legacy flat reply cache (cache/<xx>/<key>.json) to the v2 layout
cache/replies/<model_slug>/<prompt_version>/<xx>/<key>.json. Stdlib only.

Also reports and archives the retired HTTP-level cache (cache/http/*) to cache/_archive/http/. Those raw payloads
cannot be mapped to ReplyCache keys (the request messages are unknown), so they are archived, never deleted.

  python tools/migrate_cache.py --dry-run [--cache-dir cache]
  python tools/migrate_cache.py            # move
  python tools/migrate_cache.py --copy     # copy, keep the legacy files
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from pipeline.transport import ParseError, ReplyCache, model_slug, parse_reply  # noqa: E402

LEGACY_DIR = re.compile(r"^[0-9a-f]{2}$")


def legacy_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if d.is_dir() and LEGACY_DIR.match(d.name):
            out.extend(sorted(d.glob("*.json")))
    return out


def target_for(root: Path, path: Path, entry: dict | None) -> tuple[Path, str, str]:
    model = (entry or {}).get("model") if isinstance(entry, dict) else None
    pv = (entry or {}).get("prompt_version") if isinstance(entry, dict) else None
    cache = ReplyCache(root)
    key = path.stem
    target = cache._path(key, model, pv)
    return target, model_slug(model), (pv or "_unknown")


def migrate_replies(root: Path, *, dry_run: bool, copy: bool) -> tuple[Counter, dict]:
    counts: Counter = Counter()
    stats = {"moved": 0, "copied": 0, "skipped_existing": 0, "unreadable": 0}
    for path in legacy_files(root):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entry, dict):
                raise ValueError
        except (OSError, ValueError):
            entry = None
            stats["unreadable"] += 1
        target, slug, pv = target_for(root, path, entry)
        counts[(slug, pv)] += 1
        if dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            stats["skipped_existing"] += 1
            if not copy:
                path.unlink()
            continue
        if copy:
            shutil.copy2(path, target)
            stats["copied"] += 1
        else:
            shutil.move(str(path), str(target))
            stats["moved"] += 1
    if not dry_run and not copy:
        for d in root.iterdir():  # drop emptied legacy shard dirs
            if d.is_dir() and LEGACY_DIR.match(d.name) and not any(d.iterdir()):
                d.rmdir()
    return counts, stats


def http_report(root: Path) -> dict:
    http = root / "http"
    rep = {"entries": 0, "parseable_reply": 0, "unparseable": 0, "models": Counter()}
    if not http.is_dir():
        return rep
    for p in sorted(http.glob("*.json")):
        rep["entries"] += 1
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            parse_reply(payload["choices"][0]["message"]["content"])
            rep["parseable_reply"] += 1
            rep["models"][str(payload.get("model", "?"))] += 1
        except (OSError, ValueError, KeyError, IndexError, TypeError, ParseError):
            rep["unparseable"] += 1
    return rep


def archive_http(root: Path, *, dry_run: bool, copy: bool) -> int:
    http = root / "http"
    if dry_run or not http.is_dir():
        return 0
    dest = root / "_archive" / "http"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(http.iterdir()):
        if not p.is_file():
            continue
        if copy:
            shutil.copy2(p, dest / p.name)
        else:
            shutil.move(str(p), str(dest / p.name))
        n += 1
    if not copy and not any(http.iterdir()):
        http.rmdir()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", default=str(HERE.parent / "cache"))
    ap.add_argument("--dry-run", action="store_true", help="print counts per (model, prompt_version), change nothing")
    ap.add_argument("--copy", action="store_true", help="copy instead of move (legacy files stay)")
    a = ap.parse_args(argv)
    root = Path(a.cache_dir)
    if not root.is_dir():
        print(f"cache dir not found: {root}", file=sys.stderr)
        return 2
    counts, stats = migrate_replies(root, dry_run=a.dry_run, copy=a.copy)
    print(f"{'DRY RUN: ' if a.dry_run else ''}legacy reply entries per (model_slug, prompt_version):")
    for (slug, pv), n in sorted(counts.items()):
        print(f"  {slug:40s} {pv:8s} {n:6d}")
    print(f"  total {sum(counts.values())}")
    if not a.dry_run:
        print(f"  {stats}")
    elif stats["unreadable"]:
        print(f"  unreadable entries (go to _unknown): {stats['unreadable']}")
    rep = http_report(root)
    print(f"cache/http: {rep['entries']} entries, {rep['parseable_reply']} with a parseable reply, "
          f"{rep['unparseable']} not; models: {dict(rep['models'])}")
    print("  (not mappable to reply-cache keys; archived to cache/_archive/http/, never deleted)")
    if not a.dry_run:
        print(f"  archived {archive_http(root, dry_run=False, copy=a.copy)} http files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
