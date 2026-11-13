"""Regression tests for the schema fixes: nested $ref tables, wrong keys, wrong types, valid tables, scalars and spans.

NOT EXECUTED yet: written on request without running tests. Run with
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_schema_regressions.py
"""
import unittest

from pipeline.requests import PROMPT_VERSION, build_prompt
from uncertainty.policy import classify_field_v2
from uncertainty.schema_check import check_value

DEFS = {"LaborRow": {"type": "object", "properties": {
    "labor_category_title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "year_1_rate": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    "sin": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}}
TABLE_SPEC = {"anyOf": [{"type": "array", "items": {"$ref": "#/$defs/LaborRow"}}, {"type": "null"}]}
TEXT = "Principal Consultant SIN 54151S rate 241.81"


class SchemaCheckTests(unittest.TestCase):
    def test_valid_table_passes(self):
        ok, why = check_value([{"labor_category_title": "Principal Consultant", "year_1_rate": 241.81,
                                "sin": "54151S"}], TABLE_SPEC, DEFS)
        self.assertTrue(ok, why)

    def test_wrong_key_name_is_invalid(self):
        ok, why = check_value([{"labor_category": "Principal Consultant", "year_1_rate": 241.81}], TABLE_SPEC, DEFS)
        self.assertFalse(ok)
        self.assertIn("keys", why)

    def test_wrong_key_name_for_rate_is_invalid(self):
        ok, _ = check_value([{"labor_category_title": "X", "year_1": 241.81}], TABLE_SPEC, DEFS)
        self.assertFalse(ok)

    def test_currency_text_for_number_is_invalid(self):
        ok, why = check_value([{"labor_category_title": "X", "year_1_rate": "$241.81"}], TABLE_SPEC, DEFS)
        self.assertFalse(ok)
        self.assertIn("schema", why)

    def test_bool_is_not_a_number(self):
        ok, _ = check_value(True, {"type": "number"}, {})
        self.assertFalse(ok)

    def test_scalar_string_and_span_still_pass(self):
        self.assertTrue(check_value("Acme Corp", {"type": "string"}, {})[0])
        self.assertTrue(check_value("Clause A | Clause B", {"type": "string", "x-normalizer": "span"}, {})[0])
        self.assertTrue(check_value(12.5, {"anyOf": [{"type": "number"}, {"type": "null"}]}, {})[0])

    def test_null_is_not_checked(self):
        self.assertTrue(check_value(None, TABLE_SPEC, DEFS)[0])


NULLABLE_ROW_SPEC = {"anyOf": [{"$ref": "#/$defs/LaborRow"}, {"type": "null"}]}
NULLABLE_LIST = {"anyOf": [{"type": "array", "items": {"$ref": "#/$defs/LaborRow"}}, {"type": "null"}]}


class NullableAndKeyTests(unittest.TestCase):
    def test_object_with_unknown_key_is_not_accepted_through_null_branch(self):
        # the null branch has no properties; before the fix it accepted any object
        ok, _ = check_value({"labor_category": "X"}, NULLABLE_ROW_SPEC, DEFS)
        self.assertFalse(ok)

    def test_nullable_array_rejects_object_value(self):
        ok, _ = check_value({"labor_category_title": "X"}, NULLABLE_LIST, DEFS)
        self.assertFalse(ok)

    def test_nullable_array_rejects_unknown_key_inside_row(self):
        ok, why = check_value([{"labor_category": "X", "year_1_rate": 1.0}], NULLABLE_LIST, DEFS)
        self.assertFalse(ok)
        self.assertIn("keys", why)

    def test_nullable_array_rejects_wrong_types_inside_row(self):
        ok, _ = check_value([{"labor_category_title": "X", "year_1_rate": "$1.00"}], NULLABLE_LIST, DEFS)
        self.assertFalse(ok)

    def test_nullable_array_accepts_valid_table_and_null(self):
        self.assertTrue(check_value([{"labor_category_title": "X", "year_1_rate": 1.0}], NULLABLE_LIST, DEFS)[0])
        self.assertTrue(check_value(None, NULLABLE_LIST, DEFS)[0])
        self.assertTrue(check_value([], NULLABLE_LIST, DEFS)[0])

    def test_additional_properties_schema_allows_extra_keys_with_correct_type(self):
        spec = {"type": "object", "properties": {"a": {"type": "string"}},
                "additionalProperties": {"type": "number"}}
        self.assertTrue(check_value({"a": "x", "extra": 2.5}, spec, {})[0])
        self.assertFalse(check_value({"a": "x", "extra": "text"}, spec, {})[0])

    def test_pattern_properties_allow_matching_keys(self):
        spec = {"type": "object", "properties": {"a": {"type": "string"}},
                "patternProperties": {"^note_": {"type": "string"}}}
        self.assertTrue(check_value({"a": "x", "note_1": "text"}, spec, {})[0])
        self.assertFalse(check_value({"a": "x", "other": "text"}, spec, {})[0])

    def test_additional_properties_false_rejects_extra_keys(self):
        spec = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        self.assertFalse(check_value({"a": "x", "b": "y"}, spec, {})[0])

    def test_free_form_object_without_properties_is_not_key_checked(self):
        self.assertTrue(check_value({"anything": 1}, {"type": "object"}, {})[0])

    def test_strict_keys_false_gives_plain_json_schema_behaviour(self):
        ok, _ = check_value({"labor_category": "X"}, {"type": "object", "properties": {"a": {"type": "string"}}},
                            {}, strict_keys=False)
        self.assertTrue(ok)


class ClassifyOrderTests(unittest.TestCase):
    def test_schema_invalid_is_rejected_even_if_text_contains_the_value(self):
        obs = {"status": "present", "value": "$241.81", "model_confidence": 0.99}
        out = classify_field_v2(obs, {"type": "number"}, "rate $241.81", defs={})
        self.assertEqual(out["status"], "invalid")
        self.assertIsNone(out["value"])

    def test_schema_valid_but_ungrounded_is_unsupported(self):
        obs = {"status": "present", "value": 999.0, "model_confidence": 0.9}
        out = classify_field_v2(obs, {"type": "number"}, TEXT, defs={})
        self.assertEqual(out["status"], "unsupported")

    def test_schema_valid_and_grounded_is_present(self):
        obs = {"status": "present", "value": 241.81, "model_confidence": 0.8}
        out = classify_field_v2(obs, {"type": "number"}, TEXT, defs={})
        self.assertEqual(out["status"], "present")


class PromptTests(unittest.TestCase):
    def test_prompt_contains_referenced_defs_and_type_rules(self):
        schema = {"properties": {"labor_categories": TABLE_SPEC}, "$defs": DEFS}
        p = build_prompt(schema, "body", chunk_no=1, n_chunks=1)
        self.assertIn('"LaborRow"', p)
        self.assertIn("labor_category_title", p)
        self.assertIn("year_1_rate", p)
        self.assertIn("not \"$241.81\"", p)

    def test_prompt_version_changed(self):
        self.assertEqual(PROMPT_VERSION, "v3")


if __name__ == "__main__":
    unittest.main()
