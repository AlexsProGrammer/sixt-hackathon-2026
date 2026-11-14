"""Tests for T10 selector: whitelist, evidence rules, decision v2 hash check, audit guard, Gate G1."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.select_threshold import audit_selector, decide_selector, freeze_selector, sha256_obj  # noqa: E402
from evaluation.train_selector import build_selector, load_training_rows  # noqa: E402
from uncertainty.contracts import ContractError  # noqa: E402
from uncertainty.decision import make_prediction  # noqa: E402


def _load_extract4():
    spec = importlib.util.spec_from_file_location("extract4_t10_test", ROOT / "4_extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _agg(cands: dict, version: int = 3) -> dict:
    return {"contract_version": version, "candidates": cands, "diagnostics": {}}


def _selector(cells: list[dict], **extra) -> dict:
    return {
        "selector_version": 1,
        "declared_threshold": 0.99,
        "trained_on": {"run_ids": ["r1"], "split": "fit", "fingerprint": {}},
        "cells": cells,
        "kind_rules": {"json": "never", "boolean": "views_only"},
        "calibrator": None,
        **extra,
    }


def _row(doc_id: str, group: str, field: str, *, source="extractbench", family="FamA",
         kind="string", pred_value="val", pred_present=True, grounded_text=True,
         cross_view_agree=None, n_views=1, agreement=1.0, outcome="correct") -> dict:
    return {
        "doc_id": doc_id,
        "group": group,
        "source": source,
        "family": family,
        "field": field,
        "kind": kind,
        "pred_value": pred_value if pred_present else None,
        "pred_present": pred_present,
        "grounded_text": grounded_text,
        "grounded_ocr": None,
        "cross_view_agree": cross_view_agree,
        "n_views": n_views,
        "agreement": agreement,
        "families_agreeing": 1,
        "gold_present": outcome in ("correct", "wrong", "missed"),
        "match": outcome == "correct",
        "outcome": outcome,
    }


class SelectorDecisionTests(unittest.TestCase):
    def test_non_whitelisted_field_gets_null_zero(self):
        schema = {"properties": {"uic_no": {"type": "string"}, "other": {"type": "string"}}}
        agg = _agg({
            "uic_no": {"value": "1234", "eligible": True, "features": {"grounded_text": True}},
            "other": {"value": "abc", "eligible": True, "features": {"grounded_text": True}},
        })
        sel = _selector([{
            "source": "extractbench", "family": "RRCH5", "field": "uic_no",
            "require": {"evidence": "grounded_text", "min_families": 1},
        }])
        pred = make_prediction(agg, schema, method="selector", selector=sel,
                               record_meta={"source": "extractbench", "family": "RRCH5"})
        self.assertEqual(pred["uic_no"], {"value": "1234", "confidence": 1.0})
        self.assertEqual(pred["other"], {"value": None, "confidence": 0.0})

    def test_json_kind_never_booked_even_if_whitelisted(self):
        schema = {"properties": {"items": {"type": "array"}}}
        agg = _agg({
            "items": {"value": [{"a": 1}], "eligible": True, "features": {"grounded_text": True, "n_views": 2, "agreement": 1.0}},
        })
        sel = _selector([{
            "source": "extractbench", "family": "RRCH5", "field": "items",
            "require": {"evidence": "none", "min_families": 1},
        }])
        pred = make_prediction(agg, schema, method="selector", selector=sel,
                               record_meta={"source": "extractbench", "family": "RRCH5"})
        self.assertEqual(pred["items"], {"value": None, "confidence": 0.0})

    def test_require_evidence_condition_enforced(self):
        schema = {"properties": {"a": {"type": "string"}, "b": {"type": "string"}, "c": {"type": "string"}}}
        agg = _agg({
            "a": {"value": "x", "eligible": True, "features": {"grounded_text": False, "n_views": 1, "agreement": 1.0}},
            "b": {"value": "y", "eligible": True, "features": {"grounded_text": False, "n_views": 2, "agreement": 1.0, "cross_view_agree": True}},
            "c": {"value": "z", "eligible": True, "features": {"grounded_text": True, "n_views": 1, "agreement": 1.0, "families_agreeing": 1}},
        })
        sel = _selector([
            {"source": "extractbench", "family": "F", "field": "a", "require": {"evidence": "grounded_text", "min_families": 1}},
            {"source": "extractbench", "family": "F", "field": "b", "require": {"evidence": "grounded_text|views_agree", "min_families": 1}},
            {"source": "extractbench", "family": "F", "field": "c", "require": {"evidence": "grounded_text", "min_families": 2}},
        ])
        pred = make_prediction(agg, schema, method="selector", selector=sel,
                               record_meta={"source": "extractbench", "family": "F"})
        self.assertEqual(pred["a"], {"value": None, "confidence": 0.0})
        self.assertEqual(pred["b"], {"value": "y", "confidence": 1.0})
        self.assertEqual(pred["c"], {"value": None, "confidence": 0.0})

    def test_missing_selector_or_meta_raises_contract_error(self):
        schema = {"properties": {"a": {"type": "string"}}}
        agg = _agg({"a": {"value": "x", "eligible": True, "features": {"grounded_text": True}}})
        with self.assertRaises(ContractError):
            make_prediction(agg, schema, method="selector", selector=None, record_meta={"source": "eb", "family": "F"})
        with self.assertRaises(ContractError):
            make_prediction(agg, schema, method="selector", selector=_selector([]), record_meta=None)


class DecisionV2HashTests(unittest.TestCase):
    def test_selector_hash_mismatch_raises_system_exit(self):
        ext4 = _load_extract4()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sel_path = root / "selector.json"
            sel_obj = _selector([])
            sel_path.write_text(json.dumps(sel_obj), encoding="utf-8")

            pipe = {
                "workers": 1, "samples": 1, "temperature": 0.7,
                "chunk_chars": 45000, "overlap_chars": 3000,
                "batch_size": 10, "uq_method": "selector", "sampling": "mixed",
            }
            dec_path = root / "decision.json"
            dec_obj = {
                "contract_version": 2,
                "abstain_all": False,
                "threshold": 0.99,
                "method": "selector",
                "selector_path": str(sel_path),
                "selector_sha256": "0" * 64,  # mismatch
                "pipeline": pipe,
                "pipeline_sha256": ext4.sha256_obj(pipe),
            }
            dec_path.write_text(json.dumps(dec_obj), encoding="utf-8")
            with self.assertRaises(SystemExit):
                ext4.load_decision(str(dec_path))

            # Matching hash succeeds and attaches _selector
            dec_obj["selector_sha256"] = hashlib.sha256(sel_path.read_bytes()).hexdigest()
            dec_path.write_text(json.dumps(dec_obj), encoding="utf-8")
            loaded = ext4.load_decision(str(dec_path))
            self.assertEqual(loaded["_selector"]["selector_version"], 1)


class TrainSelectorGuardTests(unittest.TestCase):
    def test_training_never_uses_audit_split(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            splits_dir = root / "splits"
            runs_dir = root / "runs"
            splits_dir.mkdir()
            runs_dir.mkdir()

            manifest = {
                "manifest_version": 1,
                "splits": {
                    "fit": {"doc_ids": ["d1", "d2"]},
                    "select": {"doc_ids": ["d3"]},
                    "audit": {"doc_ids": ["d_audit"]},
                    "audit2": {"doc_ids": ["d_audit2"]},
                },
            }
            (splits_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            # 1. Requesting --split audit fails immediately
            with self.assertRaises(ValueError):
                load_training_rows(["r1"], split="audit", runs_dir=runs_dir, splits_dir=splits_dir)

            # 2. A run tagged split=audit fails
            r_aud = runs_dir / "20261114-000000-aud-111111"
            r_aud.mkdir()
            (r_aud / "run.json").write_text(json.dumps({"run_id": "aud1", "split": "audit"}), encoding="utf-8")
            (r_aud / "fields.jsonl").write_text(json.dumps(_row("d1", "g1", "f1")) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_training_rows(["aud-111111"], split="fit", runs_dir=runs_dir, splits_dir=splits_dir)

            # 3. Even with split=None, a field table containing an audit doc_id fails
            r_mix = runs_dir / "20261114-000000-mix-222222"
            r_mix.mkdir()
            (r_mix / "run.json").write_text(json.dumps({"run_id": "mix1", "split": "dev"}), encoding="utf-8")
            (r_mix / "fields.jsonl").write_text(
                json.dumps(_row("d1", "g1", "f1")) + "\n" + json.dumps(_row("d_audit", "g2", "f1")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_training_rows(["mix-222222"], split=None, runs_dir=runs_dir, splits_dir=splits_dir)

    def test_build_selector_admits_zero_error_cells_only(self):
        rows = [
            _row("d1", "g1", "good", outcome="correct"),
            _row("d2", "g2", "good", outcome="correct"),
            _row("d3", "g3", "good", outcome="correct"),
            _row("d4", "g4", "good", outcome="correct"),
            _row("d1", "g1", "bad", outcome="correct"),
            _row("d2", "g2", "bad", outcome="wrong"),
            _row("d3", "g3", "bad", outcome="correct"),
            _row("d4", "g4", "bad", outcome="correct"),
            _row("d1", "g1", "tbl", kind="json", outcome="correct"),
            _row("d2", "g2", "tbl", kind="json", outcome="correct"),
            _row("d3", "g3", "tbl", kind="json", outcome="correct"),
            _row("d4", "g4", "tbl", kind="json", outcome="correct"),
        ]
        sel = build_selector(rows, min_n=3, min_groups=2, evidence="grounded_text")
        fields = [c["field"] for c in sel["cells"]]
        self.assertEqual(fields, ["good"])
        # In LOGO, holding out g2 leaves 3 error-free rows for `bad`, so LOGO books 4 correct + 1 wrong = 5
        self.assertEqual(sel["logo_summary"]["accepted"], 5)
        self.assertEqual(sel["logo_summary"]["correct"], 4)
        self.assertEqual(sel["logo_summary"]["wrong"], 1)


class GateG1Tests(unittest.TestCase):
    def _manifest(self, run_id: str) -> dict:
        pipe = {
            "workers": 1, "samples": 1, "temperature": 0.7,
            "chunk_chars": 45000, "overlap_chars": 3000,
            "batch_size": 10, "uq_method": "k1_grounded", "sampling": "mixed",
        }
        return {"run_id": run_id, "run_complete": True, "fingerprint": {"x": 1}, "pipeline": pipe}

    def test_gate_g1_requires_300_booked_and_3_families(self):
        frozen = {"status": "frozen", "method": "selector", "threshold": 0.99, "dev_select": {"net_saving_pct": 0.05}}
        sel_man = self._manifest("sel-1")
        aud_man = self._manifest("aud-1")

        # Fails when accepted < 300
        aud_low = {"audit": {"net_saving_pct": 0.05, "accepted": 250, "families_with_booked": 4, "wilson_diagnostic": {}}}
        dec_low = decide_selector(frozen, aud_low, selector_path="s.json", selector_sha256="abc",
                                  select_manifest=sel_man, audit_manifest=aud_man)
        self.assertTrue(dec_low["abstain_all"])
        self.assertFalse(dec_low["criteria"]["audit_accepted_at_least_min"])

        # Fails when families < 3
        aud_fam = {"audit": {"net_saving_pct": 0.05, "accepted": 350, "families_with_booked": 2, "wilson_diagnostic": {}}}
        dec_fam = decide_selector(frozen, aud_fam, selector_path="s.json", selector_sha256="abc",
                                  select_manifest=sel_man, audit_manifest=aud_man)
        self.assertTrue(dec_fam["abstain_all"])
        self.assertFalse(dec_fam["criteria"]["audit_families_at_least_min"])

        # Passes Gate G1
        aud_ok = {"audit": {"net_saving_pct": 0.05, "accepted": 320, "families_with_booked": 3, "wilson_diagnostic": {}}}
        dec_ok = decide_selector(frozen, aud_ok, selector_path="s.json", selector_sha256="abc",
                                 select_manifest=sel_man, audit_manifest=aud_man)
        self.assertEqual(dec_ok["contract_version"], 2)
        self.assertFalse(dec_ok["abstain_all"])
        self.assertEqual(dec_ok["method"], "selector")
        self.assertEqual(dec_ok["selector_sha256"], "abc")


if __name__ == "__main__":
    unittest.main()
