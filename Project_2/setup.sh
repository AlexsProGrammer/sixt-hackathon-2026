#!/usr/bin/env bash
# Project 2 quick setup (about 5 min). Usage: bash setup.sh
# Python is our starting point, not a requirement: use any language you like.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PYTHON:-python3}"
"$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || { echo "Need Python 3.11+ (try: PYTHON=python3.x bash setup.sh)"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip && pip install -q -r requirements.txt
mkdir -p data
if ls data/*.csv >/dev/null 2>&1; then python starter.py
else echo "No organizer data in data/ yet, running on the small example_file.csv instead (put the full CSV into Project_2/data/, git-ignored, when you get it)"; python starter.py; fi
echo; echo "Ready. Activate with: . .venv/bin/activate. Next: open starter.py (naive baseline and simple flags to beat)."
