"""HTTP transport for the OpenAI-compatible chat endpoint (urllib only).

- Timeout per request, clear error kinds, no raw response bodies in messages (API key redacted).
- At most MAX_RETRIES retries per request, and one wait budget shared by the whole run (WAIT_BUDGET_S).
  Retry-After is honoured in seconds or as an HTTP date.
- A 429 that cannot be retried within the budget stops all further requests of the run (shared stop event).
- Reply cache: SHA-256 over endpoint, model, temperature, sample_idx, prompt version and the full messages
  (plus input_kind / attachment_sha256 when not the text default, so old text keys stay valid).
  Layout v2: <root>/replies/<model_slug>/<prompt_version>/<key[:2]>/<key>.json; the legacy <root>/<key[:2]>/<key>.json
  is read as a fallback. Only successfully parsed objects are stored, written atomically (tempfile + os.replace).
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

from pipeline.messages import key_messages

TIMEOUT_S = 300
MAX_RETRIES = 1
WAIT_BUDGET_S = 60.0
RETRY_STATUSES = (429, 500, 502, 503, 504)


_LAST = threading.local()  # usage block of the last successful post_chat in this thread (best effort metadata)


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


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


class RunState:
    """Counters and the shared stop/wait state for one run. Thread-safe."""

    def __init__(self, wait_budget: float | None = None, *,
                 min_interval: float | None = None, max_retries: int | None = None):
        self._lock = threading.Lock()
        self.stop = threading.Event()
        self.wait_budget = _env_float("LLM_WAIT_BUDGET_S", WAIT_BUDGET_S) if wait_budget is None else wait_budget
        self.min_interval = _env_float("LLM_MIN_INTERVAL_S", 0.0) if min_interval is None else min_interval
        self.max_retries = _env_int("LLM_MAX_RETRIES", MAX_RETRIES) if max_retries is None else max_retries
        self.waited = 0.0
        self.requests = 0
        self.cache_hits = 0
        self.warnings: list[str] = []
        self._next_request_at = 0.0

    def pace(self, sleep=time.sleep) -> None:
        """Enforce LLM_MIN_INTERVAL_S between outbound requests across threads."""
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = self._next_request_at - now
            self._next_request_at = max(now, self._next_request_at) + self.min_interval
        if delay > 0:
            sleep(delay)

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
        # strict=False: long quoted passages often contain literal line breaks or tabs, which strict JSON rejects.
        # Such characters are accepted only inside string values; invalid structure is still a visible error.
        obj = json.loads(s, strict=False)
    except ValueError:
        raise ParseError("reply is not valid JSON") from None
    if not isinstance(obj, dict):
        raise ParseError("reply JSON is not an object")
    return obj


def post_chat(cfg: dict, messages: list[dict], temperature: float, *, model: str | None = None,
              timeout: float = TIMEOUT_S) -> str:
    """One HTTP request to `model` (default cfg["LLM_MODEL"]). Returns the assistant text.
    Raises TransportError with a kind, status and a redacted body excerpt (max 200 chars) only.
    Usage and elapsed seconds of the call are available through last_call_meta() in the same thread."""
    key = cfg["LLM_API_KEY"]
    model = model or cfg["LLM_MODEL"]
    body = json.dumps({"model": model, "temperature": temperature, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        cfg["LLM_BASE_URL"].rstrip("/") + "/chat/completions", body,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    t0 = time.monotonic()
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
    usage = payload.get("usage") if isinstance(payload, dict) else None
    _LAST.usage = usage if isinstance(usage, dict) else None
    _LAST.elapsed = round(time.monotonic() - t0, 3)
    return content if content is not None else ""


def last_call_meta() -> dict:
    """{"usage": dict | None, "elapsed_s": float | None} of the last successful post_chat in this thread."""
    return {"usage": getattr(_LAST, "usage", None), "elapsed_s": getattr(_LAST, "elapsed", None)}


def call_with_retry(cfg: dict, messages: list[dict], temperature: float, state: RunState,
                    *, sleep=time.sleep, model: str | None = None, timeout: float | None = None) -> str:
    """post_chat with bounded retries. A 429 that cannot be retried stops the whole run.
    An HTTP 400 is added to state.warnings (model, redacted body excerpt) to debug capabilities."""
    attempt = 0
    extra = {} if model is None else {"model": model}
    if timeout is not None:
        extra["timeout"] = timeout
    while True:
        if state.stop.is_set():
            raise TransportError("stopped", "run stopped after rate limit; request not sent")
        state.pace(sleep=sleep)
        state.bump("requests")
        try:
            return post_chat(cfg, messages, temperature, **extra)
        except TransportError as e:
            if e.status == 400:
                state.warn(f"{model or cfg.get('LLM_MODEL')}: {e}"[:260])
            if not e.retryable:
                raise
            max_retries = getattr(state, "max_retries", MAX_RETRIES)
            if e.status == 429 and attempt >= max_retries:
                state.stop.set()
                raise TransportError("rate_limited", "HTTP 429 after retry; run stopped", status=429) from None
            if attempt >= max_retries:
                raise
            wait = e.retry_after if e.retry_after is not None else 2.0 * (2 ** attempt)
            if e.status == 429 and wait > state.wait_budget:
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


def call_model(cfg: dict, model: str, messages: list[dict], temperature: float, state: RunState,
               *, sleep=time.sleep, timeout: float | None = None) -> dict:
    """Call any endpoint model with retry. Returns {"text", "usage", "elapsed_s"}. The per-model timeout comes from
    models.json unless given. Raises TransportError."""
    if timeout is None:
        from pipeline.models import model_spec
        timeout = float(model_spec(model).get("timeout_s") or TIMEOUT_S)
    text = call_with_retry(cfg, messages, temperature, state, sleep=sleep, model=model, timeout=timeout)
    meta = last_call_meta()
    return {"text": text, "usage": meta["usage"], "elapsed_s": meta["elapsed_s"]}


def model_slug(model: str | None) -> str:
    """Filesystem-safe model name: '/' and ':' become '__'."""
    slug = (model or "").strip().replace("/", "__").replace(":", "__").replace("\\", "__")
    return slug or "_unknown"


def _safe_part(value: str | None) -> str:
    part = (value or "").strip().replace("/", "_").replace("\\", "_")
    return part if part and part not in (".", "..") else "_unknown"


class ReplyCache:
    """Disk cache for parsed model objects. Corrupt entries are reported and treated as misses.

    layout="v2": <root>/replies/<model_slug>/<prompt_version>/<key[:2]>/<key>.json, with a read-only fallback to the
    legacy flat layout <root>/<key[:2]>/<key>.json. layout="legacy" keeps the flat layout for reads and writes.
    """

    def __init__(self, root: Path | None, state: RunState | None = None, *, layout: str = "v2"):
        if layout not in ("v2", "legacy"):
            raise ValueError(f"unknown cache layout: {layout}")
        self.root = Path(root) if root else None
        self.state = state
        self.layout = layout

    @staticmethod
    def make_key(*, endpoint: str, model: str, temperature: float, sample_idx: int,
                 prompt_version: str, messages: list[dict],
                 input_kind: str = "text", attachment_sha256: str | None = None) -> str:
        fields = {"endpoint": endpoint, "model": model, "temperature": temperature,
                  "sample_idx": sample_idx, "prompt_version": prompt_version, "messages": messages}
        # Added only when not the default, so keys of plain text jobs equal the pre-v2 keys.
        if input_kind != "text":
            fields["input_kind"] = input_kind
        if attachment_sha256:
            fields["attachment_sha256"] = attachment_sha256
        canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _legacy_path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def _path(self, key: str, model: str | None = None, prompt_version: str | None = None) -> Path:
        if self.layout == "legacy":
            return self._legacy_path(key)
        return (self.root / "replies" / model_slug(model) / _safe_part(prompt_version) / key[:2] / f"{key}.json")

    def _read(self, path: Path) -> dict | None:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entry, dict) or not isinstance(entry.get("answer"), dict):
                raise ValueError("unexpected cache structure")
            return entry
        except (OSError, ValueError) as e:
            if self.state is not None:
                self.state.warn(f"corrupt cache entry ignored: {path.name[:12]}... ({type(e).__name__})")
            return None

    def get(self, key: str, model: str | None = None, prompt_version: str | None = None) -> dict | None:
        if self.root is None:
            return None
        path = self._path(key, model, prompt_version)
        if path.exists():
            return self._read(path)
        if self.layout == "v2":
            legacy = self._legacy_path(key)  # read-only fallback until the migration is confirmed
            if legacy.exists():
                return self._read(legacy)
        return None

    def put(self, key: str, entry: dict, model: str | None = None, prompt_version: str | None = None) -> None:
        if self.root is None:
            return
        model = model or entry.get("model")
        prompt_version = prompt_version or entry.get("prompt_version")
        target = self._path(key, model, prompt_version)
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
                prompt_version: str, build_messages, sampling: str = "mixed", model: str | None = None) -> dict:
    """Run one planned job. Always returns a result row; failures carry ok=False and an error kind.
    `model` overrides cfg["LLM_MODEL"]. build_messages may return messages or (messages, input_kind, attachment_sha256);
    attachment bytes are replaced by a placeholder in the cache key, which uses attachment_sha256 instead."""
    result = {"job_id": job["job_id"], "sample_idx": job["sample_idx"], "chunk_id": job["chunk_id"],
              "batch_id": job["batch_id"], "start": job["start"], "end": job.get("end"),
              "field_names": job["field_names"], "answer": None, "ok": False, "error": None}
    try:
        built = build_messages(job)
        if isinstance(built, tuple):
            messages, input_kind, attachment_sha = built
        else:
            messages, input_kind, attachment_sha = built, "text", None
        temp = sample_temperature(job["sample_idx"], temperature, sampling)
        model = model or cfg["LLM_MODEL"]
        key = ReplyCache.make_key(endpoint=cfg["LLM_BASE_URL"].rstrip("/"), model=model,
                                  temperature=temp, sample_idx=job["sample_idx"],
                                  prompt_version=prompt_version, messages=key_messages(messages),
                                  input_kind=input_kind, attachment_sha256=attachment_sha)
        entry = cache.get(key, model, prompt_version)
        if entry is not None:
            state.bump("cache_hits")
            answer = entry["answer"]
        else:
            _LAST.usage = None
            t0 = time.monotonic()
            reply = call_with_retry(cfg, messages, temp, state, model=model)
            elapsed = round(time.monotonic() - t0, 3)
            answer = parse_reply(reply)
            new_entry = {"answer": answer, "prompt_version": prompt_version, "model": model,
                         "temperature": temp, "sample_idx": job["sample_idx"], "input_kind": input_kind,
                         "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "elapsed_s": elapsed}
            usage = getattr(_LAST, "usage", None)
            if usage:
                new_entry["usage"] = usage
            cache.put(key, new_entry, model, prompt_version)
        result.update(answer=answer, ok=True)
    except TransportError as e:
        result["error"] = e.kind + (f":{e.status}" if e.status else "")
    except ParseError as e:
        result["error"] = "parse:" + str(e)
    except Exception as e:  # a bug must not kill the whole run silently; it is reported per job
        result["error"] = f"internal:{type(e).__name__}"
    return result
