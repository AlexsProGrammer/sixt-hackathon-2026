#!/usr/bin/env bash
# Wrapper um 4_extract.py mit identischen CLI-Args + automatischem Disk-Cache in cache/http/
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

[ -f .env ] && { set -a; source .env; set +a; }
mkdir -p cache/http cache/.hook results

cat <<'PY' > cache/.hook/sitecustomize.py
import hashlib
import io
import json
import os
import tempfile
import threading
import urllib.request
from pathlib import Path

CACHE_DIR = os.environ.get("PROBLY_HTTP_CACHE_DIR")
if CACHE_DIR:
    _orig_urlopen = urllib.request.urlopen
    _lock = threading.Lock()
    _call_counts: dict[str, int] = {}
    _stats = {"hits": 0, "misses": 0}

    class _CachedHTTPResponse(io.BytesIO):
        def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
            super().__init__(body)
            self.status = status
            self.code = status
            self.headers = headers or {"Content-Type": "application/json"}

        def getcode(self) -> int:
            return self.status

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def _cached_urlopen(url, data=None, timeout=None, *args, **kwargs):
        if isinstance(url, urllib.request.Request):
            full_url = url.full_url
            body = url.data
            method = url.get_method()
        else:
            full_url = str(url)
            body = data
            method = "POST" if data is not None else "GET"

        if method != "POST" or not body:
            return _orig_urlopen(url, data=data, timeout=timeout, *args, **kwargs) if timeout is not None else _orig_urlopen(url, data=data, *args, **kwargs)

        raw_key = hashlib.sha256(full_url.encode("utf-8") + b"\x00" + body).hexdigest()
        with _lock:
            idx = _call_counts.get(raw_key, 0)
            _call_counts[raw_key] = idx + 1

        cache_file = Path(CACHE_DIR) / f"{raw_key}_{idx}.json"
        if cache_file.exists():
            with _lock:
                _stats["hits"] += 1
            return _CachedHTTPResponse(cache_file.read_bytes())

        resp = _orig_urlopen(url, data=data, timeout=timeout, *args, **kwargs) if timeout is not None else _orig_urlopen(url, data=data, *args, **kwargs)
        payload = resp.read()
        status = getattr(resp, "status", 200)

        # Nur gültige JSON-Antworten atomar cachen (keine Fehler/429)
        if status == 200:
            try:
                json.loads(payload.decode("utf-8"))
                fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
                with os.fdopen(fd, "wb") as f:
                    f.write(payload)
                os.replace(tmp_path, cache_file)
            except Exception:
                pass

        with _lock:
            _stats["misses"] += 1
        return _CachedHTTPResponse(payload, status=status)

    urllib.request.urlopen = _cached_urlopen
PY

export PROBLY_HTTP_CACHE_DIR="$PWD/cache/http"
export PYTHONPATH="$PWD/cache/.hook:${PYTHONPATH:-}"

PY_BIN=".venv/bin/python"
[ -x "$PY_BIN" ] || PY_BIN="python3"

"$PY_BIN" 4_extract.py "$@"
