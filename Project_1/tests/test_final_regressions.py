"""Regression tests for the five last fixes before submission. Local data only, no API.

a) pipeline/transport.py    unescaped control characters (line breaks, tabs) inside JSON strings are accepted
b) pipeline/requests.py     prompt v4: booleans as JSON true/false, multi-part spans joined with " | "
c) uncertainty/grounding.py typographic variants (curly quotes, dashes, non-breaking spaces) are unified
d) uncertainty/decision.py  a non-null prediction with confidence 0.0 becomes null
e) uncertainty/uq_probly.py status_counts appear in the per-field diagnostics

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_final_regressions.py
"""
import importlib.util
import unittest
from pathlib import Path

from pipeline.merge import merge_sample_v2
from pipeline.requests import PROMPT_VERSION, RULES, build_jobs, build_prompt
from pipeline.transport import ParseError, ReplyCache, parse_reply
from uncertainty.decision import METHODS, make_prediction
from uncertainty.grounding import is_grounded, normalise
from uncertainty.uq_probly import aggregate_v2

ROOT = Path(__file__).resolve().parent.parent
SPAN = {"type": "string", "x-normalizer": "span"}
STRING = {"type": "string"}


# ---------------------------------------------------------------- a) transport
class ControlCharacterTests(unittest.TestCase):
    def test_literal_newline_and_tab_inside_a_string_are_accepted(self):
        reply = '{"clause": {"value": "Section 1\n\tThe Supplier shall deliver.", "confidence": 0.9}}'
        obj = parse_reply(reply)
        self.assertEqual(obj["clause"]["value"], "Section 1\n\tThe Supplier shall deliver.")
        self.assertEqual(obj["clause"]["confidence"], 0.9)

    def test_carriage_return_inside_a_string_is_accepted(self):
        obj = parse_reply('{"a": {"value": "line one\r\nline two", "confidence": 0.5}}')
        self.assertEqual(obj["a"]["value"], "line one\r\nline two")

    def test_control_characters_inside_a_code_fence(self):
        reply = '```json\n{"a": {"value": "x\ty\nz", "confidence": 1}}\n```'
        self.assertEqual(parse_reply(reply)["a"]["value"], "x\ty\nz")

    def test_escaped_control_characters_still_parse_to_the_same_value(self):
        raw = parse_reply('{"a": {"value": "x\ny", "confidence": 1}}')
        escaped = parse_reply('{"a": {"value": "x\\ny", "confidence": 1}}')
        self.assertEqual(raw, escaped)

    def test_broken_structure_is_still_a_parse_error(self):
        for bad in ('{"a": {"value": "x\ny", "confidence": 1}',      # missing closing brace
                    '{"a": {"value": "unterminated\n, "confidence": 1}}',
                    '{"a": "x\ny",}',                                 # trailing comma
                    'Here is the answer: {"a": 1}',
                    '["x\ny"]',                                       # not an object
                    '', '   '):
            with self.assertRaises(ParseError, msg=repr(bad)):
                parse_reply(bad)


# ---------------------------------------------------------------- b) prompt v4
class PromptV4Tests(unittest.TestCase):
    SCHEMA = {"properties": {
        "is_checked": {"anyOf": [{"type": "boolean"}, {"type": "null"}], "description": "checkbox"},
        "clause": {"type": "string", "x-normalizer": "span", "description": "a clause"}}}

    def test_prompt_version_is_v4(self):
        self.assertEqual(PROMPT_VERSION, "v4")

    def test_boolean_rule_asks_for_json_booleans_not_strings(self):
        p = build_prompt(self.SCHEMA, "body", chunk_no=1, n_chunks=1)
        self.assertIn("JSON true or false, not a string", p)
        self.assertIn("is_checked (type=boolean)", p)
        # the v3 wording asked for the strings "true" / "false"; it must be gone
        self.assertNotIn('"true"', RULES)
        self.assertNotIn('"false"', RULES)

    def test_checkbox_semantics_are_kept(self):
        self.assertIn("false if it is visibly unchecked", RULES)
        self.assertIn("null only if the section is", RULES)

    def test_span_rule_names_the_separator(self):
        p = build_prompt(self.SCHEMA, "body", chunk_no=1, n_chunks=1)
        self.assertIn('joined with " | "', p)
        self.assertIn("ONE string", p)
        self.assertIn("normalizer=span", p)

    def test_span_separator_matches_grounding_and_scorer(self):
        from uncertainty.grounding import SPAN_SEPARATOR
        self.assertEqual(SPAN_SEPARATOR, " | ")
        self.assertIn(f'"{SPAN_SEPARATOR}"', RULES)

    def test_prompt_version_is_part_of_the_cache_key(self):
        kw = dict(endpoint="https://x", model="m", temperature=0.0, sample_idx=0,
                  messages=[{"role": "user", "content": "p"}])
        self.assertNotEqual(ReplyCache.make_key(prompt_version="v3", **kw),
                            ReplyCache.make_key(prompt_version="v4", **kw),
                            "v3 replies must not be served for v4 prompts")


# ---------------------------------------------------------------- c) grounding
class TypographicVariantTests(unittest.TestCase):
    def test_straight_apostrophe_matches_curly_text(self):
        text = "This is the Supplier’s obligation under the Agreement."
        self.assertTrue(is_grounded("Supplier's obligation", text, SPAN))
        self.assertTrue(is_grounded("Supplier's obligation", text, STRING))

    def test_curly_apostrophe_matches_straight_text(self):
        self.assertTrue(is_grounded("Supplier’s obligation", "the Supplier's obligation.", SPAN))

    def test_curly_double_quotes_match_straight_quotes(self):
        text = 'hereinafter the “Company” shall'
        self.assertTrue(is_grounded('the "Company" shall', text, SPAN))
        self.assertTrue(is_grounded('the “Company” shall', 'hereinafter the "Company" shall', SPAN))

    def test_en_and_em_dash_and_minus_match_hyphen(self):
        for dash in ("–", "—", "−"):
            text = f"a non{dash}exclusive licence is granted"
            self.assertTrue(is_grounded("non-exclusive licence", text, SPAN), repr(dash))
            self.assertTrue(is_grounded(f"non{dash}exclusive licence", "a non-exclusive licence", SPAN), repr(dash))

    def test_non_breaking_space_matches_space(self):
        self.assertTrue(is_grounded("March 27, 2020", "dated March 27, 2020 by", STRING))

    def test_multi_part_span_with_typographic_variants(self):
        text = "The Supplier’s duty. Other text. A non–exclusive right."
        self.assertTrue(is_grounded("Supplier's duty | non-exclusive right", text, SPAN))
        self.assertFalse(is_grounded("Supplier's duty | exclusive ownership", text, SPAN),
                         "every part must be grounded")

    def test_normalise_unifies_only_the_glyph(self):
        self.assertEqual(normalise("Supplier’s"), normalise("Supplier's"))
        self.assertEqual(normalise("A—B"), "a-b")

    def test_different_words_and_numbers_stay_different(self):
        text = "The Supplier’s obligation is 1,234.50 EUR."
        self.assertFalse(is_grounded("Suppliers obligation", text, SPAN), "a dropped apostrophe is not a variant")
        self.assertFalse(is_grounded("Buyer's obligation", text, SPAN))
        self.assertFalse(is_grounded("1234.50", text, STRING), "thousands separator is kept")
        self.assertTrue(is_grounded("1,234.50", text, STRING))

    def test_token_bounds_survive_the_dash_mapping(self):
        # an en dash becomes "-", which must still block a numeric match inside a range
        self.assertFalse(is_grounded(12, "pages 3–12 apply", {"type": "number"}))
        self.assertTrue(is_grounded(12, "there are 12 units", {"type": "number"}))


# ---------------------------------------------------------------- d) decision
def _aggregation(features, value="Delaware"):
    return {"contract_version": 2,
            "candidates": {"law": {"value": value, "eligible": True, "reason": "majority", "features": features}}}


class ZeroConfidenceTests(unittest.TestCase):
    SCHEMA = {"properties": {"law": {"type": "string"}}}

    def test_k1_value_with_model_confidence_zero_becomes_null(self):
        agg = _aggregation({"k_expected": 1, "model_conf_min": 0.0})
        self.assertEqual(make_prediction(agg, self.SCHEMA, method="k1_grounded"),
                         {"law": {"value": None, "confidence": 0.0}})

    def test_k_agreement_conf_with_confidence_zero_becomes_null(self):
        agg = _aggregation({"k_expected": 3, "agreement": 1.0, "model_conf_min": 0.0})
        self.assertEqual(make_prediction(agg, self.SCHEMA, method="k_agreement_conf")["law"],
                         {"value": None, "confidence": 0.0})

    def test_k_entropy_with_maximal_entropy_becomes_null(self):
        agg = _aggregation({"k_expected": 3, "entropy_norm": 1.0})
        self.assertEqual(make_prediction(agg, self.SCHEMA, method="k_entropy")["law"],
                         {"value": None, "confidence": 0.0})

    def test_smallest_positive_score_keeps_the_value(self):
        agg = _aggregation({"k_expected": 1, "model_conf_min": 1e-9})
        self.assertEqual(make_prediction(agg, self.SCHEMA, method="k1_grounded")["law"],
                         {"value": "Delaware", "confidence": 1e-9})

    def test_end_to_end_no_method_returns_a_value_with_confidence_zero(self):
        text = "Governing law: Delaware."
        for k, methods in ((1, ("k1_grounded",)), (3, ("k_agreement_only", "k_agreement_conf", "k_entropy"))):
            jobs = build_jobs(text, self.SCHEMA, chunk_chars=100_000, overlap_chars=0, batch_size=10, samples=k)
            results = [{"job_id": j["job_id"], "sample_idx": j["sample_idx"], "chunk_id": j["chunk_id"],
                        "batch_id": j["batch_id"], "start": j["start"], "end": j["end"],
                        "field_names": j["field_names"], "ok": True, "error": None,
                        "answer": {"law": {"value": "Delaware", "confidence": 0.0}}} for j in jobs]
            samples = [merge_sample_v2(results, self.SCHEMA, s, planned_jobs=jobs) for s in range(k)]
            agg = aggregate_v2(samples, self.SCHEMA, text, expected_k=k)
            for method in methods:
                pred = make_prediction(agg, self.SCHEMA, method=method)["law"]
                if pred["value"] is not None:
                    self.assertGreater(pred["confidence"], 0.0, f"{method}: value with confidence 0")
                else:
                    self.assertEqual(pred["confidence"], 0.0)

    def test_scorer_would_accept_a_value_with_confidence_zero_at_threshold_zero(self):
        """Why the fix matters: the official scorer accepts confidence >= threshold, so 0.0 passes at threshold 0."""
        spec = importlib.util.spec_from_file_location("official_score", ROOT / "5_score.py")
        scorer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scorer)
        gold = [{"doc_id": "d", "source_dataset": "cuad", "schema": self.SCHEMA, "gold": {"law": "Ohio"}}]
        bad = {"d": {"law": {"value": "Delaware", "confidence": 0.0}}}   # scorer format: doc_id -> fields
        fixed = {"d": {"law": {"value": None, "confidence": 0.0}}}
        self.assertEqual(scorer.score(gold, bad, threshold=0.0)["at_threshold"]["wrong"], 1)
        self.assertEqual(scorer.score(gold, fixed, threshold=0.0)["at_threshold"]["wrong"], 0)

    def test_methods_list_is_unchanged(self):
        self.assertEqual(METHODS, ("k1_grounded", "k_agreement_only", "k_agreement_conf", "k_entropy", "calibrated"))


# ---------------------------------------------------------------- e) diagnostics
class StatusCountDiagnosticsTests(unittest.TestCase):
    TEXT = "Governing law: Delaware. Venue: Ohio courts."
    SCHEMA = {"properties": {"law": {"type": "string"}, "venue": {"type": "string"}}}

    def _aggregate(self, answers, expected_k=None, text=TEXT):
        k = len(answers)
        jobs = build_jobs(self.TEXT, self.SCHEMA, chunk_chars=100_000, overlap_chars=0, batch_size=10, samples=k)
        results = [{"job_id": j["job_id"], "sample_idx": j["sample_idx"], "chunk_id": j["chunk_id"],
                    "batch_id": j["batch_id"], "start": j["start"], "end": j["end"],
                    "field_names": j["field_names"], "answer": answers[j["sample_idx"]],
                    "ok": answers[j["sample_idx"]] is not None,
                    "error": None if answers[j["sample_idx"]] is not None else "http:500"} for j in jobs]
        samples = [merge_sample_v2(results, self.SCHEMA, s, planned_jobs=jobs) for s in range(k)]
        return aggregate_v2(samples, self.SCHEMA, text, expected_k=expected_k or k)

    @staticmethod
    def _answer(law, venue=None):
        return {"law": {"value": law, "confidence": 0.9 if law is not None else 0.0},
                "venue": {"value": venue, "confidence": 0.9 if venue is not None else 0.0}}

    def test_status_counts_are_in_the_per_field_diagnostics(self):
        # law: 2 grounded values, 1 value that is not in the text. venue: 3 explicit nulls.
        a = self._aggregate([self._answer("Delaware"), self._answer("Delaware"), self._answer("Florida")])
        per_field = a["diagnostics"]["per_field"]
        self.assertEqual(per_field["law"]["status_counts"], {"present": 2, "unsupported": 1})
        self.assertEqual(per_field["venue"]["status_counts"], {"absent": 3})
        self.assertEqual(sum(per_field["law"]["status_counts"].values()), 3)

    def test_diagnostics_match_the_candidate_features(self):
        a = self._aggregate([self._answer("Delaware"), self._answer(None), self._answer("Florida")])
        for name in self.SCHEMA["properties"]:
            self.assertEqual(a["diagnostics"]["per_field"][name]["status_counts"],
                             a["candidates"][name]["features"]["status_counts"])

    def test_status_counts_explain_an_ineligible_field(self):
        # one failed sample job: the field is not eligible, and the counts show the error, not a null vote
        a = self._aggregate([self._answer("Delaware"), self._answer("Delaware"), None])
        d = a["diagnostics"]["per_field"]["law"]
        self.assertFalse(d["eligible"])
        self.assertEqual(d["reason"], "incomplete_observations")
        self.assertEqual(d["status_counts"].get("present"), 2)
        self.assertEqual(sum(d["status_counts"].values()), 3)
        self.assertNotIn("absent", d["status_counts"], "a failed observation is not counted as an explicit null")

    def test_status_counts_present_for_unreadable_and_mismatch(self):
        unreadable = self._aggregate([self._answer("Delaware")], text=None)
        self.assertIn("status_counts", unreadable["diagnostics"]["per_field"]["law"])
        self.assertEqual(unreadable["diagnostics"]["per_field"]["law"]["reason"], "unreadable")
        mismatch = self._aggregate([self._answer("Delaware")] * 2, expected_k=3)
        self.assertEqual(mismatch["diagnostics"]["per_field"]["law"]["reason"], "sample_count_mismatch")
        self.assertEqual(sum(mismatch["diagnostics"]["per_field"]["law"]["status_counts"].values()), 2)

    def test_diagnostics_are_json_serialisable(self):
        import json
        a = self._aggregate([self._answer("Delaware"), self._answer("Delaware"), self._answer("Florida")])
        json.dumps(a["diagnostics"])


if __name__ == "__main__":
    unittest.main()
