"""HTTP transport for the OpenAI-compatible chat endpoint (urllib only).

- Timeout per request, clear error kinds, no raw response bodies in messages (API key redacted).
- At most MAX_RETRIES retries per request, and one wait budget shared by the whole run (WAIT_BUDGET_S).
  Retry-After is honoured in seconds or as an HTTP date.
- A 429 that cannot be retried within the budget stops all further requests of the run (shared stop event).
- Reply cache: SHA-256 over endpoint, model, temperature, sample_idx, prompt version and the full messages.
  Only successfully parsed objects are stored, written atomically (tempfile + os.replace).
- Parsing is strict: empty replies, non-JSON, and non-object JSON raise ParseError. Nothing is silently replaced.
"""
from __future__ import annotations

import email.utils
import hashlib
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT_S = 300
MAX_RETRIES = 1
WAIT_BUDGET_S = 60.0
RETRY_STATUSES = (429, 500, 502, 503, 504)


class TransportError(Exception):
    def __init__(self, kind: str, message: str, *, status: int | None = None,
                 retryable: bool = False, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retryable = retryable
        self.retry_after = retry_after


class ParseError(Exception):
    pass


class RunState:
    """Counters and the shared stop/wait state for one run. Thread-safe."""

    def __init__(self, wait_budget: float = WAIT_BUDGET_S):
        self._lock = threading.Lock()
        self.stop = threading.Event()
        self.wait_budget = wait_budget
        self.waited = 0.0
        self.requests = 0
        self.cache_hits = 0
        self.warnings: list[str] = []

    def bump(self, name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    def warn(self, message: str) -> None:
        with self._lock:
            self.warnings.append(message)

    def take_wait(self, seconds: float) -> bool:
        with self._lock:
            if self.waited + seconds > self.wait_budget:
                return False
            self.waited += seconds
            return True


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Retry-After as seconds or as an HTTP date. Returns None if absent or unparsable."""
    if not value:
        return None
    v = value.strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    now = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - now).total_seconds())


def redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def parse_reply(reply: object) -> dict:
    """Strict parse of one model reply: a single JSON object, optionally inside one code fence."""
    if not isinstance(reply, str) or not reply.strip():
        raise ParseError("empty reply")
    s = reply.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        obj = json.loads(s)
    except ValueError:
        raise ParseError("reply is not valid JSON") from None
    if not isinstance(obj, dict):
        raise ParseError("reply JSON is not an object")
    return obj


def post_chat(cfg: dict, messages: list[dict], temperature: float, *, timeout: float = TIMEOUT_S) -> str:
    """One HTTP request. Returns the assistant text. Raises TransportError with a kind and status only."""
    key = cfg["LLM_API_KEY"]
    body = json.dumps({"model": cfg["LLM_MODEL"], "temperature": temperature, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        cfg["LLM_BASE_URL"].rstrip("/") + "/chat/completions", body,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = redact(e.read(300).decode("utf-8", "replace"), [key]).strip()[:200]
        raise TransportError("http", f"HTTP {e.code}" + (f": {detail}" if detail else ""),
                             status=e.code, retryable=e.code in RETRY_STATUSES,
                             retry_after=parse_retry_after(e.headers.get("Retry-After"))) from None
    except TimeoutError:
        raise TransportError("timeout", "request timed out", retryable=True) from None
    except urllib.error.URLError as e:
        reason = redact(str(getattr(e, "reason", e)), [key])
        raise TransportError("unreachable", f"endpoint unreachable: {reason[:200]}", retryable=True) from None
    except OSError:
        raise TransportError("unreachable", "connection error", retryable=True) from None
    try:
        payload = json.loads(raw)
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise TransportError("bad_response", "response has no usable choices[0].message.content") from None
    return content if content is not None else ""


def call_with_retry(cfg: dict, messages: list[dict], temperature: float, state: RunState,
                    *, sleep=time.sleep) -> str:
    """post_chat with bounded retries. A 429 that cannot be retried stops the whole run."""
    attempt = 0
    while True:
        if state.stop.is_set():
            raise TransportError("stopped", "run stopped after rate limit; request not sent")
        state.bump("requests")
        try:
            return post_chat(cfg, messages, temperature)
        except TransportError as e:
            if not e.retryable:
                raise
            if e.status == 429 and attempt >= MAX_RETRIES:
                state.stop.set()
                raise TransportError("rate_limited", "HTTP 429 after retry; run stopped", status=429) from None
            if attempt >= MAX_RETRIES:
                raise
            wait = e.retry_after if e.retry_after is not None else 2.0 * (2 ** attempt)
            if e.status == 429 and wait > WAIT_BUDGET_S:
                state.stop.set()
                raise TransportError("rate_limited", f"HTTP 429, Retry-After {wait:.0f}s exceeds budget; run stopped",
                                     status=429) from None
            if not state.take_wait(wait):
                if e.status == 429:
                    state.stop.set()
                    raise TransportError("rate_limited", "HTTP 429, wait budget exhausted; run stopped",
                                         status=429) from None
                raise
            sleep(wait)
            attempt += 1


class ReplyCache:
    """Disk cache for parsed model objects. Corrupt entries are reported and treated as misses."""

    def __init__(self, root: Path | None, state: RunState | None = None):
        self.root = Path(root) if root else None
        self.state = state

    @staticmethod
    def make_key(*, endpoint: str, model: str, temperature: float, sample_idx: int,
                 prompt_version: str, messages: list[dict]) -> str:
        canonical = json.dumps({"endpoint": endpoint, "model": model, "temperature": temperature,
                                "sample_idx": sample_idx, "prompt_version": prompt_version,
                                "messages": messages}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        if self.root is None:
            return None
        path = self._path(key)
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entry, dict) or not isinstance(entry.get("answer"), dict):
                raise ValueError("unexpected cache structure")
            return entry
        except (OSError, ValueError) as e:
            if self.state is not None:
                self.state.warn(f"corrupt cache entry ignored: {path.name[:12]}... ({type(e).__name__})")
            return None

    def put(self, key: str, entry: dict) -> None:
        if self.root is None:
            return
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def sample_temperature(sample_idx: int, temperature: float, sampling: str) -> float:
    """'mixed': sample 0 is greedy (0.0), the others use `temperature`. 'identical': every sample uses `temperature`."""
    if sampling == "identical":
        return temperature
    return 0.0 if sample_idx == 0 else temperature


def execute_job(job: dict, *, cfg: dict, cache: ReplyCache, state: RunState, temperature: float,
                prompt_version: str, build_messages, sampling: str = "mixed") -> dict:
    """Run one planned job. Always returns a result row; failures carry ok=False and an error kind."""
    result = {"job_id": job["job_id"], "sample_idx": job["sample_idx"], "chunk_id": job["chunk_id"],
              "batch_id": job["batch_id"], "start": job["start"], "end": job.get("end"),
              "field_names": job["field_names"], "answer": None, "ok": False, "error": None}
    try:
        messages = build_messages(job)
        temp = sample_temperature(job["sample_idx"], temperature, sampling)
        key = ReplyCache.make_key(endpoint=cfg["LLM_BASE_URL"].rstrip("/"), model=cfg["LLM_MODEL"],
                                  temperature=temp, sample_idx=job["sample_idx"],
                                  prompt_version=prompt_version, messages=messages)
        entry = cache.get(key)
        if entry is not None:
            state.bump("cache_hits")
            answer = entry["answer"]
        else:
            reply = call_with_retry(cfg, messages, temp, state)
            answer = parse_reply(reply)
            cache.put(key, {"answer": answer, "prompt_version": prompt_version, "model": cfg["LLM_MODEL"],
                            "temperature": temp, "sample_idx": job["sample_idx"]})
        result.update(answer=answer, ok=True)
    except TransportError as e:
        result["error"] = e.kind + (f":{e.status}" if e.status else "")
    except ParseError as e:
        result["error"] = "parse:" + str(e)
    except Exception as e:  # a bug must not kill the whole run silently; it is reported per job
        result["error"] = f"internal:{type(e).__name__}"
    return result
