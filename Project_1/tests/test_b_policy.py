"""Tests for Person B: grounding, policy, and probly-based sample aggregation.

Self-contained: small invented texts, no API calls, no imports from A or C modules.
Run from Project_1:  .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_b_policy.py
"""
import math
import random
import unittest

from uncertainty.grounding import is_grounded
from uncertainty.policy import apply_policy
from uncertainty.uq_probly import aggregate_samples

STR = {"type": "string"}
NUM = {"type": "number"}
SPAN = {"x-normalizer": "span"}
BOOL = {"type": "boolean"}
JSONF = {"x-normalizer": "json"}

TEXT = (
    "Invoice 2026-7.\n"
    "Total: 1,234.50 EUR. Units: 312 and 12 items. Net  Price applies.\n"
    "Section 2 Governing law: Delaware. Venue: Ohio courts.\n"
    "Parties agree to mutual indemnification for losses caused by either party."
)
SCHEMA = {"properties": {"law": {"type": "string"}, "qty": {"type": "number"}, "total": {"type": "string"}}}


def sample(idx, law, c_law, qty, c_qty, complete=True):
    return {"sample_idx": idx, "complete": complete,
            "fields": {"law": {"value": law, "confidence": c_law},
                       "qty": {"value": qty, "confidence": c_qty},
                       "total": {"value": None, "confidence": 0.0}}}


class GroundingTests(unittest.TestCase):
    def test_numbers_keep_separators_and_do_not_match_loosely(self):
        self.assertTrue(is_grounded("1,234.50", TEXT, STR))
        self.assertFalse(is_grounded("1234.50", TEXT, STR), "comma-stripped value must not be grounded")

    def test_number_token_boundaries(self):
        self.assertFalse(is_grounded(12, "reference 312 only", NUM), "12 inside 312")
        self.assertFalse(is_grounded(12, "price 12.50", NUM), "partial decimal")
        self.assertFalse(is_grounded(12, "amount 1,12", NUM), "inside a separator-number")
        self.assertFalse(is_grounded(-12, "amount 12", NUM), "sign dropped")
        self.assertTrue(is_grounded(12, "Units: 312 and 12 items", NUM))

    def test_number_forms(self):
        self.assertTrue(is_grounded(1234, "total 1,234 units", NUM))
        self.assertTrue(is_grounded(33.3333, "share 33.3333 percent", NUM))
        self.assertFalse(is_grounded(float("nan"), "nan", NUM))
        self.assertFalse(is_grounded(float("inf"), "inf", NUM))

    def test_casefold_and_whitespace(self):
        self.assertTrue(is_grounded("net price", TEXT, STR))
        self.assertTrue(is_grounded("NET   PRICE", TEXT, STR))

    def test_long_valid_span_is_checked_not_skipped(self):
        span = ("Parties agree to mutual indemnification for losses caused by either party. "
                "The indemnified party shall give prompt written notice of any third-party claim, "
                "and the indemnifying party shall control the defence of that claim at its own cost.")
        text = "Preamble. " + span + " Schedule follows."
        self.assertTrue(is_grounded(span, text, SPAN))
        self.assertFalse(is_grounded(span.replace("prompt", "immediate"), text, SPAN),
                         "a changed word must break the span")

    def test_span_pieces_checked_separately(self):
        self.assertTrue(is_grounded("Governing law: Delaware. | Parties agree", TEXT, SPAN))
        self.assertFalse(is_grounded("Governing law: Delaware. | Texas courts", TEXT, SPAN))

    def test_scattered_words_are_not_a_span(self):
        self.assertFalse(is_grounded("Governing Delaware", TEXT, SPAN))

    def test_no_evidence_or_no_text(self):
        self.assertFalse(is_grounded("Delaware", None, STR))
        self.assertFalse(is_grounded("Delaware", "   ", STR))
        self.assertFalse(is_grounded("", TEXT, STR))
        self.assertFalse(is_grounded(None, TEXT, STR))

    def test_bool_json_and_objects_return_false(self):
        self.assertFalse(is_grounded(True, "true", BOOL))
        self.assertFalse(is_grounded("true", "true", BOOL), "checkbox-like fields are not checkable yet")
        self.assertFalse(is_grounded({"a": 1}, '{"a": 1}', JSONF))
        self.assertFalse(is_grounded([1, 2], "1 2", STR))


class PolicyTests(unittest.TestCase):
    def test_output_has_exactly_schema_fields(self):
        ans = {"law": {"value": "Delaware", "confidence": 0.7}, "extra": {"value": "x", "confidence": 1}}
        out = apply_policy(ans, SCHEMA, TEXT)
        self.assertEqual(set(out), {"law", "qty", "total"})
        self.assertEqual(out["law"], {"value": "Delaware", "confidence": 0.7})
        self.assertEqual(out["qty"], {"value": None, "confidence": 0.0})

    def test_valid_score_is_passed_unchanged(self):
        out = apply_policy({"law": {"value": "Delaware", "confidence": 0.73}}, SCHEMA, TEXT)
        self.assertEqual(out["law"]["confidence"], 0.73)

    def test_invalid_confidences_abstain(self):
        bad = [float("nan"), float("inf"), float("-inf"), True, False, "0.9", None, 1.5, -0.1]
        for c in bad:
            out = apply_policy({"law": {"value": "Delaware", "confidence": c}}, SCHEMA, TEXT)
            self.assertEqual(out["law"], {"value": None, "confidence": 0.0}, f"confidence {c!r}")

    def test_missing_fields_and_bare_values_abstain(self):
        out = apply_policy({"law": "Delaware"}, SCHEMA, TEXT)  # no confidence object
        self.assertEqual(out["law"], {"value": None, "confidence": 0.0})
        out = apply_policy({}, SCHEMA, TEXT)
        self.assertTrue(all(v == {"value": None, "confidence": 0.0} for v in out.values()))

    def test_ungrounded_and_null_values_abstain(self):
        out = apply_policy({"law": {"value": "Texas", "confidence": 0.99},
                            "qty": {"value": None, "confidence": 0.9},
                            "total": {"value": "", "confidence": 0.9}}, SCHEMA, TEXT)
        self.assertEqual(out["law"], {"value": None, "confidence": 0.0})
        self.assertEqual(out["qty"], {"value": None, "confidence": 0.0})
        self.assertEqual(out["total"], {"value": None, "confidence": 0.0})

    def test_no_evidence_abstains_even_with_high_confidence(self):
        out = apply_policy({"law": {"value": "Delaware", "confidence": 1.0}}, SCHEMA, None)
        self.assertEqual(out["law"], {"value": None, "confidence": 0.0})

    def test_threshold_zero_is_not_enough(self):
        # confidence 0 alone would still be accepted at threshold 0; value must be null too
        out = apply_policy({"law": {"value": "Texas", "confidence": 0.9}}, SCHEMA, TEXT)
        self.assertIsNone(out["law"]["value"])


class AggregationTests(unittest.TestCase):
    def test_k1_equals_apply_policy(self):
        s = [sample(0, "Delaware", 0.8, 12, 0.6)]
        self.assertEqual(aggregate_samples(s, SCHEMA, TEXT)["fields"], apply_policy(s[0]["fields"], SCHEMA, TEXT))

    def test_k1_does_not_raise_confidence(self):
        s = [sample(0, "Delaware", 0.4, 12, 0.5)]
        out = aggregate_samples(s, SCHEMA, TEXT)["fields"]
        self.assertEqual(out["law"]["confidence"], 0.4)
        self.assertEqual(out["qty"]["confidence"], 0.5)

    def test_identical_samples_have_zero_entropy_and_min_confidence(self):
        s = [sample(0, "Delaware", 0.4, 12, 0.9), sample(1, "delaware", 0.9, 12, 0.7),
             sample(2, "DELAWARE", 0.8, 12, 0.8)]
        r = aggregate_samples(s, SCHEMA, TEXT)
        law = r["diagnostics"]["per_field"]["law"]
        self.assertAlmostEqual(law["entropy"], 0.0, places=12)
        self.assertEqual(law["agreement"], 1.0)
        self.assertEqual(r["fields"]["law"]["confidence"], 0.4, "min of model confidences, never raised")

    def test_contradictory_grounded_samples_have_positive_entropy_and_null(self):
        # both values are printed in TEXT ("Delaware", "Ohio courts"), so both are real votes
        s = [sample(0, "Delaware", 0.9, 12, 0.9), sample(1, "Ohio", 0.9, 12, 0.9)]
        r = aggregate_samples(s, SCHEMA, TEXT)
        law = r["diagnostics"]["per_field"]["law"]
        self.assertAlmostEqual(law["entropy"], math.log(2), places=9)
        self.assertEqual(r["fields"]["law"], {"value": None, "confidence": 0.0})
        self.assertEqual(law["reason"], "tie")

    def test_three_way_contradiction_entropy_is_log3(self):
        text = "a: Delaware. b: Ohio. c: Texas."
        s = [sample(0, "Delaware", 0.9, 12, 0.9), sample(1, "Ohio", 0.9, 12, 0.9),
             sample(2, "Texas", 0.9, 12, 0.9)]
        ent = aggregate_samples(s, SCHEMA, text)["diagnostics"]["per_field"]["law"]["entropy"]
        self.assertAlmostEqual(ent, math.log(3), places=9)

    def test_null_majority_gives_null(self):
        s = [sample(0, None, 0.0, 12, 0.9), sample(1, None, 0.0, 12, 0.9), sample(2, "Delaware", 0.9, 12, 0.9)]
        r = aggregate_samples(s, SCHEMA, TEXT)
        self.assertEqual(r["fields"]["law"], {"value": None, "confidence": 0.0})
        self.assertEqual(r["diagnostics"]["per_field"]["law"]["reason"], "null_majority")

    def test_tie_including_null_gives_null(self):
        s = [sample(0, "Delaware", 0.9, 12, 0.9), sample(1, None, 0.0, 12, 0.9)]
        self.assertEqual(aggregate_samples(s, SCHEMA, TEXT)["fields"]["law"], {"value": None, "confidence": 0.0})

    def test_ungrounded_consensus_is_null(self):
        s = [sample(0, "Texas", 0.9, 99, 0.9), sample(1, "Texas", 0.9, 99, 0.9)]
        r = aggregate_samples(s, SCHEMA, TEXT)
        self.assertEqual(r["fields"]["law"], {"value": None, "confidence": 0.0})
        self.assertEqual(r["fields"]["qty"], {"value": None, "confidence": 0.0})

    def test_incomplete_sample_abstains_whole_document(self):
        s = [sample(0, "Delaware", 0.9, 12, 0.9), sample(1, "Delaware", 0.9, 12, 0.9, complete=False)]
        r = aggregate_samples(s, SCHEMA, TEXT)
        self.assertFalse(r["diagnostics"]["complete"])
        self.assertTrue(all(v == {"value": None, "confidence": 0.0} for v in r["fields"].values()))

    def test_empty_and_duplicate_samples(self):
        r = aggregate_samples([], SCHEMA, TEXT)
        self.assertEqual(r["diagnostics"]["n_samples"], 0)
        self.assertEqual(r["diagnostics"]["per_field"]["law"]["reason"], "no_samples")
        dup = [sample(0, "Delaware", 0.9, 12, 0.9), sample(0, "Delaware", 0.9, 12, 0.9)]
        self.assertEqual(aggregate_samples(dup, SCHEMA, TEXT)["diagnostics"]["per_field"]["law"]["reason"],
                         "duplicate_sample_idx")

    def test_result_independent_of_sample_order(self):
        s = [sample(0, "Delaware", 0.4, 12, 0.9), sample(1, "delaware", 0.9, 12, 0.7),
             sample(2, "DELAWARE", 0.8, 12, 0.8)]
        base = aggregate_samples(s, SCHEMA, TEXT)
        for seed in range(5):
            shuffled = s[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(aggregate_samples(shuffled, SCHEMA, TEXT), base)

    def test_representative_value_from_lowest_sample_idx(self):
        s = [sample(2, "DELAWARE", 0.8, 12, 0.8), sample(0, "Delaware", 0.9, 12, 0.9)]
        self.assertEqual(aggregate_samples(s, SCHEMA, TEXT)["fields"]["law"]["value"], "Delaware")

    def test_diagnostics_shape(self):
        s = [sample(0, "Delaware", 0.9, 12, 0.9), sample(1, "Delaware", 0.9, 12, 0.9)]
        d = aggregate_samples(s, SCHEMA, TEXT)["diagnostics"]
        self.assertEqual(set(d), {"n_samples", "complete", "method", "per_field"})
        self.assertEqual(set(d["per_field"]["qty"]), {"agreement", "entropy", "n_clusters", "grounded", "reason"})


if __name__ == "__main__":
    unittest.main()
