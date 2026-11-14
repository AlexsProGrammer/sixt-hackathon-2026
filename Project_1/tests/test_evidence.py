"""Tests for T08: per-type, per-source evidence features and permissive classify_field_v2.

Run from Project_1:
    .venv/bin/python -m unittest discover -s tests -p test_evidence.py
"""
import importlib.util
import unittest
from pathlib import Path

from evaluation import field_table
from uncertainty.evidence import evidence, extract_numbers, number_strength
from uncertainty.grounding import is_grounded
from uncertainty.policy import classify_field_v2

ROOT = Path(__file__).resolve().parent.parent
NUM = {"type": "number"}
STR = {"type": "string"}
BOOL = {"type": "boolean"}
JSONF = {"x-normalizer": "json"}
SPAN = {"x-normalizer": "span"}


def _score_module():
    spec = importlib.util.spec_from_file_location("official_score", ROOT / "5_score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EvidenceNumberTests(unittest.TestCase):
    def test_1234_5_matches_printed_1_234_50(self):
        ev = evidence(1234.5, NUM, {"text": "Total due: $1,234.50 USD.", "ocr": None})
        self.assertTrue(ev["grounded_text"])
        self.assertIsNone(ev["grounded_ocr"])
        self.assertEqual(ev["occurrences"], 1)
        self.assertEqual(ev["number_strength"], "strong")
        self.assertEqual(ev["kind_policy"], "evidence_or_views")

    def test_parenthesised_500_gives_minus_500(self):
        nums = extract_numbers("Net adjustment: (500) and fee ($1,234.50) in Q1.")
        self.assertEqual(nums[-500.0], 1)
        self.assertEqual(nums[-1234.5], 1)
        ev = evidence(-500, NUM, {"text": "Loss (500) reported.", "ocr": None})
        self.assertTrue(ev["grounded_text"])
        self.assertEqual(ev["occurrences"], 1)
        self.assertEqual(ev["number_strength"], "weak")

    def test_1_is_weak_and_has_many_occurrences(self):
        text = "Section 1: 1 unit at $1.00 each, total 1 item."
        ev = evidence(1, NUM, {"text": text, "ocr": None})
        self.assertTrue(ev["grounded_text"])
        self.assertEqual(ev["number_strength"], "weak")
        self.assertEqual(ev["occurrences"], 4)

    def test_number_strength_rules(self):
        for weak in (0, 0.0, 1, 1.0, 100, 100.0, 42, -500, 33.3333, 66.6667):
            self.assertEqual(number_strength(weak), "weak", repr(weak))
        for strong in (1234, 1500, -3186, 1234.5, 12.5, 0.25):
            self.assertEqual(number_strength(strong), "strong", repr(strong))
        self.assertIsNone(number_strength(True))
        self.assertIsNone(number_strength("1234"))
        self.assertIsNone(number_strength(float("nan")))

    def test_number_boundaries_do_not_match_substrings(self):
        ev = evidence(12, NUM, {"text": "Ref 312, price 12.50, code 1,12, date 2026-7.", "ocr": None})
        self.assertFalse(ev["grounded_text"])
        self.assertEqual(ev["occurrences"], 0)


class EvidenceStringAndPolicyTests(unittest.TestCase):
    def test_address_components_share(self):
        text = "Property located at 123 Main Street in Springfield."
        ev = evidence("123 Main Street, Springfield, IL", STR, {"text": text, "ocr": None})
        self.assertFalse(ev["grounded_text"])
        self.assertAlmostEqual(ev["components_grounded"], 2 / 3)

        ev_full = evidence("123 Main Street, Springfield", STR, {"text": text, "ocr": None})
        self.assertAlmostEqual(ev_full["components_grounded"], 1.0)

        ev_single = evidence("Springfield", STR, {"text": text, "ocr": None})
        self.assertTrue(ev_single["grounded_text"])
        self.assertIsNone(ev_single["components_grounded"])

    def test_boolean_gives_views_only_and_json_gives_never_book(self):
        ev_bool = evidence(True, BOOL, {"text": "true", "ocr": None})
        self.assertEqual(ev_bool["kind_policy"], "views_only")
        self.assertFalse(ev_bool["grounded_text"])
        self.assertIsNone(ev_bool["number_strength"])

        ev_bool_notext = evidence(True, BOOL, {"text": None, "ocr": None})
        self.assertIsNone(ev_bool_notext["grounded_text"])
        self.assertEqual(ev_bool_notext["kind_policy"], "views_only")

        ev_json = evidence({"a": "x"}, JSONF, {"text": "x", "ocr": None})
        self.assertEqual(ev_json["kind_policy"], "never_book")

    def test_ocr_source_fallback_and_missing_sources(self):
        ev = evidence("Delaware", STR, {"text": None, "ocr": "Governing law: Delaware."})
        self.assertIsNone(ev["grounded_text"])
        self.assertTrue(ev["grounded_ocr"])
        self.assertEqual(ev["occurrences"], 1)

        ev_none = evidence("Delaware", STR, {"text": "  ", "ocr": None})
        self.assertIsNone(ev_none["grounded_text"])
        self.assertIsNone(ev_none["grounded_ocr"])
        self.assertEqual(ev_none["occurrences"], 0)

    def test_classify_field_v2_features_vs_strict(self):
        obs = {"status": "present", "value": "Texas", "model_confidence": 0.9}
        strict_out = classify_field_v2(obs, STR, "Governing law: Delaware.", defs={}, evidence_mode="strict")
        self.assertEqual(strict_out["status"], "unsupported")

        feat_out = classify_field_v2(obs, STR, "Governing law: Delaware.", defs={}, evidence_mode="features")
        self.assertEqual(feat_out["status"], "present")
        self.assertEqual(feat_out["value"], "Texas")
        self.assertFalse(feat_out["evidence"]["grounded_text"])

        # Missing text layer: unreadable in strict, present (grounded_text=None) in features
        self.assertEqual(classify_field_v2(obs, STR, None, evidence_mode="strict")["status"], "unreadable")
        no_text_out = classify_field_v2(obs, STR, None, evidence_mode="features")
        self.assertEqual(no_text_out["status"], "present")
        self.assertIsNone(no_text_out["evidence"]["grounded_text"])

        # Schema-invalid and json are still hard-rejected in features mode
        bad_schema = classify_field_v2({"status": "present", "value": "45", "model_confidence": 0.9}, NUM, "45",
                                       evidence_mode="features")
        self.assertEqual(bad_schema["status"], "invalid")
        json_out = classify_field_v2({"status": "present", "value": {"a": "x"}, "model_confidence": 0.9},
                                     JSONF, "x", evidence_mode="features")
        self.assertEqual(json_out["status"], "unsupported")

    def test_strict_is_grounded_still_matches_legacy_behaviour(self):
        self.assertFalse(is_grounded("1234.50", "Total: 1,234.50", STR))
        self.assertTrue(is_grounded("1,234.50", "Total: 1,234.50", STR))

    def test_field_table_populates_evidence_columns(self):
        rec = {
            "doc_id": "d1",
            "source_dataset": "extractbench",
            "schema": {"title": "Fam", "properties": {"amt": NUM, "addr": STR, "flag": BOOL}},
            "gold": {"amt": 1234.5, "addr": "123 Main St, Austin, TX", "flag": True},
        }
        preds = {
            "d1": {
                "amt": {"value": 1234.5, "confidence": 0.99},
                "addr": {"value": "123 Main St, Austin, TX", "confidence": 0.95},
                "flag": {"value": True, "confidence": 0.9},
            }
        }
        rows = {r["field"]: r for r in field_table.doc_rows(rec, preds, _score_module(), text="Total $1,234.50 at 123 Main St in Austin.")}
        self.assertTrue(rows["amt"]["grounded_text"])
        self.assertFalse(rows["amt"]["grounded_text_strict"])
        self.assertEqual(rows["amt"]["number_strength"], "strong")
        self.assertEqual(rows["amt"]["occurrences"], 1)
        self.assertAlmostEqual(rows["addr"]["components_grounded"], 2 / 3)
        self.assertEqual(rows["flag"]["kind_policy"], "views_only")


if __name__ == "__main__":
    unittest.main()
