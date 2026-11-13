"""Reports from a run's field table (T03). Output: RUN/report.md and RUN/report.json.

    python -m evaluation.report --run RUN_ID_OR_DIR [--rebuild] [--min-n 3] [--min-groups 1]
                                [--evidence grounded_text] [--conf 0.0] [--no-write]

Sections
  1. headline counts (correct / wrong / hallucinated / missed / true_null)
  2. precision tables per (source, kind, grounded), per confidence bucket, per (family, field)
  3. leave-one-group-out (LOGO) whitelist simulation, grid over min_n, min_groups and evidence requirement
  4. Wilson-95 upper bound of the error rate of what the whitelist books
  5. net saving at E = 20 / 100 / 500 (review cost 1, same formula as 5_score.net_saving)
  6. missed-savings report: correct values that were not booked, grouped by reason

LOGO whitelist: a (family, field) cell books a prediction only if, among the candidate predictions of the cell
that come from OTHER document groups, there are at least `min_n` (from at least `min_groups` groups) and all of
them are correct. The row's own group never takes part in its own decision. Candidates = predictions that pass
the evidence requirement and the confidence floor.

Numbers on a run are only as good as the split they come from. Dev runs without a held-out split say nothing
about the hidden test.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import registry  # noqa: E402
from evaluation.field_table import load_field_table, outcome_counts  # noqa: E402

ERROR_COSTS = (20, 100, 500)
EVIDENCE = ("none", "grounded_text", "grounded", "cross_view")
GRID_MIN_N = (3, 5, 10, 20)
GRID_MIN_GROUPS = (1, 3)
GRID_EVIDENCE = ("grounded_text", "none")
REASONS = ("booked", "no_prediction", "below_confidence", "no_evidence", "cell_too_small", "too_few_groups",
           "cell_has_errors")
CELL = ("family", "field")


# ---------------------------------------------------------------- statistics

def wilson_upper(errors: int, n: int, z: float = 1.96) -> float | None:
    """Upper end of the Wilson 95% interval for an error proportion errors/n. None when n == 0."""
    if n <= 0:
        return None
    p = errors / n
    z2 = z * z
    centre = p + z2 / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return min(1.0, (centre + half) / (1 + z2 / n))


def is_error(r: dict) -> bool:
    return r["outcome"] in ("wrong", "hallucinated")


def stats(rows: list[dict]) -> dict:
    """Counts over predictions (rows with a non-null prediction)."""
    c = Counter(r["outcome"] for r in rows)
    n = c["correct"] + c["wrong"] + c["hallucinated"]
    err = c["wrong"] + c["hallucinated"]
    return {"n": n, "correct": c["correct"], "wrong": c["wrong"], "hallucinated": c["hallucinated"],
            "precision": c["correct"] / n if n else None, "wilson95_err_upper": wilson_upper(err, n)}


def net_saving(booked: int, bad: int, n_fields: int, error_cost: float, review_cost: float = 1.0) -> float:
    """Same as 5_score.net_saving: (n * review - ((n - booked) * review + bad * error_cost)) / (n * review).
    `booked` includes the `bad` values."""
    return (booked * review_cost - bad * error_cost) / (n_fields * review_cost) if n_fields else 0.0


# ---------------------------------------------------------------- LOGO whitelist

def passes_evidence(r: dict, evidence: str) -> bool:
    if evidence == "none":
        return True
    if evidence == "grounded_text":
        return bool(r.get("grounded_text"))
    if evidence == "grounded":
        return bool(r.get("grounded_text") or r.get("grounded_ocr"))
    if evidence == "cross_view":
        return r.get("cross_view_agree") is True
    raise ValueError(f"unknown evidence requirement {evidence!r}; allowed: {', '.join(EVIDENCE)}")


def cell_of(r: dict) -> tuple:
    return tuple(r[k] for k in CELL)


def logo_decisions(rows: list[dict], *, min_n: int = 3, min_groups: int = 1, evidence: str = "grounded_text",
                   conf: float = 0.0) -> list[tuple[dict, str]]:
    """(row, reason) for every row. reason == "booked" means the whitelist books the prediction.

    Own-group exclusion: the cell statistics are computed once over all candidates and the row's own group
    contribution is subtracted again, which is the same as recomputing the cell without that group."""
    cand = [r for r in rows if r["pred_present"] and passes_evidence(r, evidence)
            and (r.get("conf_out") if r.get("conf_out") is not None else 0.0) >= conf]
    cand_ids = {id(r) for r in cand}
    cell_n: Counter = Counter()
    cell_err: Counter = Counter()
    grp_n: Counter = Counter()
    grp_err: Counter = Counter()
    for r in cand:
        k, g = cell_of(r), r["group"]
        cell_n[k] += 1
        grp_n[(k, g)] += 1
        if not r["match"]:
            cell_err[k] += 1
            grp_err[(k, g)] += 1
    cell_groups = Counter(k for k, _ in grp_n)
    out: list[tuple[dict, str]] = []
    for r in rows:
        if not r["pred_present"]:
            out.append((r, "no_prediction"))
        elif id(r) not in cand_ids:
            ok_evidence = passes_evidence(r, evidence)
            out.append((r, "no_evidence" if not ok_evidence else "below_confidence"))
        else:
            k, g = cell_of(r), r["group"]
            n_other = cell_n[k] - grp_n[(k, g)]
            err_other = cell_err[k] - grp_err[(k, g)]
            groups_other = cell_groups[k] - 1
            if n_other < min_n:
                reason = "cell_too_small"
            elif groups_other < min_groups:
                reason = "too_few_groups"
            elif err_other > 0:
                reason = "cell_has_errors"
            else:
                reason = "booked"
            out.append((r, reason))
    return out


def simulate(rows: list[dict], n_fields: int | None = None, **params) -> dict:
    n_fields = len(rows) if n_fields is None else n_fields
    dec = logo_decisions(rows, **params)
    booked = [r for r, why in dec if why == "booked"]
    bad = sum(1 for r in booked if not r["match"])
    res = {**params, "n_fields": n_fields, "booked": len(booked), "wrong": bad,
           "wilson95_err_upper": wilson_upper(bad, len(booked)),
           "families": len({r["family"] for r in booked}), "groups": len({r["group"] for r in booked})}
    for e in ERROR_COSTS:
        res[f"net_e{e}"] = net_saving(len(booked), bad, n_fields, e)
    return res


def missed_savings(rows: list[dict], **params) -> dict:
    """Correct values that were not booked, by reason. Value = number of fields (each worth 1 review cost)."""
    dec = logo_decisions(rows, **params)
    reasons = Counter(why for r, why in dec if r["match"] and why != "booked")
    by_family: dict[str, Counter] = defaultdict(Counter)
    for r, why in dec:
        if r["match"] and why != "booked":
            by_family[r["family"]][why] += 1
    total = sum(reasons.values())
    return {"params": params, "correct_not_booked": total, "by_reason": dict(reasons.most_common()),
            "by_family": {f: dict(c.most_common()) for f, c in
                          sorted(by_family.items(), key=lambda kv: -sum(kv[1].values()))[:25]}}


# ---------------------------------------------------------------- tables

def group_table(rows: list[dict], keyf, *, min_n: int = 1, limit: int = 60) -> list[dict]:
    t: dict = defaultdict(list)
    for r in rows:
        if r["pred_present"]:
            t[keyf(r)].append(r)
    items = []
    for k, v in t.items():
        s = stats(v)
        if s["n"] >= min_n:
            items.append({"key": k if isinstance(k, str) else " / ".join(str(x) for x in k), **s})
    items.sort(key=lambda x: (x["wrong"] + x["hallucinated"], -x["n"]))
    return items[:limit]


def conf_bucket(r: dict) -> str:
    c = r["conf_out"]
    return "n/a" if c is None else f"{min(c, 1.0):.2f}"


def build_report(rows: list[dict], *, min_n: int = 3, min_groups: int = 1, evidence: str = "grounded_text",
                 conf: float = 0.0) -> dict:
    n_fields = len(rows)
    params = {"min_n": min_n, "min_groups": min_groups, "evidence": evidence, "conf": conf}
    return {
        "n_docs": len({r["doc_id"] for r in rows}), "n_groups": len({r["group"] for r in rows}), "n_fields": n_fields,
        "outcomes": outcome_counts(rows),
        "predictions": stats([r for r in rows if r["pred_present"]]),
        "by_source_kind_grounded": group_table(rows, lambda r: (r["source"], r["kind"], r["grounded_text"])),
        "by_confidence": group_table(rows, conf_bucket, limit=200),
        "by_family_field_grounded": group_table([r for r in rows if r["grounded_text"]],
                                                lambda r: (r["family"], r["field"]), min_n=3),
        "by_route": group_table(rows, lambda r: r["route"]),
        "whitelist_params": params,
        "whitelist": simulate(rows, n_fields, **params),
        "whitelist_grid": [simulate(rows, n_fields, min_n=m, min_groups=g, evidence=e)
                           for e in GRID_EVIDENCE for g in GRID_MIN_GROUPS for m in GRID_MIN_N],
        "missed_savings": missed_savings(rows, **params),
    }


# ---------------------------------------------------------------- markdown

def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _table(items: list[dict], title: str) -> list[str]:
    out = [f"\n### {title}\n", "| n | correct | wrong | halluc | precision | wilson95 err upper | key |",
           "|---:|---:|---:|---:|---:|---:|---|"]
    for x in items:
        out.append(f"| {x['n']} | {x['correct']} | {x['wrong']} | {x['hallucinated']} | {_pct(x['precision'])} | "
                   f"{_pct(x['wilson95_err_upper'])} | {x['key']} |")
    return out


def to_markdown(rep: dict, title: str) -> str:
    o, p = rep["outcomes"], rep["predictions"]
    w = rep["whitelist"]
    lines = [f"# Field report: {title}\n",
             f"{rep['n_docs']} documents, {rep['n_groups']} groups, {rep['n_fields']} fields. "
             f"Outcomes: " + ", ".join(f"{k}={v}" for k, v in o.items()) + ".",
             f"Non-null predictions: {p['n']}, precision {_pct(p['precision'])}, "
             f"Wilson-95 error upper bound {_pct(p['wilson95_err_upper'])}.\n",
             "## Leave-one-group-out whitelist\n",
             f"Parameters: {json.dumps(rep['whitelist_params'])}. Booked **{w['booked']}** values, "
             f"**{w['wrong']}** wrong (Wilson-95 error upper bound {_pct(w['wilson95_err_upper'])}), "
             f"{w['families']} families, {w['groups']} groups. Net saving: "
             + ", ".join(f"E={e}: {w[f'net_e{e}']:+.2%}" for e in ERROR_COSTS) + ".\n",
             "| evidence | min_n | min_groups | booked | wrong | wilson95 err upper | families | net E=20 | net E=100 | net E=500 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g in rep["whitelist_grid"]:
        lines.append(f"| {g['evidence']} | {g['min_n']} | {g['min_groups']} | {g['booked']} | {g['wrong']} | "
                     f"{_pct(g['wilson95_err_upper'])} | {g['families']} | {g['net_e20']:+.2%} | "
                     f"{g['net_e100']:+.2%} | {g['net_e500']:+.2%} |")
    ms = rep["missed_savings"]
    lines += ["\n## Missed savings (correct values not booked, whitelist parameters above)\n",
              f"{ms['correct_not_booked']} correct values were not booked.\n", "| reason | fields |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in ms["by_reason"].items()]
    lines += ["\n| family | reasons |", "|---|---|"]
    lines += [f"| {f} | {json.dumps(c)} |" for f, c in ms["by_family"].items()]
    lines.append("\n## Precision tables (non-null predictions only)")
    lines += _table(rep["by_source_kind_grounded"], "source / kind / grounded_text")
    lines += _table(rep["by_route"], "route")
    lines += _table(rep["by_confidence"], "confidence written to preds (rounded)")
    lines += _table(rep["by_family_field_grounded"], "family / field (grounded only, n >= 3), safest first")
    return "\n".join(lines) + "\n"


def legacy_families(rows: list[dict]) -> list[dict]:
    """Map the untitled-document families `stem:*` back to "?" (what analyse_fields.py used), to reproduce its numbers."""
    return [{**r, "family": "?"} if r["family"].startswith("stem:") else r for r in rows]


def write_report(run_dir: Path, rows: list[dict], **params) -> dict:
    run_dir = Path(run_dir)
    rep = build_report(rows, **params)
    run = registry.read_run(run_dir)
    registry.atomic_write_text(run_dir / "report.json", json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    registry.atomic_write_text(run_dir / "report.md", to_markdown(rep, run.get("name", run_dir.name)))
    return rep


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run id, unambiguous name fragment, or run folder path")
    ap.add_argument("--rebuild", action="store_true", help="rebuild fields.jsonl first")
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--min-groups", type=int, default=1)
    ap.add_argument("--evidence", choices=EVIDENCE, default="grounded_text")
    ap.add_argument("--conf", type=float, default=0.0, help="confidence floor of the candidates")
    ap.add_argument("--legacy-families", action="store_true",
                    help="treat untitled documents as one family '?' (reproduces analyse_fields.py: 378 booked at min_n=3)")
    ap.add_argument("--no-write", action="store_true", help="print only, do not write report.md/json")
    a = ap.parse_args(argv)
    run_dir = registry.resolve_run(a.run)
    rows = load_field_table(run_dir, rebuild=a.rebuild)
    if a.legacy_families:
        rows = legacy_families(rows)
    params = {"min_n": a.min_n, "min_groups": a.min_groups, "evidence": a.evidence, "conf": a.conf}
    rep = build_report(rows, **params)
    if not a.no_write:
        write_report(run_dir, rows, **params)
    w = rep["whitelist"]
    print(f"{run_dir.name}: {rep['n_docs']} docs, {rep['n_fields']} fields, outcomes {json.dumps(rep['outcomes'])}")
    print(f"LOGO whitelist {json.dumps(params)}: booked={w['booked']} wrong={w['wrong']} "
          f"wilson95_err_upper={_pct(w['wilson95_err_upper'])} " + " ".join(f"net_e{e}={w[f'net_e{e}']:+.2%}" for e in ERROR_COSTS))
    for g in rep["whitelist_grid"]:
        print(f"  evidence={g['evidence']:13s} min_n={g['min_n']:2d} min_groups={g['min_groups']}: "
              f"booked={g['booked']:5d} wrong={g['wrong']:3d} net_e100={g['net_e100']:+.2%}")
    if not a.no_write:
        print(f"wrote {run_dir / 'report.md'} and report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
