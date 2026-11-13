"""Frozen, group-disjoint dev splits (T03).

    python -m evaluation.splits --seed 13 [--data data/unified/dev.jsonl] [--out-dir data/splits] [--force]

Writes data/splits/<name>.jsonl (full dev records, gold included, like dev.jsonl) and data/splits/manifest.json:

    fit      50% of dev groups   train: whitelist, calibration, features
    select   25%                 choose: model, thresholds, parameters
    audit    25%                 run ONCE per release candidate. Contains no group that earlier runs looked at.
    audit2   reserve carved from `fit` groups no model run has seen yet. Re-audit after a change to the pipeline.
    smoke    12 docs from `fit` (2+2 CUAD short/long, 4 EB text-good, 2 EB damaged text, 2 EB no text)

- A group = documents that must never be split (partitions.group_of: pages, re-renders, corrupted twins).
- fit/select/audit are stratified systematically by (source, family) over groups, deterministic in --seed.
- `seen` groups (earlier dev_select/dev_audit partition files, see partitions.SEEN_GOLD_FILES) never enter audit.
- audit2 and smoke are subsets of dev groups taken out of fit, so fit/select/audit/audit2 are pairwise disjoint.
  smoke is a subset of fit (overlap by design, it only exists for quick checks).
- The manifest freezes ids and sha256. A second run refuses to overwrite it (use --force and treat every earlier
  audit number as void), because audit2 depends on which runs exist at creation time.

Gold is only written into the split files for scoring. Nothing here reads it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import docs  # noqa: E402
from evaluation.partitions import group_of, seen_doc_ids  # noqa: E402

SPLIT_NAMES = ("fit", "select", "audit", "audit2", "smoke")
FIT_SHARE, SELECT_SHARE = 0.50, 0.25      # audit gets the rest
SMOKE_QUOTA = (("cuad_short", 2), ("cuad_long", 2), ("eb_text_good", 4), ("eb_damaged", 2), ("eb_no_text", 2))
MANIFEST_VERSION = 1
NOT_A_MODEL_RUN_MODES = ("abstain_all", "offline")
DEFAULT_SEED = 13


# ---------------------------------------------------------------- helpers

def _u(seed: int, salt: str, key: str) -> float:
    return int(hashlib.sha256(f"{seed}:{salt}:{key}".encode("utf-8")).hexdigest()[:12], 16) / float(16 ** 12)


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ids_sha256(ids) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def stratum_of(rec: dict) -> tuple[str, str]:
    return (rec.get("source_dataset", "?"), docs.family_of(rec))


def group_strata(records: list[dict]) -> dict[str, tuple[str, str]]:
    """group -> its (source, family). A group that spans two families takes the most common one."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        votes[group_of(r["doc_id"])][stratum_of(r)] += 1
    return {g: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for g, c in votes.items()}


def assign_groups(strata_of: dict[str, tuple], seed: int, seen_groups: set[str]) -> dict[str, str]:
    """Systematic stratified assignment: inside a stratum the groups are put in hash order and cut at 50/25/25
    with a stratum-specific offset, so small strata do not all land in `fit`."""
    by_stratum: dict[tuple, list[str]] = defaultdict(list)
    for g, s in strata_of.items():
        by_stratum[s].append(g)
    out: dict[str, str] = {}
    for s, groups in by_stratum.items():
        groups.sort(key=lambda g: _u(seed, "order", g))
        offset = _u(seed, "offset", "|".join(s))
        n = len(groups)
        for i, g in enumerate(groups):
            q = (i + offset) / n
            out[g] = "fit" if q < FIT_SHARE else "select" if q < FIT_SHARE + SELECT_SHARE else "audit"
    for g in seen_groups:
        if out.get(g) == "audit":
            out[g] = "select"          # a document that was looked at cannot be a fresh audit document
    return out


def pin_damaged_to_fit(assigned: dict[str, str], strata_of: dict[str, tuple], seed: int) -> list[str]:
    """The smoke set needs damaged-text documents (K-1) inside `fit`. All K-1 pages are one filing, i.e. one
    group, so chance alone can leave `fit` without any. If so, the first damaged group in hash order is moved to
    `fit`. Returns the moved groups (written to the manifest)."""
    damaged = sorted((g for g, s in strata_of.items() if docs.is_damaged_family(s[1])), key=lambda g: _u(seed, "pin", g))
    if not damaged or any(assigned[g] == "fit" for g in damaged):
        return []
    assigned[damaged[0]] = "fit"
    return [damaged[0]]


def stratified_pick(groups: list[str], strata_of: dict[str, tuple], k: int, seed: int, salt: str) -> list[str]:
    """k groups, spread over strata proportionally (largest remainder), deterministic."""
    if k >= len(groups):
        return sorted(groups)
    by_stratum: dict[tuple, list[str]] = defaultdict(list)
    for g in groups:
        by_stratum[strata_of[g]].append(g)
    for lst in by_stratum.values():
        lst.sort(key=lambda g: _u(seed, salt, g))
    quota = {s: k * len(lst) / len(groups) for s, lst in by_stratum.items()}
    take = {s: int(q) for s, q in quota.items()}
    rest = k - sum(take.values())
    for s in sorted(quota, key=lambda s: (-(quota[s] - take[s]), _u(seed, salt + ":rem", "|".join(s))))[:rest]:
        take[s] += 1
    return sorted(g for s, lst in by_stratum.items() for g in lst[: take[s]])


def stratified_sample(records: list[dict], n: int, seed: int) -> list[dict]:
    """n documents stratified by (source, family), different groups first inside a stratum.
    Returned in the original file order. Used by run_batch --random."""
    if n >= len(records):
        return list(records)
    by_stratum: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        by_stratum[stratum_of(r)].append(r)
    total = len(records)
    quota = {s: n * len(v) / total for s, v in by_stratum.items()}
    take = {s: min(int(q), len(by_stratum[s])) for s, q in quota.items()}
    rest = n - sum(take.values())
    order = sorted(quota, key=lambda s: (-(quota[s] - take[s]), _u(seed, "sample:rem", "|".join(s))))
    while rest > 0:
        moved = False
        for s in order:
            if rest > 0 and take[s] < len(by_stratum[s]):
                take[s] += 1
                rest -= 1
                moved = True
        if not moved:
            break
    chosen: set[str] = set()
    for s, lst in by_stratum.items():
        seen_g: set[str] = set()
        first, later = [], []
        for r in sorted(lst, key=lambda r: _u(seed, "sample", r["doc_id"])):
            g = group_of(r["doc_id"])
            (later if g in seen_g else first).append(r)
            seen_g.add(g)
        chosen |= {r["doc_id"] for r in (first + later)[: take[s]]}
    return [r for r in records if r["doc_id"] in chosen]


# ---------------------------------------------------------------- inputs that depend on earlier work

def seen_ids(root: Path, extra: list[str] | None = None) -> set[str]:
    """Documents looked at in earlier partition experiments (smoke sets plus old dev_select/dev_audit files)."""
    ids = set(seen_doc_ids(root))
    paths = [root / "results" / d.name / f for d in (root / "results").glob("partitions*") if d.is_dir()
             for f in ("dev_select_gold.jsonl", "dev_audit_gold.jsonl")]
    paths += [Path(p) for p in (extra or [])]
    for p in paths:
        if p.exists():
            ids |= {r["doc_id"] for r in read_jsonl(p)}
    return ids


def model_run_ids(runs_dir: Path) -> set[str]:
    """doc_ids that any model run has produced predictions for. Abstain-all/offline/baseline runs do not count."""
    ids: set[str] = set()
    for rj in sorted(runs_dir.glob("*/run.json")):
        try:
            run = json.loads(rj.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if run.get("mode") in NOT_A_MODEL_RUN_MODES or str(run.get("name", "")).startswith("base_"):
            continue
        preds = rj.parent / "preds.jsonl"
        if preds.exists():
            ids |= {r["doc_id"] for r in read_jsonl(preds)}
    return ids


# ---------------------------------------------------------------- smoke set

def pick_smoke(fit_records: list[dict], seed: int) -> tuple[list[dict], dict]:
    """12 documents from `fit`, one per group, classified by what the text layer looks like."""
    def key(r):
        return _u(seed, "smoke", r["doc_id"])

    ordered = sorted(fit_records, key=key)
    chosen: list[dict] = []
    used_groups: set[str] = set()
    composition: dict[str, list[str]] = {}
    missing: dict[str, int] = {}

    def take(cls: str, n: int, accept, distinct_family: bool = False, distinct_group: bool = True):
        got, fams = [], set()
        for r in ordered:
            if len(got) >= n:
                break
            g = group_of(r["doc_id"])
            if (distinct_group and g in used_groups) or (distinct_family and docs.family_of(r) in fams):
                continue
            if accept(r):
                got.append(r)
                used_groups.add(g)
                fams.add(docs.family_of(r))
        if len(got) < n:
            missing[cls] = n - len(got)
        composition[cls] = [r["doc_id"] for r in got]
        chosen.extend(got)

    text_cache: dict[str, str | None] = {}

    def text(r):
        if r["doc_id"] not in text_cache:
            text_cache[r["doc_id"]] = docs.doc_text(r)
        return text_cache[r["doc_id"]]

    def cuad(r, long_: bool):
        t = text(r)
        return r["source_dataset"] == "cuad" and t is not None and (len(t) >= docs.CUAD_LONG_CHARS) == long_

    def eb_good(r):
        if r["source_dataset"] == "cuad" or docs.is_damaged_family(docs.family_of(r)):
            return False
        t = text(r)
        return t is not None and docs.text_quality(t) >= 0.5 and docs.perception_of(r) == "P0"

    def eb_damaged(r):
        return r["source_dataset"] != "cuad" and docs.is_damaged_family(docs.family_of(r)) and text(r) is not None

    def eb_none(r):
        return r["source_dataset"] != "cuad" and text(r) is None

    quota = dict(SMOKE_QUOTA)
    take("cuad_short", quota["cuad_short"], lambda r: cuad(r, False))
    take("cuad_long", quota["cuad_long"], lambda r: cuad(r, True))
    take("eb_text_good", quota["eb_text_good"], eb_good, distinct_family=True)
    take("eb_damaged", quota["eb_damaged"], eb_damaged, distinct_group=False)  # all K-1 pages are one group
    take("eb_no_text", quota["eb_no_text"], eb_none, distinct_family=True)
    order = {r["doc_id"]: i for i, r in enumerate(fit_records)}
    chosen.sort(key=lambda r: order[r["doc_id"]])
    return chosen, {"composition": composition, "missing": missing}


# ---------------------------------------------------------------- build

def summarise(rows: list[dict]) -> dict:
    ids = sorted(r["doc_id"] for r in rows)
    return {
        "n_docs": len(rows), "n_groups": len({group_of(i) for i in ids}), "ids_sha256": ids_sha256(ids),
        "by_source": dict(sorted(Counter(r.get("source_dataset", "?") for r in rows).items())),
        "by_family": dict(sorted(Counter(docs.family_of(r) for r in rows).items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_perception": dict(sorted(Counter(docs.perception_of(r) for r in rows).items())),
        "doc_ids": ids,
    }


def check_disjoint(parts: dict[str, list[dict]]) -> None:
    groups = {n: {group_of(r["doc_id"]) for r in rows} for n, rows in parts.items()}
    names = [n for n in ("fit", "select", "audit", "audit2")]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if groups[a] & groups[b]:
                raise SystemExit(f"ERROR: groups shared between {a} and {b}: {sorted(groups[a] & groups[b])[:3]}")
    if {r["doc_id"] for r in parts["smoke"]} - {r["doc_id"] for r in parts["fit"]}:
        raise SystemExit("ERROR: smoke is not a subset of fit")


def build(data: Path, out_dir: Path, seed: int, *, root: Path = ROOT, runs_dir: Path | None = None,
          extra_seen: list[str] | None = None, audit2_frac: float = 0.5, force: bool = False) -> dict:
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists() and not force:
        raise SystemExit(f"ERROR: {manifest_path} exists. The splits are frozen; --force rewrites them and voids "
                         f"every earlier audit number.")
    records = read_jsonl(data)
    strata = group_strata(records)
    seen = seen_ids(root, extra_seen)
    seen_groups = {group_of(i) for i in seen}
    assigned = assign_groups(strata, seed, seen_groups)
    pinned = pin_damaged_to_fit(assigned, strata, seed)

    # audit2: fit groups that no model run has looked at
    ran = model_run_ids(runs_dir or root / "results" / "runs")
    ran_groups = {group_of(i) for i in ran}
    fit_groups = sorted(g for g, s in assigned.items() if s == "fit")
    pool = [g for g in fit_groups if g not in ran_groups]
    n_audit2 = round(audit2_frac * sum(1 for s in assigned.values() if s == "audit"))
    audit2 = set(stratified_pick(pool, strata, min(n_audit2, len(pool)), seed, "audit2"))
    for g in audit2:
        assigned[g] = "audit2"

    parts: dict[str, list[dict]] = {n: [] for n in ("fit", "select", "audit", "audit2")}
    for r in records:
        parts[assigned[group_of(r["doc_id"])]].append(r)
    parts["smoke"], smoke_info = pick_smoke(parts["fit"], seed)
    check_disjoint(parts)
    if sum(len(parts[n]) for n in ("fit", "select", "audit", "audit2")) != len(records):
        raise SystemExit("ERROR: splits do not cover every record exactly once")
    if {group_of(r["doc_id"]) for r in parts["audit"]} & seen_groups:
        raise SystemExit("ERROR: a seen group landed in audit")

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, rows in parts.items():
        path = out_dir / f"{name}.jsonl"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        files[name] = sha256_file(path)
    manifest = {
        "manifest_version": MANIFEST_VERSION, "seed": seed, "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {"file": str(data), "sha256": sha256_file(data), "n_docs": len(records), "n_groups": len(strata)},
        "shares": {"fit": FIT_SHARE, "select": SELECT_SHARE, "audit": 1 - FIT_SHARE - SELECT_SHARE},
        "grouping": "evaluation.partitions.group_of (-pNNNN, -rN, _corrupted stripped)",
        "stratification": "systematic over (source_dataset, family)",
        "seen": {"n_docs": len(seen), "n_groups": len(seen_groups)},
        "pinned_to_fit": pinned,
        "audit2": {"frac_of_audit_groups": audit2_frac, "pool_groups": len(pool), "n_groups": len(audit2),
                   "rule": "fit groups with no prediction in any model run at creation time"},
        "smoke": {"quota": dict(SMOKE_QUOTA), **smoke_info, "note": "subset of fit"},
        "group_overlap": 0,
        "splits": {n: {**summarise(rows), "file": f"{n}.jsonl", "file_sha256": files[n]} for n, rows in parts.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def load_split(name: str, splits_dir: Path | None = None, verify: bool = True) -> list[dict]:
    """Records of a frozen split. Verifies the file hash against the manifest."""
    d = splits_dir or ROOT / "data" / "splits"
    path = d / f"{name}.jsonl"
    if not path.exists():
        raise SystemExit(f"ERROR: split {name!r} not found at {path}. Create it with: python -m evaluation.splits")
    if verify and (d / "manifest.json").exists():
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        want = man.get("splits", {}).get(name, {}).get("file_sha256")
        if want and sha256_file(path) != want:
            raise SystemExit(f"ERROR: {path} differs from the frozen manifest (sha256 mismatch).")
    return read_jsonl(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data" / "unified" / "dev.jsonl"))
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "splits"))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--seen", action="append", default=[], help="extra gold/record jsonl whose documents count as seen")
    ap.add_argument("--audit2-frac", type=float, default=0.5, help="audit2 size as a fraction of the audit group count")
    ap.add_argument("--force", action="store_true", help="overwrite frozen splits (voids earlier audit numbers)")
    a = ap.parse_args(argv)
    m = build(Path(a.data), Path(a.out_dir), a.seed, extra_seen=a.seen, audit2_frac=a.audit2_frac, force=a.force)
    print(f"dev: {m['source']['n_docs']} docs, {m['source']['n_groups']} groups, seed {a.seed}, "
          f"seen {m['seen']['n_docs']} docs / {m['seen']['n_groups']} groups")
    print(f"{'split':8s} {'docs':>5s} {'groups':>6s}  by_source  |  perception")
    for n, s in m["splits"].items():
        print(f"{n:8s} {s['n_docs']:5d} {s['n_groups']:6d}  {s['by_source']}  |  {s['by_perception']}")
    print(f"audit2: pool {m['audit2']['pool_groups']} unrun fit groups, took {m['audit2']['n_groups']}")
    if m["smoke"]["missing"]:
        print(f"WARNING: smoke is short of: {m['smoke']['missing']}")
    print(f"wrote {a.out_dir}/*.jsonl and manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
