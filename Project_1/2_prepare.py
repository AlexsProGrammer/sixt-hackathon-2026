#!/usr/bin/env python3
"""Turns data/raw/ into data/unified/dev.jsonl and test_public.jsonl, one JSON record per document.
Record: doc_id, source_dataset, split, tags, pages, schema, gold (null = absent from the document).
Split by hash of the document group, about 25% public test. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterator

HERE = Path(__file__).parent
DATA = HERE / "data"
RAW = DATA / "raw"
SELECTION = HERE / "selection.tsv"


def make_record(*, doc_id, source_dataset, license, language, pages, schema, gold, gold_evidence=None, tags=None) -> dict:
    return {"doc_id": f"{source_dataset}:{doc_id}", "source_dataset": source_dataset, "license": license,
            "split": "dev", "language": language, "pages": pages, "schema": schema, "gold": gold,
            "gold_evidence": gold_evidence or {}, "tags": tags or []}


# ---------------------------------------------------------------- ExtractBench (Apache-2.0)
def _scalar(v):
    if v is None or (isinstance(v, (str, int, float)) and not isinstance(v, bool)):
        return v, False
    if isinstance(v, bool):
        return ("true" if v else "false"), False          # checkboxes
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False), True


def load_extractbench() -> Iterator[dict]:
    """Short split, PDFs <= 1 MB. Nested objects/arrays become JSON strings scored all-or-nothing."""
    root = RAW / "extractbench"
    keep = {l.split("\t")[0] for l in SELECTION.read_text().splitlines() if l.strip() and not l.startswith("#")}
    for line in (root / "short.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        if row["id"] not in keep:
            continue
        schema, expected, rules = json.loads(row["data_schema"]), json.loads(row["expected_output"]), json.loads(row["field_rules"])
        for prop in schema.get("properties", {}).values():
            if prop.get("type") in ("object", "array"):
                prop["x-normalizer"] = "json"
        gold, evidence = {}, {}
        for k, v in expected.items():
            gold[k], nested = _scalar(v)
            if nested:                                       # schemas using $ref/anyOf are not caught by the type check above
                schema.setdefault("properties", {}).setdefault(k, {})["x-normalizer"] = "json"
            ev = (rules.get(k) or {}).get("evidence") or []
            if v is not None and not nested and ev and ev[0].get("page") is not None and ev[0].get("bbox"):
                evidence[k] = {"page": ev[0]["page"], "bbox": ev[0]["bbox"]}
        yield make_record(doc_id=row["id"], source_dataset="extractbench", license="Apache-2.0", language="en",
                          pages=[str((root / row["pdf"]).relative_to(DATA))], schema=schema, gold=gold,
                          gold_evidence=evidence, tags=list(row.get("tags") or []))


# ---------------------------------------------------------------- CUAD (CC BY 4.0, labels)
def load_cuad() -> Iterator[dict]:
    """510 contracts x 41 clauses. Gold = answer spans joined with ' | ', null if absent."""
    path = RAW / "cuad" / "CUADv1.json"
    for contract in json.loads(path.read_text(encoding="utf-8"))["data"]:
        para = contract["paragraphs"][0]
        gold, evidence = {}, {}
        for qa in para["qas"]:
            name = qa["id"].rsplit("__", 1)[1]
            answers = [] if qa.get("is_impossible") else qa.get("answers", [])
            gold[name] = " | ".join(a["text"] for a in answers) if answers else None
            if answers:
                evidence[name] = {"spans": [{"start": a["answer_start"], "end": a["answer_start"] + len(a["text"])} for a in answers]}
        yield make_record(doc_id=contract["title"], source_dataset="cuad", license="CC-BY-4.0", language="en",
                          pages=[str(path.relative_to(DATA))], gold=gold, gold_evidence=evidence,
                          schema={"properties": {k: {"type": "string", "x-normalizer": "span"} for k in gold}})


# ---------------------------------------------------------------- InvoiceBenchmark (MIT)
def _f(norm, desc, **extra):
    return {"x-normalizer": norm, "description": desc, **extra}


IB_SCHEMA = {"properties": {
    "invoice_id": _f("id", "Invoice number as printed."),
    "vendor": _f("string", "Name of the company that issued the invoice."),
    "recipient": _f("string", "Name of the customer the invoice is addressed to."),
    "date": _f("date", "Invoice date."),
    "due_date": _f("date", "Payment due date. Null if the document has none."),
    "currency": _f("string", "ISO 4217 currency code, for example EUR."),
    "subtotal": _f("amount", "Net amount before VAT."),
    "vat_rate": _f("amount", "VAT rate as a fraction (0.20 for 20 percent; '20%' is accepted). Null if rates are mixed."),
    "vat_amount": _f("amount", "Total VAT amount."),
    "discount_amount": _f("amount", "Discount that is actually applied. Null if the invoice has no discount; 0.00 if a conditional discount is shown but not applied."),
    "total": _f("amount", "Total amount payable.")}}


def load_invoicebenchmark() -> Iterator[dict]:
    """200 synthetic invoices. Gold holds the TRUE totals; 80 printed totals or subtotals are wrong."""
    root = RAW / "invoicebenchmark" / "output"
    for gt in sorted((root / "ground_truth").glob("*.json")):
        d = json.loads(gt.read_text(encoding="utf-8"))
        page = root / "pdf" / f"{gt.stem}.pdf"
        gold = {k: d.get(k) for k in IB_SCHEMA["properties"]}
        gold["discount_amount"] = d["discount_amount"] if d.get("discount") else None
        v = d.get("variants", {})
        tags = [f"{k}:{val}" for k, val in v.items() if val not in (None, "none")]
        tags += {"total_error": ["inconsistent_total"], "subtotal_error": ["inconsistent_subtotal"]}.get(v.get("consistency"), [])
        tags += ["credit_note"] if d.get("is_credit_note") else []
        tags += ["no_discount"] if d.get("discount") is None else (["conditional_discount"] if d["discount"].get("conditional") else [])
        yield make_record(doc_id=d["invoice_id"], source_dataset="invoicebenchmark", license="MIT", language="en",
                          pages=[str(page.relative_to(DATA))], schema=IB_SCHEMA, gold=gold, tags=tags)


# ---------------------------------------------------------------- invoice-extraction-benchmark (data CC BY 4.0)
DREW_SCHEMA = {"properties": {
    "vendor_name": _f("string", "Name of the company that issued the document."),
    "invoice_number": _f("id", "Invoice number as printed. Null if the document has none."),
    "invoice_date": _f("date", "Invoice date."),
    "due_date": _f("date", "Payment due date. Null if the document has none."),
    "currency": _f("string", "ISO 4217 code of the currency the amounts are payable in, for example NAD or USD."),
    "subtotal": _f("amount", "Amount before tax. Null if not shown."),
    "tax": _f("amount", "Total tax (VAT or sales tax). Null if not shown."),
    "total": _f("amount", "Total amount payable. Null if not shown (for example on statements)."),
    "document_type": _f("string", "One of: invoice, credit_note, other.", enum=["invoice", "credit_note", "other"]),
    "line_items": _f("json", "JSON list of {description, amount, alt_amounts}.")}}


def load_drew_ipp() -> Iterator[dict]:
    """181 synthetic invoices with simulated scan damage. Multi-invoice files use the first invoice."""
    corpus = RAW / "drew-ipp-invoices" / "corpus" / "v1"
    for line in (corpus / "metadata.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row, exp = json.loads(line), json.loads(line)["expected"]
        gold = {k: exp.get(k) for k in DREW_SCHEMA["properties"] if k != "line_items"}
        gold["line_items"] = json.dumps(exp["lines"], sort_keys=True, ensure_ascii=False) if exp.get("lines") else None
        tags = [f"difficulty:{row['difficulty']}", f"render:{row['render']}"] + list(row.get("tags") or [])
        tags += [f"damage:{row['severity']}"] if row.get("severity") else []
        tags += [f"degradation:{d['kind'] if isinstance(d, dict) else d}" for d in row.get("degradations") or []]
        tags += ["should_flag"] if exp.get("should_flag") else []
        tags += ["adversarial_null"] if gold["invoice_number"] is None else []
        yield make_record(doc_id=row["doc_id"], source_dataset="drew_ipp_invoices", license="CC-BY-4.0", language="en",
                          pages=[str((corpus / row["file_name"]).relative_to(DATA))], schema=DREW_SCHEMA, gold=gold,
                          tags=list(dict.fromkeys(tags)))


LOADERS = {"extractbench": load_extractbench, "cuad": load_cuad,
           "invoicebenchmark": load_invoicebenchmark, "drew_ipp": load_drew_ipp}
DEFAULT_SOURCES = ["extractbench", "cuad"]   # one contract set + one forms/scans set; invoice sets are opt-in


# ---------------------------------------------------------------- split and write
def _bucket(text: str) -> float:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def assign_split(doc_id: str, salt: str = "", hidden: float = 0.2, public: float = 0.25) -> str:
    group = re.sub(r"-p\d+$", "", doc_id)
    if salt and _bucket(salt + group) < hidden:
        return "test_hidden"
    return "test_public" if _bucket(group) < public else "dev"


def write(path: Path, records: list) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="+", choices=list(LOADERS), default=DEFAULT_SOURCES,
                    help="default: extractbench cuad (the invoice sets are optional extras)")
    a = ap.parse_args()
    records = []
    for name in a.sources:
        if not (RAW / {"drew_ipp": "drew-ipp-invoices"}.get(name, name) / ".complete").exists():
            raise SystemExit(f"data/raw/ is missing {name}. Run: bash 1_download.sh")
        records += LOADERS[name]()
    seen, unique = set(), []
    for r in records:                                       # drop exact duplicates (same pages and gold)
        k = hashlib.sha256((json.dumps(r["gold"], sort_keys=True) + "".join(r["pages"])).encode()).hexdigest()
        if k not in seen:
            seen.add(k)
            unique.append(r)
    salt = os.environ.get("HIDDEN_SALT", "")
    unique = [{**r, "split": assign_split(r["doc_id"], salt)} for r in unique]
    outputs = [("dev", "unified/dev.jsonl"), ("test_public", "unified/test_public.jsonl")]
    if salt:
        outputs.append(("test_hidden", "hidden_test/test_hidden.jsonl"))
    for split, path in outputs:
        n = write(DATA / path, [r for r in unique if r["split"] == split])
        print(f"{split:12s} {n:5d} documents -> data/{path}" + ("  (organizers only, never share)" if split == "test_hidden" else ""))


if __name__ == "__main__":
    main()
