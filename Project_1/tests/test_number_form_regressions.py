"""Regression tests for the JSON form of whole numbers (found while checking the probly3 scores). No API.

The official scorer compares str(value) for fields without a normalizer: 45442.0 != 45442 and 7689 != 7689.0.
Dev gold: a whole number is an int when the document prints it without decimals, a float when it prints ".00".
Before the fix the model's JSON form was passed through, so 45442.0 for a printed "45,442" was accepted and wrong,
and a number printed as "7,689.00" was rejected as not grounded.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_number_form_regressions.py
"""
import importlib.util
import unittest
from pathlib import Path

from uncertainty.grounding import canonical_number, is_grounded
from uncertainty.policy import apply_policy, classify_field_v2

ROOT = Path(__file__).resolve().parent.parent
NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
INTEGER = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
PLAIN_TEXT = "Capital contributed during the year 45,442 and ending capital account 42256."
DECIMAL_TEXT = "Base vehicle value $7,689.00 Condition adjustment 0.00 Total 154147.0"


def _score_module():
    spec = importlib.util.spec_from_file_location("official_score", ROOT / "5_score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _same_type(a, b):
    return type(a) is type(b) and a == b


class CanonicalNumberTests(unittest.TestCase):
    def test_float_becomes_int_when_printed_without_decimals(self):
        self.assertTrue(_same_type(canonical_number(45442.0, PLAIN_TEXT, NUMBER), 45442))
        self.assertTrue(_same_type(canonical_number(42256.0, PLAIN_TEXT, NUMBER), 42256))

    def test_int_becomes_float_when_printed_with_zero_decimals(self):
        self.assertTrue(_same_type(canonical_number(7689, DECIMAL_TEXT, NUMBER), 7689.0))
        self.assertTrue(_same_type(canonical_number(154147, DECIMAL_TEXT, NUMBER), 154147.0))
        self.assertTrue(_same_type(canonical_number(0, DECIMAL_TEXT, NUMBER), 0.0))

    def test_already_matching_form_is_kept(self):
        self.assertTrue(_same_type(canonical_number(45442, PLAIN_TEXT, NUMBER), 45442))
        self.assertTrue(_same_type(canonical_number(7689.0, DECIMAL_TEXT, NUMBER), 7689.0))

    def test_integer_schema_is_always_int(self):
        self.assertTrue(_same_type(canonical_number(52.0, "52.00 entries", INTEGER), 52))
        self.assertTrue(_same_type(canonical_number(52.0, None, {"type": "integer"}), 52))

    def test_both_forms_or_no_form_leave_the_value_unchanged(self):
        both = "Amount 500 and later amount 500.00"
        self.assertTrue(_same_type(canonical_number(500.0, both, NUMBER), 500.0))
        self.assertTrue(_same_type(canonical_number(500, both, NUMBER), 500))
        self.assertTrue(_same_type(canonical_number(999.0, PLAIN_TEXT, NUMBER), 999.0))

    def test_fractions_strings_bools_and_none_are_untouched(self):
        self.assertEqual(canonical_number(33.3333, "share 33.3333 %", NUMBER), 33.3333)
        self.assertEqual(canonical_number("45,442", PLAIN_TEXT, NUMBER), "45,442")
        self.assertIs(canonical_number(True, PLAIN_TEXT, NUMBER), True)
        self.assertIsNone(canonical_number(None, PLAIN_TEXT, NUMBER))
        self.assertEqual(canonical_number([1.0], PLAIN_TEXT, NUMBER), [1.0])

    def test_part_of_a_longer_number_is_not_evidence(self):
        # "442" inside "45,442" and "7689" inside "7,689.00" are not the printed number
        self.assertTrue(_same_type(canonical_number(442.0, PLAIN_TEXT, NUMBER), 442.0))
        self.assertFalse(is_grounded(442, PLAIN_TEXT, NUMBER))
        self.assertFalse(is_grounded(689, DECIMAL_TEXT, NUMBER))
        self.assertFalse(is_grounded(7689, "value 7,689.50", NUMBER), ".50 is another number")
        self.assertFalse(is_grounded(7689, "value 17,689.00", NUMBER))

    def test_negative_whole_number(self):
        self.assertTrue(_same_type(canonical_number(-3186.0, "loss -3,186 reported", NUMBER), -3186))


class GroundingOfZeroDecimalsTests(unittest.TestCase):
    def test_whole_number_printed_with_zero_decimals_is_grounded(self):
        self.assertTrue(is_grounded(7689, DECIMAL_TEXT, NUMBER))
        self.assertTrue(is_grounded(7689.0, DECIMAL_TEXT, NUMBER))
        self.assertTrue(is_grounded(154147, DECIMAL_TEXT, NUMBER))

    def test_plain_whole_number_is_still_grounded(self):
        self.assertTrue(is_grounded(45442, PLAIN_TEXT, NUMBER))
        self.assertTrue(is_grounded(45442.0, PLAIN_TEXT, NUMBER))

    def test_number_that_is_not_printed_stays_ungrounded(self):
        self.assertFalse(is_grounded(7690, DECIMAL_TEXT, NUMBER))
        self.assertFalse(is_grounded(7689.5, DECIMAL_TEXT, NUMBER))


class PolicyAndScorerTests(unittest.TestCase):
    def _classified(self, value, text, spec=NUMBER):
        return classify_field_v2({"status": "present", "value": value, "model_confidence": 0.99}, spec, text, defs={})

    def test_classify_field_v2_returns_the_printed_form(self):
        out = self._classified(45442.0, PLAIN_TEXT)
        self.assertEqual(out["status"], "present")
        self.assertTrue(_same_type(out["value"], 45442))
        out = self._classified(7689, DECIMAL_TEXT)
        self.assertEqual(out["status"], "present")
        self.assertTrue(_same_type(out["value"], 7689.0))
        self.assertEqual(out["model_confidence"], 0.99, "the confidence is not changed")

    def test_apply_policy_returns_the_printed_form(self):
        schema = {"properties": {"capital": NUMBER}}
        out = apply_policy({"capital": {"value": 45442.0, "confidence": 0.9}}, schema, PLAIN_TEXT)
        self.assertTrue(_same_type(out["capital"]["value"], 45442))

    def test_ungrounded_and_invalid_values_are_still_rejected(self):
        self.assertEqual(self._classified(999.0, PLAIN_TEXT)["status"], "unsupported")
        self.assertEqual(self._classified("45,442", PLAIN_TEXT)["status"], "invalid")

    def test_official_scorer_counts_the_old_form_wrong_and_the_new_form_correct(self):
        scorer = _score_module()
        schema = {"properties": {"capital": NUMBER, "value": NUMBER}}
        gold = [{"doc_id": "d", "source_dataset": "extractbench", "schema": schema,
                 "gold": {"capital": 45442, "value": 7689.0}}]
        text = PLAIN_TEXT + " " + DECIMAL_TEXT
        model = {"capital": {"value": 45442.0, "confidence": 0.99}, "value": {"value": 7689, "confidence": 0.99}}
        old = {"d": model}  # passed through unchanged, as before the fix
        res_old = scorer.score(gold, old, threshold=0.95)["at_threshold"]
        self.assertEqual((res_old["correct"], res_old["wrong"]), (0, 2))
        new = {"d": apply_policy(model, schema, text)}
        res_new = scorer.score(gold, new, threshold=0.95)["at_threshold"]
        self.assertEqual((res_new["correct"], res_new["wrong"]), (2, 0))


if __name__ == "__main__":
    unittest.main()
