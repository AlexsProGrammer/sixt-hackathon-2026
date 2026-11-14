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
EVIDENCE = ("none", "grounded_text", "grounded_text_strict", "grounded", "cross_view")
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
    if evidence == "grounded_text_strict":
        return bool(r["grounded_text_strict"] if "grounded_text_strict" in r else r.get("grounded_text"))
    if evidence == "grounded":
        return bool(r.get("grounded_text") or r.get("grounded_ocr"))
    if evidence == "cross_view":
        return r.get("cross_view_agree") is True
    raise ValueError(f"unknown evidence requirement {evidence!r}; allowed: {', '.join(EVIDENCE)}")


def cell_of(r: dict, cell_keys: tuple[str, ...] = CELL) -> tuple:
    return tuple(r.get(k) for k in cell_keys)


def logo_decisions(rows: list[dict], *, min_n: int = 3, min_groups: int = 1, evidence: str = "grounded_text",
                   conf: float = 0.0, cell_keys: tuple[str, ...] = CELL) -> list[tuple[dict, str]]:
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
        k, g = cell_of(r, cell_keys), r["group"]
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
            k, g = cell_of(r, cell_keys), r["group"]
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
                 conf: float = 0.0, cell_keys: tuple[str, ...] = CELL) -> dict:
    n_fields = len(rows)
    params: dict = {"min_n": min_n, "min_groups": min_groups, "evidence": evidence, "conf": conf}
    if tuple(cell_keys) != CELL:
        params["cell_keys"] = tuple(cell_keys)
    grid_extra = {"cell_keys": tuple(cell_keys)} if tuple(cell_keys) != CELL else {}
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
        "whitelist_grid": [simulate(rows, n_fields, min_n=m, min_groups=g, evidence=e, **grid_extra)
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


# ---------------------------------------------------------------- diff between two runs

TRANSITIONS = ("correct->wrong", "correct->hallucinated", "wrong->correct", "hallucinated->correct",
               "correct->missed", "correct->true_null", "missed->correct", "true_null->correct",
               "wrong->missed", "hallucinated->missed")


def _at0(rows: list[dict]) -> dict:
    """Precision and coverage at threshold 0 (every written prediction is accepted): 5_score.at_threshold."""
    c = w = h = m = tn = 0
    for r in rows:
        if r["pred_present"]:
            if r["gold_present"]:
                if r["match"]:
                    c += 1
                else:
                    w += 1
            else:
                h += 1
        elif r["gold_present"]:
            m += 1
        else:
            tn += 1
    acc, gold = c + w + h, c + w + m
    return {"n_fields": len(rows), "accepted": acc, "correct": c, "wrong": w, "hallucinated": h,
            "precision": c / acc if acc else None, "coverage": (c + w) / gold if gold else 0.0}


def _grouped_at0(rows: list[dict], key: str, limit: int = 40) -> list[dict]:
    t: dict = defaultdict(list)
    for r in rows:
        t[r[key]].append(r)
    out = []
    for k, group in t.items():
        m = _at0(group)
        out.append({"key": k, **m})
    out.sort(key=lambda x: (x["wrong"] + x["hallucinated"], -x["n_fields"]))
    return out[:limit]


def diff_field_tables(rows_a: list[dict], rows_b: list[dict], *, name_a: str, name_b: str,
                      max_details: int = 200) -> dict:
    """Per-field outcome transitions between two runs over the same documents (e.g. prompt v2 -> v4).

    Rows are aligned on (doc_id, field). Fields predicted in only one run count as missed on the other side
    (a new prediction can be a fix or a regression). Regressions (a correct value that became wrong or
    hallucinated) are listed per field with the values, truncated to 120 characters."""
    a = {(r["doc_id"], r["field"]): r for r in rows_a}
    b = {(r["doc_id"], r["field"]): r for r in rows_b}
    common = sorted(set(a) & set(b))
    only_a = len(set(a) - set(b))
    only_b = len(set(b) - set(a))

    def outcome(rows, key):
        r = rows.get(key)
        return r["outcome"] if r else "missed"

    transitions: Counter = Counter()
    by_family: dict[str, Counter] = defaultdict(Counter)
    by_kind: dict[str, Counter] = defaultdict(Counter)
    by_field: dict[str, Counter] = defaultdict(Counter)
    regressions, fixes = [], []

    def record(key: tuple, ra: dict | None, rb: dict | None) -> None:
        """One aligned field pair. A field that exists in only one run counts as missed on the other side."""
        oa = ra["outcome"] if ra else "missed"
        ob = rb["outcome"] if rb else "missed"
        if oa == ob:
            return
        template = ra or rb
        trans = f"{oa}->{ob}"
        transitions[trans] += 1
        by_family[template["family"]][trans] += 1
        by_kind[template["kind"]][trans] += 1
        by_field[key[1]][trans] += 1
        if oa == "correct" and ob in ("wrong", "hallucinated"):
            regressions.append({"doc_id": key[0], "field": key[1], "family": template["family"], "kind": template["kind"],
                                "route_a": (ra or {}).get("route"), "route_b": (rb or {}).get("route"),
                                "gold_present": bool(template["gold_present"]),
                                "a": str((ra or {}).get("pred_value"))[:120], "b": str((rb or {}).get("pred_value"))[:120]})
        elif oa in ("wrong", "hallucinated", "missed", "true_null") and ob == "correct":
            fixes.append({"doc_id": key[0], "field": key[1], "family": template["family"], "a": oa,
                          "a_value": str((ra or {}).get("pred_value"))[:120],
                          "b_value": str((rb or {}).get("pred_value"))[:120]})

    for key in common:
        record(key, a[key], b[key])
    for key in sorted(set(a) - set(b)):
        record(key, a[key], None)
    for key in sorted(set(b) - set(a)):
        record(key, None, b[key])
    return {
        "run_a": name_a, "run_b": name_b,
        "n_common_fields": len(common), "n_fields_only_a": only_a, "n_fields_only_b": only_b,
        "outcomes_a": outcome_counts(rows_a), "outcomes_b": outcome_counts(rows_b),
        "at0_a": _at0(rows_a), "at0_b": _at0(rows_b),
        "by_route_a": _grouped_at0(rows_a, "route"), "by_route_b": _grouped_at0(rows_b, "route"),
        "by_kind_a": _grouped_at0(rows_a, "kind"), "by_kind_b": _grouped_at0(rows_b, "kind"),
        "transitions": {**{t: 0 for t in TRANSITIONS}, **dict(transitions)},
        "regressions": regressions[:max_details], "n_regressions": len(regressions),
        "fixes": fixes[:max_details], "n_fixes": len(fixes),
        "by_family": {f: dict(c) for f, c in sorted(by_family.items())},
        "by_kind": {f: dict(c) for f, c in sorted(by_kind.items())},
        "by_field": {f: dict(c) for f, c in sorted(by_field.items(), key=lambda kv: -sum(kv[1].values()))[:40]},
    }


def diff_markdown(d: dict) -> str:
    def table(key_rows, title):
        out = [f"\n### {title}\n", "| n_fields | accepted | correct | wrong | halluc | precision | coverage | key |",
               "|---:|---:|---:|---:|---:|---:|---:|---|"]
        out += [f"| {x['n_fields']} | {x['accepted']} | {x['correct']} | {x['wrong']} | {x['hallucinated']} | "
                f"{_pct(x['precision'])} | {_pct(x['coverage'])} | {x['key']} |" for x in key_rows]
        return out
    lines = [f"# Run diff: {d['run_a']}  ->  {d['run_b']}\n",
             f"{d['n_common_fields']} common fields ({d['n_fields_only_a']} only in A, {d['n_fields_only_b']} only in B).",
             f"Outcomes A: {json.dumps(d['outcomes_a'])}",
             f"Outcomes B: {json.dumps(d['outcomes_b'])}",
             f"At threshold 0: A precision {_pct(d['at0_a']['precision'])} coverage {_pct(d['at0_a']['coverage'])} | "
             f"B precision {_pct(d['at0_b']['precision'])} coverage {_pct(d['at0_b']['coverage'])}\n",
             "## Transitions (A -> B)\n"]
    lines += [f"- {t}: {n}" for t, n in d["transitions"].items() if n]
    lines += [f"\n**{d['n_regressions']} regressions (correct -> wrong/hallucinated), {d['n_fixes']} fixes.**",
              "\n### Regressions (first 40)\n", "| doc | field | family | A | B |", "|---|---|---|---|---|"]
    lines += [f"| {r['doc_id'].rsplit('/', 1)[-1]} | {r['field']} | {r['family'][:30]} | {r['a'][:60]} | {r['b'][:60]} |"
              for r in d["regressions"][:40]]
    lines += table(d["by_route_b"], f"Run B at threshold 0 per route (A: {[ (x['key'], x['accepted']) for x in d['by_route_a'] ]})")
    lines += table(d["by_kind_b"], "Run B at threshold 0 per kind")
    lines += ["\n### Transitions per family\n", "| family | transitions |", "|---|---|"]
    lines += [f"| {f} | {json.dumps(c)} |" for f, c in d["by_family"].items()]
    lines += ["\n### Transitions per field (top 40)\n", "| field | transitions |", "|---|---|"]
    lines += [f"| {f} | {json.dumps(c)} |" for f, c in d["by_field"].items()]
    return "\n".join(lines) + "\n"


def write_diff(run_a: Path, run_b: Path) -> dict:
    rows_a = load_field_table(Path(run_a))
    rows_b = load_field_table(Path(run_b))
    d = diff_field_tables(rows_a, rows_b, name_a=Path(run_a).name, name_b=Path(run_b).name)
    registry.atomic_write_text(Path(run_b) / "diff.json", json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    registry.atomic_write_text(Path(run_b) / "diff.md", diff_markdown(d))
    return d


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run id, unambiguous name fragment, or run folder path")
    ap.add_argument("--rebuild", action="store_true", help="rebuild fields.jsonl first")
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--min-groups", type=int, default=1)
    ap.add_argument("--evidence", choices=EVIDENCE, default="grounded_text")
    ap.add_argument("--conf", type=float, default=0.0, help="confidence floor of the candidates")
    ap.add_argument("--cell-keys", nargs="+", default=list(CELL), help="columns forming the LOGO cell key")
    ap.add_argument("--legacy-families", action="store_true",
                    help="treat untitled documents as one family '?' (reproduces analyse_fields.py: 378 booked at min_n=3)")
    ap.add_argument("--no-write", action="store_true", help="print only, do not write report.md/json")
    ap.add_argument("--diff", nargs=2, metavar=("RUN_A", "RUN_B"),
                    help="per-field outcome transitions between two runs (A -> B), written to RUN_B/diff.md")
    a = ap.parse_args(argv)
    if a.diff:
        run_a, run_b = (registry.resolve_run(x) for x in a.diff)
        d = write_diff(run_a, run_b)
        t = d["transitions"]
        print(f"diff {d['run_a']} -> {d['run_b']}: {d['n_common_fields']} common fields, "
              f"{d['n_regressions']} regressions, {d['n_fixes']} fixes")
        print("  transitions: " + ", ".join(f"{k}={v}" for k, v in t.items() if v))
        print(f"  at threshold 0: A precision {_pct(d['at0_a']['precision'])} coverage {_pct(d['at0_a']['coverage'])}"
              f" | B precision {_pct(d['at0_b']['precision'])} coverage {_pct(d['at0_b']['coverage'])}")
        print(f"wrote {run_b / 'diff.md'} and diff.json")
        return 0
    run_dir = registry.resolve_run(a.run)
    rows = load_field_table(run_dir, rebuild=a.rebuild)
    if a.legacy_families:
        rows = legacy_families(rows)
    params = {"min_n": a.min_n, "min_groups": a.min_groups, "evidence": a.evidence, "conf": a.conf}
    if tuple(a.cell_keys) != CELL:
        params["cell_keys"] = tuple(a.cell_keys)
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
