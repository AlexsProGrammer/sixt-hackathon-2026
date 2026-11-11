import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("score", Path(__file__).parent / "5_score.py")
S = importlib.util.module_from_spec(_spec)
sys.modules["score"] = S
_spec.loader.exec_module(S)

SCHEMA = {"properties": {
    "total": {"x-normalizer": "amount"},
    "date": {"x-normalizer": "date"},
    "invoice_no": {"x-normalizer": "id"},
    "po_number": {"x-normalizer": "id"},
}}


def rec(doc_id, gold):
    return {"doc_id": doc_id, "source_dataset": "synthetic", "schema": SCHEMA, "gold": gold}


def pred(value, conf=1.0):
    return {"value": value, "confidence": conf}


class Normalisers(unittest.TestCase):
    def test_amount(self):
        self.assertEqual(S.norm_amount("EUR 1.234,50"), "1234.50")
        self.assertEqual(S.norm_amount("1,234.50"), "1234.50")
        self.assertEqual(S.norm_amount("12,5"), "12.50")

    def test_percent_and_rates(self):
        self.assertEqual(S.norm_amount("20%"), S.norm_amount("0.20"))
        self.assertEqual(S.norm_amount("7.5 %"), S.norm_amount("0.075"))
        self.assertNotEqual(S.norm_amount("20%"), S.norm_amount("20.00"))
        self.assertEqual(S.norm_amount("12,50"), "12.50")

    def test_more_date_formats(self):
        self.assertEqual(S.norm_date("31-Oct-2025"), "2025-10-31")
        self.assertEqual(S.norm_date("October 31, 2025"), "2025-10-31")

    def test_date(self):
        self.assertEqual(S.norm_date("13.11.2026"), "2026-11-13")
        self.assertEqual(S.norm_date("2026-11-13"), "2026-11-13")

    def test_id(self):
        self.assertEqual(S.norm_id("INV-001 / A"), "inv001a")


class Nested(unittest.TestCase):
    def test_json_compare_ignores_key_order_and_spacing(self):
        a = '{"b":1,"a":[1,2]}'
        self.assertEqual(S.norm_json(a), S.norm_json({"a": [1, 2], "b": 1}))
        self.assertEqual(S.norm_json(a), S.norm_json('{ "a": [1, 2], "b": 1 }'))
        self.assertNotEqual(S.norm_json(a), S.norm_json('{"a":[2,1],"b":1}'))


class Business(unittest.TestCase):
    def setUp(self):
        self.gold = [rec("d1", {"total": "1.00", "date": "2026-01-01", "invoice_no": "A", "po_number": "B"})]
        self.preds = {"d1": {"total": pred("1.00", 0.95), "date": pred("2026-01-01", 0.90),
                             "invoice_no": pred("A", 0.85), "po_number": pred("WRONG", 0.30)}}

    def test_best_threshold_skips_the_wrong_value(self):
        b = S.score(self.gold, self.preds)["business"]
        self.assertEqual(b["threshold"], 0.85)
        self.assertAlmostEqual(b["saving_pct"], 0.75)      # 3 of 4 fields saved, the 4th goes to a human

    def test_accepting_everything_loses_money(self):
        m = S.at_threshold(S.collect(self.gold, self.preds), 0.0)
        self.assertLess(S.net_saving(m, 1, 100)["saving"], 0)

    def test_automation_that_never_pays_off_is_zero(self):
        res = S.score([rec("d1", {"total": "1.00"})], {"d1": {"total": pred("2.00", 0.9)}})
        self.assertEqual(res["business"]["saving"], 0.0)


class Declared(unittest.TestCase):
    def setUp(self):
        self.gold = [rec("d1", {"total": "1.00", "date": "2026-01-01", "invoice_no": "A", "po_number": "B"})]
        self.preds = {"d1": {"total": pred("1.00", 0.95), "date": pred("2026-01-01", 0.90),
                             "invoice_no": pred("A", 0.85), "po_number": pred("WRONG", 0.30)}}

    def test_declared_threshold_is_scored_as_given(self):
        d = S.score(self.gold, self.preds, threshold=0.85)["declared"]
        self.assertEqual((d["precision"], d["band"], d["accepted"]), (1.0, 0.99, 3))
        self.assertAlmostEqual(d["net_saving_pct"], 0.75)

    def test_too_low_a_threshold_is_penalised_even_if_a_better_one_exists(self):
        d = S.score(self.gold, self.preds, threshold=0.0)["declared"]
        self.assertEqual(d["band"], None)                 # 75% precision: below every band
        self.assertLess(d["net_saving_pct"], 0)           # one wrong value costs 100 reviews

    def test_no_declared_block_without_threshold(self):
        self.assertNotIn("declared", S.score(self.gold, self.preds))


class Spans(unittest.TestCase):
    def test_span_match_is_token_f1(self):
        gold = "This Agreement shall be governed by the laws of the State of New York"
        self.assertTrue(S.values_match("this agreement shall be governed by the laws of the State of New York.", gold, "span"))
        self.assertFalse(S.values_match("the State of New York", gold, "span"))
        self.assertFalse(S.values_match("Delaware law applies", gold, "span"))


class Outcomes(unittest.TestCase):
    def setUp(self):
        self.gold = [rec("d1", {"total": "12.50", "date": "13.11.2026", "invoice_no": "A1", "po_number": None})]

    def test_all_outcome_types(self):
        preds = {"d1": {
            "total": pred("12,50"),          # correct after normalisation
            "date": pred("14.11.2026"),      # wrong
            "invoice_no": pred(None),        # missed (abstain)
            "po_number": pred("P-9"),        # hallucinated: gold is null
        }}
        r = S.at_threshold(S.collect(self.gold, preds), 0.0)
        self.assertEqual((r["correct"], r["wrong"], r["missed"], r["hallucinated"], r["true_null"]), (1, 1, 1, 1, 0))
        self.assertAlmostEqual(r["precision"], 1 / 3)
        self.assertEqual(r["hallucination_rate"], 1.0)

    def test_true_null_is_not_a_false_positive(self):
        preds = {"d1": {"total": pred("12.50"), "date": pred("13.11.2026"), "invoice_no": pred("a1"), "po_number": pred(None)}}
        r = S.at_threshold(S.collect(self.gold, preds), 0.0)
        self.assertEqual((r["precision"], r["recall"], r["hallucinated"], r["true_null"]), (1.0, 1.0, 0, 1))

    def test_missing_prediction_counts_as_abstain(self):
        r = S.at_threshold(S.collect(self.gold, {}), 0.0)
        self.assertEqual((r["accepted"], r["missed"], r["true_null"]), (0, 3, 1))


class Curve(unittest.TestCase):
    def test_threshold_trades_coverage_for_precision(self):
        gold = [rec("d1", {"total": "1.00", "date": "2026-01-01", "invoice_no": "A", "po_number": "B"})]
        preds = {"d1": {
            "total": pred("1.00", 0.95), "date": pred("2026-01-01", 0.90),
            "invoice_no": pred("A", 0.85), "po_number": pred("WRONG", 0.30),
        }}
        res = S.score(gold, preds, target=0.99)
        self.assertLess(res["at_threshold_0"]["precision"], 0.99)
        self.assertTrue(res["headline"]["reached_target"])
        self.assertAlmostEqual(res["headline"]["coverage_at_target_precision"], 0.75)
        self.assertEqual(res["headline"]["threshold_at_target"], 0.85)

    def test_precision_ladder(self):
        gold = [rec("d1", {"total": "1.00", "date": "2026-01-01", "invoice_no": "A", "po_number": "B"})]
        preds = {"d1": {"total": pred("1.00", 0.95), "date": pred("2026-01-01", 0.90),
                        "invoice_no": pred("A", 0.85), "po_number": pred("WRONG", 0.30)}}
        ladder = S.score(gold, preds)["coverage_at_precision"]
        self.assertAlmostEqual(ladder["0.99"], 0.75)
        self.assertAlmostEqual(ladder["0.8"], 0.75)  # accepting all 4 gives 75% precision, below 0.8

    def test_target_not_reached(self):
        gold = [rec("d1", {"total": "1.00"})]
        res = S.score(gold, {"d1": {"total": pred("2.00", 0.9)}}, target=0.99)
        self.assertFalse(res["headline"]["reached_target"])
        self.assertEqual(res["headline"]["coverage_at_target_precision"], 0.0)


if __name__ == "__main__":
    unittest.main()
