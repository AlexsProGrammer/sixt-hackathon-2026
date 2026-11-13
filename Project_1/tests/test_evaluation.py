"""Tests for evaluation: validation, group split, threshold adapter over the official scorer.

Hand-made records with expected counts computed by hand (see comments). No model, no API.
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_evaluation.py
"""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation.prepare import group_of, split, split_of, strip_gold, write
from evaluation.select_threshold import choose_threshold, load_scorer
from evaluation.validate import validate_predictions

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}}


def rec(doc, a, b):
    return {"doc_id": doc, "source_dataset": "cuad", "pages": ["raw\\x.pdf"], "schema": SCHEMA,
            "gold": {"a": a, "b": b}, "tags": ["length:short"]}


def pred(doc, a, ca, b, cb):
    def fv(v, c):
        return {"value": v, "confidence": c}
    return {"doc_id": doc, "fields": {"a": fv(a, ca), "b": fv(b, cb)}}


GOLD = [rec("d1", "X", None), rec("d2", "Y", "Z"), rec("d3", None, None)]


class ValidateTests(unittest.TestCase):
    def good(self):
        return [pred("d1", "X", 0.99, None, 0.0), pred("d2", "Y", 0.98, "Z", 0.97),
                pred("d3", None, 0.0, None, 0.0)]

    def test_valid_output(self):
        self.assertEqual(validate_predictions(GOLD, self.good()), [])

    def test_missing_duplicate_unknown_doc(self):
        p = self.good()
        errs = validate_predictions(GOLD, p[:2] + [p[0]] + [pred("zz", None, 0, None, 0)])
        joined = " | ".join(errs)
        self.assertIn("missing prediction for doc_id: d3", joined)
        self.assertIn("duplicate doc_id: d1", joined)
        self.assertIn("unknown doc_id: zz", joined)

    def test_field_set_must_match_schema(self):
        p = self.good()
        del p[0]["fields"]["b"]
        p[1]["fields"]["extra"] = {"value": None, "confidence": 0.0}
        joined = " | ".join(validate_predictions(GOLD, p))
        self.assertIn("missing field b", joined)
        self.assertIn("unexpected field extra", joined)

    def test_confidence_rules(self):
        cases = [float("nan"), float("inf"), True, "0.9", 1.5, -0.1]
        for c in cases:
            p = self.good()
            p[0]["fields"]["a"]["confidence"] = c
            self.assertTrue(validate_predictions(GOLD, p), f"confidence {c!r} must be rejected")

    def test_null_requires_zero_confidence(self):
        p = self.good()
        p[2]["fields"]["a"] = {"value": None, "confidence": 0.5}
        self.assertTrue(any("requires confidence 0" in e for e in validate_predictions(GOLD, p)))

    def test_missing_explicit_confidence_is_rejected(self):
        p = self.good()
        p[0]["fields"]["a"] = {"value": "X"}
        self.assertTrue(validate_predictions(GOLD, p))

    def test_cli_valid_and_invalid(self):
        tmp = Path(tempfile.mkdtemp())
        inp, good, bad = tmp / "in.jsonl", tmp / "good.jsonl", tmp / "bad.jsonl"
        inp.write_text("".join(json.dumps({k: v for k, v in r.items() if k != "gold"}) + "\n" for r in GOLD))
        good.write_text("".join(json.dumps(p) + "\n" for p in self.good()))
        bad.write_text(json.dumps(self.good()[0]) + "\n")
        ok = subprocess.run([sys.executable, "-m", "evaluation.validate", "--input", str(inp), "--pred", str(good)],
                            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "VALID"))
        ko = subprocess.run([sys.executable, "-m", "evaluation.validate", "--input", str(inp), "--pred", str(bad)],
                            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(ko.returncode, 1)


class SplitTests(unittest.TestCase):
    def test_pages_of_one_filing_share_a_group_and_a_split(self):
        self.assertEqual(group_of("x-p0001"), "x")
        for seed in (1, 42, 999):
            self.assertEqual(split_of("filing", seed), split_of("filing", seed))
        recs = [rec(f"filing-p{i:04d}", "a", None) for i in range(1, 6)] + [rec(f"other{i}", "a", None) for i in range(40)]
        parts = split(recs, 42)
        pages = {r["doc_id"] for r in recs if r["doc_id"].startswith("filing-")}
        self.assertTrue(pages <= {r["doc_id"] for r in parts["dev_train"]} or pages <= {r["doc_id"] for r in parts["dev_cal"]})

    def test_files_disjoint_gold_free_and_deterministic(self):
        tmp = Path(tempfile.mkdtemp())
        data = tmp / "dev.jsonl"
        recs = [rec(f"g{i}-p0001", "a", None) for i in range(30)] + [rec(f"g{i}-p0002", "b", None) for i in range(30)]
        data.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        m1 = write(str(data), str(tmp / "s1"), 42)
        m2 = write(str(data), str(tmp / "s2"), 42)
        self.assertEqual(m1["docs"], m2["docs"])
        self.assertEqual(m1["group_overlap"], 0)
        self.assertEqual(sum(m1["docs"].values()), len(recs))
        for name in ("dev_train", "dev_cal"):
            text = (tmp / "s1" / f"{name}_input.jsonl").read_text(encoding="utf-8")
            self.assertNotIn('"gold"', text)
            self.assertIn('"doc_id"', text)
            self.assertTrue((tmp / "s1" / f"{name}_gold.jsonl").exists())
        train = {json.loads(l)["doc_id"] for l in (tmp / "s1" / "dev_train_gold.jsonl").read_text().splitlines() if l}
        cal = {json.loads(l)["doc_id"] for l in (tmp / "s1" / "dev_cal_gold.jsonl").read_text().splitlines() if l}
        self.assertFalse(train & cal)

    def test_strip_gold(self):
        self.assertEqual(set(strip_gold({"doc_id": "x", "gold": {}, "gold_evidence": {}})), {"doc_id"})


class ThresholdTests(unittest.TestCase):
    def test_load_scorer_is_the_official_module(self):
        s = load_scorer()
        self.assertTrue(hasattr(s, "score") and hasattr(s, "load_preds"))
        self.assertEqual(Path(s.__file__).name, "5_score.py")

    def test_positive_saving_hand_computed(self):
        # gold present: d1.a, d2.a, d2.b. Predictions are all correct, confidences 0.99, 0.98, 0.97.
        # Threshold 0.97 accepts all three: accepted 3, wrong 0, hallucinated 0.
        # Saving = (6 - (6 - 3)) / 6 = 0.5 per the scorer's formula.
        preds = [pred("d1", "X", 0.99, None, 0.0), pred("d2", "Y", 0.98, "Z", 0.97),
                 pred("d3", None, 0.0, None, 0.0)]
        # The scorer arithmetic is checked directly (the adapter's gate is tested separately below).
        scorer = load_scorer()
        pmap = {p["doc_id"]: p["fields"] for p in preds}
        d = scorer.score(GOLD, pmap, threshold=0.97, review_cost=1.0, error_cost=100.0)["declared"]
        self.assertEqual((d["accepted"], d["wrong"], d["hallucinated"]), (3, 0, 0))
        self.assertAlmostEqual(d["net_saving_pct"], 0.5)
        sweep = scorer.score(GOLD, pmap, review_cost=1.0, error_cost=100.0)["business"]
        self.assertAlmostEqual(sweep["threshold"], 0.97)

    def test_in_sample_selection_never_activates_and_reports_diagnostic(self):
        # 3 accepted, 0 errors: in-sample only, so the decision abstains whatever the numbers are.
        preds = [pred("d1", "X", 0.99, None, 0.0), pred("d2", "Y", 0.98, "Z", 0.97),
                 pred("d3", None, 0.0, None, 0.0)]
        d = choose_threshold(GOLD, preds, 100.0, manifest={"run_id": "r1", "pipeline": {"samples": 1}})
        self.assertTrue(d["abstain_all"])
        self.assertIn("in-sample", d["method_text"])
        self.assertGreater(d["diagnostic_wilson_audit"]["upper_95"], 0.01)
        self.assertFalse(d["diagnostic_wilson_audit"]["at_most_1_percent"])

    def test_wilson_bound_values(self):
        from evaluation.select_threshold import wilson_upper
        self.assertEqual(wilson_upper(0, 0), 1.0)
        self.assertAlmostEqual(wilson_upper(0, 300), 0.01264, places=4)   # > 1%: 300 errorless fields are not enough
        self.assertLess(wilson_upper(0, 400), 0.01)
        self.assertGreater(wilson_upper(1, 10), wilson_upper(0, 10))

    def test_no_positive_saving_gives_all_abstain_with_zero_saving(self):
        # Every accepted value is wrong or hallucinated at confidence 0.99, and nothing is correct.
        # No threshold has positive saving, so the decision is all-abstain: nulls are counted, saving 0.
        preds = [pred("d1", "WRONG", 0.99, None, 0.0), pred("d2", "WRONG", 0.99, "Zz", 0.0),
                 pred("d3", "Q", 0.99, None, 0.0)]
        d = choose_threshold(GOLD, preds, 100.0, manifest={"run_id": "r2", "pipeline": {"samples": 1}})
        self.assertTrue(d["abstain_all"])
        self.assertEqual(d["threshold"], 1.0)
        self.assertIsNone(d["pipeline"])
        self.assertEqual((d["accepted"], d["wrong"], d["hallucinated"]), (0, 0, 0))
        self.assertEqual(d["net_saving_pct"], 0.0)

    def test_invalid_predictions_are_refused(self):
        preds = [pred("d1", "X", 0.99, None, 0.0), pred("d2", "Y", float("nan"), "Z", 0.9),
                 pred("d3", None, 0.0, None, 0.0)]
        with self.assertRaises(ValueError):
            choose_threshold(GOLD, preds)

    def test_no_manifest_still_gives_a_valid_abstaining_decision(self):
        preds = [pred("d1", "X", 0.99, None, 0.0), pred("d2", "Y", 0.98, "Z", 0.97),
                 pred("d3", None, 0.0, None, 0.0)]
        d = choose_threshold(GOLD, preds, 100.0, manifest=None)
        self.assertTrue(d["abstain_all"])
        self.assertIsNone(d["pipeline"])


if __name__ == "__main__":
    unittest.main()
