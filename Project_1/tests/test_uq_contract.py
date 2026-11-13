"""Contract version 2: field-wise merge, statuses, evidence, hard exclusions. Local data, no API.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_uq_contract.py
"""
import unittest

from pipeline.merge import merge_sample_v2
from pipeline.requests import build_jobs
from uncertainty.contracts import CONTRACT_VERSION, ContractError, check_sample
from uncertainty.policy import classify_field_v2

TEXT = "Governing law: Delaware. Parties: Acme Corp and Globex Ltd. Units 42."
SCHEMA = {"properties": {"law": {"type": "string"}, "parties": {"type": "string"}, "units": {"type": "number"}}}


def wide_schema(n=12):
    return {"properties": {f"f{i:02d}": {"type": "string"} for i in range(n)}}


def jobs_for(schema, k=1, text=TEXT, chunk=100_000):
    return build_jobs(text, schema, chunk_chars=chunk, overlap_chars=0, batch_size=10, samples=k)


def run_result(job, answer=None, *, ok=True, error=None):
    return {"job_id": job["job_id"], "sample_idx": job["sample_idx"], "chunk_id": job["chunk_id"],
            "batch_id": job["batch_id"], "start": job["start"], "end": job["end"],
            "field_names": job["field_names"], "answer": answer, "ok": ok, "error": error}


class MergeV2Tests(unittest.TestCase):
    def setUp(self):
        self.schema = SCHEMA
        self.jobs = jobs_for(self.schema)

    def run_sample(self, answer):
        results = [run_result(j, answer) for j in self.jobs]
        return merge_sample_v2(results, self.schema, 0, planned_jobs=self.jobs)

    def test_explicit_null_is_absent_not_missing(self):
        s = self.run_sample({"law": {"value": None, "confidence": 0.9}, "parties": {"value": None, "confidence": 0.8},
                             "units": {"value": None, "confidence": 0.7}})
        self.assertEqual(s["fields"]["law"]["status"], "absent")
        self.assertTrue(s["fields"]["law"]["complete"])
        self.assertTrue(s["complete"])

    def test_field_not_in_reply_is_missing(self):
        s = self.run_sample({"law": {"value": "Delaware", "confidence": 0.9}})
        self.assertEqual(s["fields"]["parties"]["status"], "missing")
        self.assertFalse(s["fields"]["parties"]["complete"])
        # sample-level complete means "every planned job succeeded"; the reply itself was successful here
        self.assertTrue(s["complete"])

    def test_bad_confidences_are_invalid_not_scores(self):
        for bad in (True, float("nan"), float("inf"), 1.5, "0.9", None):
            s = self.run_sample({"law": {"value": "Delaware", "confidence": bad},
                                 "parties": {"value": None, "confidence": 0.0},
                                 "units": {"value": None, "confidence": 0.0}})
            self.assertEqual(s["fields"]["law"]["status"], "invalid", repr(bad))
            self.assertIsNone(s["fields"]["law"]["model_confidence"])

    def test_bare_value_without_confidence_is_invalid(self):
        s = self.run_sample({"law": "Delaware"})
        self.assertEqual(s["fields"]["law"]["status"], "invalid")

    def test_failed_job_is_error_not_absent(self):
        results = [run_result(j, None, ok=False, error="http:429") for j in self.jobs]
        s = merge_sample_v2(results, self.schema, 0, planned_jobs=self.jobs)
        self.assertEqual(s["fields"]["law"]["status"], "error")
        self.assertFalse(s["complete"])

    def test_missing_planned_result_is_missing(self):
        results = [run_result(j, {"law": {"value": "Delaware", "confidence": 0.9}}) for j in self.jobs[:0]]
        s = merge_sample_v2(results, self.schema, 0, planned_jobs=self.jobs)
        self.assertEqual(s["fields"]["law"]["status"], "missing")
        self.assertEqual(s["fields"]["law"]["reason"], "no result for planned job")

    def test_unplanned_and_duplicate_results_raise(self):
        good = run_result(self.jobs[0], {})
        with self.assertRaises(ContractError):
            merge_sample_v2([good, dict(good)], self.schema, 0, planned_jobs=self.jobs)
        rogue = dict(good, job_id="s0-c9-b9")
        with self.assertRaises(ContractError):
            merge_sample_v2([rogue], self.schema, 0, planned_jobs=self.jobs)

    def test_conflicting_values_across_chunks_are_invalid(self):
        jobs = build_jobs("a" * 50 + " x " + "b" * 50, self.schema, chunk_chars=60, overlap_chars=0,
                          batch_size=10, samples=1)
        self.assertGreater(len(jobs), 1)
        answers = [{"law": {"value": "Delaware", "confidence": 0.9}},
                   {"law": {"value": "Texas", "confidence": 0.9}}] + [{}] * (len(jobs) - 2)
        results = [run_result(j, a) for j, a in zip(jobs, answers)]
        s = merge_sample_v2(results, self.schema, 0, planned_jobs=jobs)
        self.assertEqual(s["fields"]["law"]["status"], "invalid")
        self.assertEqual(s["fields"]["law"]["reason"], "conflicting values across chunks")

    def test_present_with_evidence_and_minimum_confidence(self):
        jobs = build_jobs("x" * 30 + "Delaware" + "y" * 30, self.schema, chunk_chars=40, overlap_chars=0,
                          batch_size=10, samples=1)
        answers = [{"law": {"value": "Delaware", "confidence": 0.9}}, {"law": {"value": "Delaware", "confidence": 0.6}}]
        answers += [{}] * (len(jobs) - 2)
        results = [run_result(j, a) for j, a in zip(jobs, answers)]
        s = merge_sample_v2(results, self.schema, 0, planned_jobs=jobs)
        law = s["fields"]["law"]
        self.assertEqual(law["status"], "present")
        self.assertEqual(law["model_confidence"], 0.6)
        self.assertGreaterEqual(len(law["evidence"]), 1)
        self.assertIn("start", law["evidence"][0])

    def test_failed_foreign_batch_keeps_complete_fields(self):
        schema = wide_schema(12)
        jobs = jobs_for(schema)
        self.assertEqual(len(jobs), 2)  # batch 0: f00-f09, batch 1: f10-f11
        results = [run_result(jobs[0], {f"f{i:02d}": {"value": None, "confidence": 0.0} for i in range(10)}),
                   run_result(jobs[1], None, ok=False, error="timeout")]
        s = merge_sample_v2(results, schema, 0, planned_jobs=jobs)
        self.assertFalse(s["complete"], "sample-level completeness is false")
        self.assertTrue(s["fields"]["f00"]["complete"], "fields of the healthy batch stay complete")
        self.assertEqual(s["fields"]["f00"]["status"], "absent")
        self.assertEqual(s["fields"]["f11"]["status"], "error")

    def test_sample_passes_structural_check(self):
        s = self.run_sample({"law": {"value": None, "confidence": 0.0}})
        self.assertEqual(check_sample(s, self.schema), [])
        self.assertEqual(s["contract_version"], CONTRACT_VERSION)


class ClassifyV2Tests(unittest.TestCase):
    def test_ungrounded_present_is_unsupported_and_not_boosted(self):
        obs = {"status": "present", "value": "Texas", "model_confidence": 0.99}
        out = classify_field_v2(obs, {"type": "string"}, TEXT)
        self.assertEqual(out["status"], "unsupported")
        self.assertIsNone(out["value"])

    def test_grounded_keeps_model_confidence_exactly(self):
        obs = {"status": "present", "value": "Delaware", "model_confidence": 0.73}
        out = classify_field_v2(obs, {"type": "string"}, TEXT)
        self.assertEqual((out["status"], out["model_confidence"]), ("present", 0.73))

    def test_no_text_is_unreadable(self):
        obs = {"status": "present", "value": "Delaware", "model_confidence": 0.9}
        self.assertEqual(classify_field_v2(obs, {"type": "string"}, None)["status"], "unreadable")

    def test_absent_and_error_pass_through(self):
        self.assertEqual(classify_field_v2({"status": "absent", "model_confidence": 0.8}, {}, TEXT)["status"], "absent")
        self.assertEqual(classify_field_v2({"status": "error", "reason": "http:500"}, {}, TEXT)["status"], "error")


if __name__ == "__main__":
    unittest.main()
