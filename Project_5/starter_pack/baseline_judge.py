"""Baseline judge: one LLM call per reply, criterion and policy pasted into a plain prompt. Shipped as baseline_judge.py.

Deliberately naive. It is the starting point teams improve, not a good judge: no examples, no rule checks, no
decomposition, no voting, one model for every language.

Stdlib only. It talks to any OpenAI-compatible chat-completions endpoint. Configure it with environment variables:

    JUDGE_LLM_BASE_URL    endpoint base URL, up to and excluding /chat/completions   (required)
    JUDGE_LLM_API_KEY     API key                                                     (required)
    JUDGE_LLM_MODEL       model id                                                    (required)
    JUDGE_LLM_MAX_TOKENS  answer length limit, default 5: enough for one word. If your prompt lets the model reason
                          before answering, raise it, and make sure your parsing finds the final PASS or FAIL.
                          A cut-off answer is neither, so it is counted as fail (run_judge.py reports how many).
    JUDGE_LLM_TIMEOUT     seconds per request, default 60
    JUDGE_LLM_MAX_RETRIES retries on rate limits (HTTP 429) and server errors, default 6, with growing waits
                          (about two minutes in total before giving up)
    JUDGE_LLM_CACHE       optional path to a JSON file caching responses by (model, prompt). Saves budget on reruns,
                          but do NOT set it when measuring repeat consistency: a cache answers every repeat the same.

Run it on the fast dev subset and score it:

    python3 run_judge.py --judge baseline_judge.py --pairs dev_pairs_fast.jsonl --criterion JUDGE1_CRITERION.md \\
        --policy policy.md --out baseline_fast.csv
    python3 score.py baseline_fast.csv dev_pairs_fast.jsonl

Your judge keeps the same judge() signature and takes the criterion as input: for the surprise criterion the same
file is run with a different criterion and examples.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request

PROMPT = """You review a customer-service reply before it is sent.

{criterion}

Company policy:
{policy}

Customer question ({lang}): {question}
Reply ({lang}): {reply}

Answer with exactly one word: PASS or FAIL."""

MAX_RETRIES = int(os.environ.get("JUDGE_LLM_MAX_RETRIES", "6"))  # on rate limits (429) and server errors
_RETRY_STATUS = {429, 500, 502, 503, 504}
_cache: dict[str, str] | None = None
unparsed = 0  # answers that were neither PASS nor FAIL; counted as fail, reported by run_judge.py
_lock = threading.Lock()  # run_judge calls judge() from several threads: guards the cache and the counter


class LLMError(RuntimeError):
    pass


def _config() -> tuple[str, str, str, float, int]:
    base = os.environ.get("JUDGE_LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("JUDGE_LLM_API_KEY", "")
    model = os.environ.get("JUDGE_LLM_MODEL", "")
    missing = [n for n, v in (("JUDGE_LLM_BASE_URL", base), ("JUDGE_LLM_API_KEY", key), ("JUDGE_LLM_MODEL", model)) if not v]
    if missing:
        raise LLMError(f"set {', '.join(missing)} to use the baseline judge (see the top of baseline_judge.py)")
    return (base, key, model, float(os.environ.get("JUDGE_LLM_TIMEOUT", "60")),
            int(os.environ.get("JUDGE_LLM_MAX_TOKENS", "5")))


def _post(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """One HTTP POST returning the parsed JSON body. Raises urllib.error.HTTPError on a non-2xx status."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(2**attempt + random.random(), 60.0)


def _call(prompt: str) -> str:
    base, key, model, timeout, max_tokens = _config()
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES + 1):
        try:
            body = _post(f"{base}/chat/completions", payload, headers, timeout)
            return body["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise LLMError(f"LLM endpoint refused the key (HTTP {e.code}): check it is set, valid and has budget")
            if e.code not in _RETRY_STATUS or attempt == MAX_RETRIES:
                raise LLMError(f"LLM request failed with HTTP {e.code}") from e
            time.sleep(_wait(attempt, e.headers.get("Retry-After") if e.headers else None))
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == MAX_RETRIES:
                raise LLMError(f"LLM request failed: {e}") from e
            time.sleep(_wait(attempt, None))
    raise LLMError("unreachable")


def _cache_path() -> str | None:
    return os.environ.get("JUDGE_LLM_CACHE") or None


def complete(prompt: str) -> str:
    """The model's answer to one prompt, from the cache if JUDGE_LLM_CACHE is set."""
    global _cache
    path = _cache_path()
    if not path:
        return _call(prompt)
    key = hashlib.sha256(f"{os.environ.get('JUDGE_LLM_MODEL', '')}\n{prompt}".encode("utf-8")).hexdigest()
    with _lock:
        if _cache is None:
            _cache = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        if key in _cache:
            return _cache[key]
    answer = _call(prompt)  # outside the lock, so parallel calls stay parallel
    with _lock:
        _cache[key] = answer
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
    return answer


def parse(answer: str) -> str:
    """'pass' or 'fail'. An answer that is neither counts as fail: the conservative choice for a reply checker."""
    global unparsed
    word = answer.strip().strip("*.`'\" ").upper()
    if word.startswith("PASS"):
        return "pass"
    if not word.startswith("FAIL"):
        with _lock:
            unparsed += 1
            first = unparsed <= 3
        if first:
            print(f"baseline_judge: unparseable answer {answer[:40]!r}, counted as fail"
                  + (" (further ones are only counted)" if unparsed == 3 else ""), file=sys.stderr)
    return "fail"


def judge(question: str, reply: str, lang: str, criterion: str, policy: str) -> str:
    prompt = PROMPT.format(criterion=criterion.strip(), policy=policy.strip(), lang=lang, question=question, reply=reply)
    return parse(complete(prompt))
