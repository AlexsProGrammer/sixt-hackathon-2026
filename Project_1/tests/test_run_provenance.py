"""Run provenance: resume binding, incomplete runs, decision-file strictness, no secrets in artefacts.

Uses the real CLI against a local mock endpoint with synthetic data. No real API call.
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_run_provenance.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

from tests.test_integration import CUAD_TEXT, Handler, Mock

ROOT = Path(__file__).resolve().parent.parent
SECRET = "sk-TEST-PROVENANCE-KEY-987"


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/v1"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        Mock.mode, Mock.hits = "ok", []
        data = self.tmp / "data"
        (data / "raw" / "cuad").mkdir(parents=True)
        (data / "raw" / "cuad" / "CUADv1.json").write_text(json.dumps({"data": [
            {"title": "TESTDOC", "paragraphs": [{"context": CUAD_TEXT}]}]}), encoding="utf-8")
        self.data = data
        props = {"f00": {"type": "string", "description": "The licensor name."},
                 "f01": {"type": "string", "description": "An invented field."}}
        self.inp = self.tmp / "input.jsonl"
        self.inp.write_text(json.dumps({"doc_id": "cuad:TESTDOC", "source_dataset": "cuad",
                                        "pages": ["raw\\cuad\\CUADv1.json"],
                                        "schema": {"type": "object", "properties": props}}) + "\n", encoding="utf-8")
        self.cache = self.tmp / "cache"

    def cli(self, args, *, url=None, llm=True, extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}
        env["EXTRACT_SKIP_DOTENV"] = "1"
        env["EXTRACT_DATA_DIR"] = str(self.data)
        if llm:
            env.update({"LLM_BASE_URL": url or self.url, "LLM_API_KEY": SECRET, "LLM_MODEL": "mock-model"})
        env.update(extra_env or {})
        return subprocess.run([sys.executable, "4_extract.py", *args], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=180)

    def args(self, out, *extra):
        return ["--data", str(self.inp), "--out", str(out), "--cache-dir", str(self.cache), "--mode", "llm", *extra]

    def manifest(self, out):
        return json.loads((out.with_suffix("").with_name(out.stem + ".manifest.json")).read_text(encoding="utf-8"))

    def test_complete_run_is_marked_complete_and_leaks_no_secret(self):
        out = self.tmp / "ok.jsonl"
        p = self.cli(self.args(out, "--samples", "3"))
        self.assertEqual(p.returncode, 0, p.stderr)
        man = self.manifest(out)
        self.assertTrue(man["run_complete"])
        self.assertEqual(man["uq"]["method"], "k_agreement_conf")
        self.assertEqual(len(man["segments"]), 1)
        text = (self.tmp / "ok.manifest.json").read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET, p.stdout + p.stderr)
        self.assertEqual(man["fingerprint"]["endpoint_host"], "127.0.0.1:" + str(self.srv_port()))

    def srv_port(self):
        return self.srv.server_address[1]

    def test_identical_resume_is_accepted_and_segments_accumulate(self):
        out = self.tmp / "res.jsonl"
        self.assertEqual(self.cli(self.args(out)).returncode, 0)
        p = self.cli(self.args(out, "--resume"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.manifest(out)["segments"]), 2)

    def test_changed_input_is_rejected_on_resume(self):
        out = self.tmp / "inp.jsonl"
        self.assertEqual(self.cli(self.args(out)).returncode, 0)
        self.inp.write_text(self.inp.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        p = self.cli(self.args(out, "--resume"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("input file, code version or endpoint differs", p.stderr)

    def test_changed_endpoint_is_rejected_on_resume(self):
        out = self.tmp / "ep.jsonl"
        self.assertEqual(self.cli(self.args(out)).returncode, 0)
        other = self.url.replace("127.0.0.1", "localhost")
        p = self.cli(self.args(out, "--resume"), url=other)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("endpoint differs", p.stderr)

    def test_rate_limit_marks_run_incomplete(self):
        Mock.mode = "rate_limit"
        out = self.tmp / "rl.jsonl"
        p = self.cli(self.args(out, "--on-error", "abstain"))
        self.assertEqual(p.returncode, 0, p.stderr)
        man = self.manifest(out)
        self.assertTrue(man["stopped_429"])
        self.assertFalse(man["run_complete"], "a rate-limited run is never complete")

    def test_decision_threshold_out_of_range_is_refused(self):
        dec = self.tmp / "bad_thr.json"
        dec.write_text(json.dumps({"contract_version": 1, "abstain_all": True, "threshold": 1.5}), encoding="utf-8")
        p = self.cli(["--data", str(self.inp), "--out", str(self.tmp / "t.jsonl"), "--decision", str(dec)], llm=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("threshold", p.stderr)

    def test_decision_pipeline_hash_mismatch_is_refused(self):
        pipe = {"workers": 1, "samples": 3, "temperature": 0.7, "chunk_chars": 45000, "overlap_chars": 3000,
                "batch_size": 10, "uq_method": "k_agreement_conf", "sampling": "mixed", "model": "mock-model",
                "prompt_version": "v2"}
        dec = self.tmp / "hash.json"
        dec.write_text(json.dumps({"contract_version": 1, "abstain_all": False, "threshold": 0.9,
                                   "pipeline": pipe, "pipeline_sha256": "0" * 64}), encoding="utf-8")
        p = self.cli(["--data", str(self.inp), "--out", str(self.tmp / "h.jsonl"), "--decision", str(dec)])
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("pipeline_sha256", p.stderr)

    def test_k1_grounded_with_several_samples_is_refused(self):
        p = self.cli(self.args(self.tmp / "k.jsonl", "--samples", "3", "--uq-method", "k1_grounded"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("k1_grounded needs --samples 1", p.stderr)

    def test_entropy_with_one_sample_is_refused(self):
        p = self.cli(self.args(self.tmp / "e.jsonl", "--uq-method", "k_entropy"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("needs --samples 2", p.stderr)

    def test_samples_sidecar_written_for_llm_runs(self):
        out = self.tmp / "side.jsonl"
        self.assertEqual(self.cli(self.args(out, "--samples", "2")).returncode, 0)
        rows = [json.loads(l) for l in (self.tmp / "side.samples.jsonl").read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["samples"]), 2)
        self.assertEqual(rows[0]["samples"][0]["contract_version"], 2)


if __name__ == "__main__":
    unittest.main()
