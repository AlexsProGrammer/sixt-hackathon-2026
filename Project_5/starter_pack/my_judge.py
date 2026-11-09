"""Your judge, laid out as the four recipe steps. Shipped in the pack as my_judge.py.

As shipped it behaves exactly like baseline_judge.py, so your first run reproduces the baseline. Then fill in the
steps, one at a time, and measure after each (iterate on dev_pairs_fast.jsonl; how long a run takes depends
mostly on your LLM endpoint's rate limit):

    python3 run_judge.py --judge my_judge.py --pairs dev_pairs_fast.jsonl --criterion JUDGE1_CRITERION.md \\
        --policy policy.md --dev dev_pairs.jsonl --out mine_fast.csv
    python3 score.py mine_fast.csv dev_pairs_fast.jsonl --baseline baseline_dev_verdicts.csv
    python3 diagnose.py mine_fast.csv dev_pairs_fast.jsonl

Rules of the game:
- Everything criterion-specific must come from the inputs (criterion, policy, dev examples), never be hard-coded:
  for the surprise criterion this same file is run with a different criterion and examples.
- judge() sees one reply at a time and must not keep state between calls. It runs in several threads at once, so
  only read module-level data after prepare().
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_judge import PROMPT, complete, parse  # noqa: E402  (baseline_judge.py sits next to this file)

VOTES = 1  # Step 3 option: majority of several calls (costs VOTES calls per reply). The baseline runs at
# temperature 0, so votes only differ if you vary the prompt, the model or the temperature between them.
EXAMPLES: list[dict] = []  # filled by prepare(); read-only afterwards


def prepare(criterion: str, policy: str, dev_pairs: list[dict]) -> None:
    """Called once before judging, with the labelled dev pairs (pass --dev to run_judge.py).

    Step 3 option: pick a few labelled examples to show the LLM. Choose them from dev_pairs by what they teach,
    not by hard-coding texts, so the same code picks sensible examples for the surprise criterion too.
    """
    EXAMPLES.clear()
    # e.g. EXAMPLES.extend(one harmful and one harmless pair per edit type from dev_pairs)


def rules(question: str, reply: str, lang: str, policy: str) -> str | None:
    """Step 2: checks plain code can do. Return "fail" when a rule is sure the reply breaks the criterion, else None.

    Ideas: every number in the reply must appear in the policy for that topic; a word like "always" next to a
    claim the policy hedges. Test each rule on dev: it must never fail a harmless edit.
    """
    return None


def build_prompt(question: str, reply: str, lang: str, criterion: str, policy: str) -> str:
    """Step 3: the LLM part. Better instructions, examples, sub-questions, per-language hints...

    The baseline reads only a one-word answer: JUDGE_LLM_MAX_TOKENS defaults to 5 and parse() looks for PASS or FAIL
    at the start. If your prompt lets the model reason first, raise JUDGE_LLM_MAX_TOKENS and parse the final answer
    yourself, or every cut-off answer silently counts as fail (run_judge.py prints how many there were).
    """
    return PROMPT.format(criterion=criterion.strip(), policy=policy.strip(), lang=lang, question=question, reply=reply)


def judge(question: str, reply: str, lang: str, criterion: str, policy: str) -> str:
    verdict = rules(question, reply, lang, policy)
    if verdict is not None:
        return verdict
    prompt = build_prompt(question, reply, lang, criterion, policy)
    votes = [parse(complete(prompt)) for _ in range(VOTES)]
    return "fail" if votes.count("fail") * 2 >= len(votes) else "pass"
