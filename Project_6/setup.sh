#!/usr/bin/env bash
# Project 6 quick setup (about 2 min). Usage: bash setup.sh
# Python is our starting point, not a requirement: use any language you like.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY="${PYTHON:-python3}"
"$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || { echo "Need Python 3.11+ (try: PYTHON=python3.x bash setup.sh)"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip && pip install -q -r requirements.txt
cd starter
python run.py --repeat
python evaluate.py predictions.csv ../data/validation_labels.csv --task-truth ../data/validation_labels.csv \
    --flags ../data/validation.csv --train-truth ../data/validation_labels.csv
echo; echo "Ready. Activate with: . .venv/bin/activate. Next: read starter/solution.py and beat the baseline."
