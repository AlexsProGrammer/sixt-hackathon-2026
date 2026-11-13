"""probly-based aggregation and decision methods (contract version 2). Local data, no API.

Expected numbers are computed by hand in the comments.
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_uq_decision.py
"""
import math
import random
import unittest

from pipeline.merge import merge_sample_v2
from pipeline.requests import build_jobs
from uncertainty.decision import make_prediction, score_for
from uncertainty.uq_probly import aggregate_v2

TEXT = "Governing law: Delaware. Venue: Ohio courts. Texas branch. Units 42."
SCHEMA = {"properties": {"law": {"type": "string"}, "units": {"type": "number"}}}


def jobs_for(k, schema=SCHEMA):
    return build_jobs(TEXT, schema, chunk_chars=100_000, overlap_chars=0, batch_size=10, samples=k)


def samples_from(answers_by_sample, schema=SCHEMA, jobs=None):
    """answers_by_sample: list (one per sample) of answer dicts, or None for a failed sample job."""
    k = len(answers_by_sample)
    jobs = jobs or jobs_for(k, schema)
    results = []
    for j in jobs:
        ans = answers_by_sample[j["sample_idx"]]
        results.append({"job_id": j["job_id"], "sample_idx": j["sample_idx"], "chunk_id": j["chunk_id"],
                        "batch_id": j["batch_id"], "start": j["start"], "end": j["end"],
                        "field_names": j["field_names"], "answer": ans, "ok": ans is not None,
                        "error": None if ans is not None else "http:500"})
    return [merge_sample_v2(results, schema, s, planned_jobs=jobs) for s in range(k)]


def ans(law, c_law, units=None, c_units=0.0):
    return {"law": {"value": law, "confidence": c_law},
            "units": {"value": units, "confidence": c_units if units is not None else 0.0}}


def agg(answers, schema=SCHEMA):
    k = len(answers)
    return aggregate_v2(samples_from(answers, schema), schema, TEXT, expected_k=k)


class ProbabilityTests(unittest.TestCase):
    def test_entropy_of_identical_samples_is_zero(self):
        a = agg([ans("Delaware", 0.9), ans("Delaware", 0.8), ans("Delaware", 0.7)])
        f = a["candidates"]["law"]["features"]
        self.assertAlmostEqual(f["entropy_nats"], 0.0, places=12)
        self.assertEqual(f["agreement"], 1.0)

    def test_two_way_split_entropy_is_ln2_per_probly(self):
        a = agg([ans("Delaware", 0.9), ans("Ohio courts", 0.9)])  # K=2: 1/2 and 1/2
        f = a["candidates"]["law"]["features"]
        self.assertAlmostEqual(f["entropy_nats"], math.log(2), places=9)
        self.assertFalse(a["candidates"]["law"]["eligible"], "tie is not eligible")

    def test_two_one_split_entropy(self):
        a = agg([ans("Delaware", 0.9), ans("Delaware", 0.9), ans("Ohio courts", 0.9)])
        h = -(2 / 3 * math.log(2 / 3) + 1 / 3 * math.log(1 / 3))
        self.assertAlmostEqual(a["candidates"]["law"]["features"]["entropy_nats"], h, places=9)


class DecisionTests(unittest.TestCase):
    def test_k_agreement_takes_min_of_share_and_confidence(self):
        a = agg([ans("Delaware", 0.9), ans("Delaware", 0.5), ans("Delaware", 0.8)])
        pred = make_prediction(a, SCHEMA, method="k_agreement_conf")
        self.assertEqual(pred["law"], {"value": "Delaware", "confidence": 0.5})

    def test_k_entropy_uses_probly_entropy_in_the_score(self):
        a = agg([ans("Delaware", 0.9), ans("Delaware", 0.9), ans("Ohio courts", 0.9)])
        expected = 1 - (-(2 / 3 * math.log(2 / 3) + 1 / 3 * math.log(1 / 3))) / math.log(3)
        self.assertAlmostEqual(score_for("k_entropy", a["candidates"]["law"]["features"]), expected, places=9)

    def test_same_agreement_different_distribution_changes_entropy_score(self):
        # K=5: winner share 3/5 in both cases. Second case splits the rest into two clusters.
        schema = SCHEMA
        a1 = agg([ans("Delaware", 0.9), ans("Delaware", 0.9), ans("Delaware", 0.9),
                  ans("Ohio courts", 0.9), ans("Ohio courts", 0.9)])
        a2 = agg([ans("Delaware", 0.9), ans("Delaware", 0.9), ans("Delaware", 0.9),
                  ans("Ohio courts", 0.9), ans("Texas branch", 0.9)])
        f1, f2 = a1["candidates"]["law"]["features"], a2["candidates"]["law"]["features"]
        self.assertAlmostEqual(f1["agreement"], f2["agreement"])
        self.assertNotAlmostEqual(f1["entropy_nats"], f2["entropy_nats"], places=3)
        s1 = make_prediction(a1, schema, method="k_entropy")["law"]["confidence"]
        s2 = make_prediction(a2, schema, method="k_entropy")["law"]["confidence"]
        self.assertNotAlmostEqual(s1, s2, places=3)
        self.assertLess(s2, s1, "more spread gives higher entropy and a lower score")
        ag1 = make_prediction(a1, schema, method="k_agreement_conf")["law"]["confidence"]
        ag2 = make_prediction(a2, schema, method="k_agreement_conf")["law"]["confidence"]
        self.assertEqual(ag1, ag2, "agreement method cannot tell them apart")

    def test_k1_grounded_is_the_model_confidence(self):
        a = agg([ans("Delaware", 0.66)])
        self.assertEqual(make_prediction(a, SCHEMA, method="k1_grounded")["law"]["confidence"], 0.66)

    def test_k_methods_refuse_wrong_k(self):
        a1 = agg([ans("Delaware", 0.9)])
        with self.assertRaises(ValueError):
            make_prediction(a1, SCHEMA, method="k_entropy")
        a3 = agg([ans("Delaware", 0.9)] * 3)
        with self.assertRaises(ValueError):
            make_prediction(a3, SCHEMA, method="k1_grounded")

    def test_null_majority_and_tie_give_null(self):
        a = agg([ans(None, 0.0), ans(None, 0.0), ans("Delaware", 0.9)])
        self.assertEqual(make_prediction(a, SCHEMA, method="k_agreement_conf")["law"], {"value": None, "confidence": 0.0})
        self.assertEqual(a["candidates"]["law"]["reason"], "null_majority")

    def test_unsupported_majority_gives_null(self):
        a = agg([ans("Florida", 0.9), ans("Florida", 0.9), ans("Florida", 0.9)])  # not in TEXT
        self.assertEqual(a["candidates"]["law"]["reason"], "unsupported_majority")
        self.assertIsNone(make_prediction(a, SCHEMA, method="k_agreement_conf")["law"]["value"])

    def test_failed_sample_observation_is_not_a_null_vote(self):
        samples = samples_from([ans("Delaware", 0.9), ans("Delaware", 0.9), None])
        a = aggregate_v2(samples, SCHEMA, TEXT, expected_k=3)
        cand = a["candidates"]["law"]
        self.assertFalse(cand["eligible"])
        self.assertEqual(cand["reason"], "incomplete_observations")
        self.assertNotIn("null_share", cand["features"], "no null cluster was formed")

    def test_wide_schema_failed_batch_keeps_other_fields(self):
        schema = {"properties": {f"f{i:02d}": {"type": "string"} for i in range(11)}}
        text = "alpha beta gamma"
        jobs = build_jobs(text, schema, chunk_chars=100_000, overlap_chars=0, batch_size=10, samples=2)
        self.assertEqual(len(jobs), 4)  # 2 samples x 2 batches
        results = []
        for j in jobs:
            fail = j["sample_idx"] == 1 and j["batch_id"] == 1
            answer = None if fail else {n: {"value": "alpha" if n == "f00" else None,
                                            "confidence": 0.9 if n == "f00" else 0.0} for n in j["field_names"]}
            results.append({"job_id": j["job_id"], "sample_idx": j["sample_idx"], "chunk_id": j["chunk_id"],
                            "batch_id": j["batch_id"], "start": j["start"], "end": j["end"],
                            "field_names": j["field_names"], "answer": answer, "ok": not fail,
                            "error": None if not fail else "timeout"})
        samples = [merge_sample_v2(results, schema, s, planned_jobs=jobs) for s in range(2)]
        a = aggregate_v2(samples, schema, text, expected_k=2)
        self.assertTrue(a["candidates"]["f00"]["eligible"])
        self.assertEqual(a["candidates"]["f00"]["value"], "alpha")
        self.assertFalse(a["candidates"]["f10"]["eligible"])

    def test_order_independent(self):
        answers = [ans("Delaware", 0.4), ans("delaware", 0.9), ans("DELAWARE", 0.8)]
        samples = samples_from(answers)
        base = aggregate_v2(samples, SCHEMA, TEXT, expected_k=3)
        for seed in range(5):
            shuffled = samples[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(aggregate_v2(shuffled, SCHEMA, TEXT, expected_k=3), base)

    def test_sample_count_mismatch_is_ineligible(self):
        samples = samples_from([ans("Delaware", 0.9)] * 2)
        a = aggregate_v2(samples, SCHEMA, TEXT, expected_k=3)
        self.assertEqual(a["candidates"]["law"]["reason"], "sample_count_mismatch")

    def test_prediction_has_exactly_schema_fields_and_finite_scores(self):
        a = agg([ans("Delaware", 0.9), ans("Delaware", 0.8), ans("Delaware", 0.7)])
        pred = make_prediction(a, SCHEMA, method="k_entropy")
        self.assertEqual(set(pred), set(SCHEMA["properties"]))
        for v in pred.values():
            self.assertTrue(math.isfinite(v["confidence"]))
            self.assertTrue(0.0 <= v["confidence"] <= 1.0)

    def test_calibrated_needs_an_artefact(self):
        a = agg([ans("Delaware", 0.9)])
        with self.assertRaises(Exception):
            make_prediction(a, SCHEMA, method="calibrated", calibration=None)


if __name__ == "__main__":
    unittest.main()
