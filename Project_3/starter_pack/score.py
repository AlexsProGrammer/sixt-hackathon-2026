"""Score a judge on paired edit cases. Standalone (stdlib only), shipped in the contestant pack as score.py.

    python3 score.py verdicts.csv dev_pairs.jsonl [--baseline baseline_verdicts.csv] [--repeat run2.csv]
        [--human-labels h.csv] [--json out.json]

verdicts.csv:   case_id,original,edited      (pass | fail; the judge's verdict on each side of the case)
pairs.jsonl:    the answer key: case_id, edit_type, edit_family (harmless|harmful), lang, ...
human labels:   case_id,side,label           (side = original | edited; optional)

Metrics
- catch     = share of harmful cases where the judge passes the original AND fails the edited reply.
- keep      = share of harmless cases where the judge passes both the original and the edited reply.
- raw catch / raw stability are reported too (edited fails; verdict unchanged), but they reward a judge that
  rejects everything (it is perfectly "stable" and "catches" everything), so they are not the score.
- combined  = harmonic mean of macro catch and macro keep (macro = mean over edit types, so a frequent edit type
  cannot carry the score). A judge that rejects everything gets catch 0 and keep 0 -> combined 0; accept-all gets
  keep 1 but catch 0 -> combined 0.
- kappa     = Cohen's kappa of the judge's verdicts vs the construction labels (original = pass; edited = pass for
  harmless, fail for harmful), over every judged reply; and vs human labels where provided.
- consistency (with --repeat run2.csv, a second run of the same judge on the same pairs): the share of replies that
  got the same verdict both times, and Cohen's kappa between the two runs. A judge can be perfectly consistent and
  still wrong, so read it next to the score, never instead of it.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict

NAN = float("nan")


def read_pairs(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_verdicts(path: str) -> dict[str, tuple[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        o, e = r["original"].strip().lower(), r["edited"].strip().lower()
        if o not in ("pass", "fail") or e not in ("pass", "fail"):
            sys.exit(f"verdicts must be 'pass' or 'fail', got {o!r}/{e!r} for {r['case_id']}")
        out[r["case_id"]] = (o, e)
    return out


def kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    if n == 0:
        return NAN
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return NAN if pe >= 1 else (po - pe) / (1 - pe)


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if not math.isnan(x)]
    return sum(xs) / len(xs) if xs else NAN


def _hmean(a: float, b: float) -> float:
    if math.isnan(a) or math.isnan(b):
        return NAN
    return 0.0 if a + b == 0 else 2 * a * b / (a + b)


def _rates(cases: list[dict], verdicts: dict[str, tuple[str, str]]) -> dict:
    harmful = [verdicts[c["case_id"]] for c in cases if c["edit_family"] == "harmful"]
    harmless = [verdicts[c["case_id"]] for c in cases if c["edit_family"] == "harmless"]

    def share(xs: list, pred) -> float:
        return sum(1 for x in xs if pred(x)) / len(xs) if xs else NAN

    return {
        "n_harmful": len(harmful),
        "n_harmless": len(harmless),
        "catch": share(harmful, lambda v: v == ("pass", "fail")),
        "raw_catch": share(harmful, lambda v: v[1] == "fail"),
        "keep": share(harmless, lambda v: v == ("pass", "pass")),
        "raw_stability": share(harmless, lambda v: v[0] == v[1]),
        "original_pass": share(harmful + harmless, lambda v: v[0] == "pass"),
    }


def consistency(cases: list[dict], run1: dict[str, tuple[str, str]], run2: dict[str, tuple[str, str]]) -> dict:
    """Agreement of two runs of the same judge, over every distinct judged reply (each case judges two)."""
    a, b = {}, {}
    for c in cases:
        if c["case_id"] not in run1 or c["case_id"] not in run2:
            raise ValueError(f"case {c['case_id']} is missing from one of the runs; repeat the run on the same pairs file")
        for side, key in ((0, (c["orig_lang"], c["original"])), (1, (c["lang"], c["edited"]))):
            a[key], b[key] = run1[c["case_id"]][side], run2[c["case_id"]][side]
    keys = sorted(a)
    x, y = [a[k] for k in keys], [b[k] for k in keys]
    return {"n_replies": len(keys), "same_verdict": sum(p == q for p, q in zip(x, y)) / len(keys) if keys else NAN,
            "kappa_between_runs": kappa(x, y)}


def score(cases: list[dict], verdicts: dict[str, tuple[str, str]], human: dict | None = None) -> dict:
    missing = [c["case_id"] for c in cases if c["case_id"] not in verdicts]
    if missing:
        raise ValueError(f"{len(missing)} of {len(cases)} case ids have no verdict, e.g. {missing[:3]}. Score against the "
                         "same pairs file you ran the judge on (e.g. verdicts from dev_pairs_fast.jsonl need "
                         "dev_pairs_fast.jsonl). A --baseline file may cover more cases than that.")
    by_type: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        by_type[c["edit_type"]].append(c)
    per_type = {t: _rates(cs, verdicts) for t, cs in sorted(by_type.items())}
    macro_catch = _mean([r["catch"] for t, r in per_type.items() if r["n_harmful"]])
    macro_keep = _mean([r["keep"] for t, r in per_type.items() if r["n_harmless"]])
    y, p = [], []
    for c in cases:
        o, e = verdicts[c["case_id"]]
        y += ["pass", c["edited_label"]]
        p += [o, e]
    out = {
        "n_cases": len(cases),
        "combined": _hmean(macro_catch, macro_keep),
        "macro_catch": macro_catch,
        "macro_keep": macro_keep,
        "micro": _rates(cases, verdicts),
        "kappa_vs_construction": kappa(y, p),
        "per_edit_type": per_type,
        "per_lang": _group(cases, verdicts, "lang"),
        "per_visibility": _group(cases, verdicts, "visibility"),
    }
    if human:
        hy, hp = [], []
        for c in cases:
            for side, v in zip(("original", "edited"), verdicts[c["case_id"]]):
                lab = human.get((c["case_id"], side))
                if lab:
                    hy.append(lab)
                    hp.append(v)
        out["n_human_labels"] = len(hy)
        out["kappa_vs_human"] = kappa(hy, hp)
    return out


def _group(cases: list[dict], verdicts: dict, key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        groups[str(c.get(key))].append(c)
    out = {}
    for g, cs in sorted(groups.items()):
        r = _rates(cs, verdicts)
        r["combined_micro"] = _hmean(r["catch"], r["keep"])
        out[g] = r
    return out


def read_human(path: str) -> dict[tuple[str, str], str]:
    with open(path, newline="", encoding="utf-8") as f:
        return {
            (r["case_id"], r["side"]): r["label"].strip().lower()
            for r in csv.DictReader(f)
            if r["label"].strip().lower() in ("pass", "fail")
        }


def fmt(x: float) -> str:
    return "  n/a" if isinstance(x, float) and math.isnan(x) else f"{x:.3f}"


def report(res: dict, base: dict | None = None) -> str:
    lines = [f"cases: {res['n_cases']}"]

    def row(name: str, key: str) -> str:
        s = f"{name:<26} {fmt(res[key])}"
        if base is not None:
            d = res[key] - base[key]
            s += f"   (baseline {fmt(base[key])}, delta {'+' if d >= 0 else ''}{d:.3f})"
        return s

    lines += [row("COMBINED (the score)", "combined"), row("macro catch", "macro_catch"), row("macro keep", "macro_keep"),
              row("kappa vs construction", "kappa_vs_construction")]
    if "consistency" in res:
        c = res["consistency"]
        lines.append(f"{'consistency (2 runs)':<26} same verdict {fmt(c['same_verdict'])}, kappa {fmt(c['kappa_between_runs'])}"
                     f"  (n={c['n_replies']} replies)")
    if "kappa_vs_human" in res:
        lines.append(f"{'kappa vs human':<26} {fmt(res['kappa_vs_human'])}  (n={res['n_human_labels']} labelled replies)")
    m = res["micro"]
    lines.append(
        f"micro: catch {fmt(m['catch'])}  keep {fmt(m['keep'])}  raw catch {fmt(m['raw_catch'])}  "
        f"raw stability {fmt(m['raw_stability'])}  original pass {fmt(m['original_pass'])}"
    )
    lines.append("\nper edit type              n   catch   keep  raw_stab")
    for t, r in res["per_edit_type"].items():
        n = r["n_harmful"] or r["n_harmless"]
        lines.append(f"  {t:<24}{n:>4}  {fmt(r['catch'])}  {fmt(r['keep'])}  {fmt(r['raw_stability'])}")
    keys = ["per_lang"]
    if any(g != "None" for g in res["per_visibility"]):  # dev files have no visibility field
        keys.insert(0, "per_visibility")
    for key in keys:
        lines.append(f"\n{key.replace('_', ' ')}            catch   keep  combined")
        for g, r in res[key].items():
            lines.append(f"  {g:<20} {fmt(r['catch'])}  {fmt(r['keep'])}  {fmt(r['combined_micro'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verdicts")
    ap.add_argument("pairs")
    ap.add_argument("--baseline", help="verdicts CSV of the baseline judge, to report the improvement")
    ap.add_argument("--repeat", help="verdicts CSV of a second run of the same judge on the same pairs (consistency)")
    ap.add_argument("--human-labels")
    ap.add_argument("--json", help="also write the full result as JSON")
    a = ap.parse_args(argv)
    cases = read_pairs(a.pairs)
    human = read_human(a.human_labels) if a.human_labels else None
    try:
        res = score(cases, read_verdicts(a.verdicts), human)
        if a.repeat:
            res["consistency"] = consistency(cases, read_verdicts(a.verdicts), read_verdicts(a.repeat))
        base = score(cases, read_verdicts(a.baseline), human) if a.baseline else None
    except ValueError as e:
        sys.exit(str(e))
    print(report(res, base))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"result": res, "baseline": base}, f, indent=1)
    return res


if __name__ == "__main__":
    main()
