#!/usr/bin/env bash
# Called as: bash run_hidden.sh <input.jsonl> <output.jsonl>   (run from Project_1; input must be gold-free)
# Final configuration: frozen decision file (threshold, abstain_all, pipeline). Output must be a fresh path.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: bash run_hidden.sh <input.jsonl> <output.jsonl>  (e.g. data/unified/dev.jsonl results/llm_dev.jsonl)" >&2
    exit 2
fi
# Interpreter: the project venv (Python 3.12, probly installed) if present, else python3.
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
else
    PY="python3"
fi
"$PY" 4_extract.py --data "$1" --out "$2" --mode llm --on-error abstain --decision submission/decision.json
