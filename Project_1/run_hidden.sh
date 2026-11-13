#!/usr/bin/env bash
# Called as: bash run_hidden.sh <input.jsonl> <output.jsonl>. Replace the line below with your own extractor.
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "usage: bash run_hidden.sh <input.jsonl> <output.jsonl>  (e.g. data/unified/dev.jsonl results/llm_dev.jsonl)" >&2
    exit 2
fi
python3 4_extract.py --data "$1" --out "$2" --mode llm
