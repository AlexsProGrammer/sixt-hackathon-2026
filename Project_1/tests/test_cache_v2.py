"""Cache v2: model-scoped layout, key compatibility, legacy fallback, migration."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import mkdtemp

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import migrate_cache  # noqa: E402
import cache_stats  # noqa: E402
from pipeline.transport import ReplyCache, RunState, model_slug  # noqa: E402

MSGS = [{"role": "user", "content": "A"}]
KW = dict(endpoint="e", model="vertex_ai/gemini-3.7-flash", temperature=0.0, sample_idx=0,
          prompt_version="v4", messages=MSGS)


def old_key(**kw) -> str:
    canonical = json.dumps(kw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_legacy(root: Path, key: str, model, pv) -> Path:
    entry = {"answer": {"x": 1}, "sample_idx": 0, "temperature": 0.0}
    if model:
        entry["model"] = model
    if pv:
        entry["prompt_version"] = pv
    p = root / key[:2] / f"{key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entry), encoding="utf-8")
    return p


class KeyTests(unittest.TestCase):
    def test_text_key_equals_pre_v2_key(self):
        self.assertEqual(ReplyCache.make_key(**KW), old_key(**KW))
        self.assertEqual(ReplyCache.make_key(**KW, input_kind="text", attachment_sha256=None), old_key(**KW))

    def test_input_kind_and_attachment_change_key(self):
        base = ReplyCache.make_key(**KW)
        pdf = ReplyCache.make_key(**KW, input_kind="pdf", attachment_sha256="a" * 64)
        pdf2 = ReplyCache.make_key(**KW, input_kind="pdf", attachment_sha256="b" * 64)
        png = ReplyCache.make_key(**KW, input_kind="png", attachment_sha256="a" * 64)
        self.assertEqual(len({base, pdf, pdf2, png}), 4)


class LayoutTests(unittest.TestCase):
    def test_path_contains_model_slug_and_prompt_version(self):
        root = Path(mkdtemp())
        c = ReplyCache(root)
        key = ReplyCache.make_key(**KW)
        p = c._path(key, KW["model"], "v4")
        self.assertEqual(p, root / "replies" / "vertex_ai__gemini-3.7-flash" / "v4" / key[:2] / f"{key}.json")
        self.assertEqual(model_slug("a/b:c"), "a__b__c")

    def test_roundtrip_is_model_scoped(self):
        root = Path(mkdtemp())
        c = ReplyCache(root, RunState())
        key = ReplyCache.make_key(**KW)
        c.put(key, {"answer": {"x": 1}, "model": "m1", "prompt_version": "v4"}, "m1", "v4")
        self.assertEqual(c.get(key, "m1", "v4")["answer"], {"x": 1})
        self.assertIsNone(c.get(key, "m2", "v4"))
        self.assertIsNone(c.get(key, "m1", "v3"))
        self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_legacy_fallback_read(self):
        root = Path(mkdtemp())
        key = ReplyCache.make_key(**KW)
        write_legacy(root, key, KW["model"], "v4")
        self.assertEqual(ReplyCache(root).get(key, KW["model"], "v4")["answer"], {"x": 1})
        self.assertIsNone(ReplyCache(root, layout="v2").get("ff" + "0" * 62, KW["model"], "v4"))

    def test_legacy_layout_writes_flat(self):
        root = Path(mkdtemp())
        c = ReplyCache(root, layout="legacy")
        c.put("ab" + "1" * 62, {"answer": {}}, "m", "v1")
        self.assertTrue((root / "ab" / ("ab" + "1" * 62 + ".json")).exists())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(mkdtemp())
        self.k = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(4)]
        self.paths = [write_legacy(self.root, self.k[0], "vertex_ai/gemini-3.7-flash", "v4"),
                      write_legacy(self.root, self.k[1], "vertex_ai/gemini-3.7-flash", "v4"),
                      write_legacy(self.root, self.k[2], "openai/gpt-x", "v2"),
                      write_legacy(self.root, self.k[3], None, None)]

    def test_dry_run_counts_and_changes_nothing(self):
        counts, _ = migrate_cache.migrate_replies(self.root, dry_run=True, copy=False)
        self.assertEqual(dict(counts), {("vertex_ai__gemini-3.7-flash", "v4"): 2, ("openai__gpt-x", "v2"): 1,
                                        ("_unknown", "_unknown"): 1})
        self.assertTrue(all(p.exists() for p in self.paths))
        self.assertFalse((self.root / "replies").exists())

    def test_copy_keeps_legacy_and_creates_v2(self):
        migrate_cache.migrate_replies(self.root, dry_run=False, copy=True)
        self.assertTrue(all(p.exists() for p in self.paths))
        c = ReplyCache(self.root, layout="v2")
        self.assertTrue(c._path(self.k[0], "vertex_ai/gemini-3.7-flash", "v4").exists())
        self.assertTrue(c._path(self.k[2], "openai/gpt-x", "v2").exists())
        self.assertTrue(c._path(self.k[3], None, None).exists())
        self.assertIn("_unknown", {p.name for p in (self.root / "replies").iterdir()})

    def test_move_removes_legacy(self):
        migrate_cache.migrate_replies(self.root, dry_run=False, copy=False)
        self.assertFalse(any(p.exists() for p in self.paths))
        rows = cache_stats.collect(self.root)
        self.assertEqual(sum(r[2] for r in rows), 4)
        # entries remain readable through the v2 path
        self.assertIsNotNone(ReplyCache(self.root).get(self.k[0], "vertex_ai/gemini-3.7-flash", "v4"))

    def test_http_archived_not_deleted(self):
        http = self.root / "http"
        http.mkdir()
        (http / "a_0.json").write_text(json.dumps(
            {"model": "m", "choices": [{"message": {"content": '{"a": 1}'}}]}), encoding="utf-8")
        (http / "b_0.json").write_text("garbage", encoding="utf-8")
        rep = migrate_cache.http_report(self.root)
        self.assertEqual((rep["entries"], rep["parseable_reply"], rep["unparseable"]), (2, 1, 1))
        self.assertEqual(migrate_cache.archive_http(self.root, dry_run=False, copy=False), 2)
        self.assertEqual(len(list((self.root / "_archive" / "http").glob("*.json"))), 2)

    def test_purge(self):
        migrate_cache.migrate_replies(self.root, dry_run=False, copy=False)
        self.assertEqual(cache_stats.main(["--cache-dir", str(self.root), "--purge", "openai/gpt-x"]), 0)
        self.assertTrue((self.root / "replies" / "openai__gpt-x").exists())  # no --yes: nothing deleted
        cache_stats.main(["--cache-dir", str(self.root), "--purge", "openai/gpt-x", "--yes"])
        self.assertFalse((self.root / "replies" / "openai__gpt-x").exists())


if __name__ == "__main__":
    unittest.main()
