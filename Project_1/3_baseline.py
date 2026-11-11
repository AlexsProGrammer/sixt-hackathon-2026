#!/usr/bin/env python3
"""No-AI references to beat. --mode never: no answers (saves nothing). --mode common: most common training value per field.
    python 3_baseline.py --train data/unified/dev.jsonl --target data/unified/test_public.jsonl --out preds.jsonl [--mode common|never]
"""
import argparse
import collections
import json


def signature(rec) -> tuple:
    return rec["source_dataset"], tuple(sorted(rec["schema"]["properties"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["common", "never"], default="common")
    a = ap.parse_args()

    counts = collections.defaultdict(collections.Counter)   # (signature, field) -> value counts (None included)
    n_docs = collections.Counter()
    if a.mode == "common":
        for line in open(a.train, encoding="utf-8"):
            r = json.loads(line)
            n_docs[signature(r)] += 1
            for f, v in r["gold"].items():
                counts[(signature(r), f)][None if v is None or str(v).strip() == "" else str(v)] += 1

    with open(a.target, encoding="utf-8") as fin, open(a.out, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            fields = {}
            for f in r["gold"]:
                value, conf = None, 0.0
                c = counts.get((signature(r), f))
                if c:
                    top, k = c.most_common(1)[0]
                    if top is not None:
                        value, conf = top, k / n_docs[signature(r)]
                fields[f] = {"value": value, "confidence": round(conf, 4)}
            fout.write(json.dumps({"doc_id": r["doc_id"], "fields": fields}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
