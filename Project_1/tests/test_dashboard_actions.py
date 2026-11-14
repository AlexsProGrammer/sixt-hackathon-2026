"""Unit tests for `dashboard.actions` (no Streamlit import)."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import actions  # noqa: E402


class ActionsTests(unittest.TestCase):
    def test_no_streamlit_import(self) -> None:
        tree = ast.parse((ROOT / "dashboard" / "actions.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(a.name.startswith("streamlit") for a in node.names))
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertFalse(node.module.startswith("streamlit"))

    def test_rejects_unsafe_run_ids_and_unknown_actions(self) -> None:
        with self.assertRaises(ValueError):
            actions.run_action("unknown_action", {})
        for bad in ("../x", "a; rm -rf /", "/etc/passwd", ""):
            with self.assertRaises(ValueError):
                actions.run_action("field_table", {"run_id": bad, "dry_run": True})

    def test_dry_run_argv_shapes(self) -> None:
        r1 = actions.run_action("field_table", {"run_id": "20261113-demo-123456", "dry_run": True})
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["argv"][1:], ["-m", "evaluation.field_table", "20261113-demo-123456"])

        r2 = actions.run_action("score_run", {"run_id": "20261113-demo-123456", "threshold": 0.99, "dry_run": True})
        self.assertEqual(r2["argv"][1:], ["-m", "evaluation.registry", "score", "20261113-demo-123456", "--threshold", "0.9900"])

        r3 = actions.run_action("diff", {"run_a": "run_a_1", "run_b": "run_b_2", "dry_run": True})
        self.assertEqual(r3["argv"][1:], ["-m", "evaluation.report", "--run", "run_b_2", "--diff", "run_a_1", "run_b_2"])


if __name__ == "__main__":
    unittest.main()
