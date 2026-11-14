"""Unit tests for `dashboard.pipeline_info` (no Streamlit import)."""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import pipeline_info  # noqa: E402
from pipeline import eb_pipeline  # noqa: E402


class PipelineInfoTests(unittest.TestCase):
    def test_no_streamlit_import(self) -> None:
        tree = ast.parse((ROOT / "dashboard" / "pipeline_info.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(a.name.startswith("streamlit") for a in node.names))
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertFalse(node.module.startswith("streamlit"))

    def test_describe_submission_decision(self) -> None:
        dec_path = ROOT / "submission" / "decision.json"
        desc = pipeline_info.describe(str(dec_path))
        self.assertTrue(desc.abstain_all)
        self.assertTrue(any("abstain_all" in w for w in desc.warnings))
        src = pipeline_info.build_mermaid(desc, threshold=0.99)
        self.assertTrue(src.startswith("flowchart"))
        self.assertIn("disabled (abstain all)", src)

    def test_describe_synthetic_v2_and_defaults(self) -> None:
        desc_def = pipeline_info.describe(None)
        self.assertIsNotNone(desc_def.models["A"]["name"])
        self.assertIsNotNone(desc_def.models["B"]["name"])
        mmd_def = pipeline_info.build_mermaid(desc_def, threshold=0.99)
        self.assertIn(desc_def.models["B"]["name"].split("/")[-1], mmd_def)

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dec_v2.json"
            p.write_text(
                json.dumps({
                    "contract_version": 2,
                    "threshold": 0.98,
                    "abstain_all": False,
                    "models": {"A": "vertex_ai/gemini-3.7-flash", "B": "vertex_ai/claude-sonnet-5.5"},
                    "routes": {"cuad": {"pipeline": "cuad", "samples": 3, "uq_method": "k_entropy"}},
                }),
                encoding="utf-8",
            )
            desc_v2 = pipeline_info.describe(str(p))
            self.assertEqual(desc_v2.contract_version, 2)
            self.assertEqual(desc_v2.models["A"]["source"], "decision.json")
            active_routes = [r["route"] for r in desc_v2.routes if r["active"]]
            self.assertEqual(active_routes, ["cuad"])
            mmd = pipeline_info.build_mermaid(desc_v2, threshold=0.98)
            self.assertIn("gemini-3.7-flash", mmd)
            self.assertIn("class R_GOOD inactive;", mmd)


if __name__ == "__main__":
    unittest.main()
