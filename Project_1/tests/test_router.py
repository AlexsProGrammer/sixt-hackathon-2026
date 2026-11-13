"""T05: document router and text-layer quality gate. No network, no real data needed (synthetic PDFs/CUAD)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import router, text_quality  # noqa: E402

CLEAN = ("The partnership agreed to pay the annual rent for the building and the tenant shall maintain the "
         "premises in good order during the whole term of this lease and report any damage to the landlord.")
DAMAGED = "ine Harbour Water Utillties LLC ruitland Park FL ergeant Ine ountry Club ewport Beach ndustrial Park"
CFG = {"version": 1, "tau_q": 0.6, "w_clipped": 2.0, "w_odd": 2.0, "damaged_families": []}

def make_pdf(text: bytes) -> bytes:
    """Minimal one-page PDF with a Helvetica text line (empty text = a page without a text layer)."""
    stream = b"BT /F1 12 Tf 20 100 Td (" + text + b") Tj ET" if text else b""
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 600 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer<</Size " + str(len(objs) + 1).encode() + b"/Root 1 0 R>>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return bytes(out)


def eb_rec(name="x.pdf", title=None):
    rec = {"doc_id": f"extractbench:short/{name}", "source_dataset": "extractbench",
           "pages": [f"raw\\extractbench\\docs\\short\\{name}"], "schema": {"properties": {"a": {"type": "string"}}}}
    if title:
        rec["schema"]["title"] = title
    return rec


class DataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.docs = self.tmp / "raw" / "extractbench" / "docs" / "short"
        self.docs.mkdir(parents=True)
        (self.tmp / "raw" / "cuad").mkdir(parents=True)
        (self.tmp / "raw" / "cuad" / "CUADv1.json").write_text(json.dumps({"data": [
            {"title": "DOC", "paragraphs": [{"context": CLEAN}, {"context": "second paragraph"}]}]}), encoding="utf-8")
        router._pdftotext.cache_clear()
        router._pypdf.cache_clear()


class QualityTests(unittest.TestCase):
    def test_damaged_scores_below_clean(self):
        clean, cf = text_quality.quality(CLEAN * 2)
        damaged, df = text_quality.quality(DAMAGED * 2)
        self.assertGreater(clean, damaged)
        self.assertGreater(df["clipped_ratio"], cf["clipped_ratio"])
        self.assertGreater(clean, 0.8)

    def test_clipped_tokens_found(self):
        words = text_quality.load_words()
        self.assertTrue(text_quality._is_clipped("ine", words))       # pine
        self.assertTrue(text_quality._is_clipped("ruitland", words) or "fruitland" not in words)
        self.assertFalse(text_quality._is_clipped("water", words))

    def test_odd_characters(self):
        self.assertEqual(text_quality.odd_char_ratio("plain text, 12.50 $ (ok)"), 0.0)
        self.assertGreater(text_quality.odd_char_ratio("a\ufffd\ufffdb\ue000"), 0.5)
        self.assertEqual(text_quality.odd_char_ratio("caf\u00e9 \u201cquoted\u201d \u2014 dash"), 0.0)

    def test_engine_agreement(self):
        self.assertEqual(text_quality.engine_agreement("alpha beta gamma", "gamma beta alpha"), 1.0)
        self.assertEqual(text_quality.engine_agreement("alpha beta", "gamma delta"), 0.0)
        self.assertIsNone(text_quality.engine_agreement("alpha beta", None))
        low = text_quality.score(text_quality.features(CLEAN * 2, "unrelated words entirely different here"))
        self.assertLess(low, text_quality.score(text_quality.features(CLEAN * 2, CLEAN * 2)))

    def test_empty_and_short_text(self):
        self.assertEqual(text_quality.quality("")[0], 0.0)
        self.assertEqual(text_quality.quality(None)[0], 0.0)
        self.assertLess(text_quality.quality("the rent")[0], 0.3)      # too little text to trust

    def test_score_is_deterministic_and_bounded(self):
        a, b = text_quality.quality(CLEAN)[0], text_quality.quality(CLEAN)[0]
        self.assertEqual(a, b)
        self.assertTrue(0.0 <= a <= 1.0)


class RouteTests(DataDir):
    def test_cuad_route(self):
        rec = {"doc_id": "cuad:DOC", "source_dataset": "cuad", "pages": ["raw\\cuad\\CUADv1.json"], "schema": {}}
        r = router.route(rec, self.tmp, config=CFG)
        self.assertEqual((r["route"], r["text_source"]), ("cuad", "cuad"))
        self.assertIn("second paragraph", r["text"])
        self.assertEqual(set(r), {"route", "text", "text_source", "quality", "quality_features"})

    def test_cuad_missing_title_does_not_raise(self):
        rec = {"doc_id": "cuad:NOPE", "source_dataset": "cuad", "pages": [], "schema": {}}
        self.assertEqual(router.route(rec, self.tmp, config=CFG)["route"], "cuad")

    def test_given_text_good_and_damaged(self):
        rec = eb_rec()
        self.assertEqual(router.route(rec, self.tmp, text=CLEAN * 2, config=CFG)["route"], "pdf_text_good")
        self.assertEqual(router.route(rec, self.tmp, text=DAMAGED * 2, config=CFG)["route"], "pdf_text_damaged")
        self.assertEqual(router.route(rec, self.tmp, text=None, config=CFG)["route"], "pdf_no_text")
        self.assertEqual(router.route(rec, self.tmp, text="  \n", config=CFG)["route"], "pdf_no_text")

    def test_flagged_family_is_damaged_even_with_clean_looking_text(self):
        cfg = {**CFG, "damaged_families": ["Schedule K-1 (Form 1065)"]}
        rec = eb_rec(title="Schedule K-1 (Form 1065)")
        r = router.route(rec, self.tmp, text=CLEAN * 2, config=cfg)
        self.assertEqual(r["route"], "pdf_text_damaged")
        self.assertTrue(r["quality_features"]["family_flagged"])
        self.assertEqual(router.route(eb_rec(title="Other"), self.tmp, text=CLEAN * 2, config=cfg)["route"], "pdf_text_good")

    def test_pdf_file_with_text_layer(self):
        text = "The tenant shall maintain the premises and pay the annual rent to the landlord in good order"
        (self.docs / "t.pdf").write_bytes(make_pdf(text.encode()))
        r = router.route(eb_rec("t.pdf"), self.tmp, config={**CFG, "tau_q": 0.0})
        if shutil.which("pdftotext"):
            self.assertEqual(r["text_source"], "pdftotext")
        self.assertIn(r["route"], ("pdf_text_good", "pdf_text_damaged"))
        self.assertIn("tenant", r["text"])

    def test_missing_pdftotext_falls_back_to_pypdf(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf not installed")
        text = "The tenant shall maintain the premises and pay the annual rent to the landlord in good order"
        (self.docs / "t.pdf").write_bytes(make_pdf(text.encode()))
        with mock.patch.object(router.shutil, "which", return_value=None):
            router._pdftotext.cache_clear()
            r = router.route(eb_rec("t.pdf"), self.tmp, config=CFG)
            body = router.pdf_text(self.docs / "t.pdf")
        self.assertEqual(r["text_source"], "pypdf")
        self.assertIn("tenant", r["text"])
        self.assertIn("tenant", body)

    def test_pdftotext_failure_falls_back_to_pypdf(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("pypdf not installed")
        text = "The tenant shall maintain the premises and pay the annual rent to the landlord in good order"
        (self.docs / "t.pdf").write_bytes(make_pdf(text.encode()))
        with mock.patch.object(router.subprocess, "run", side_effect=OSError("boom")):
            router._pdftotext.cache_clear()
            r = router.route(eb_rec("t.pdf"), self.tmp, config=CFG)
        self.assertEqual(r["text_source"], "pypdf")

    def test_corrupted_file_never_raises(self):
        (self.docs / "bad.pdf").write_bytes(b"this is not a pdf at all")
        r = router.route(eb_rec("bad.pdf"), self.tmp, config=CFG)
        self.assertIn(r["route"], ("pdf_corrupted", "pdf_no_text"))
        if shutil.which("pdftoppm"):
            self.assertEqual(r["route"], "pdf_corrupted")
        self.assertIsNone(r["text"])

    def test_empty_file_and_missing_file_never_raise(self):
        (self.docs / "empty.pdf").write_bytes(b"")
        self.assertIn(router.route(eb_rec("empty.pdf"), self.tmp, config=CFG)["route"], ("pdf_corrupted", "pdf_no_text"))
        self.assertEqual(router.route(eb_rec("gone.pdf"), self.tmp, config=CFG)["route"], "pdf_corrupted")
        self.assertEqual(router.route({}, self.tmp, config=CFG)["route"], "pdf_corrupted")
        self.assertEqual(router.route({"source_dataset": "extractbench", "pages": ["../../etc/passwd"]},
                                      self.tmp, config=CFG)["route"], "pdf_corrupted")

    def test_non_pdf_page_is_no_text(self):
        (self.docs / "scan.png").write_bytes(b"\x89PNG")
        self.assertEqual(router.route(eb_rec("scan.png"), self.tmp, config=CFG)["route"], "pdf_no_text")

    def test_renderable_pdf_without_text_is_no_text_not_corrupted(self):
        if not shutil.which("pdftoppm"):
            self.skipTest("pdftoppm not installed")
        (self.docs / "blank.pdf").write_bytes(make_pdf(b""))
        r = router.route(eb_rec("blank.pdf"), self.tmp, config=CFG)
        self.assertEqual(r["route"], "pdf_no_text")

    def test_extract_reuses_router_readers(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("extract4_router_test", ROOT / "4_extract.py")
        ex = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ex)
        self.assertIs(ex.router, router)
        rec = {"doc_id": "cuad:DOC", "source_dataset": "cuad", "pages": [], "schema": {}}
        with mock.patch.object(ex, "DATA", self.tmp):
            self.assertEqual(ex.full_text(rec), CLEAN + "\nsecond paragraph")
        (self.docs / "bad.pdf").write_bytes(b"junk")
        with mock.patch.object(ex, "DATA", self.tmp):
            self.assertIsNone(ex.full_text(eb_rec("bad.pdf")))

    def test_summary_cli(self):
        (self.docs / "bad.pdf").write_bytes(b"junk")
        inp = self.tmp / "in.jsonl"
        inp.write_text(json.dumps(eb_rec("bad.pdf")) + "\n" + json.dumps(
            {"doc_id": "cuad:DOC", "source_dataset": "cuad", "pages": [], "schema": {}}) + "\n", encoding="utf-8")
        env = {**os.environ, "EXTRACT_DATA_DIR": str(self.tmp)}
        p = subprocess.run([sys.executable, "-m", "pipeline.router", "--data", str(inp), "--summary"], cwd=ROOT,
                           env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("2 documents", p.stdout)
        self.assertIn("cuad", p.stdout)


class TuneTests(unittest.TestCase):
    def test_tuning_prefers_recall_within_false_flag_budget(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import tune_quality
        good = text_quality.features(CLEAN * 3)
        bad = text_quality.features(DAMAGED * 3)
        rows = [{"doc_id": f"g{i}", "family": "F", "feats": good, "hit": 1.0, "n_values": 5} for i in range(8)] + \
               [{"doc_id": f"b{i}", "family": "F", "feats": bad, "hit": 0.0, "n_values": 5} for i in range(8)]
        best = tune_quality.tune(rows)
        self.assertEqual((best["fn"], best["fp"]), (0, 0))
        self.assertGreater(best["tau_q"], text_quality.score(bad))
        self.assertLessEqual(best["tau_q"], text_quality.score(good))

    def test_config_file_is_valid_and_gold_free(self):
        cfg = json.loads(router.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertTrue(0.0 < cfg["tau_q"] < 1.0)
        self.assertIsInstance(cfg["damaged_families"], list)


if __name__ == "__main__":
    unittest.main()
