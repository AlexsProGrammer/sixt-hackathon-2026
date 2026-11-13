"""Integration tests: the real CLI (4_extract.py) as a subprocess against a local mock endpoint.

Synthetic data only (invented contract text with evidence beyond character 60,000, an unreadable "scan").
No real API call: the endpoint is 127.0.0.1. The real .env is never loaded (EXTRACT_SKIP_DOTENV=1).
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p test_integration.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUAD_TEXT = "Header clause. " + "p" * 70_000 + " Acme Corp is the licensor under this agreement. " + "q" * 800


class Mock:
    """Answers like a model: finds 'Acme Corp' in the document part, invents a value for f01."""
    mode = "ok"            # ok | broken | rate_limit
    hits: list = []        # temperatures of received requests

    @classmethod
    def answer(cls, prompt: str) -> str:
        names = re.findall(r"^- (\S+) \(", prompt, re.M)
        part = prompt.split("--- DOCUMENT PART (data) ---\n", 1)[1].split("\n--- END OF DOCUMENT PART ---")[0]
        out = {}
        for n in names:
            if n == "f00" and "Acme Corp" in part:
                out[n] = {"value": "Acme Corp", "confidence": 0.9}
            elif n == "f01":
                out[n] = {"value": "Invented Value", "confidence": 0.99}  # not in the text: must be dropped
            else:
                out[n] = {"value": None, "confidence": 0.0}
        return json.dumps(out)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        Mock.hits.append(body.get("temperature"))
        if Mock.mode == "rate_limit":
            self._send(429, b'{"error":"rate"}', {"Retry-After": "3600"})
            return
        if Mock.mode == "broken":
            content = "Sorry, here is the result without JSON."
        else:
            content = Mock.answer(body["messages"][-1]["content"])
        payload = {"choices": [{"message": {"content": content}}]}
        self._send(200, json.dumps(payload).encode(), {})

    def _send(self, status, data, headers):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class CliTests(unittest.TestCase):
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
        (data / "raw" / "extractbench" / "docs").mkdir(parents=True)
        (data / "raw" / "extractbench" / "docs" / "scan.pdf").write_bytes(b"not a real pdf")
        self.data = data
        props = {"f00": {"type": "string", "description": "The licensor name."},
                 "f01": {"type": "string", "description": "An invented field."}}
        self.inp = self.tmp / "input.jsonl"
        recs = [
            {"doc_id": "cuad:TESTDOC", "source_dataset": "cuad", "pages": ["raw\\cuad\\CUADv1.json"],
             "schema": {"type": "object", "properties": props}},
            {"doc_id": "extractbench:scan", "source_dataset": "extractbench",
             "pages": ["raw\\extractbench\\docs\\scan.pdf"], "schema": {"type": "object", "properties": props}},
        ]
        self.inp.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        self.cache = self.tmp / "cache"

    def run_cli(self, args, *, llm=True, extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}
        env["EXTRACT_SKIP_DOTENV"] = "1"
        env["EXTRACT_DATA_DIR"] = str(self.data)
        if llm:
            env.update({"LLM_BASE_URL": self.url, "LLM_API_KEY": "sk-TEST-INTEGRATION-KEY", "LLM_MODEL": "mock-model"})
        env.update(extra_env or {})
        return subprocess.run([sys.executable, "4_extract.py", *args], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=180)

    def base_args(self, out, *extra):
        return ["--data", str(self.inp), "--out", str(out), "--cache-dir", str(self.cache), *extra]

    def rows(self, path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_k1_happy_path_with_evidence_beyond_60k(self):
        out = self.tmp / "run.jsonl"
        p = self.run_cli(self.base_args(out, "--mode", "llm"))
        self.assertEqual(p.returncode, 0, p.stderr)
        by = {r["doc_id"]: r["fields"] for r in self.rows(out)}
        self.assertEqual(by["cuad:TESTDOC"]["f00"], {"value": "Acme Corp", "confidence": 0.9})
        self.assertEqual(by["cuad:TESTDOC"]["f01"], {"value": None, "confidence": 0.0})
        self.assertEqual(by["extractbench:scan"]["f00"], {"value": None, "confidence": 0.0})
        self.assertEqual(len(Mock.hits), 2, "two chunks x one batch, no request for the scan")
        man = json.loads((self.tmp / "run.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(man["contract_version"], 1)
        self.assertEqual(man["n_written"], 2)
        diag = {r["doc_id"]: r["diagnostics"] for r in self.rows(self.tmp / "run.diagnostics.jsonl")}
        self.assertEqual(diag["extractbench:scan"]["per_field"]["f00"]["reason"], "unreadable")
        self.assertNotIn("sk-TEST-INTEGRATION-KEY", p.stdout + p.stderr)

    def test_k3_uses_temperature_zero_then_configured_and_probly_entropy_zero(self):
        out = self.tmp / "k3.jsonl"
        p = self.run_cli(self.base_args(out, "--mode", "llm", "--samples", "3", "--temperature", "0.7"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(Mock.hits), 6, "3 samples x 2 chunks")
        self.assertEqual(Mock.hits.count(0.0), 2, "sample 0 at temperature 0")
        self.assertEqual(Mock.hits.count(0.7), 4)
        by = {r["doc_id"]: r["fields"] for r in self.rows(out)}
        self.assertEqual(by["cuad:TESTDOC"]["f00"]["value"], "Acme Corp")
        self.assertLessEqual(by["cuad:TESTDOC"]["f00"]["confidence"], 0.9, "agreement never raises confidence")
        diag = {r["doc_id"]: r["diagnostics"] for r in self.rows(self.tmp / "k3.diagnostics.jsonl")}
        self.assertEqual(diag["cuad:TESTDOC"]["per_field"]["f00"]["entropy_nats"], 0.0)
        self.assertEqual(diag["cuad:TESTDOC"]["uq_method"], "k_agreement_conf")
        self.assertTrue(diag["cuad:TESTDOC"]["uq_called"])

    def test_broken_json_fail_mode_leaves_document_unwritten_and_exits_1(self):
        Mock.mode = "broken"
        out = self.tmp / "fail.jsonl"
        p = self.run_cli(self.base_args(out, "--mode", "llm"))
        self.assertEqual(p.returncode, 1)
        ids = [r["doc_id"] for r in self.rows(out)]
        self.assertNotIn("cuad:TESTDOC", ids)
        self.assertIn("--resume", p.stderr)

    def test_broken_json_abstain_mode_writes_nulls_with_diagnosis(self):
        Mock.mode = "broken"
        out = self.tmp / "abstain.jsonl"
        p = self.run_cli(self.base_args(out, "--mode", "llm", "--on-error", "abstain"))
        self.assertEqual(p.returncode, 0, p.stderr)
        by = {r["doc_id"]: r["fields"] for r in self.rows(out)}
        self.assertTrue(all(v["value"] is None and v["confidence"] == 0.0 for v in by["cuad:TESTDOC"].values()))
        diag = {r["doc_id"]: r["diagnostics"] for r in self.rows(self.tmp / "abstain.diagnostics.jsonl")}
        self.assertTrue(any(e.startswith("parse:") for e in diag["cuad:TESTDOC"]["job_failures"]))

    def test_429_stops_the_run_without_further_requests(self):
        Mock.mode = "rate_limit"
        out = self.tmp / "rl.jsonl"
        p = self.run_cli(self.base_args(out, "--mode", "llm", "--samples", "3"))
        self.assertEqual(p.returncode, 1)
        man = json.loads((self.tmp / "rl.manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(man["stopped_429"])
        self.assertEqual(len(Mock.hits), 1, "only the first request is sent; the run stops")
        self.assertEqual(man["requests"], 1)

    def test_config_missing_in_llm_mode_fails_before_output(self):
        out = self.tmp / "noconf.jsonl"
        p = self.run_cli(self.base_args(out, "--mode", "llm"), llm=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("LLM_BASE_URL", p.stderr)
        self.assertIn("LLM_API_KEY", p.stderr)
        self.assertFalse(out.exists())

    def test_abstain_all_needs_no_credentials_and_no_request(self):
        out = self.tmp / "all.jsonl"
        p = self.run_cli(self.base_args(out, "--abstain-all"), llm=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = self.rows(out)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(v == {"value": None, "confidence": 0.0} for r in rows for v in r["fields"].values()))
        self.assertEqual(Mock.hits, [])

    def test_resume_rules_and_identical_pipeline(self):
        out = self.tmp / "res.jsonl"
        self.assertEqual(self.run_cli(self.base_args(out, "--mode", "llm")).returncode, 0)
        again = self.run_cli(self.base_args(out, "--mode", "llm"))
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("--resume", again.stderr)
        other = self.run_cli(self.base_args(out, "--mode", "llm", "--chunk-chars", "20000", "--resume"))
        self.assertNotEqual(other.returncode, 0)
        self.assertIn("pipeline configuration differs", other.stderr)
        before = len(Mock.hits)
        ok = self.run_cli(self.base_args(out, "--mode", "llm", "--resume"))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(len(Mock.hits), before, "resumed documents are not requested again")
        man = json.loads((self.tmp / "res.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(man["n_skipped_resumed"], 2)
        self.assertEqual(len(self.rows(out)), 2)

    def test_second_run_is_served_from_cache(self):
        self.assertEqual(self.run_cli(self.base_args(self.tmp / "c1.jsonl", "--mode", "llm")).returncode, 0)
        first = len(Mock.hits)
        self.assertEqual(self.run_cli(self.base_args(self.tmp / "c2.jsonl", "--mode", "llm")).returncode, 0)
        self.assertEqual(len(Mock.hits), first, "no new requests on identical jobs")
        man = json.loads((self.tmp / "c2.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(man["cache_hits"], 2)

    def test_decision_abstain_all_needs_no_api(self):
        dec = self.tmp / "decision.json"
        dec.write_text(json.dumps({"contract_version": 1, "run_id": "x", "threshold": 1.0,
                                   "abstain_all": True, "method": "all_abstain", "pipeline": None}), encoding="utf-8")
        out = self.tmp / "dec.jsonl"
        p = self.run_cli(self.base_args(out, "--decision", str(dec)), llm=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(Mock.hits, [])

    def test_decision_pipeline_conflict_with_cli_is_an_error(self):
        dec = self.tmp / "decision2.json"
        dec.write_text(json.dumps({"contract_version": 1, "run_id": "x", "threshold": 0.9, "abstain_all": False,
                                   "method": "empirical", "pipeline": {
                                       "model": "mock-model", "prompt_version": "v2", "samples": 1,
                                       "temperature": 0.7, "workers": 1, "chunk_chars": 45000,
                                       "overlap_chars": 3000, "batch_size": 10,
                                       "uq_method": "k1_grounded", "sampling": "mixed"}}), encoding="utf-8")
        p = self.run_cli(self.base_args(self.tmp / "conf.jsonl", "--decision", str(dec), "--chunk-chars", "1000"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("contradict", p.stderr)

    def test_unknown_contract_version_is_rejected(self):
        dec = self.tmp / "decision3.json"
        dec.write_text(json.dumps({"contract_version": 9, "abstain_all": True}), encoding="utf-8")
        p = self.run_cli(self.base_args(self.tmp / "v9.jsonl", "--decision", str(dec)), llm=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("contract_version", p.stderr)

    def test_input_is_gold_free(self):
        self.assertNotIn("gold", self.inp.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
