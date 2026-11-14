"""Train a field-level whitelist selector (T10) from run field tables (`fields.jsonl`).

    python -m evaluation.train_selector --runs RUN_ID... --split fit --min-n 3 --min-groups 2 \\
        --evidence grounded_text --out submission/selector.json

Never trains on `audit` or `audit2`: checks both `--split` and every `doc_id` against `data/splits/manifest.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import field_table, registry, splits  # noqa: E402
from evaluation.select_threshold import wilson_upper  # noqa: E402
from uncertainty.decision import evidence_satisfied, views_agree  # noqa: E402

SELECTOR_VERSION = 1
AUDIT_SPLITS = ("audit", "audit2")
DEFAULT_KIND_RULES = {"json": "never", "boolean": "views_only"}


def _audit_doc_ids(manifest: dict) -> set[str]:
    out: set[str] = set()
    for s in AUDIT_SPLITS:
        out.update((manifest.get("splits") or {}).get(s, {}).get("doc_ids") or [])
    return out


def load_training_rows(
    run_refs: list[str],
    *,
    split: str | None = "fit",
    runs_dir: Path | None = None,
    splits_dir: Path | None = None,
) -> tuple[list[dict], list[str], dict]:
    """Load field-table rows for training, enforcing the audit-split guard against manifest.json."""
    if split in AUDIT_SPLITS:
        raise ValueError(f"cannot train selector on audit split {split!r}")
    manifest_path = (splits_dir or (ROOT / "data" / "splits")) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit_ids = _audit_doc_ids(manifest)
    allowed_ids: set[str] | None = None
    if split is not None:
        split_info = (manifest.get("splits") or {}).get(split)
        if not split_info:
            raise ValueError(f"unknown split {split!r} in splits manifest")
        allowed_ids = set(split_info.get("doc_ids") or [])

    rows: list[dict] = []
    run_ids: list[str] = []
    fingerprints: list[dict] = []
    for ref in run_refs:
        rdir = registry.resolve_run(ref, runs_dir=runs_dir)
        run = registry.read_run(rdir)
        if run.get("split") in AUDIT_SPLITS:
            raise ValueError(f"run {run.get('run_id')} has audit split {run.get('split')!r}")
        run_ids.append(str(run.get("run_id") or rdir.name))
        pipe = run.get("pipeline") or {}
        fingerprints.append({
            "run_id": run.get("run_id"),
            "model": pipe.get("model"),
            "models": run.get("models"),
            "prompt_version": pipe.get("prompt_version"),
            "pipeline_sha256": run.get("pipeline_sha256"),
            "samples": pipe.get("samples"),
        })
        ft = field_table.load_field_table(rdir)
        for row in ft:
            if allowed_ids is not None and row["doc_id"] not in allowed_ids:
                continue
            if row["doc_id"] in audit_ids:
                raise ValueError(f"audit split doc_id {row['doc_id']!r} found in training rows")
            rows.append(row)

    if not rows:
        raise ValueError(f"no training rows found for runs={run_refs!r} split={split!r}")

    fp = fingerprints[0] if len(fingerprints) == 1 else {"runs": fingerprints}
    return rows, run_ids, fp


def _row_qualifies(row: dict, *, evidence: str, min_families: int, kind_rules: dict) -> bool:
    if not row.get("pred_present"):
        return False
    kind = row.get("kind", "string")
    if kind_rules.get(kind) == "never":
        return False
    if kind_rules.get(kind) == "views_only" and not views_agree(row):
        return False
    if not evidence_satisfied(row, evidence):
        return False
    if min_families > 1:
        fam_agree = row.get("families_agreeing")
        if fam_agree is None or int(fam_agree) < min_families:
            return False
    return True


def _admitted_cells(
    rows: list[dict],
    *,
    min_n: int,
    min_groups: int,
    evidence: str,
    min_families: int,
    kind_rules: dict,
) -> tuple[list[dict], list[dict]]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if _row_qualifies(r, evidence=evidence, min_families=min_families, kind_rules=kind_rules):
            grouped[(str(r["source"]), str(r["family"]), str(r["field"]))].append(r)

    cells: list[dict] = []
    candidates: list[dict] = []
    for (source, family, field) in sorted(grouped):
        cell_rows = grouped[(source, family, field)]
        n = len(cell_rows)
        groups = len({r["group"] for r in cell_rows})
        errors = sum(1 for r in cell_rows if r.get("outcome") in ("wrong", "hallucinated") or not r.get("match"))
        kind = str(cell_rows[0].get("kind", "string"))
        w_up = round(wilson_upper(errors, n), 6)
        summary = {
            "source": source,
            "family": family,
            "field": field,
            "kind": kind,
            "n": n,
            "groups": groups,
            "errors": errors,
            "wilson_upper": w_up,
        }
        candidates.append(summary)
        if errors == 0 and n >= min_n and groups >= min_groups:
            cells.append({
                "source": source,
                "family": family,
                "field": field,
                "kind": kind,
                "require": {"evidence": evidence, "min_families": min_families},
                "n": n,
                "groups": groups,
                "errors": 0,
                "wilson_upper": w_up,
            })
    return cells, candidates


def logo_simulate(
    rows: list[dict],
    *,
    min_n: int,
    min_groups: int,
    evidence: str,
    min_families: int = 1,
    kind_rules: dict | None = None,
    error_cost: float = 100.0,
) -> dict:
    """Leave-one-group-out simulation on training rows."""
    kr = kind_rules or dict(DEFAULT_KIND_RULES)
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_group[str(r["group"])].append(r)

    accepted = correct = wrong = hallucinated = 0
    families_booked: set[str] = set()
    for held_group in sorted(by_group):
        train_rows = [r for g, rs in by_group.items() if g != held_group for r in rs]
        cells, _ = _admitted_cells(
            train_rows,
            min_n=min_n,
            min_groups=min_groups,
            evidence=evidence,
            min_families=min_families,
            kind_rules=kr,
        )
        allowed = {(c["source"], c["family"], c["field"]) for c in cells}
        for r in by_group[held_group]:
            if not _row_qualifies(r, evidence=evidence, min_families=min_families, kind_rules=kr):
                continue
            if (str(r["source"]), str(r["family"]), str(r["field"])) not in allowed:
                continue
            accepted += 1
            families_booked.add(str(r["family"]))
            if r.get("outcome") == "correct":
                correct += 1
            elif r.get("outcome") == "hallucinated":
                hallucinated += 1
            else:
                wrong += 1

    n_fields = len(rows)
    errs = wrong + hallucinated
    net = (correct - error_cost * errs) / n_fields if n_fields > 0 else 0.0
    return {
        "n_fields": n_fields,
        "n_groups": len(by_group),
        "accepted": accepted,
        "correct": correct,
        "wrong": wrong,
        "hallucinated": hallucinated,
        "families_booked": len(families_booked),
        "net_saving_pct_e100": round(net, 6),
        "wilson_upper": round(wilson_upper(errs, accepted), 6),
    }


def build_selector(
    rows: list[dict],
    *,
    min_n: int = 3,
    min_groups: int = 2,
    evidence: str = "grounded_text",
    min_families: int = 1,
    declared_threshold: float = 0.99,
    run_ids: list[str] | tuple[str, ...] = (),
    split: str = "fit",
    fingerprint: dict | None = None,
    error_cost: float = 100.0,
) -> dict:
    """Build a version-1 selector artefact from field-table rows."""
    kind_rules = dict(DEFAULT_KIND_RULES)
    cells, candidates = _admitted_cells(
        rows,
        min_n=min_n,
        min_groups=min_groups,
        evidence=evidence,
        min_families=min_families,
        kind_rules=kind_rules,
    )
    logo = logo_simulate(
        rows,
        min_n=min_n,
        min_groups=min_groups,
        evidence=evidence,
        min_families=min_families,
        kind_rules=kind_rules,
        error_cost=error_cost,
    )
    return {
        "selector_version": SELECTOR_VERSION,
        "declared_threshold": float(declared_threshold),
        "trained_on": {
            "run_ids": list(run_ids),
            "split": split,
            "fingerprint": fingerprint or {},
            "params": {
                "min_n": int(min_n),
                "min_groups": int(min_groups),
                "evidence": str(evidence),
                "min_families": int(min_families),
            },
        },
        "cells": cells,
        "kind_rules": kind_rules,
        "calibrator": None,
        "logo_summary": logo,
        "candidate_cells": candidates,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True, help="run id(s), name fragment(s), or folder path(s)")
    ap.add_argument("--split", default="fit", help="training split (default: fit; audit splits forbidden)")
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--min-groups", type=int, default=2)
    ap.add_argument("--min-families", type=int, default=1)
    ap.add_argument("--evidence", default="grounded_text")
    ap.add_argument("--declared-threshold", type=float, default=0.99)
    ap.add_argument("--error-cost", type=float, default=100.0)
    ap.add_argument("--runs-dir", help="default: results/runs")
    ap.add_argument("--splits-dir", help="default: data/splits")
    ap.add_argument("--out", required=True, help="output selector.json path")
    a = ap.parse_args(argv)

    rows, run_ids, fp = load_training_rows(
        a.runs,
        split=a.split,
        runs_dir=Path(a.runs_dir) if a.runs_dir else None,
        splits_dir=Path(a.splits_dir) if a.splits_dir else None,
    )
    sel = build_selector(
        rows,
        min_n=a.min_n,
        min_groups=a.min_groups,
        evidence=a.evidence,
        min_families=a.min_families,
        declared_threshold=a.declared_threshold,
        run_ids=run_ids,
        split=a.split,
        fingerprint=fp,
        error_cost=a.error_cost,
    )
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sel, indent=2, ensure_ascii=False), encoding="utf-8")

    logo = sel["logo_summary"]
    print(f"selector -> {out_path} ({len(sel['cells'])} cells from {len(sel['candidate_cells'])} candidates)")
    print(
        f"LOGO (fit): accepted={logo['accepted']} correct={logo['correct']} "
        f"wrong={logo['wrong']} hallucinated={logo['hallucinated']} "
        f"families={logo['families_booked']} net@100={logo['net_saving_pct_e100']:+.2%} "
        f"wilson_upper={logo['wilson_upper']:.4f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
