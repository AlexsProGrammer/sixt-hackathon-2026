"""Unit tests for `dashboard.data` on fake run folders (no Streamlit import)."""
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

from dashboard import data  # noqa: E402
from evaluation import registry  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class DashboardDataTests(unittest.TestCase):
    def test_data_module_does_not_import_streamlit(self) -> None:
        tree = ast.parse((ROOT / "dashboard" / "data.py").read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertFalse(any(m == "streamlit" or m.startswith("streamlit.") for m in imported))

    def test_fake_run_bundle_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "20261114-120000-demo-abc123"
            run_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text(
                json.dumps({
                    "run_id": "20261114-120000-demo-abc123",
                    "name": "demo",
                    "split": "dev",
                    "created_at": "2026-11-14T12:00:00",
                    "status": "complete",
                    "tags": ["test"],
                    "summary": {"n_docs": 1, "n_fields": 4, "accepted": 2, "net_saving_pct_e100": 0.25},
                }),
                encoding="utf-8",
            )
            (run_dir / "manifest.json").write_text(
                json.dumps({"run_id": "abc123", "n_written": 1, "requests": 1, "cache_hits": 0}),
                encoding="utf-8",
            )
            (run_dir / "score.json").write_text(
                json.dumps({"curve": [{"threshold": 0.99, "n_fields": 4, "accepted": 2, "correct": 2, "wrong": 0, "hallucinated": 0, "precision": 1.0, "coverage": 0.67}]}),
                encoding="utf-8",
            )
            _write_jsonl(run_dir / "preds.jsonl", [{
                "doc_id": "eb:doc1",
                "fields": {
                    "f_green": {"value": "Acme", "confidence": 0.995},
                    "f_red": {"value": "WrongCo", "confidence": 0.995},
                    "f_yellow": {"value": "42", "confidence": 0.70},
                    "f_grey": {"value": None, "confidence": 0.0},
                },
            }])
            _write_jsonl(run_dir / "diagnostics.jsonl", [{
                "doc_id": "eb:doc1",
                "diagnostics": {
                    "per_field": {
                        "f_green": {"reason": "whitelist", "grounded": True},
                        "f_yellow": {"reason": "low_conf"},
                    }
                },
            }])
            _write_jsonl(run_dir / "samples.jsonl", [{
                "doc_id": "eb:doc1",
                "samples": [{"view": "A-pdf", "fields": {"f_green": {"value": "Acme", "status": "present", "model_confidence": 0.99}}}],
            }])
            _write_jsonl(run_dir / "gold.jsonl", [{
                "doc_id": "eb:doc1",
                "source_dataset": "extractbench",
                "schema": {"properties": {"f_green": {"type": "string"}, "f_red": {"type": "string"}, "f_yellow": {"type": "string"}, "f_grey": {"type": "string"}}},
                "gold": {"f_green": "Acme", "f_red": "RightCo", "f_yellow": "42", "f_grey": None},
            }])
            _write_jsonl(run_dir / "fields.jsonl", [
                {"doc_id": "eb:doc1", "family": "FormX", "route": "pdf_vision", "kind": "string", "field": "f_green", "pred_value": "Acme", "pred_present": True, "conf_out": 0.995, "grounded_text": True, "grounded_ocr": None, "cross_view_agree": True, "gold_present": True, "outcome": "correct"},
                {"doc_id": "eb:doc1", "family": "FormX", "route": "pdf_vision", "kind": "string", "field": "f_red", "pred_value": "WrongCo", "pred_present": True, "conf_out": 0.995, "grounded_text": False, "grounded_ocr": None, "cross_view_agree": False, "gold_present": True, "outcome": "wrong"},
                {"doc_id": "eb:doc1", "family": "FormX", "route": "pdf_vision", "kind": "number", "field": "f_yellow", "pred_value": "42", "pred_present": True, "conf_out": 0.70, "grounded_text": False, "grounded_ocr": None, "cross_view_agree": None, "gold_present": True, "outcome": "correct"},
                {"doc_id": "eb:doc1", "family": "FormX", "route": "pdf_vision", "kind": "string", "field": "f_grey", "pred_value": None, "pred_present": False, "conf_out": None, "grounded_text": False, "grounded_ocr": None, "cross_view_agree": None, "gold_present": False, "outcome": "true_null"},
            ])
            registry.append_index(run_dir)

            idx = data.load_index(runs_dir)
            self.assertEqual(len(idx), 1)
            self.assertEqual(idx[0]["run_id"], "20261114-120000-demo-abc123")
            self.assertEqual(data.list_run_ids(runs_dir), ["20261114-120000-demo-abc123"])

            bundle = data.load_run_bundle("20261114-120000-demo-abc123", runs_dir=runs_dir)
            self.assertIn("eb:doc1", bundle["preds"])
            self.assertEqual(len(bundle["fields"]), 4)

            rows = data.build_doc_field_rows("eb:doc1", bundle, threshold=0.99)
            by_f = {r["field"]: r for r in rows}
            self.assertEqual(by_f["f_green"]["color"], "green")
            self.assertEqual(by_f["f_green"]["decision"], "booked")
            self.assertIn("grounded_text", by_f["f_green"]["evidence_flags"])
            self.assertIn("views_agree", by_f["f_green"]["evidence_flags"])
            self.assertEqual(len(by_f["f_green"]["per_view"]), 1)
            self.assertEqual(by_f["f_red"]["color"], "red")
            self.assertEqual(by_f["f_yellow"]["color"], "yellow")
            self.assertEqual(by_f["f_yellow"]["decision"], "to human")
            self.assertEqual(by_f["f_grey"]["color"], "grey")

            rel = data.compute_reliability_bins(bundle["fields"])
            self.assertEqual(len(rel), 2)
            ff = data.compute_family_field_stats(bundle["fields"], threshold=0.99)
            self.assertEqual(len(ff), 4)
            rt, kd = data.compute_route_kind_stats(bundle["fields"], threshold=0.99)
            self.assertEqual(rt[0]["booked"], 2)
            self.assertEqual(kd[0]["kind"], "number")

    def test_reviews_and_stratified_sampling_and_save_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rev_path = Path(tmp) / "reviews.jsonl"
            data.append_review({"run_id": "r1", "doc_id": "d1", "field": "f1", "action": "accept", "value": "X", "reviewer": "alice"}, reviews_path=rev_path)
            data.append_review({"run_id": "r1", "doc_id": "d1", "field": "f1", "action": "edit", "value": "Y", "reviewer": "alice"}, reviews_path=rev_path)
            revs = data.load_reviews(rev_path)
            self.assertEqual(len(revs), 2)
            latest = data.latest_reviews_map(revs, run_id="r1")
            self.assertEqual(latest[("d1", "f1")]["action"], "edit")
            self.assertEqual(latest[("d1", "f1")]["value"], "Y")

            recs = [
                {"doc_id": f"eb:{i}", "source_dataset": "extractbench"} for i in range(5)
            ] + [
                {"doc_id": f"cuad:{i}", "source_dataset": "cuad"} for i in range(5)
            ]
            sampled = data.sample_stratified_records(recs, 4, seed=7)
            self.assertEqual(len(sampled), 4)
            sources = [r["source_dataset"] for r in sampled]
            self.assertEqual(sources.count("extractbench"), 2)
            self.assertEqual(sources.count("cuad"), 2)

            # Save a session run to registry
            sess_dir = Path(tmp) / "sess" / "20261114-120500-sess-111111"
            sess_dir.mkdir(parents=True)
            (sess_dir / "run.json").write_text(json.dumps({"run_id": "20261114-120500-sess-111111", "name": "sess", "split": "dev", "status": "complete", "tags": ["session"]}), encoding="utf-8")
            runs_dir = Path(tmp) / "runs"
            dest = data.save_session_run_to_registry({"run_id": "20261114-120500-sess-111111", "run_dir": str(sess_dir)}, runs_dir=runs_dir)
            self.assertTrue((dest / "run.json").is_file())
            self.assertEqual(len(data.load_index(runs_dir)), 1)


if __name__ == "__main__":
    unittest.main()
