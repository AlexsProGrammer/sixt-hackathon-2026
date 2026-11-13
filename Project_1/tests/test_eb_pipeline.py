"""T06: ExtractBench vision pipeline. Mocked transport (post_chat), synthetic PDFs, no network."""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import eb_pipeline, router, transport  # noqa: E402
from pipeline.prompts_eb import EB_PROMPT_VERSION, build_prompt, eb_jobs  # noqa: E402
from pipeline.transport import ReplyCache, RunState, TransportError  # noqa: E402
from tests.test_router import make_pdf  # noqa: E402
from uncertainty.decision import make_prediction  # noqa: E402
from uncertainty.single_view import aggregate_single_view  # noqa: E402

GEMINI, CLAUDE, GPT = "vertex_ai/gemini-3.7-flash", "vertex_ai/claude-sonnet-5.5", "gpt-5.6-sol"
CFG = {"LLM_BASE_URL": "http://x", "LLM_API_KEY": "k", "LLM_MODEL": GEMINI}
TEXT = b"Pine Harbour Water Utilities LLC pays 1234 dollars"

SCHEMA = {"type": "object", "title": "Form X", "properties": {
    "name": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Name", "description": "Entity name verbatim."},
    "amount": {"anyOf": [{"type": "number"}, {"type": "null"}], "title": "Amount",
               "description": "Amount as a JSON number, thousands comma removed."},
    "final": {"anyOf": [{"type": "boolean"}, {"type": "null"}], "title": "Final",
              "description": "TWO-STATE: true only if marked. Never null."}}}


def rec_for(name="a.pdf", schema=None):
    return {"doc_id": f"extractbench:short/{name}", "source_dataset": "extractbench",
            "pages": [f"raw\\extractbench\\docs\\short\\{name}"], "schema": schema or SCHEMA}


def answer(model_conf=0.9, **over):
    base = {"name": "Pine Harbour Water Utilities LLC", "amount": 1234, "final": False}
    base.update(over)
    return json.dumps({k: {"value": v, "confidence": model_conf} for k, v in base.items()})


class FakeLLM:
    """Replaces transport.post_chat. Records (model, content-part types) per request."""

    def __init__(self, replies=None, fail=None):
        self.calls: list[dict] = []
        self.replies = replies or {}
        self.fail = fail or {}      # model -> list of TransportError raised for the first requests

    def __call__(self, cfg, messages, temperature, *, model=None, timeout=300):
        content = messages[0]["content"]
        parts = [p["type"] for p in content] if isinstance(content, list) else ["text"]
        self.calls.append({"model": model, "parts": parts, "messages": messages, "temperature": temperature})
        queue = self.fail.get(model)
        if queue:
            raise queue.pop(0)
        return self.replies.get(model, answer())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.docs = self.tmp / "data" / "raw" / "extractbench" / "docs" / "short"
        self.docs.mkdir(parents=True)
        (self.docs / "a.pdf").write_bytes(make_pdf(TEXT))
        self.data = self.tmp / "data"
        router._pdftotext.cache_clear()
        self.state = RunState()

    def ctx(self, fake, eb=None, cache=True):
        cache_obj = ReplyCache(self.tmp / "cache" if cache else None, self.state)
        ctx = mock.Mock()
        ctx.cfg, ctx.cache, ctx.state = CFG, cache_obj, self.state
        ctx.eb = eb_pipeline.resolve_eb({"model_a": GEMINI, "model_b": CLAUDE, **(eb or {})}, env={})
        patcher = mock.patch.object(transport, "post_chat", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return ctx

    def run_views(self, ctx, route="pdf_text_good", rec=None):
        rec = rec or rec_for()
        routed = router.route(rec, self.data)
        routed = {**routed, "route": route}
        return eb_pipeline.run_views(rec, routed, ctx, data_dir=self.data)


class PromptTests(unittest.TestCase):
    def test_full_description_and_type_in_prompt(self):
        jobs = eb_jobs(SCHEMA)
        self.assertEqual(len(jobs), 1)
        p = build_prompt(jobs[0]["schema"], "pdf")
        self.assertIn("Entity name verbatim.", p)
        self.assertIn("TWO-STATE: true only if marked. Never null.", p)
        self.assertIn("type=number", p)
        self.assertIn("attached as a PDF", p)
        self.assertIn("images", build_prompt(jobs[0]["schema"], "png"))
        self.assertEqual(EB_PROMPT_VERSION, "eb-v1")

    def test_defs_are_sent(self):
        schema = {"$defs": {"Row": {"type": "object", "properties": {"code": {"type": "string"}}}},
                  "properties": {"rows": {"type": "array", "items": {"$ref": "#/$defs/Row"}}}}
        p = build_prompt(eb_jobs(schema)[0]["schema"])
        self.assertIn('"$defs"', p)
        self.assertIn('"code"', p)

    def test_batches_of_sixty(self):
        schema = {"properties": {f"f{i}": {"type": "string"} for i in range(130)}}
        jobs = eb_jobs(schema, 60)
        self.assertEqual([len(j["field_names"]) for j in jobs], [60, 60, 10])
        self.assertEqual([j["job_id"] for j in jobs], ["s0-c0-b0", "s0-c0-b1", "s0-c0-b2"])
        self.assertTrue(all(j["sample_idx"] == 0 for j in jobs))

    def test_views_parsing(self):
        self.assertEqual(eb_pipeline.parse_views(None), ["A-pdf"])
        self.assertEqual(eb_pipeline.parse_views("A"), ["A-pdf"])
        self.assertEqual(eb_pipeline.parse_views("A-pdf,B-pdf"), ["A-pdf", "B-pdf"])
        self.assertEqual(eb_pipeline.parse_views("full"), ["full"])
        with self.assertRaises(ValueError):
            eb_pipeline.parse_views("C-pdf")
        self.assertEqual(eb_pipeline.views_for_route("pdf_no_text", ["full"]), ["A-pdf", "B-pdf"])
        self.assertEqual(eb_pipeline.views_for_route("pdf_text_good", ["full"]), ["A-pdf", "B-pdf", "A-text"])
        self.assertEqual(eb_pipeline.views_for_route("pdf_no_text", ["A-pdf", "A-text"]), ["A-pdf"])
        self.assertEqual(eb_pipeline.views_for_route("cuad", ["full"]), [])


class ViewTests(Base):
    def test_gemini_and_claude_get_the_pdf_as_file_part(self):
        fake = FakeLLM()
        views = self.run_views(self.ctx(fake, {"views": ["A-pdf", "B-pdf"]}))
        self.assertEqual([v["view_id"] for v in views], ["A-pdf", "B-pdf"])
        by_model = {c["model"]: c for c in fake.calls}
        for model in (GEMINI, CLAUDE):
            self.assertEqual(by_model[model]["parts"], ["text", "file"], model)
            uri = by_model[model]["messages"][0]["content"][1]["file"]["file_data"]
            self.assertTrue(uri.startswith("data:application/pdf;base64,"))
            self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), (self.docs / "a.pdf").read_bytes())
        self.assertTrue(all(v["input_kind"] == "pdf_file" for v in views))
        self.assertTrue(all(v["complete"] for v in views))
        self.assertEqual(views[0]["fields"]["name"]["status"], "present")
        self.assertEqual(views[0]["fields"]["name"]["value"], "Pine Harbour Water Utilities LLC")
        self.assertEqual(views[0]["fields"]["name"]["model_confidence"], 0.9)

    @unittest.skipUnless(shutil.which("pdftoppm"), "pdftoppm not installed")
    def test_png_fallback_for_model_without_pdf_support(self):
        fake = FakeLLM(replies={GPT: answer()})
        views = self.run_views(self.ctx(fake, {"views": ["A-pdf"], "model_a": GPT}))
        self.assertEqual(views[0]["input_kind"], "png")
        self.assertEqual(fake.calls[0]["parts"][0], "text")
        self.assertTrue(all(p == "image_url" for p in fake.calls[0]["parts"][1:]))
        self.assertGreaterEqual(len(fake.calls[0]["parts"]), 2)
        self.assertEqual(views[0]["attempts"][0]["kind"], "png")
        self.assertTrue(views[0]["complete"])

    def test_model_without_any_supported_input_is_an_error_view(self):
        fake = FakeLLM()
        views = self.run_views(self.ctx(fake, {"views": ["A-pdf"], "model_a": "mistral-ocr-4"}))
        self.assertFalse(views[0]["complete"])
        self.assertEqual(views[0]["errors"], ["no_supported_input"])
        self.assertEqual(fake.calls, [])
        self.assertEqual(views[0]["fields"]["name"]["status"], "error")

    @unittest.skipUnless(shutil.which("pdftoppm"), "pdftoppm not installed")
    def test_size_rejection_falls_back_to_lower_dpi_png(self):
        err = TransportError("http", "HTTP 413", status=413)
        fake = FakeLLM(fail={GEMINI: [err]})
        views = self.run_views(self.ctx(fake, {"views": ["A-pdf"]}))
        self.assertEqual([a["kind"] for a in views[0]["attempts"]], ["pdf_file", "png"])
        self.assertEqual(views[0]["attempts"][1]["dpi"], 100)
        self.assertEqual(views[0]["input_kind"], "png")
        self.assertTrue(views[0]["complete"])
        self.assertEqual(views[0]["attempts"][0]["error"], "http:413")

    def test_timeout_does_not_trigger_fallback(self):
        err = TransportError("timeout", "request timed out")
        fake = FakeLLM(fail={GEMINI: [err, err, err]})
        views = self.run_views(self.ctx(fake, {"views": ["A-pdf"]}))
        self.assertFalse(views[0]["complete"])
        self.assertEqual(len(views[0]["attempts"]), 1)
        self.assertEqual(views[0]["errors"], ["timeout"])

    def test_pdf_over_page_cap_is_rendered_not_sent_whole(self):
        ctx = self.ctx(FakeLLM(), {"views": ["A-pdf"], "max_pages": 0})
        doc = eb_pipeline.Document(rec_for(), self.data, ctx.eb)
        attempts = eb_pipeline.plan_attempts(GEMINI, doc, ctx.eb)
        self.assertEqual([a["kind"] for a in attempts], ["png", "png"])
        ctx.eb["max_pdf_bytes"], ctx.eb["max_pages"] = 10, 10
        self.assertEqual(eb_pipeline.plan_attempts(GEMINI, doc, ctx.eb)[0]["kind"], "png")   # size cap

    def test_missing_file_is_an_error_view(self):
        views = self.run_views(self.ctx(FakeLLM()), rec=rec_for("missing.pdf"))
        self.assertFalse(views[0]["complete"])
        self.assertTrue(views[0]["errors"][0].startswith("missing_file"))

    def test_text_view_uses_the_text_layer_only_on_good_route(self):
        fake = FakeLLM()
        ctx = self.ctx(fake, {"views": ["full"]})
        views = self.run_views(ctx, route="pdf_text_good")
        self.assertEqual([v["view_id"] for v in views], ["A-pdf", "B-pdf", "A-text"])
        self.assertEqual(views[2]["input_kind"], "text")
        self.assertEqual(sum(1 for c in fake.calls if c["parts"] == ["text"]), 1)
        fake.calls.clear()
        views = self.run_views(ctx, route="pdf_text_damaged")
        self.assertEqual([v["view_id"] for v in views], ["A-pdf", "B-pdf"])

    def test_views_are_cached_separately_per_model(self):
        fake = FakeLLM(replies={GEMINI: answer(name="From Gemini"), CLAUDE: answer(name="From Claude")})
        ctx = self.ctx(fake, {"views": ["A-pdf", "B-pdf"]})
        first = self.run_views(ctx)
        self.assertEqual(len(fake.calls), 2)
        second = self.run_views(ctx)
        self.assertEqual(len(fake.calls), 2)                      # both from cache
        self.assertEqual(self.state.cache_hits, 2)
        self.assertEqual(first[0]["fields"]["name"]["value"], "From Gemini")
        self.assertEqual(second[1]["fields"]["name"]["value"], "From Claude")
        root = self.tmp / "cache" / "replies"
        self.assertTrue((root / transport.model_slug(GEMINI) / EB_PROMPT_VERSION).is_dir())
        self.assertTrue((root / transport.model_slug(CLAUDE) / EB_PROMPT_VERSION).is_dir())

    def test_cache_key_has_no_base64_and_depends_on_pdf_bytes(self):
        fake = FakeLLM()
        self.run_views(self.ctx(fake))
        keys = [p.name for p in (self.tmp / "cache" / "replies").rglob("*.json")]
        self.assertEqual(len(keys), 1)
        (self.docs / "a.pdf").write_bytes(make_pdf(b"Another text entirely"))
        self.run_views(self.ctx(fake))
        self.assertEqual(len(list((self.tmp / "cache" / "replies").rglob("*.json"))), 2)

    def test_batches_make_one_request_each(self):
        schema = {"properties": {f"f{i}": {"type": "string", "description": f"d{i}"} for i in range(130)}}
        reply = json.dumps({f"f{i}": {"value": f"v{i}", "confidence": 0.8} for i in range(130)})
        fake = FakeLLM(replies={GEMINI: reply})
        views = self.run_views(self.ctx(fake), rec=rec_for(schema=schema))
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(views[0]["n_requests"], 3)
        self.assertEqual(views[0]["fields"]["f129"]["value"], "v129")

    def test_parse_error_marks_fields_as_error(self):
        fake = FakeLLM(replies={GEMINI: "not json"})
        views = self.run_views(self.ctx(fake))
        self.assertFalse(views[0]["complete"])
        self.assertTrue(views[0]["errors"][0].startswith("parse:"))
        self.assertEqual(views[0]["fields"]["amount"]["status"], "error")

    def test_corrupted_route_uses_png_only(self):
        if not shutil.which("pdftoppm"):
            self.skipTest("pdftoppm not installed")
        fake = FakeLLM()
        views = self.run_views(self.ctx(fake, {"views": ["full"]}), route="pdf_corrupted")
        self.assertEqual([v["view_id"] for v in views], ["A-pdf"])
        self.assertEqual(views[0]["input_kind"], "png")
        self.assertTrue(all(p in ("text", "image_url") for p in fake.calls[0]["parts"]))


class AggregationTests(unittest.TestCase):
    def view(self, **fields):
        base = {"name": ("present", "Pine Harbour Water Utilities LLC", 0.9), "amount": ("present", 1234, 0.9),
                "final": ("present", False, 0.95)}
        base.update(fields)
        return {"view_id": "A-pdf", "model": GEMINI, "input_kind": "pdf_file", "fields": {
            n: {"status": s, "value": v, "model_confidence": c, "complete": True, "evidence": [], "reason": ""}
            for n, (s, v, c) in base.items()}}

    def test_text_grounding_is_a_feature_not_a_filter(self):
        agg = aggregate_single_view(self.view(), SCHEMA, "Pine Harbour Water Utilities LLC pays 1234", route="pdf_text_good")
        self.assertTrue(agg["candidates"]["name"]["eligible"])
        self.assertTrue(agg["candidates"]["name"]["features"]["grounded_text"])
        # damaged text layer: the value is not grounded, but it is still a candidate
        agg = aggregate_single_view(self.view(), SCHEMA, "ine Harbour Water Utillties LLC", route="pdf_text_damaged")
        c = agg["candidates"]["name"]
        self.assertTrue(c["eligible"])
        self.assertIs(c["features"]["grounded_text"], False)
        # no text layer at all
        agg = aggregate_single_view(self.view(), SCHEMA, None, route="pdf_no_text")
        self.assertTrue(agg["candidates"]["name"]["eligible"])
        self.assertIsNone(agg["candidates"]["name"]["features"]["grounded_text"])

    def test_prediction_contract(self):
        agg = aggregate_single_view(self.view(final=("present", False, 0.95)), SCHEMA, None)
        fields = make_prediction(agg, SCHEMA, method="k1_grounded")
        self.assertEqual(set(fields), set(SCHEMA["properties"]))
        self.assertEqual(fields["name"], {"value": "Pine Harbour Water Utilities LLC", "confidence": 0.9})
        self.assertEqual(fields["final"]["value"], False)       # a False boolean is a value, not an abstention
        self.assertEqual(agg["candidates"]["final"]["features"]["kind_policy"], "views_only")

    def test_absent_error_and_schema_violations_abstain(self):
        v = self.view(name=("absent", None, 0.9), amount=("present", "1,234", 0.9), final=("error", None, None))
        agg = aggregate_single_view(v, SCHEMA, None)
        fields = make_prediction(agg, SCHEMA, method="k1_grounded")
        self.assertEqual(agg["candidates"]["name"]["reason"], "null_majority")
        self.assertTrue(agg["candidates"]["amount"]["reason"].startswith("invalid"))
        self.assertEqual(agg["candidates"]["final"]["reason"], "incomplete_observations")
        for n in SCHEMA["properties"]:
            self.assertEqual(fields[n], {"value": None, "confidence": 0.0})


class CliWiringTests(Base):
    """4_extract.py: --eb-views routes ExtractBench documents to the vision pipeline, CUAD stays on text."""

    def load_extractor(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("extract4_t06", ROOT / "4_extract.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.DATA = self.data
        return mod

    def test_extract_llm_dispatches_to_vision_pipeline(self):
        ex = self.load_extractor()
        fake = FakeLLM()
        ctx = self.ctx(fake, {"views": ["A-pdf"]})
        ctx.pipeline = {**ex.DEFAULTS, "uq_method": "k1_grounded"}
        res = ex.extract_llm(rec_for(), ctx)
        self.assertEqual(res["fields"]["name"]["value"], "Pine Harbour Water Utilities LLC")
        self.assertEqual(res["diagnostics"]["pipeline"], "eb-vision")
        self.assertIn(res["diagnostics"]["route"], eb_pipeline.VISION_ROUTES)
        self.assertEqual(res["diagnostics"]["views"][0]["input_kind"], "pdf_file")
        self.assertEqual(res["samples"][0]["view_id"], "A-pdf")
        self.assertEqual(fake.calls[0]["parts"], ["text", "file"])
        self.assertEqual(res["job_failures"], [])

    def test_without_eb_the_text_pipeline_is_used(self):
        ex = self.load_extractor()
        fake = FakeLLM()
        ctx = self.ctx(fake)
        ctx.eb = None
        ctx.pipeline = {**ex.DEFAULTS, "uq_method": "k1_grounded"}
        ex.extract_llm(rec_for(), ctx)
        self.assertEqual(fake.calls[0]["parts"], ["text"])      # text prompt, no attachment


if __name__ == "__main__":
    unittest.main()
