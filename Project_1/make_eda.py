#!/usr/bin/env python3
"""Generates Project_1/EDA.md from data/unified/dev.jsonl (no test_public leakage)."""
import collections
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "extract_example", Path(__file__).parent / "4_extract_example.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

doc_text = _mod.doc_text
MAX_CHARS = _mod.MAX_CHARS

HERE = Path(__file__).parent
DEV = HERE / "data/unified/dev.jsonl"
TEST = HERE / "data/unified/test_public.jsonl"
OUT = HERE / "EDA.md"

dev_recs = [json.loads(l) for l in DEV.open(encoding="utf-8") if l.strip()]
test_recs = [json.loads(l) for l in TEST.open(encoding="utf-8") if l.strip()]

by_src = collections.defaultdict(lambda: {"docs": 0, "fields": 0, "nulls": 0, "present": 0})
norm_counts = collections.Counter()
tag_counts = collections.Counter()
char_lengths = []
empty_text_docs = []
corrupted_docs = []

for r in dev_recs:
    src = r["source_dataset"]
    props = r["schema"]["properties"]
    by_src[src]["docs"] += 1
    if "corrupted" in r["doc_id"].lower():
        corrupted_docs.append(r["doc_id"])
    for t in r.get("tags") or []:
        tag_counts[t] += 1
    for f, gold_val in r["gold"].items():
        by_src[src]["fields"] += 1
        kind = props.get(f, {}).get("x-normalizer", "string")
        norm_counts[kind] += 1
        if gold_val is None or str(gold_val).strip() == "":
            by_src[src]["nulls"] += 1
        else:
            by_src[src]["present"] += 1

    txt = doc_text(r)
    if txt is None:
        empty_text_docs.append(r["doc_id"])
    else:
        char_lengths.append((len(txt), r["doc_id"], src))

truncated = [x for x in char_lengths if x[0] >= MAX_CHARS]
total_docs = len(dev_recs)
total_fields = sum(v["fields"] for v in by_src.values())
total_nulls = sum(v["nulls"] for v in by_src.values())

lines = [
    "# Exploratory Data Analysis (Project 1)",
    "",
    f"Analysis performed strictly on `data/unified/dev.jsonl` ({total_docs} documents, {total_fields:,} fields). "
    f"`data/unified/test_public.jsonl` ({len(test_recs)} documents) is held out for evaluation only.",
    "",
    "## 1. Dataset Breakdown & Sparsity (Absent vs. Present Fields)",
    "",
    "| Dataset | Dev Docs | Total Fields | Present (Non-Null) | Absent (`null`) | Null Rate |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
]
for src, s in sorted(by_src.items()):
    null_pct = 100.0 * s["nulls"] / s["fields"] if s["fields"] else 0.0
    lines.append(f"| `{src}` | {s['docs']} | {s['fields']:,} | {s['present']:,} | {s['nulls']:,} | {null_pct:.1f}% |")
lines.append(
    f"| **Total** | **{total_docs}** | **{total_fields:,}** | **{total_fields - total_nulls:,}** | "
    f"**{total_nulls:,}** | **{100.0 * total_nulls / total_fields:.1f}%** |"
)

lines += [
    "",
    "**Key takeaway:** Most target fields in a schema are absent (`null`). Because hallucinating a value on a `null` field incurs the full 100x error penalty, abstention on absent fields dominates net savings.",
    "",
    "## 2. Field Normalizer Types (`5_score.py`)",
    "",
    "| Normalizer (`x-normalizer`) | Field Count | Share | Scoring Rule |",
    "| --- | ---: | ---: | --- |",
]
rules_desc = {
    "span": "Token F1 >= 0.8 (` | ` separated)",
    "string": "Case-insensitive, collapsed whitespace",
    "amount": "Canonical float (handles `,`/`.` and `%`)",
    "date": "Canonical `YYYY-MM-DD`",
    "id": "Alphanumeric lowercase only",
    "json": "Canonical sorted JSON (all-or-nothing)",
}
for k, cnt in norm_counts.most_common():
    lines.append(f"| `{k}` | {cnt:,} | {100.0 * cnt / total_fields:.1f}% | {rules_desc.get(k, '')} |")

lines += [
    "",
    "## 3. Document Length, Truncation & Degradation Risks",
    "",
    f"- **Documents hitting `4_extract_example.py`'s `MAX_CHARS = {MAX_CHARS:,}` limit:** {len(truncated)} docs",
    f"- **Documents with no extractable PDF text (scanned/image-only):** {len(empty_text_docs)} docs",
    f"- **Explicitly corrupted PDFs (`*_corrupted` in `doc_id`):** {len(corrupted_docs)} docs",
]
if tag_counts:
    lines += ["", "### Document Condition Tags (`dev.jsonl`)", "", "| Tag | Docs |", "| --- | ---: |"]
    for t, cnt in tag_counts.most_common(15):
        lines.append(f"| `{t}` | {cnt} |")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Wrote {OUT} ({total_docs} dev docs, {total_fields:,} fields)")