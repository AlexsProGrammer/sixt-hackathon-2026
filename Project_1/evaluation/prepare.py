"""Deterministic group-aware split of dev into dev_train (~70%) and dev_cal (~30%).

Pages of one filing share a group id (doc_id without the trailing "-pNNNN"), so they always land in the same split.
Assignment uses SHA-256 of "seed:group", so it is reproducible and does not depend on row order.

Writes to --out-dir:
  dev_train_gold.jsonl  dev_train_input.jsonl  dev_cal_gold.jsonl  dev_cal_input.jsonl  split_manifest.json
The *_input files contain no gold field (keys starting with "gold" are removed).

    python -m evaluation.prepare --data data/unified/dev.jsonl --out-dir results/split --seed 42
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

TRAIN_SHARE = 0.7


def group_of(doc_id: str) -> str:
    return re.sub(r"-p\d+$", "", doc_id)


def split_of(group: str, seed: int) -> str:
    bucket = int(hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "dev_train" if bucket < TRAIN_SHARE else "dev_cal"


def strip_gold(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("gold")}


def split(records: list[dict], seed: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"dev_train": [], "dev_cal": []}
    for rec in records:
        out[split_of(group_of(rec["doc_id"]), seed)].append(rec)
    return out


def write(data_path: str, out_dir: str, seed: int) -> dict:
    records = [json.loads(line) for line in open(data_path, encoding="utf-8") if line.strip()]
    parts = split(records, seed)
    # disjointness, checked rather than assumed
    groups = {name: {group_of(r["doc_id"]) for r in rows} for name, rows in parts.items()}
    overlap = groups["dev_train"] & groups["dev_cal"]
    if overlap:
        raise SystemExit(f"ERROR: {len(overlap)} document groups appear in both splits")
    if sum(len(r) for r in parts.values()) != len(records):
        raise SystemExit("ERROR: split does not cover every record exactly once")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in parts.items():
        with open(out / f"{name}_gold.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        with open(out / f"{name}_input.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(strip_gold(r), ensure_ascii=False) + "\n" for r in rows)
    manifest = {
        "source": Path(data_path).name, "seed": seed, "train_share_target": TRAIN_SHARE,
        "n_docs": len(records), "n_groups": len(set(group_of(r["doc_id"]) for r in records)),
        "docs": {k: len(v) for k, v in parts.items()},
        "groups": {k: len(v) for k, v in groups.items()},
        "group_overlap": 0,
    }
    (out / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)
    m = write(a.data, a.out_dir, a.seed)
    print(json.dumps(m, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
