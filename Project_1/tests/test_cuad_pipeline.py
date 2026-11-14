"""T07: CUAD analysis and long-context pipeline tests. Mocked transport, no network."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import cuad_pipeline, transport  # noqa: E402
from pipeline.transport import ReplyCache, RunState  # noqa: E402
from tools import cuad_analysis  # noqa: E402

GEMINI = "vertex_ai/gemini-3.7-flash"
CLAUDE = "vertex_ai/claude-sonnet-5.5"
CFG = {"LLM_BASE_URL": "http://x", "LLM_API_KEY": "k", "LLM_MODEL": GEMINI}


def _make_cuad_schema(names: list[str] | None = None) -> dict:
    cats = names or list(cuad_pipeline.load_categories().keys())
    return {"type": "object", "properties": {c: {"type": "string", "x-normalizer": "span"} for c in cats}}


class TestCuadCategories(unittest.TestCase):
    def test_category_file_has_41_entries_matching_schema(self):
        cats = cuad_pipeline.load_categories()
        self.assertEqual(len(cats), 41)
        self.assertTrue(all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in cats.items()))
        dev_path = ROOT / "data" / "unified" / "dev.jsonl"
        if dev_path.exists():
            with open(dev_path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("source_dataset") == "cuad":
                        self.assertEqual(list(rec["schema"]["properties"].keys()), list(cats.keys()))
                        break


class TestCuadPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = RunState()

    def _ctx(self, fake, views="A"):
        cache = ReplyCache(self.tmp / "cache", self.state)
        ctx = mock.Mock()
        ctx.cfg, ctx.cache, ctx.state = CFG, cache, self.state
        ctx.cuad = cuad_pipeline.resolve_cuad(
            {"views": cuad_pipeline.parse_views(views), "model_a": GEMINI, "model_b": CLAUDE},
            env={},
        )
        patcher = mock.patch.object(transport, "post_chat", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return ctx

    def test_long_contract_not_chunked_when_it_fits(self):
        # GEMINI has max_context_chars = 400_000 in models.json
        schema = _make_cuad_schema()
        text = "Section 1. " + ("A" * 250_000) + " End of Agreement."
        jobs = cuad_pipeline.plan_jobs(text, schema, GEMINI)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["start"], 0)
        self.assertEqual(jobs[0]["end"], len(text))
        self.assertEqual(len(jobs[0]["field_names"]), 41)

    def test_contract_chunked_when_exceeding_max_context(self):
        schema = _make_cuad_schema(["Document Name", "Governing Law"])
        text = "A" * 450_000
        jobs = cuad_pipeline.plan_jobs(text, schema, GEMINI, chunk_chars=300_000, overlap_chars=5_000)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["start"], 0)
        self.assertEqual(jobs[1]["end"], len(text))

    def test_resolve_cuad_chunk_chars_env_overrides(self):
        cfg = cuad_pipeline.resolve_cuad(env={"LLM_CHUNK_CHARS": "35000", "LLM_CHUNK_CHARS_A": "20000"})
        self.assertEqual(cfg["chunk_chars_a"], 20000)
        self.assertEqual(cfg["chunk_chars_b"], 35000)
        schema = _make_cuad_schema(["Document Name", "Governing Law"])
        jobs = cuad_pipeline.plan_jobs("A" * 50_000, schema, GEMINI, max_chars=cfg["chunk_chars_a"])
        self.assertEqual(len(jobs), 3)
        self.assertTrue(all(len(j["text"]) <= 20000 for j in jobs))

    def test_spans_joined_in_document_order_and_grounded_with_glyph_norm(self):
        text = (
            'MASTER SERVICES AGREEMENT.\n'
            'Section 2: “Alpha Corp” and ‘Beta LLC’ agree.\n'
            'Section 9: This Agreement is governed by the laws of Delaware.\n'
            'Section 12: Either party may terminate for convenience upon 30 days notice.\n'
        )
        schema = _make_cuad_schema(["Document Name", "Parties", "Governing Law", "Termination For Convenience"])
        # Return out-of-order passages for Parties and a paraphrased/ungrounded value for Governing Law
        reply = json.dumps({
            "Document Name": {"value": "MASTER SERVICES AGREEMENT", "confidence": 0.99},
            "Parties": {"value": "'Beta LLC' | \"Alpha Corp\"", "confidence": 0.95},
            "Governing Law": {"value": "Governed by New York law (paraphrase)", "confidence": 0.90},
            "Termination For Convenience": {
                "value": "Either party may terminate for convenience upon 30 days notice. | Nonexistent clause.",
                "confidence": 0.92,
            },
        })
        calls = []

        def fake(cfg, messages, temperature, *, model=None, timeout=300):
            calls.append(model)
            return reply

        ctx = self._ctx(fake, views="full")
        rec = {"doc_id": "cuad:test", "source_dataset": "cuad", "schema": schema}
        routed = {"route": "cuad", "text": text, "text_source": "cuad", "quality": 1.0, "quality_features": {}}
        out = cuad_pipeline.extract_document(rec, routed, ctx)

        self.assertEqual(calls, [GEMINI, CLAUDE])
        self.assertEqual(len(out["samples"]), 2)
        self.assertEqual(out["fields"]["Document Name"]["value"], "MASTER SERVICES AGREEMENT")
        # Reordered into document order despite model returning Beta before Alpha, with glyph norm matching curly quotes
        self.assertEqual(out["fields"]["Parties"]["value"], '"Alpha Corp" | \'Beta LLC\'')
        # Paraphrased value dropped by per-passage grounding post-check
        self.assertIsNone(out["fields"]["Governing Law"]["value"])
        # Grounded piece kept, ungrounded piece dropped
        self.assertEqual(
            out["fields"]["Termination For Convenience"]["value"],
            "Either party may terminate for convenience upon 30 days notice.",
        )


class TestCuadAnalysis(unittest.TestCase):
    def test_classify_wrong_modes(self):
        doc = "Alpha Clause One. Beta Clause Two is longer here. Gamma Clause Three."
        self.assertEqual(cuad_analysis.classify_wrong("Not in doc at all", "Alpha Clause One.", doc), "paraphrase")
        self.assertEqual(cuad_analysis.classify_wrong("Beta Clause", "Beta Clause Two is longer here.", doc), "subset")
        self.assertEqual(cuad_analysis.classify_wrong("Beta Clause Two is longer here.", "Beta Clause", doc), "superset")
        self.assertEqual(
            cuad_analysis.classify_wrong("Alpha Clause One.", "Alpha Clause One. | Gamma Clause Three.", doc),
            "missing_passages",
        )
        self.assertEqual(cuad_analysis.classify_wrong("Gamma Clause Three.", "Alpha Clause One.", doc), "other_location")


if __name__ == "__main__":
    unittest.main()
