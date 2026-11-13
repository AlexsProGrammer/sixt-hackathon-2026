#!/usr/bin/env bash
# Compatibility wrapper around 4_extract.py. The reply cache (cache/replies/<model>/<prompt_version>/...) is built in;
# the former HTTP-level sitecustomize hook (cache/http) is retired.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

[ -f .env ] && { set -a; source .env; set +a; }

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

exec "$PY" 4_extract.py "$@"
