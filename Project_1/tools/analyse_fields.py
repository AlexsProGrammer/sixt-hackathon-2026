#!/usr/bin/env python3
"""Per-field error analysis of an existing prediction file against dev gold. No API calls.
usage: .venv/bin/python -m tools.analyse_fields results/llm_dev.jsonl"""
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = load("scorer", ROOT / "5_score.py")
X = load("extract", ROOT / "4_extract.py")
from uncertainty.grounding import is_grounded, field_kind  # noqa: E402


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m tools.analyse_fields <preds.jsonl>")
    preds = S.load_preds(sys.argv[1])
    gold = [r for r in S.read_jsonl(str(ROOT / "data/unified/dev.jsonl")) if r["doc_id"] in preds]
    rows = []
    for rec in gold:
        props = rec["schema"].get("properties", {})
        fam = "cuad" if rec["source_dataset"] == "cuad" else str(rec["schema"].get("title", "?"))[:45]
        grp = re.sub(r"-p\d+(-r\d+)?$", "", rec["doc_id"])   # -r1..-r4 are re-renders of the same page
        try:
            text = X.full_text(rec)
        except Exception:
            text = None
        for r in S.collect([rec], preds):
            spec = props.get(r["field"], {})
            val = (preds[rec["doc_id"]].get(r["field"]) or {}).get("value")
            r.update(fam=fam, grp=grp, kind=field_kind(spec), has_text=bool(text and text.strip()),
                     grounded=bool(r["pred_present"] and is_grounded(val, text, spec)))
            rows.append(r)

    N = len(rows)
    acc = [r for r in rows if r["pred_present"]]
    print(f"{len(gold)} docs, {N} fields, {len(acc)} non-null predictions")

    def st(rs):
        c = sum(r["match"] for r in rs)
        h = sum(not r["gold_present"] for r in rs)
        return len(rs), c, len(rs) - c - h, h

    def show(title, keyf, rs, min_n=1, limit=80):
        t = defaultdict(list)
        for r in rs:
            t[keyf(r)].append(r)
        items = [(k, v) for k, v in t.items() if len(v) >= min_n]
        items.sort(key=lambda kv: (st(kv[1])[2] + st(kv[1])[3], -len(kv[1])))
        print(f"\n== {title}\n{'n':>5} {'ok':>5} {'wrong':>5} {'hall':>5} {'prec':>6}  key")
        for k, v in items[:limit]:
            n, c, w, h = st(v)
            print(f"{n:5d} {c:5d} {w:5d} {h:5d} {c/n:6.3f}  {k}")

    show("source / kind / grounded", lambda r: (r["source"], r["kind"], r["grounded"]), acc)
    show("source / confidence", lambda r: (r["source"], round(min(r["conf"], 1.0), 2)), acc, limit=200)
    show("family / field (grounded only, n>=3), safest first", lambda r: (r["fam"], r["field"]),
         [r for r in acc if r["grounded"]], min_n=3)

    def simulate(min_n, grounded=True, tconf=0.0):
        cand = [r for r in acc if r["conf"] >= tconf and (r["grounded"] or not grounded)]
        by = defaultdict(list)
        for r in cand:
            by[(r["fam"], r["field"])].append(r)
        booked = bad = 0
        for r in cand:
            others = [o for o in by[(r["fam"], r["field"])] if o["grp"] != r["grp"]]
            if len(others) >= min_n and all(o["match"] for o in others):
                booked += 1
                bad += not r["match"]
        print(f"min_n={min_n:2d} grounded={grounded!s:5} conf>={tconf}: booked={booked:5d} wrong={bad:3d} "
              f"net={(booked - 100 * bad) / N:+.2%} of {N} fields")

    print("\n== leave-one-group-out whitelist (cell booked only if 0 errors on OTHER document groups)")
    for m in (3, 5, 10, 20):
        for g in (True, False):
            simulate(m, g)
    simulate(5, True, 0.9)


if __name__ == "__main__":
    main()
