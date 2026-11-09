#!/usr/bin/env bash
# Called as: bash run_hidden.sh <input.jsonl> <output.jsonl>. Replace the line below with your own extractor.
set -euo pipefail
python3 4_extract_example.py --data "$1" --out "$2"
