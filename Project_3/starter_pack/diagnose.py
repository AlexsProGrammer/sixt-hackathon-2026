"""Show where a judge fails, with example replies. Standalone (stdlib only), shipped in the pack as diagnose.py.

    python3 diagnose.py verdicts.csv dev_pairs.jsonl [--examples 3] [--edit-type hedge_removal] [--lang de]

For every edit type it prints how often the judge got the pair right, and then a few failed pairs side by side:
- a harmful case fails when the judge does not pass the original AND fail the edited reply (a miss);
- a harmless case fails when the judge does not pass both (a false alarm).
Use it for Step 1 of the recipe: find the two or three failure types that cost the most, then read the examples.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import textwrap
from collections import defaultdict


def _jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _verdicts(path: str) -> dict[str, tuple[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["case_id"]: (r["original"].strip().lower(), r["edited"].strip().lower()) for r in csv.DictReader(f)}


def correct(case: dict, verdict: tuple[str, str]) -> bool:
    return verdict == (("pass", "fail") if case["edit_family"] == "harmful" else ("pass", "pass"))


def _wrap(label: str, text: str) -> str:
    return textwrap.fill(text, width=110, initial_indent=f"    {label:<10}", subsequent_indent=" " * 14)


def diagnose(cases: list[dict], verdicts: dict[str, tuple[str, str]], examples: int, seed: int = 0) -> str:
    cases = [c for c in cases if c["case_id"] in verdicts]
    by_type: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        by_type[c["edit_type"]].append(c)
    rows = []
    for t, cs in by_type.items():
        wrong = [c for c in cs if not correct(c, verdicts[c["case_id"]])]
        rows.append((len(wrong) / len(cs), t, cs, wrong))
    rows.sort(key=lambda r: (-r[0], r[1]))

    out = [f"{len(cases)} cases. Edit types, worst first ('miss' = harmful edit let through, 'false alarm' = harmless edit failed):",
           "", f"  {'edit type':<26}{'family':<10}{'n':>4}  {'wrong':>6}  wrong by language"]
    for rate, t, cs, wrong in rows:
        langs = defaultdict(lambda: [0, 0])
        for c in cs:
            langs[c["lang"]][1] += 1
        for c in wrong:
            langs[c["lang"]][0] += 1
        per_lang = "  ".join(f"{lang} {w}/{n}" for lang, (w, n) in sorted(langs.items()))
        out.append(f"  {t:<26}{cs[0]['edit_family']:<10}{len(cs):>4}  {rate:>6.0%}  {per_lang}")

    rng = random.Random(seed)
    for rate, t, cs, wrong in rows:
        if not wrong or examples <= 0:
            continue
        kind = "miss" if cs[0]["edit_family"] == "harmful" else "false alarm"
        out += ["", f"--- {t}: {len(wrong)} wrong ({kind}) — examples"]
        for c in rng.sample(wrong, min(examples, len(wrong))):
            v = verdicts[c["case_id"]]
            out.append(f"  [{c['case_id']} {c['lang']}] judge said original={v[0]}, edited={v[1]}   ({c['edit_note']})")
            out.append(_wrap("Q:", c["question"]))
            out.append(_wrap("original:", c["original"]))
            out.append(_wrap("edited:", c["edited"]))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verdicts")
    ap.add_argument("pairs")
    ap.add_argument("--examples", type=int, default=3, help="failed pairs to show per edit type")
    ap.add_argument("--edit-type", help="only this edit type")
    ap.add_argument("--lang", help="only this language")
    a = ap.parse_args(argv)
    cases = _jsonl(a.pairs)
    if a.edit_type:
        cases = [c for c in cases if c["edit_type"] == a.edit_type]
    if a.lang:
        cases = [c for c in cases if c["lang"] == a.lang]
    verdicts = _verdicts(a.verdicts)
    if not any(c["case_id"] in verdicts for c in cases):
        sys.exit("no case in the pairs file has a verdict: check you passed the matching files")
    print(diagnose(cases, verdicts, a.examples))


if __name__ == "__main__":
    main()
