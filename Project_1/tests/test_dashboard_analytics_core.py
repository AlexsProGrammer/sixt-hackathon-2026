"""Unit tests for `dashboard.analytics_core` (no Streamlit import)."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import analytics_core  # noqa: E402


class AnalyticsCoreTests(unittest.TestCase):
    def test_no_streamlit_import(self) -> None:
        tree = ast.parse((ROOT / "dashboard" / "analytics_core.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(a.name.startswith("streamlit") for a in node.names))
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertFalse(node.module.startswith("streamlit"))

    def test_break_even_precision(self) -> None:
        self.assertAlmostEqual(analytics_core.break_even_precision(20.0), 0.95238, places=4)
        self.assertAlmostEqual(analytics_core.break_even_precision(100.0), 0.990099, places=4)
        self.assertAlmostEqual(analytics_core.break_even_precision(500.0), 0.998004, places=4)

    def test_verdict_cases(self) -> None:
        self.assertEqual(analytics_core.verdict(1.0, 0.12, 10, 0.99), "full_success")
        self.assertEqual(analytics_core.verdict(0.96, 0.05, 10, 0.99), "partial")
        self.assertEqual(analytics_core.verdict(1.0, 0.0, 0, 0.99), "partial")
        self.assertEqual(analytics_core.verdict(0.90, -0.15, 10, 0.99), "fails")
        self.assertEqual(analytics_core.verdict(None, None, 0, 0.99), "no_gold")

    def test_summarize_curve_and_ece(self) -> None:
        score = {
            "curve": [
                {"threshold": 0.90, "n_fields": 100, "accepted": 50, "wrong": 1, "hallucinated": 0, "precision": 0.98, "coverage": 0.50},
                {"threshold": 0.99, "n_fields": 100, "accepted": 20, "wrong": 0, "hallucinated": 0, "precision": 1.00, "coverage": 0.20},
            ],
            "coverage_at_precision": {"0.99": 0.20},
        }
        sm = analytics_core.summarize_curve(score, 0.99, error_cost=100.0)
        self.assertEqual(sm["verdict"], "full_success")
        self.assertAlmostEqual(sm["avg_precision_curve"], 0.99, places=4)
        self.assertAlmostEqual(sm["net_at_tau"], 0.20, places=4)
        self.assertAlmostEqual(sm["avg_net_curve"], (-0.50 + 0.20) / 2.0, places=4)
        self.assertAlmostEqual(sm["robustness_pct"], 0.50, places=4)

        ece = analytics_core.compute_ece([
            {"count": 10, "mean_conf": 0.9, "precision": 0.8},
            {"count": 10, "mean_conf": 1.0, "precision": 1.0},
        ])
        self.assertAlmostEqual(ece, 0.05, places=4)

    def test_infer_run_profile_precedence(self) -> None:
        b1 = {
            "manifest": {"pipeline": {"uq_method": "k_entropy", "samples": 3}, "models_used": ["m1"], "mode": "llm"},
            "diagnostics": {"d1": {"uq_method": "k1_grounded", "expected_k": 1}},
            "run": {"name": "base_never"},
        }
        p1 = analytics_core.infer_run_profile(b1)
        self.assertEqual(p1["source_of_info"], "manifest")
        self.assertEqual(p1["uq_method"], "k_entropy")
        self.assertEqual(p1["samples"], 3)

        b2 = {"manifest": {}, "diagnostics": {"d1": {"uq_method": "k_agreement_only", "expected_k": 5}}, "run": {"name": "base_never"}}
        p2 = analytics_core.infer_run_profile(b2)
        self.assertEqual(p2["source_of_info"], "diagnostics")
        self.assertEqual(p2["samples"], 5)

        b3 = {"manifest": {}, "diagnostics": {}, "run": {"name": "base_never"}}
        p3 = analytics_core.infer_run_profile(b3)
        self.assertEqual(p3["source_of_info"], "inferred")
        self.assertIn("never", p3["uq_method"])


if __name__ == "__main__":
    unittest.main()
