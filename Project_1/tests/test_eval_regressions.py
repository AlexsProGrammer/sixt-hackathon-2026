"""Regression tests for the evaluation fixes: ablation input contract, separate methods, frozen selection and
release criteria. Synthetic data only, no API.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_eval_regressions.py
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from evaluation import ablation
from evaluation.ablation import SplitError
from evaluation.select_threshold import audit, decide, freeze
from pipeline.merge import merge_sample_v2
from pipeline.requests import build_jobs
from uncertainty.decision import make_prediction
from uncertainty.uq_probly import aggregate_v2

TEXT = "Governing law: Delaware. Units 42."
SCHEMA = {"properties": {"law": {"type": "string"}, "units": {"type": "number"}}}
PIPE = {"workers": 1, "samples": 3, "temperature": 0.7, "chunk_chars": 45000, "overlap_chars": 3000,
        "batch_size": 10, "uq_method": "k_agreement_conf", "sampling": "mixed", "model": "m",
        "prompt_version": "v2"}


def make_samples(answers, k, text=TEXT):
    """answers: list (per sample) of answer dicts or None (failed job)."""
    rec_schema = SCHEMA
    jobs = build_jobs(text, rec_schema, chunk_chars=100_000, overlap_chars=0, batch_size=10, samples=k)
    results = []
    for j in jobs:
        ans = answers[j["sample_idx"]]
        results.append({"job_id": j["job_id"], "sample_idx": j["sample_idx"], "chunk_id": j["chunk_id"],
                        "batch_id": j["batch_id"], "start": j["start"], "end": j["end"],
                        "field_names": j["field_names"], "answer": ans, "ok": ans is not None,
                        "error": None if ans is not None else "http:500"})
    return [merge_sample_v2(results, rec_schema, s, planned_jobs=jobs) for s in range(k)]


def ans(law, c):
    return {"law": {"value": law, "confidence": c}, "units": {"value": None, "confidence": 0.0}}


class EnvDir(unittest.TestCase):
    """Synthetic CUAD document so that ablation can re-read the text through 4_extract.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        d = self.tmp / "data" / "raw" / "cuad"
        d.mkdir(parents=True)
        (d / "CUADv1.json").write_text(json.dumps({"data": [
            {"title": t, "paragraphs": [{"context": TEXT}]} for t in ("DOC", "DOC2", "TECH")]}), encoding="utf-8")
        (self.tmp / "data" / "raw" / "extractbench").mkdir(parents=True)
        (self.tmp / "data" / "raw" / "extractbench" / "scan.pdf").write_bytes(b"not a pdf")
        old = os.environ.get("EXTRACT_DATA_DIR")
        os.environ["EXTRACT_DATA_DIR"] = str(self.tmp / "data")
        self.addCleanup(lambda: os.environ.pop("EXTRACT_DATA_DIR", None) if old is None
                        else os.environ.__setitem__("EXTRACT_DATA_DIR", old))
        self.rec = {"doc_id": "cuad:DOC", "source_dataset": "cuad", "pages": ["raw\\cuad\\CUADv1.json"],
                    "schema": SCHEMA}
        self.scan = {"doc_id": "extractbench:scan", "source_dataset": "extractbench",
                     "pages": ["raw\\extractbench\\scan.pdf"], "schema": SCHEMA}

    def write_split(self, recs, samples_rows, manifest, name="s"):
        inp = self.tmp / f"{name}_input.jsonl"
        inp.write_text("".join(json.dumps({k: v for k, v in r.items() if not k.startswith("gold")}) + "\n"
                               for r in recs), encoding="utf-8")
        smp = self.tmp / f"{name}.samples.jsonl"
        smp.write_text("".join(json.dumps(r) + "\n" for r in samples_rows), encoding="utf-8")
        man = self.tmp / f"{name}.manifest.json"
        man.write_text(json.dumps(manifest), encoding="utf-8")
        return inp, smp, man

    def manifest(self, **kw):
        m = {"run_id": "run-x", "run_complete": True, "pipeline": dict(PIPE), "fingerprint": {"fingerprint_sha256": "f"},
             "failed_doc_ids": [], "abstained_after_error_doc_ids": []}
        m.update(kw)
        return m


class AblationContractTests(EnvDir):
    def test_missing_sample_index_is_refused_not_reducing_k(self):
        full = make_samples([ans("Delaware", 0.9)] * 3, 3)
        inp, smp, man = self.write_split([self.rec], [{"doc_id": "cuad:DOC", "samples": full[:2]}], self.manifest())
        with self.assertRaises(SplitError):
            ablation.load_split(inp, smp, man, ablation._extractor())

    def test_duplicate_sample_index_is_refused(self):
        full = make_samples([ans("Delaware", 0.9)] * 3, 3)
        dup = [full[0], full[0], full[2]]
        inp, smp, man = self.write_split([self.rec], [{"doc_id": "cuad:DOC", "samples": dup}], self.manifest())
        with self.assertRaises(SplitError):
            ablation.load_split(inp, smp, man, ablation._extractor())

    def test_sample_for_unknown_document_is_refused(self):
        full = make_samples([ans("Delaware", 0.9)] * 3, 3)
        inp, smp, man = self.write_split([self.rec], [{"doc_id": "cuad:DOC", "samples": full},
                                                      {"doc_id": "cuad:OTHER", "samples": full}], self.manifest())
        with self.assertRaises(SplitError):
            ablation.load_split(inp, smp, man, ablation._extractor())

    def test_unexplained_missing_document_is_refused(self):
        full = make_samples([ans("Delaware", 0.9)] * 3, 3)
        inp, smp, man = self.write_split([self.rec, dict(self.rec, doc_id="cuad:DOC2")],
                                         [{"doc_id": "cuad:DOC", "samples": full}], self.manifest())
        with self.assertRaises(SplitError):
            ablation.load_split(inp, smp, man, ablation._extractor())

    def test_technical_failure_and_scan_are_explicit_and_counted(self):
        full = make_samples([ans("Delaware", 0.9)] * 3, 3)
        recs = [self.rec, dict(self.rec, doc_id="cuad:TECH"), self.scan]
        inp, smp, man = self.write_split(recs, [{"doc_id": "cuad:DOC", "samples": full}],
                                         self.manifest(failed_doc_ids=["cuad:TECH"]))
        out = self.tmp / "abl"
        rep = ablation.run(inp, smp, man, out, gold_path=None)
        self.assertEqual(rep["n_docs_unreadable"], 1)
        self.assertEqual(rep["n_docs_technical_failure"], 1)
        self.assertEqual(rep["expected_k"], 3)
        rows = [json.loads(l) for l in (out / "k_agreement_conf_predictions.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 3, "every input document appears in the predictions")
        tech = [r for r in rows if r["doc_id"] == "cuad:TECH"][0]
        self.assertTrue(all(v["value"] is None and v["confidence"] == 0.0 for v in tech["fields"].values()))

    def test_k1_method_on_k3_run_uses_sample_zero_only(self):
        full = make_samples([ans("Delaware", 0.9), ans("Delaware", 0.2), ans("Delaware", 0.3)], 3)
        inp, smp, man = self.write_split([self.rec], [{"doc_id": "cuad:DOC", "samples": full}], self.manifest())
        out = self.tmp / "abl2"
        ablation.run(inp, smp, man, out, gold_path=None)
        row = json.loads((out / "k1_grounded_predictions.jsonl").read_text().splitlines()[0])
        self.assertEqual(row["fields"]["law"]["confidence"], 0.9)


class MethodTests(unittest.TestCase):
    def test_agreement_only_ignores_model_confidence_and_conf_variant_uses_minimum(self):
        samples = make_samples([ans("Delaware", 0.9), ans("Delaware", 0.4), ans("Delaware", 0.8)], 3)
        agg = aggregate_v2(samples, SCHEMA, TEXT, expected_k=3)
        only = make_prediction(agg, SCHEMA, method="k_agreement_only")["law"]["confidence"]
        conf = make_prediction(agg, SCHEMA, method="k_agreement_conf")["law"]["confidence"]
        self.assertEqual(only, 1.0)
        self.assertEqual(conf, 0.4)

    def test_old_method_name_is_refused(self):
        samples = make_samples([ans("Delaware", 0.9)] * 3, 3)
        agg = aggregate_v2(samples, SCHEMA, TEXT, expected_k=3)
        with self.assertRaises(ValueError):
            make_prediction(agg, SCHEMA, method="k_agreement")


def gold_rows(n, good):
    return [{"doc_id": f"d{i}", "source_dataset": "cuad", "pages": [], "schema": {"properties": {"a": {}}},
             "gold": {"a": "X" if i < good else None}} for i in range(n)]


def preds_rows(n, conf=0.99, correct=True):
    return [{"doc_id": f"d{i}", "fields": {"a": {"value": "X", "confidence": conf}}} for i in range(n)]


class FreezeAndDecideTests(unittest.TestCase):
    def manifests(self, sel_id="sel", aud_id="aud", sel_complete=True, aud_complete=True):
        base = {"contract_version": 1, "pipeline": dict(PIPE), "fingerprint": {"fingerprint_sha256": "f"},
                "n_written": 0}
        return ({**base, "run_id": sel_id, "run_complete": sel_complete},
                {**base, "run_id": aud_id, "run_complete": aud_complete})

    def test_freeze_picks_best_dev_select_method_and_audit_reuses_threshold(self):
        gold = gold_rows(50, 50)
        pred_by = {"k_agreement_conf": preds_rows(50, 0.99), "k_entropy": preds_rows(50, 0.6)}
        frozen = freeze(gold, pred_by, 100.0)
        self.assertEqual(frozen["method"], "k_agreement_conf")
        self.assertIsNotNone(frozen["threshold"])
        res = audit(frozen, gold, preds_rows(50, 0.99), 100.0)
        self.assertEqual(res["threshold"], frozen["threshold"], "audit must not re-optimise the threshold")

    def test_freeze_without_positive_saving_freezes_all_abstain(self):
        gold = gold_rows(5, 0)
        frozen = freeze(gold, {"k_agreement_conf": preds_rows(5, 0.99)}, 100.0)
        self.assertIsNone(frozen["threshold"])

    def test_active_only_when_every_criterion_holds(self):
        gold = gold_rows(50, 50)
        frozen = freeze(gold, {"k_agreement_conf": preds_rows(50, 0.99)}, 100.0)
        sel, aud = self.manifests()
        res = audit(frozen, gold, preds_rows(50, 0.99), 100.0)
        dec = decide(frozen, res, sel, aud)
        self.assertEqual(dec["status"], "active")
        self.assertFalse(dec["abstain_all"])
        self.assertEqual(dec["pipeline"]["uq_method"], "k_agreement_conf")
        self.assertIn("pipeline_sha256", dec)

    def test_incomplete_select_run_blocks_release(self):
        gold = gold_rows(50, 50)
        frozen = freeze(gold, {"k_agreement_conf": preds_rows(50, 0.99)}, 100.0)
        sel, aud = self.manifests(sel_complete=False)
        dec = decide(frozen, audit(frozen, gold, preds_rows(50, 0.99), 100.0), sel, aud)
        self.assertEqual(dec["status"], "measurement_incomplete")
        self.assertTrue(dec["abstain_all"])

    def test_same_run_as_audit_is_not_independent(self):
        gold = gold_rows(50, 50)
        frozen = freeze(gold, {"k_agreement_conf": preds_rows(50, 0.99)}, 100.0)
        sel, aud = self.manifests(sel_id="same", aud_id="same")
        dec = decide(frozen, audit(frozen, gold, preds_rows(50, 0.99), 100.0), sel, aud)
        self.assertFalse(dec["criteria"]["independent_audit"])
        self.assertTrue(dec["abstain_all"])

    def test_too_few_accepted_audit_fields_keep_all_abstain(self):
        gold = gold_rows(10, 10)
        frozen = freeze(gold, {"k_agreement_conf": preds_rows(10, 0.99)}, 100.0)
        sel, aud = self.manifests()
        dec = decide(frozen, audit(frozen, gold, preds_rows(10, 0.99), 100.0), sel, aud)
        self.assertEqual(dec["status"], "all_abstain")
        self.assertFalse(dec["criteria"]["audit_accepted_at_least_min"])

    def test_wilson_is_reported_but_not_a_criterion(self):
        gold = gold_rows(50, 50)
        frozen = freeze(gold, {"k_agreement_conf": preds_rows(50, 0.99)}, 100.0)
        sel, aud = self.manifests()
        dec = decide(frozen, audit(frozen, gold, preds_rows(50, 0.99), 100.0), sel, aud)
        self.assertNotIn("diagnostic_wilson", " ".join(dec["criteria"]))
        self.assertIn("upper_95", dec["diagnostic_wilson_audit"])


if __name__ == "__main__":
    unittest.main()
