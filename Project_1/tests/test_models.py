"""Model adapter layer: registry, message builders, cache key independence of attachment bytes, rendering."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from pipeline import transport  # noqa: E402
from pipeline.messages import (ATTACHMENT_PLACEHOLDER, key_messages, pdf_messages, png_messages,  # noqa: E402
                               text_messages)
from pipeline.models import (fallback_order, load_models, model_roles, pick_input_kind,  # noqa: E402
                             supported_kinds, update_supports)
from pipeline.render import render_pages  # noqa: E402
from pipeline.transport import ReplyCache, RunState, TransportError, call_model, execute_job  # noqa: E402

PDF = b"%PDF-1.4 fake bytes A"
PDF2 = b"%PDF-1.4 fake bytes B"
KW = dict(endpoint="e", model="m", temperature=0.0, sample_idx=0, prompt_version="v1")


def key_for(messages, kind, sha):
    return ReplyCache.make_key(**KW, messages=key_messages(messages), input_kind=kind, attachment_sha256=sha)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(mkdtemp()) / "models.json"
        self.path.write_text(json.dumps({
            "defaults": {"family": "unknown", "supports": {"text": True, "pdf_file": None, "pdf_image_url": None, "png": None},
                         "timeout_s": 300},
            "models": {
                "full": {"family": "f", "supports": {"pdf_file": True, "pdf_image_url": True, "png": True}},
                "claude": {"family": "c", "supports": {"pdf_file": True, "pdf_image_url": False, "png": True}},
                "gpt": {"family": "g", "supports": {"pdf_file": False, "pdf_image_url": False, "png": True}},
                "plain": {"family": "p"},
            }}), encoding="utf-8")

    def test_defaults_filled_in(self):
        m = load_models(self.path)
        self.assertEqual(m["plain"]["supports"]["text"], True)
        self.assertEqual(m["plain"]["timeout_s"], 300)
        self.assertEqual(m["full"]["family"], "f")

    def test_order_pdf_file_first(self):
        avail = ["text", "png", "pdf_image_url", "pdf_file"]
        self.assertEqual(pick_input_kind("full", avail, self.path), "pdf_file")
        self.assertEqual(fallback_order("full", avail, self.path), ["pdf_file", "pdf_image_url", "png", "text"])

    def test_skips_rejected_kinds(self):
        avail = ["pdf_file", "pdf_image_url", "png", "text"]
        self.assertEqual(pick_input_kind("claude", avail, self.path), "pdf_file")
        self.assertEqual(pick_input_kind("gpt", avail, self.path), "png")
        self.assertEqual(fallback_order("gpt", avail, self.path), ["png", "text"])

    def test_respects_availability(self):
        self.assertEqual(pick_input_kind("gpt", ["text"], self.path), "text")
        self.assertEqual(pick_input_kind("full", ["pdf_image_url", "text"], self.path), "pdf_image_url")

    def test_untested_is_unsupported_and_unknown_model_is_text(self):
        self.assertEqual(pick_input_kind("plain", ["pdf_file", "png", "text"], self.path), "text")
        self.assertEqual(pick_input_kind("never-seen", ["pdf_file", "text"], self.path), "text")
        self.assertIsNone(pick_input_kind("plain", ["pdf_file"], self.path))
        self.assertEqual(supported_kinds("claude", self.path), ["pdf_file", "png", "text"])

    def test_update_supports_writes_file(self):
        update_supports({"gpt": {"png": False}, "new": {"pdf_file": True}}, self.path, probed_at="t")
        data = json.loads(self.path.read_text())
        self.assertFalse(data["models"]["gpt"]["supports"]["png"])
        self.assertTrue(data["models"]["new"]["supports"]["pdf_file"])
        self.assertEqual(data["models"]["new"]["probed_at"], "t")

    def test_repo_models_json_is_valid(self):
        m = load_models()
        self.assertIn("vertex_ai/gemini-3.7-flash", m)
        self.assertEqual(pick_input_kind("gpt-5.6-sol", ["pdf_file", "pdf_image_url", "text"]), "text")

    def test_model_roles(self):
        env = {"LLM_MODEL": "d", "LLM_MODEL_B": "b", "LLM_MODEL_OCR": " "}
        self.assertEqual(model_roles(env), {"default": "d", "A": "d", "B": "b", "C": None, "ocr": None})
        self.assertEqual(model_roles({"LLM_MODEL": "d", "LLM_MODEL_A": "a"})["A"], "a")


class BuilderTests(unittest.TestCase):
    def test_text(self):
        msgs, kind, sha = text_messages("P", "body")
        self.assertEqual((kind, sha), ("text", None))
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("P", msgs[0]["content"])
        self.assertIn("body", msgs[0]["content"])

    def test_pdf_file_and_image_url(self):
        b64 = base64.b64encode(PDF).decode()
        msgs, kind, sha = pdf_messages("P", PDF, "file")
        parts = msgs[0]["content"]
        self.assertEqual(parts[0], {"type": "text", "text": "P"})
        self.assertEqual(parts[1], {"type": "file", "file": {"file_data": f"data:application/pdf;base64,{b64}"}})
        self.assertEqual(kind, "pdf")
        self.assertEqual(len(sha), 64)
        msgs2, kind2, sha2 = pdf_messages("P", PDF, "image_url")
        self.assertEqual(msgs2[0]["content"][1], {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{b64}"}})
        self.assertEqual((kind2, sha2), (kind, sha))
        with self.assertRaises(ValueError):
            pdf_messages("P", PDF, "bogus")

    def test_png_multi_page(self):
        msgs, kind, sha = png_messages("P", [b"\x89PNGa", b"\x89PNGb"])
        parts = msgs[0]["content"]
        self.assertEqual([p["type"] for p in parts], ["text", "image_url", "image_url"])
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(kind, "png")
        self.assertNotEqual(sha, png_messages("P", [b"\x89PNGb", b"\x89PNGa"])[2])  # page order matters
        self.assertNotEqual(sha, png_messages("P", [b"\x89PNGa"])[2])
        with self.assertRaises(ValueError):
            png_messages("P", [])


class KeyTests(unittest.TestCase):
    def test_key_messages_scrubs_base64_and_keeps_input_intact(self):
        msgs, _, _ = pdf_messages("P", PDF, "file")
        scrubbed = key_messages(msgs)
        blob = json.dumps(scrubbed)
        self.assertNotIn(base64.b64encode(PDF).decode(), blob)
        self.assertIn(ATTACHMENT_PLACEHOLDER, blob)
        self.assertIn(base64.b64encode(PDF).decode(), json.dumps(msgs))  # original unchanged

    def test_key_depends_on_sha_not_on_base64(self):
        m1, k1, s1 = pdf_messages("P", PDF, "file")
        m2, _, s2 = pdf_messages("P", PDF2, "file")
        self.assertNotEqual(key_for(m1, k1, s1), key_for(m2, k1, s2))
        # same sha with different bytes in the message: identical key (content is not hashed)
        self.assertEqual(key_for(m1, k1, s1), key_for(m2, k1, s1))

    def test_key_depends_on_mode_and_kind_and_prompt(self):
        mf, k, s = pdf_messages("P", PDF, "file")
        mi, _, _ = pdf_messages("P", PDF, "image_url")
        self.assertNotEqual(key_for(mf, k, s), key_for(mi, k, s))
        mp, kp, sp = png_messages("P", [b"x"])
        self.assertNotEqual(key_for(mf, k, s), key_for(mp, kp, sp))
        mq, kq, sq = pdf_messages("Q", PDF, "file")
        self.assertNotEqual(key_for(mf, k, s), key_for(mq, kq, sq))

    def test_text_key_unchanged(self):
        msgs, kind, sha = text_messages("P", "t")
        old = ReplyCache.make_key(**KW, messages=msgs)
        self.assertEqual(key_for(msgs, kind, sha), old)


class TransportTests(unittest.TestCase):
    cfg = {"LLM_BASE_URL": "http://x/v1", "LLM_API_KEY": "SECRET", "LLM_MODEL": "default-m"}

    def test_post_chat_uses_model_parameter_and_records_meta(self):
        seen = {}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"choices": [{"message": {"content": "hi"}}], "usage": {"total_tokens": 3}}).encode()

        def fake(req, timeout):
            seen["body"] = json.loads(req.data)
            seen["timeout"] = timeout
            return Resp()

        with mock.patch.object(transport.urllib.request, "urlopen", fake):
            res = call_model(self.cfg, "other-m", [{"role": "user", "content": "q"}], 0.0, RunState())
        self.assertEqual(seen["body"]["model"], "other-m")
        self.assertEqual(res["text"], "hi")
        self.assertEqual(res["usage"], {"total_tokens": 3})
        self.assertIsNotNone(res["elapsed_s"])

    def test_http_400_is_logged_redacted(self):
        import io, urllib.error
        err = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"error":"bad key SECRET not allowed"}'))
        state = RunState()
        with mock.patch.object(transport.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(TransportError) as cm:
                call_model(self.cfg, "gpt", [{"role": "user", "content": "q"}], 0.0, state)
        self.assertEqual(cm.exception.status, 400)
        self.assertNotIn("SECRET", str(cm.exception))
        self.assertTrue(any("gpt" in w and "400" in w for w in state.warnings))
        self.assertFalse(any("SECRET" in w for w in state.warnings))

    def test_execute_job_with_attachment_builder_and_model_override(self):
        root = Path(mkdtemp())
        cache = ReplyCache(root)
        state = RunState()
        job = {"job_id": "j", "sample_idx": 0, "chunk_id": 0, "batch_id": 0, "start": 0, "end": None, "field_names": ["f"]}
        builder = lambda j: pdf_messages("P", PDF, "file")  # noqa: E731
        run = lambda: execute_job(job, cfg=self.cfg, cache=cache, state=state, temperature=0.0, prompt_version="v9",  # noqa: E731
                                  build_messages=builder, model="claude-x")
        with mock.patch.object(transport, "call_with_retry", return_value='{"f": 1}') as c:
            r1 = run()
            r2 = run()
        self.assertTrue(r1["ok"] and r2["ok"])
        self.assertEqual(c.call_count, 1)
        self.assertEqual(c.call_args.kwargs["model"], "claude-x")
        files = list((root / "replies" / "claude-x" / "v9").rglob("*.json"))
        self.assertEqual(len(files), 1)
        entry = json.loads(files[0].read_text())
        self.assertEqual(entry["input_kind"], "pdf")
        self.assertNotIn(base64.b64encode(PDF).decode(), files[0].read_text())

    def test_resolve_endpoint_uses_per_model_override_and_falls_back(self):
        cfg = {
            "LLM_BASE_URL": "https://default.example/v1",
            "LLM_API_KEY": "sk-default",
            "LLM_MODEL": "m-default",
            "endpoints": {
                "m-b": {"LLM_BASE_URL": "https://b.example/v1/", "LLM_API_KEY": "sk-b"},
                "m-c": {"LLM_BASE_URL": "https://default.example/v1", "LLM_API_KEY": "sk-c"},
            },
        }
        self.assertEqual(transport.resolve_endpoint(cfg), ("https://default.example/v1", "sk-default", "m-default"))
        self.assertEqual(transport.resolve_endpoint(cfg, "m-b"), ("https://b.example/v1", "sk-b", "m-b"))
        self.assertEqual(transport.resolve_endpoint(cfg, "m-c"), ("https://default.example/v1", "sk-c", "m-c"))
        self.assertEqual(transport.resolve_endpoint(cfg, "m-other"), ("https://default.example/v1", "sk-default", "m-other"))
        roles = model_roles({"LLM_MODEL": "m-def", "LLM_MODEL_C": "m-c"})
        self.assertEqual(roles["C"], "m-c")

    def test_json_mode_and_400_fallback(self):
        import io, urllib.error
        transport._NO_JSON_MODE.clear()
        seen_bodies = []

        def fake_urlopen(req, timeout=300):
            body = json.loads(req.data)
            seen_bodies.append(body)
            if "response_format" in body:
                raise urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"error":"response_format not supported"}'))
            resp = mock.MagicMock()
            resp.__enter__ = mock.Mock(return_value=resp)
            resp.__exit__ = mock.Mock(return_value=False)
            resp.read.return_value = json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()
            return resp

        with mock.patch.object(transport.urllib.request, "urlopen", side_effect=fake_urlopen):
            out1 = transport.post_chat(self.cfg, [{"role": "user", "content": "q"}], 0.0, model="gemma-no-json")
            out2 = transport.post_chat(self.cfg, [{"role": "user", "content": "q"}], 0.0, model="gemma-no-json")
        self.assertEqual(out1, '{"ok": true}')
        self.assertEqual(out2, '{"ok": true}')
        self.assertEqual(len(seen_bodies), 3)  # 1st tried json_object -> 400 -> fallback; 2nd skipped json_object directly
        self.assertIn("response_format", seen_bodies[0])
        self.assertNotIn("response_format", seen_bodies[1])
        self.assertNotIn("response_format", seen_bodies[2])


@unittest.skipUnless(shutil.which("pdftoppm"), "pdftoppm not installed")
class RenderTests(unittest.TestCase):
    def make_pdf(self, root: Path) -> Path:
        # minimal valid one-page PDF
        objs = ["<</Type/Catalog/Pages 2 0 R>>", "<</Type/Pages/Kids[3 0 R]/Count 1>>",
                "<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
                None, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
        stream = "BT /F1 18 Tf 10 40 Td (Hello) Tj ET"
        objs[3] = f"<</Length {len(stream)}>>\nstream\n{stream}\nendstream"
        out, offs = b"%PDF-1.4\n", []
        for i, o in enumerate(objs, 1):
            offs.append(len(out))
            out += f"{i} 0 obj\n{o}\nendobj\n".encode()
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
        out += f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
        p = root / "t.pdf"
        p.write_bytes(out)
        return p

    def test_render_and_cache(self):
        root = Path(mkdtemp())
        pdf = self.make_pdf(root)
        pages = render_pages(pdf, dpi=50, cache_root=root / "cache")
        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0].read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(pages[0].name, "page-1.png")
        self.assertEqual(pages[0].parent.name, "50")
        with mock.patch("pipeline.render.subprocess.run", side_effect=AssertionError("must hit the cache")):
            self.assertEqual(render_pages(pdf, dpi=50, cache_root=root / "cache"), pages)

    def test_corrupted_pdf_returns_empty(self):
        root = Path(mkdtemp())
        bad = root / "bad.pdf"
        bad.write_bytes(b"not a pdf at all")
        self.assertEqual(render_pages(bad, cache_root=root / "cache"), [])
        self.assertEqual(render_pages(root / "missing.pdf", cache_root=root / "cache"), [])


if __name__ == "__main__":
    unittest.main()
