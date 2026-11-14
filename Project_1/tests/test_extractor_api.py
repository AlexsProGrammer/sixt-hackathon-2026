"""Tests for pipeline.extractor library API and decision v2 (T11)."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import extractor


def _selector_obj(cells=None):
    return {
        "selector_version": 1,
        "declared_threshold": 0.99,
        "kind_rules": {"json": "never", "boolean": "views_only"},
        "cells": cells or [],
    }


def _write_selector(root: Path, cells=None) -> tuple[Path, str]:
    p = root / "selector.json"
    data = json.dumps(_selector_obj(cells)).encode("utf-8")
    p.write_bytes(data)
    return p, hashlib.sha256(data).hexdigest()


class DecisionLoaderTests(unittest.TestCase):
    def test_v1_and_v2_decisions_load(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sel_path, sel_sha = _write_selector(root)

            v1 = root / "v1.json"
            v1.write_text(json.dumps({
                "contract_version": 1,
                "abstain_all": True,
                "threshold": 1.0,
                "method": "all_abstain",
            }), encoding="utf-8")
            d1 = extractor.load_decision(v1)
            self.assertEqual(d1["contract_version"], 1)
            self.assertTrue(d1["abstain_all"])

            v2 = root / "v2.json"
            v2.write_text(json.dumps({
                "contract_version": 2,
                "abstain_all": False,
                "threshold": 0.99,
                "routes": {
                    "cuad": {"pipeline": "cuad", "views": ["A", "B"], "prompt": "cuad-v1"},
                    "pdf_text_good": {"pipeline": "eb", "views": ["A-pdf", "B-pdf", "A-text"]},
                    "pdf_corrupted": {"pipeline": "abstain"},
                },
                "models": {"A": "mock-a", "B": "mock-b"},
                "selector": {"path": str(sel_path), "sha256": sel_sha},
                "cascade": True,
            }), encoding="utf-8")
            d2 = extractor.load_decision(v2)
            self.assertEqual(d2["contract_version"], 2)
            self.assertEqual(d2["_selector"]["selector_version"], 1)
            self.assertEqual(d2["_selector_sha256"], sel_sha)

    def test_unknown_keys_and_selector_sha_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sel_path, sel_sha = _write_selector(root)

            bad_key = root / "bad_key.json"
            bad_key.write_text(json.dumps({
                "contract_version": 2,
                "abstain_all": True,
                "threshold": 0.99,
                "unexpected_field": 123,
            }), encoding="utf-8")
            with self.assertRaises(SystemExit):
                extractor.load_decision(bad_key)

            bad_sha = root / "bad_sha.json"
            bad_sha.write_text(json.dumps({
                "contract_version": 2,
                "abstain_all": False,
                "threshold": 0.99,
                "routes": {"legacy_text": {"pipeline": "legacy_text"}},
                "selector": {"path": str(sel_path), "sha256": "f" * 64},
            }), encoding="utf-8")
            with self.assertRaises(SystemExit):
                extractor.load_decision(bad_sha)

            # Verify valid sha works
            good = root / "good.json"
            good.write_text(json.dumps({
                "contract_version": 2,
                "abstain_all": False,
                "threshold": 0.99,
                "routes": {"legacy_text": {"pipeline": "legacy_text"}},
                "selector": {"path": str(sel_path), "sha256": sel_sha},
            }), encoding="utf-8")
            self.assertEqual(extractor.load_decision(good)["_selector_sha256"], sel_sha)

    def test_model_env_override_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sel_path, sel_sha = _write_selector(root)
            dec_path = root / "dec.json"
            dec_obj = {
                "contract_version": 2,
                "abstain_all": False,
                "threshold": 0.99,
                "routes": {"legacy_text": {"pipeline": "legacy_text"}},
                "models": {"A": "frozen-model"},
                "selector": {"path": str(sel_path), "sha256": sel_sha},
            }
            dec_path.write_text(json.dumps(dec_obj), encoding="utf-8")

            env = {
                "LLM_BASE_URL": "http://127.0.0.1:9999/v1",
                "LLM_API_KEY": "sk-test",
                "LLM_MODEL": "other-model",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with self.assertRaises(SystemExit):
                    extractor.load_config(dec_path)

                dec_obj["allow_model_env_override"] = True
                dec_path.write_text(json.dumps(dec_obj), encoding="utf-8")
                cfg = extractor.load_config(dec_path)
                self.assertEqual(cfg.cfg["LLM_MODEL"], "other-model")


class ExtractorApiTests(unittest.TestCase):
    def test_v2_route_dispatch_and_progress_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sel_path, sel_sha = _write_selector(root)
            dec_path = root / "dec.json"
            dec_path.write_text(json.dumps({
                "contract_version": 2,
                "abstain_all": False,
                "threshold": 0.99,
                "routes": {
                    "cuad": {"pipeline": "cuad", "views": ["A"], "prompt": "cuad-v1"},
                    "pdf_text_good": {"pipeline": "eb", "views": ["A-pdf"]},
                    "pdf_corrupted": {"pipeline": "abstain"},
                },
                "models": {"A": "mock-model-a", "B": "mock-model-b"},
                "selector": {"path": str(sel_path), "sha256": sel_sha},
                "cascade": True,
            }), encoding="utf-8")

            inp = root / "in.jsonl"
            recs = [
                {"doc_id": "cuad:1", "source_dataset": "cuad", "family": "cuad",
                 "schema": {"properties": {"Parties": {"type": "string", "x-normalizer": "span"}}},
                 "pages": [], "text": "This Agreement is between Alpha Inc. and Beta LLC."},
                {"doc_id": "eb:good", "source_dataset": "extractbench", "family": "F1",
                 "schema": {"properties": {"f1": {"type": "string"}}},
                 "pages": ["doc1.pdf"], "text": "Invoice total 100"},
                {"doc_id": "eb:bad", "source_dataset": "extractbench", "family": "F1",
                 "schema": {"properties": {"f1": {"type": "string"}}},
                 "pages": ["bad.pdf"], "text": ""},
            ]
            inp.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
            out = root / "out.jsonl"

            env = {
                "LLM_BASE_URL": "http://127.0.0.1:9999/v1",
                "LLM_API_KEY": "sk-test",
                "LLM_MODEL": "mock-model-a",
                "EXTRACT_SKIP_DOTENV": "1",
            }

            def fake_route(rec, data_dir, text=None):
                if rec["doc_id"] == "cuad:1":
                    return {"route": "cuad", "text_source": "cuad", "quality": 1.0,
                            "quality_features": {}, "text": rec["text"], "ocr": None}
                if rec["doc_id"] == "eb:good":
                    return {"route": "pdf_text_good", "text_source": "pdftotext", "quality": 0.9,
                            "quality_features": {}, "text": rec["text"], "ocr": None}
                return {"route": "pdf_corrupted", "text_source": "none", "quality": 0.0,
                        "quality_features": {}, "text": None, "ocr": None}

            def fake_cuad(rec, routed, ctx):
                ctx.state.bump("requests")
                ctx.state.bump_model("requests", "mock-model-a")
                return {
                    "fields": {"Parties": {"value": None, "confidence": 0.0}},
                    "diagnostics": {"route": "cuad", "text_source": "cuad", "prompt_version": "cuad-v1",
                                    "views": [{"view_id": "A-text", "model": "mock-model-a", "input_kind": "text",
                                               "complete": True, "errors": []}]},
                    "job_failures": [],
                    "samples": [],
                }

            def fake_eb(rec, routed, ctx, data_dir=None):
                ctx.state.bump("requests")
                ctx.state.bump_model("requests", "mock-model-a")
                return {
                    "fields": {"f1": {"value": None, "confidence": 0.0}},
                    "diagnostics": {"route": "pdf_text_good", "text_source": "pdftotext", "prompt_version": "eb-v1",
                                    "views": [{"view_id": "A-pdf", "model": "mock-model-a", "input_kind": "pdf",
                                               "complete": True, "errors": []}]},
                    "job_failures": [],
                    "samples": [],
                }

            progress_calls = []
            with mock.patch.dict(os.environ, env, clear=False), \
                 mock.patch.object(extractor, "full_text", side_effect=lambda rec, d=None: rec.get("text") or None), \
                 mock.patch.object(extractor.router, "route", side_effect=fake_route), \
                 mock.patch.object(extractor.cuad_pipeline, "extract_document", side_effect=fake_cuad) as m_cuad, \
                 mock.patch.object(extractor.eb_pipeline, "extract_document", side_effect=fake_eb) as m_eb, \
                 mock.patch.object(extractor, "load_cuad", return_value={}):
                cfg = extractor.load_config(dec_path, no_cache=True)
                res = extractor.run_file(
                    inp, out, cfg,
                    progress=lambda done, total, doc_id, doc_res: progress_calls.append((done, total, doc_id, doc_res["route"])),
                )

            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(m_cuad.call_count, 1)
            self.assertEqual(m_eb.call_count, 1)
            self.assertEqual(progress_calls, [
                (1, 3, "cuad:1", "cuad"),
                (2, 3, "eb:good", "pdf_text_good"),
                (3, 3, "eb:bad", "pdf_corrupted"),
            ])
            man = res["manifest"]
            self.assertEqual(man["routes_used"], {"cuad": 1, "pdf_text_good": 1, "pdf_corrupted": 1})
            self.assertEqual(man["requests_by_model"], {"mock-model-a": 2})
            self.assertEqual(man["selector_sha256"], sel_sha)
            self.assertEqual(sorted(man["input_kinds"]), ["pdf", "text"])
            self.assertEqual(sorted(man["prompt_versions"]), ["cuad-v1", "eb-v1"])

    def test_abstain_all_makes_no_requests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dec_path = root / "abstain.json"
            dec_path.write_text(json.dumps({
                "contract_version": 2,
                "abstain_all": True,
                "threshold": 1.0,
            }), encoding="utf-8")
            inp = root / "in.jsonl"
            inp.write_text(json.dumps({
                "doc_id": "d1", "source_dataset": "extractbench",
                "schema": {"properties": {"a": {"type": "string"}}}, "pages": [],
            }) + "\n", encoding="utf-8")
            out = root / "out.jsonl"

            with mock.patch("pipeline.transport.post_chat") as m_post:
                cfg = extractor.load_config(dec_path, no_cache=True)
                res = extractor.run_file(inp, out, cfg)
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(m_post.call_count, 0)
            self.assertEqual(res["manifest"]["requests"], 0)
            pred = json.loads(out.read_text(encoding="utf-8").strip())
            self.assertEqual(pred["fields"]["a"], {"value": None, "confidence": 0.0})


if __name__ == "__main__":
    unittest.main()
