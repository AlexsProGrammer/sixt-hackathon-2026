"""Run a judge on paired cases and write verdicts. Standalone (stdlib only), shipped in the pack as run_judge.py.

    python3 run_judge.py --judge my_judge.py --pairs dev_pairs_fast.jsonl --criterion JUDGE1_CRITERION.md \\
        --policy policy.md --out verdicts.csv [--dev dev_pairs.jsonl]

Your file must define

    def judge(question: str, reply: str, lang: str, criterion: str, policy: str) -> str   # "pass" or "fail"

and may define

    def prepare(criterion: str, policy: str, dev_pairs: list[dict]) -> None   # called once before judging

The judge sees ONE reply at a time, never the pair, the edit type or the label. Each distinct (lang, question, reply)
is judged once, in a shuffled order, and the verdict is reused for every case that contains it. Your code is run the
same way on test cases you have not seen, and with the surprise criterion.

Speed: --workers N judges N replies at once (default 5). If your endpoint answers "too many requests" (HTTP 429),
the baseline client waits and retries (JUDGE_LLM_MAX_RETRIES, default 6); if it still fails, the run stops at once
rather than spending your budget on the rest. Lower --workers if that happens. Your judge()
must then be thread-safe: no shared mutable state without a lock. If it is not, run with --workers 1. Iterate on
dev_pairs_fast.jsonl (a small stratified subset) and use dev_pairs.jsonl for final numbers. How fast a run is depends
mostly on the rate limit of your LLM endpoint, not on --workers.

Rule: the judge must not keep state between calls (for example to find a near-duplicate reply it saw earlier and
diff the two). Your code may be run with --isolate, which loads a fresh copy of your module (and calls prepare()
again) for every reply; a judge that only works with shared state across calls will then behave differently.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import traceback
import importlib.util
import json
import random
import sys


def load_judge(path: str):
    spec = importlib.util.spec_from_file_location("contestant_judge", path)
    if spec is None or spec.loader is None:
        sys.exit(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # so the end-of-run report can find its counters
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "judge", None)):
        sys.exit(f"{path} must define judge(question, reply, lang, criterion, policy)")
    return mod


def _norm(v) -> str:
    if isinstance(v, bool):
        return "pass" if v else "fail"
    s = str(v).strip().lower()
    if s not in ("pass", "fail"):
        raise ValueError(f"judge returned {v!r}, expected 'pass' or 'fail'")
    return s


def _prepared(mod, criterion: str, policy: str, dev_pairs: list[dict] | None):
    if callable(getattr(mod, "prepare", None)):
        mod.prepare(criterion, policy, dev_pairs or [])
    return mod


def run(
    judge_path: str, cases: list[dict], criterion: str, policy: str, dev_pairs: list[dict] | None = None,
    seed: int = 0, isolate: bool = False, workers: int = 1, progress: bool = False,
) -> dict:
    """Returns {case_id: (original verdict, edited verdict)}."""
    mod = _prepared(load_judge(judge_path), criterion, policy, dev_pairs)
    items = set()
    for c in cases:
        items.add((c["orig_lang"], c["question_original"], c["original"]))
        items.add((c["lang"], c["question"], c["edited"]))
    order = sorted(items)
    random.Random(seed).shuffle(order)

    def one(it: tuple[str, str, str]) -> str:
        m = _prepared(load_judge(judge_path), criterion, policy, dev_pairs) if isolate else mod
        return _norm(m.judge(it[1], it[2], it[0], criterion, policy))

    verdict = {}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = {pool.submit(one, it): it for it in order}
        for done, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            verdict[futures[fut]] = fut.result()
            if progress and (done % 25 == 0 or done == len(order)):
                print(f"  judged {done}/{len(order)} replies", file=sys.stderr)
    except BaseException:
        # stop at the first error instead of judging (and paying for) everything still queued
        pool.shutdown(wait=True, cancel_futures=True)
        print(f"  stopped after {len(verdict)}/{len(order)} replies", file=sys.stderr)
        raise
    pool.shutdown(wait=True)
    return {
        c["case_id"]: (
            verdict[(c["orig_lang"], c["question_original"], c["original"])],
            verdict[(c["lang"], c["question"], c["edited"])],
        )
        for c in cases
    }


def _jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judge", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--criterion", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dev", help="labelled dev pairs passed to prepare(), if your judge defines it")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--isolate", action="store_true", help="fresh module (and prepare()) for every reply")
    ap.add_argument("--workers", type=int, default=5, help="replies judged in parallel (default 5; 1 = sequential)")
    ap.add_argument("--traceback", action="store_true", help="show the full traceback when the judge raises")
    a = ap.parse_args(argv)
    with open(a.criterion, encoding="utf-8") as f:
        criterion = f.read()
    with open(a.policy, encoding="utf-8") as f:
        policy = f.read()
    try:
        res = run(a.judge, _jsonl(a.pairs), criterion, policy, _jsonl(a.dev) if a.dev else None, a.seed, a.isolate,
                  a.workers, progress=True)
    except Exception as e:  # noqa: BLE001 - one readable line for the common case (missing settings, bad answer)
        if a.traceback:
            traceback.print_exc()
        sys.exit(f"error: {type(e).__name__}: {e}" + ("" if a.traceback else "   (run with --traceback for details)"))
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "original", "edited"])
        for cid in sorted(res):
            w.writerow([cid, *res[cid]])
    print(f"wrote {len(res)} verdict rows to {a.out}")
    unparsed = _unparsed_count()
    if unparsed:
        print(f"WARNING: {unparsed} LLM answers were neither PASS nor FAIL and were counted as fail. If your prompt makes "
              "the model reason first, raise JUDGE_LLM_MAX_TOKENS and parse the final answer.", file=sys.stderr)


def _unparsed_count() -> int:
    """Answers the baseline's parse() could not read, summed over every loaded copy of it (judges import it)."""
    return sum(getattr(m, "unparsed", 0) for name, m in list(sys.modules.items())
               if name in ("baseline_judge", "contestant_judge") or name.endswith("hackathon_baseline_judge"))


if __name__ == "__main__":
    main()
