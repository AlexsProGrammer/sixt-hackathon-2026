"""Group-disjoint partitions inside dev: dev_fit (50%), dev_select (30%), dev_audit (20%) of document groups.

- Groups = doc_id without the trailing "-pNNNN", as in 2_prepare.py, so pages of one filing stay together.
- Assignment = SHA-256 of "seed:group", reproducible and independent of row order.
- Documents already looked at in earlier runs (the smoke sets and the 6-document functional measurement) are
  "seen". Their groups never enter dev_audit. They may be used for fit or select.
- The audit set is therefore not a fresh holdout for those documents. The manifest says how many groups are seen.

    python -m evaluation.partitions --data data/unified/dev.jsonl --out-dir results/partitions_v1 --seed 20260113

Writes <name>_gold.jsonl and <name>_input.jsonl (no gold) for each partition, plus partitions_manifest.json
with the frozen document ids per partition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PARTITIONS = ("dev_fit", "dev_select", "dev_audit")
SEEN_GOLD_FILES = ("results/smoke10_gold.jsonl", "results/smoke2_gold.jsonl", "results/final_dev_gold.jsonl")


def group_of(doc_id: str) -> str:
    return re.sub(r"-p\d+$", "", doc_id)


def _u(seed: int, group: str) -> float:
    return int(hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF


def assign(group: str, seed: int, seen: bool) -> str:
    u = _u(seed, group)
    if seen:  # seen groups may never be audit
        return "dev_select" if u < 0.5 else "dev_fit"
    if u < 0.20:
        return "dev_audit"
    if u < 0.50:
        return "dev_select"
    return "dev_fit"


def seen_doc_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for rel in SEEN_GOLD_FILES:
        p = root / rel
        if p.exists():
            ids |= {json.loads(line)["doc_id"] for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}
    return ids


def strip_gold(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("gold")}


def build(data: str, out_dir: str, seed: int, root: Path) -> dict:
    records = [json.loads(line) for line in open(data, encoding="utf-8") if line.strip()]
    seen_ids = seen_doc_ids(root)
    seen_groups = {group_of(d) for d in seen_ids}
    parts: dict[str, list[dict]] = {p: [] for p in PARTITIONS}
    group_part: dict[str, str] = {}
    for rec in records:
        g = group_of(rec["doc_id"])
        if g not in group_part:
            group_part[g] = assign(g, seed, g in seen_groups)
        parts[group_part[g]].append(rec)

    # disjointness and coverage are checked, not assumed
    groups = {p: {group_of(r["doc_id"]) for r in rows} for p, rows in parts.items()}
    for a in PARTITIONS:
        for b in PARTITIONS:
            if a < b and groups[a] & groups[b]:
                raise SystemExit(f"ERROR: groups shared between {a} and {b}")
    if sum(len(v) for v in parts.values()) != len(records):
        raise SystemExit("ERROR: partitions do not cover every record exactly once")
    if any(group_of(d) in seen_groups for d in (r["doc_id"] for r in parts["dev_audit"])):
        raise SystemExit("ERROR: a seen group landed in dev_audit")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frozen = {}
    for name, rows in parts.items():
        with open(out / f"{name}_gold.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        with open(out / f"{name}_input.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(strip_gold(r), ensure_ascii=False) + "\n" for r in rows)
        ids = sorted(r["doc_id"] for r in rows)
        frozen[name] = {"n_docs": len(rows), "n_groups": len(groups[name]),
                        "n_seen_docs": sum(1 for i in ids if i in seen_ids),
                        "ids_sha256": hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest(),
                        "doc_ids": ids}
    manifest = {
        "source": Path(data).name, "seed": seed, "n_docs": len(records), "n_groups": len(group_part),
        "seen_docs_total": len(seen_ids), "seen_groups_total": len(seen_groups),
        "audit_available": frozen["dev_audit"]["n_docs"] > 0 and frozen["dev_audit"]["n_seen_docs"] == 0,
        "partitions": frozen, "group_overlap": 0,
        "note": "dev_audit contains no document that was looked at earlier; it is still a dev split, not test_public.",
    }
    (out / "partitions_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=20260113)
    ap.add_argument("--root", default=".", help="project root that contains the seen-results files")
    a = ap.parse_args(argv)
    m = build(a.data, a.out_dir, a.seed, Path(a.root))
    summary = {k: {"n_docs": v["n_docs"], "n_groups": v["n_groups"], "n_seen_docs": v["n_seen_docs"]}
               for k, v in m["partitions"].items()}
    print(json.dumps({"n_docs": m["n_docs"], "seen_docs_total": m["seen_docs_total"],
                      "audit_available": m["audit_available"], "partitions": summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
