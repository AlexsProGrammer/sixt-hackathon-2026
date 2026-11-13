#!/usr/bin/env bash
# Called as: bash run_hidden.sh <input.jsonl> <output.jsonl>   (run from Project_1; input must be gold-free)
# Final configuration: frozen decision file (threshold, abstain_all, pipeline).
# An existing output file and its side files are removed first: the run never fails on a pre-created or
# repeated output path, and an old output is never taken over.
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
if [ -d "$2" ]; then
    echo "ERROR: output path is a directory: $2" >&2
    exit 2
fi
# Side files are named after the output stem (4_extract.py: OUT.jsonl -> OUT.diagnostics.jsonl, ...).
OUT_BASE="${2%.*}"
case "$(basename -- "$2")" in *.*) ;; *) OUT_BASE="$2" ;; esac
rm -f -- "$2" "$OUT_BASE.diagnostics.jsonl" "$OUT_BASE.manifest.json" "$OUT_BASE.samples.jsonl"
"$PY" 4_extract.py --data "$1" --out "$2" --mode llm --on-error abstain --decision submission/decision.json
