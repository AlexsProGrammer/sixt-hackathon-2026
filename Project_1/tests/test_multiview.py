"""Tests for T09: multi-view agreement with probly, cascade, and report summary."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation import report  # noqa: E402
from pipeline import cuad_pipeline, eb_pipeline  # noqa: E402
from uncertainty.decision import make_prediction  # noqa: E402
from uncertainty.multiview import aggregate_views, should_run_secondary_views  # noqa: E402


def _view(
    view_id: str,
    model: str,
    input_kind: str,
    fields: dict[str, tuple[str, object, float | None]],
    *,
    complete: bool = True,
) -> dict:
    obs_map = {}
    for k, (status, val, conf) in fields.items():
        obs_map[k] = {
            "status": status,
            "value": val,
            "model_confidence": conf,
            "complete": status in ("present", "absent"),
            "evidence": None,
            "reason": "" if status in ("present", "absent") else status,
        }
    return {
        "view_id": view_id,
        "model": model,
        "input_kind": input_kind,
        "fields": obs_map,
        "complete": complete,
        "errors": [] if complete else ["error"],
    }


SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "total": {"type": "number"},
        "flag": {"type": "boolean"},
        "clause": {"type": "string", "x-normalizer": "span"},
        "items": {"type": "array", "items": {"type": "string"}},
    },
}


class MultiViewTests(unittest.TestCase):
    def test_string_case_clusters_together(self):
        v1 = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"company": ("present", "Pine Harbour LLC", 0.95)})
        v2 = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"company": ("present", "  pine   harbour llc ", 0.90)})
        agg = aggregate_views([v1, v2], SCHEMA, {"text": "Pine Harbour LLC"})
        cand = agg["candidates"]["company"]
        self.assertEqual(agg["contract_version"], 3)
        self.assertTrue(cand["eligible"])
        self.assertEqual(cand["value"], "Pine Harbour LLC")
        f = cand["features"]
        self.assertEqual(f["n_views"], 2)
        self.assertEqual(f["n_valid"], 2)
        self.assertEqual(f["n_clusters"], 1)
        self.assertEqual(f["agreement"], 1.0)
        self.assertEqual(f["entropy_nats"], 0.0)
        self.assertEqual(f["entropy_norm"], 0.0)
        self.assertTrue(f["unanimous_nonnull"])
        self.assertEqual(f["families_agreeing"], 2)
        self.assertAlmostEqual(f["model_conf_min"], 0.90)
        self.assertAlmostEqual(f["model_conf_mean"], 0.925)

    def test_number_int_vs_float_clusters_together(self):
        v1 = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"total": ("present", 1234, 0.9)})
        v2 = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"total": ("present", 1234.0, 0.85)})
        agg = aggregate_views([v1, v2], SCHEMA, {"text": "Total is 1,234"})
        cand = agg["candidates"]["total"]
        self.assertTrue(cand["eligible"])
        self.assertEqual(cand["value"], 1234)
        self.assertEqual(cand["features"]["n_clusters"], 1)
        self.assertEqual(cand["features"]["agreement"], 1.0)
        self.assertTrue(cand["features"]["unanimous_nonnull"])

    def test_span_clustering_f1_threshold(self):
        # 10 tokens vs 9 of 10 + 1 different -> 9/10 P, 9/10 R -> F1 = 0.9 >= 0.8 -> one cluster
        s1 = "the party shall not assign this agreement without prior consent"
        s2 = "the party shall not assign this agreement without written consent"  # F1 = 0.9
        v1 = _view("A-text", "vertex_ai/gemini-3.7-flash", "text", {"clause": ("present", s1, 0.9)})
        v2 = _view("B-text", "vertex_ai/claude-sonnet-5.5", "text", {"clause": ("present", s2, 0.85)})
        agg = aggregate_views([v1, v2], SCHEMA, {"text": s1})
        self.assertEqual(agg["candidates"]["clause"]["features"]["n_clusters"], 1)
        self.assertTrue(agg["candidates"]["clause"]["features"]["unanimous_nonnull"])

        # F1 = 0.5 < 0.8 -> two clusters, tie -> ineligible
        t1 = "alpha beta gamma delta"
        t2 = "alpha beta epsilon zeta"  # 2/4 = 0.5
        v3 = _view("A-text", "vertex_ai/gemini-3.7-flash", "text", {"clause": ("present", t1, 0.9)})
        v4 = _view("B-text", "vertex_ai/claude-sonnet-5.5", "text", {"clause": ("present", t2, 0.85)})
        agg2 = aggregate_views([v3, v4], SCHEMA, {"text": t1})
        cand2 = agg2["candidates"]["clause"]
        self.assertEqual(cand2["features"]["n_clusters"], 2)
        self.assertFalse(cand2["eligible"])
        self.assertEqual(cand2["reason"], "tie")
        self.assertAlmostEqual(cand2["features"]["entropy_nats"], math.log(2))
        self.assertAlmostEqual(cand2["features"]["entropy_norm"], 1.0)

    def test_one_view_errored_excluded_not_unanimous(self):
        v1 = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"company": ("present", "Acme Corp", 0.95)})
        v2 = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"company": ("error", None, None)}, complete=False)
        agg = aggregate_views([v1, v2], SCHEMA, {"text": "Acme Corp"})
        cand = agg["candidates"]["company"]
        self.assertTrue(cand["eligible"])
        self.assertEqual(cand["value"], "Acme Corp")
        self.assertEqual(cand["features"]["n_views"], 2)
        self.assertEqual(cand["features"]["n_valid"], 1)
        self.assertFalse(cand["features"]["unanimous_nonnull"])
        self.assertEqual(cand["features"]["families_agreeing"], 1)
        self.assertEqual(cand["features"]["entropy_norm"], 0.0)

    def test_entropy_values(self):
        # [1, 0] -> entropy 0
        v1 = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"company": ("present", "Acme", 0.9)})
        v2 = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"company": ("present", "Acme", 0.8)})
        agg1 = aggregate_views([v1, v2], SCHEMA)
        self.assertEqual(agg1["candidates"]["company"]["features"]["entropy_nats"], 0.0)
        self.assertEqual(agg1["candidates"]["company"]["features"]["entropy_norm"], 0.0)

        # [0.5, 0.5] -> entropy log(2), normalised to 1.0
        v3 = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"company": ("present", "Beta", 0.8)})
        agg2 = aggregate_views([v1, v3], SCHEMA)
        self.assertAlmostEqual(agg2["candidates"]["company"]["features"]["entropy_nats"], math.log(2))
        self.assertAlmostEqual(agg2["candidates"]["company"]["features"]["entropy_norm"], 1.0)

    def test_order_independence_and_priority(self):
        v_gem_pdf = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"company": ("present", "Acme Corp.", 0.95)})
        v_cla_pdf = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"company": ("present", "acme corp.", 0.90)})
        v_gem_txt = _view("A-text", "vertex_ai/gemini-3.7-flash", "text", {"company": ("present", "ACME CORP.", 0.85)})
        agg_fwd = aggregate_views([v_gem_pdf, v_cla_pdf, v_gem_txt], SCHEMA)
        agg_rev = aggregate_views([v_gem_txt, v_cla_pdf, v_gem_pdf], SCHEMA)
        self.assertEqual(agg_fwd, agg_rev)
        # Representative comes from gemini-PDF
        self.assertEqual(agg_fwd["candidates"]["company"]["value"], "Acme Corp.")
        # 2 distinct families (gemini, claude) across 3 views
        self.assertEqual(agg_fwd["candidates"]["company"]["features"]["families_agreeing"], 2)

    def test_diagnostics_truncation_and_make_prediction(self):
        long_str = "x" * 260
        v1 = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"company": ("present", long_str, 0.92)})
        v2 = _view("B-pdf", "vertex_ai/claude-sonnet-5.5", "pdf", {"company": ("present", long_str, 0.88)})
        agg = aggregate_views([v1, v2], SCHEMA)
        members = agg["diagnostics"]["per_field"]["company"]["members"]
        self.assertEqual(len(members), 2)
        self.assertEqual(len(members[0]["value"]), 200)
        self.assertTrue(members[0]["value"].endswith("..."))

        preds = make_prediction(agg, SCHEMA, method="k_agreement_conf")
        self.assertAlmostEqual(preds["company"]["confidence"], 0.88)
        preds_ent = make_prediction(agg, SCHEMA, method="k_entropy")
        self.assertAlmostEqual(preds_ent["company"]["confidence"], 1.0)

    def test_cascade_gate_and_pipeline(self):
        rec = {"doc_id": "d1", "source_dataset": "extractbench", "schema": {"title": "FormX", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}}}
        v_null = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"a": ("absent", None, 0.9), "b": ("present", "hi", 0.9)})
        v_hit = _view("A-pdf", "vertex_ai/gemini-3.7-flash", "pdf", {"a": ("present", "val", 0.9), "b": ("absent", None, 0.9)})

        # Without selector -> always run secondary views
        self.assertTrue(should_run_secondary_views(v_null, rec, None))
        # With selector [("FormX", "a")] -> skip when 'a' is null, run when 'a' is non-null
        self.assertFalse(should_run_secondary_views(v_null, rec, [("FormX", "a")]))
        self.assertTrue(should_run_secondary_views(v_hit, rec, [("FormX", "a")]))

        # Check cuad_pipeline.run_views with cascade=True
        calls = []

        def fake_run_text(view_id, model, r, text, ctx, cfg):
            calls.append(view_id)
            return v_null

        class Ctx:
            cfg = {}
            cache = None
            state = None
            cuad = cuad_pipeline.resolve_cuad({
                "views": ["A-text", "B-text"],
                "cascade": True,
                "candidate_cells": [("cuad", "a")],
            })

        rec_cuad = {"doc_id": "c1", "source_dataset": "cuad", "schema": rec["schema"]}
        with patch.object(cuad_pipeline, "run_text_view", side_effect=fake_run_text):
            out = cuad_pipeline.run_views(rec_cuad, {"route": "cuad", "text": "contract text"}, Ctx())
        self.assertEqual(calls, ["A-text"])
        self.assertEqual(len(out), 1)

    def test_report_multiview_summary(self):
        rows = [
            {"doc_id": "d1", "field": "f1", "kind": "string", "pred_present": True, "outcome": "correct",
             "unanimous_nonnull": True, "families_agreeing": 2},
            {"doc_id": "d2", "field": "f1", "kind": "string", "pred_present": True, "outcome": "wrong",
             "unanimous_nonnull": False, "families_agreeing": 1},
            {"doc_id": "d3", "field": "f1", "kind": "string", "pred_present": True, "outcome": "wrong",
             "unanimous_nonnull": True, "families_agreeing": 2},
        ]
        mv = report.multiview_summary(rows)
        self.assertIsNotNone(mv)
        self.assertEqual(mv["wrong_total"], 2)
        self.assertEqual(mv["wrong_both_families_agree"], 1)
        self.assertAlmostEqual(mv["wrong_both_families_share"], 0.5)


if __name__ == "__main__":
    unittest.main()
