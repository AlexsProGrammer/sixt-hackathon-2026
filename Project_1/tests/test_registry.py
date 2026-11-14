"""Run registry (T02): run folders, gold subset, scoring, index, legacy import, --run-dir CLI.

No model and no API: the CLI test uses --abstain-all.
    .venv/bin/python -m unittest discover -s tests -p test_registry.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from evaluation import registry
from tools import import_legacy_runs as legacy

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}}


def rec(doc, a, b, split="dev"):
    return {"doc_id": doc, "source_dataset": "cuad", "split": split, "pages": ["raw\\x.pdf"], "schema": SCHEMA,
            "gold": {"a": a, "b": b}, "gold_evidence": {"a": "x"}, "tags": ["length:short"]}


def pred(doc, a, ca, b, cb):
    return {"doc_id": doc, "fields": {"a": {"value": a, "confidence": ca}, "b": {"value": b, "confidence": cb}}}


def write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


RECS = [rec("d1", "x", "y"), rec("d2", "p", None), rec("d3", "q", "r")]
PREDS = [pred("d1", "x", 1.0, "WRONG", 1.0), pred("d2", "p", 1.0, "halluc", 1.0)]  # d3 not predicted


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runs = self.tmp / "runs"

    def make_run(self, name="t", records=RECS, preds=PREDS):
        run_dir = registry.new_run(name, "dev", ["cli"], runs_dir=self.runs)
        registry.write_inputs(run_dir, records)
        write_jsonl(run_dir / "preds.jsonl", preds)
        return run_dir

    def test_new_run_id_and_run_json(self):
        d = registry.new_run("my name!", "dev", ["cli"], runs_dir=self.runs)
        self.assertRegex(d.name, r"^\d{8}-\d{6}-my-name-[0-9a-f]{6}$")
        run = registry.read_run(d)
        self.assertEqual((run["run_id"], run["split"], run["tags"], run["status"]), (d.name, "dev", ["cli"], "created"))
        self.assertIn("commit", run["git"])
        self.assertEqual(registry.get_run(d.name, self.runs)["path"], str(d))
        with self.assertRaises(KeyError):
            registry.get_run("nope", self.runs)

    def test_write_inputs_strips_gold_and_keeps_doc_ids(self):
        d = self.make_run()
        inp = registry.read_jsonl(d / "input.jsonl")
        gold = registry.read_jsonl(d / "gold.jsonl")
        self.assertEqual([r["doc_id"] for r in inp], ["d1", "d2", "d3"])
        self.assertEqual([r["doc_id"] for r in gold], [r["doc_id"] for r in inp])
        self.assertFalse(any(k.startswith("gold") for r in inp for k in r), "gold leaked into input.jsonl")
        self.assertEqual(registry.read_run(d)["input"]["kind"], "copy")

    def test_write_inputs_without_gold_writes_no_gold_file(self):
        d = registry.new_run("nogold", "hidden", runs_dir=self.runs)
        registry.write_inputs(d, [{k: v for k, v in r.items() if not k.startswith("gold")} for r in RECS])
        self.assertFalse((d / "gold.jsonl").exists())
        with self.assertRaises(FileNotFoundError):
            registry.score_run(d)

    def test_big_input_becomes_reference(self):
        d = registry.new_run("big", "dev", runs_dir=self.runs)
        info = registry.write_inputs(d, RECS, input_ref="data/unified/dev.jsonl", input_sha256="abc", max_copy_bytes=10)
        self.assertEqual((info["kind"], info["input_ref"], info["input_sha256"]), ("ref", "data/unified/dev.jsonl", "abc"))
        self.assertFalse((d / "input.jsonl").exists())
        self.assertTrue((d / "gold.jsonl").exists())

    def test_score_equals_official_scorer_on_matching_gold(self):
        """2 predicted docs out of 3: the run score must equal 5_score.py on a 2-doc gold, not on all 3."""
        d = self.make_run()
        summary = registry.score_run(d, 0.99)
        gold2 = tempfile.NamedTemporaryFile("w", suffix=".jsonl", dir=self.tmp, delete=False)
        gold2.write("".join(json.dumps(r) + "\n" for r in RECS[:2]))
        gold2.close()
        ref = self.tmp / "ref.json"
        p = subprocess.run([sys.executable, str(ROOT / "5_score.py"), "--gold", gold2.name, "--pred",
                            str(d / "preds.jsonl"), "--threshold", "0.99", "--json", str(ref)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        official = json.loads(ref.read_text(encoding="utf-8"))
        mine = json.loads((d / "score.json").read_text(encoding="utf-8"))
        self.assertEqual(mine, official)
        self.assertEqual(summary["n_docs"], 2)
        # d1.a correct, d1.b wrong, d2.a correct, d2.b hallucinated
        self.assertEqual((summary["accepted"], summary["correct"], summary["wrong"], summary["hallucinated"]),
                         (4, 2, 1, 1))
        self.assertEqual(summary["n_fields"], 4)
        # net saving e100: manual 4, system 0*1 + (1+1)*100 = 200 -> (4-200)/4
        self.assertAlmostEqual(summary["net_saving_pct_e100"], -49.0)
        self.assertAlmostEqual(summary["net_saving_pct_e20"], (4 - 40) / 4)
        self.assertAlmostEqual(summary["net_saving_pct_e500"], (4 - 1000) / 4)
        # gold subset now has exactly the doc_ids of preds
        self.assertEqual([r["doc_id"] for r in registry.read_jsonl(d / "gold.jsonl")], ["d1", "d2"])
        self.assertEqual(registry.read_run(d)["summary"]["wrong"], 1)

    def test_score_rejects_predictions_without_gold(self):
        d = self.make_run(preds=PREDS + [pred("zzz", "x", 1.0, "y", 1.0)])
        with self.assertRaises(ValueError):
            registry.score_run(d)

    def test_by_source_in_summary(self):
        d = self.make_run()
        s = registry.score_run(d, 0.99)
        self.assertEqual(s["by_source"]["cuad"]["wrong"], 1)
        self.assertEqual(s["by_source"]["cuad"]["n_fields"], 4)

    def test_index_round_trip_and_upsert(self):
        d = self.make_run("first")
        registry.finish_run(d, "complete")
        registry.score_run(d, 0.99)
        row = registry.append_index(d)
        self.assertEqual(registry.load_index(self.runs), [row])
        self.assertEqual(row["run_id"], d.name)
        for key in ("name", "split", "n_docs", "n_fields", "models", "pipeline_sha256", "prompt_version",
                    "decision_sha256", "threshold", "accepted", "wrong", "hallucinated", "precision", "coverage",
                    "net_saving_pct_e20", "net_saving_pct_e100", "net_saving_pct_e500", "best_threshold_net_e100",
                    "by_source", "tags", "status"):
            self.assertIn(key, row)
        self.assertEqual(row["status"], "complete")
        d2 = self.make_run("second")
        registry.append_index(d2)
        registry.append_index(d)  # same run again: replaced, not duplicated
        self.assertEqual([r["run_id"] for r in registry.load_index(self.runs)], [d2.name, d.name])
        self.assertEqual(len(registry.rebuild_index(self.runs)), 2)

    def test_index_survives_parallel_writers(self):
        dirs = [self.make_run(f"r{i}") for i in range(8)]
        threads = [threading.Thread(target=registry.append_index, args=(d,)) for d in dirs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ids = [r["run_id"] for r in registry.load_index(self.runs)]
        self.assertEqual(sorted(ids), sorted(d.name for d in dirs))

    def test_atomic_write_leaves_no_temp_file(self):
        p = self.tmp / "sub" / "f.json"
        registry.atomic_write_text(p, "{}")
        registry.atomic_write_text(p, '{"a": 1}')
        self.assertEqual(json.loads(p.read_text()), {"a": 1})
        self.assertEqual([x.name for x in p.parent.iterdir()], ["f.json"])

    def test_resolve_run(self):
        d = self.make_run("findme")
        self.assertEqual(registry.resolve_run(d.name, self.runs), d)
        self.assertEqual(registry.resolve_run("findme", self.runs), d)
        with self.assertRaises(KeyError):
            registry.resolve_run("missing", self.runs)


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.results, self.runs = self.tmp / "results", self.tmp / "runs"
        self.results.mkdir()
        self.dev = self.tmp / "dev.jsonl"
        self.test = self.tmp / "test_public.jsonl"
        write_jsonl(self.dev, RECS)
        write_jsonl(self.test, [rec("t1", "a", "b", "test_public")])
        self.gold_files = {"dev": self.dev, "test_public": self.test}

    def run_import(self, **kw):
        return legacy.import_all(self.results, self.runs, self.gold_files, 0.99, **kw)

    def test_import_fake_run_with_and_without_manifest(self):
        write_jsonl(self.results / "fake.jsonl", PREDS)
        write_jsonl(self.results / "fake.diagnostics.jsonl", [{"doc_id": "d1", "diagnostics": {}}])
        (self.results / "fake_score.json").write_text('{"stale": true}')  # must be ignored
        write_jsonl(self.results / "with_man.jsonl", [pred("d1", "x", 1.0, "y", 1.0)])
        (self.results / "with_man.manifest.json").write_text(json.dumps(
            {"run_complete": True, "pipeline": {"model": "m1"}, "fingerprint": {"pipeline_sha256": "h", "prompt_version": "v4"}}))
        write_jsonl(self.results / "empty.jsonl", [])
        write_jsonl(self.results / "foreign.jsonl", [pred("unknown-doc", "x", 1.0, "y", 1.0)])
        write_jsonl(self.results / "t.jsonl", [pred("t1", "a", 1.0, "b", 1.0)])

        res = {r["name"]: r for r in self.run_import()}
        self.assertEqual({k: v["status"] for k, v in res.items()},
                         {"fake": "imported", "foreign": "rejected", "t": "imported", "with_man": "imported"})

        fake = registry.get_run(res["fake"]["run_id"], self.runs)
        self.assertEqual((fake["tags"], fake["provenance"], fake["split"]), (["legacy"], "unknown", "dev"))
        d = Path(fake["path"])
        self.assertEqual([r["doc_id"] for r in registry.read_jsonl(d / "gold.jsonl")], ["d1", "d2"])
        self.assertTrue((d / "diagnostics.jsonl").exists())
        self.assertFalse((d / "manifest.json").exists())
        self.assertEqual(fake["summary"]["n_docs"], 2)
        self.assertEqual(fake["summary"]["wrong"], 1)  # scored against the matching subset, d3 is not counted
        self.assertEqual(fake["summary"]["n_fields"], 4)

        man = registry.get_run(res["with_man"]["run_id"], self.runs)
        self.assertEqual((man["provenance"], man["status"], man["models"]), ("manifest", "complete", ["m1"]))
        self.assertEqual(registry.get_run(res["t"]["run_id"], self.runs)["split"], "test_public")

        index = {r["name"]: r for r in registry.load_index(self.runs)}
        self.assertEqual(set(index), {"fake", "with_man", "t"})
        self.assertEqual(index["with_man"]["prompt_version"], "v4")
        self.assertEqual(index["with_man"]["pipeline_sha256"], "h")

    def test_import_is_idempotent(self):
        write_jsonl(self.results / "fake.jsonl", PREDS)
        self.run_import()
        again = self.run_import()
        self.assertEqual(again[0]["status"], "skipped")
        self.assertEqual(len(list(self.runs.glob("*/run.json"))), 1)
        forced = self.run_import(force=True)
        self.assertEqual(forced[0]["status"], "imported")
        self.assertEqual(len(list(self.runs.glob("*/run.json"))), 1)
        self.assertEqual(len(registry.rebuild_index(self.runs)), 1)


class RunDirCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.inp = self.tmp / "dev.jsonl"
        write_jsonl(self.inp, RECS)

    def cli(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}
        env["EXTRACT_SKIP_DOTENV"] = "1"
        return subprocess.run([sys.executable, "4_extract.py", *args], cwd=ROOT, env=env, capture_output=True,
                              text=True, timeout=120)

    def test_run_dir_collects_everything(self):
        run_dir = self.tmp / "runs" / "20260101-000000-cli-abc123"
        p = self.cli("--data", str(self.inp), "--run-dir", str(run_dir), "--abstain-all", "--run-name", "cli")
        self.assertEqual(p.returncode, 0, p.stderr)
        for name in ("run.json", "input.jsonl", "gold.jsonl", "preds.jsonl", "diagnostics.jsonl", "manifest.json",
                     "score.json"):
            self.assertTrue((run_dir / name).exists(), name)
        run = registry.read_run(run_dir)
        self.assertEqual((run["status"], run["name"], run["split"], run["mode"]), ("complete", "cli", "dev", "abstain_all"))
        self.assertEqual(run["summary"]["accepted"], 0)
        self.assertEqual(run["summary"]["n_docs"], 3)
        self.assertFalse(any(k.startswith("gold") for r in registry.read_jsonl(run_dir / "input.jsonl") for k in r))
        index = registry.load_index(run_dir.parent)
        self.assertEqual([r["run_id"] for r in index], [run_dir.name])
        self.assertEqual(index[0]["status"], "complete")

    def test_limit_scores_only_the_run_subset(self):
        run_dir = self.tmp / "runs" / "limit"
        p = self.cli("--data", str(self.inp), "--run-dir", str(run_dir), "--abstain-all", "--limit", "2")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([r["doc_id"] for r in registry.read_jsonl(run_dir / "gold.jsonl")], ["d1", "d2"])
        self.assertEqual(registry.read_run(run_dir)["summary"]["n_docs"], 2)

    def test_out_outside_run_dir_is_refused(self):
        p = self.cli("--data", str(self.inp), "--run-dir", str(self.tmp / "r"), "--out", str(self.tmp / "o.jsonl"),
                     "--abstain-all")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("inside the run folder", p.stderr)

    def test_without_flag_nothing_changes(self):
        out = self.tmp / "plain.jsonl"
        p = self.cli("--data", str(self.inp), "--out", str(out), "--abstain-all")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(x.name for x in self.tmp.iterdir()),
                         ["dev.jsonl", "plain.diagnostics.jsonl", "plain.jsonl", "plain.manifest.json",
                          "plain.samples.jsonl"])

    def test_out_is_required_without_run_dir(self):
        p = self.cli("--data", str(self.inp), "--abstain-all")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--out is required", p.stderr)


class CompareResultsTests(unittest.TestCase):
    def test_compare_reads_the_index(self):
        spec = importlib.util.spec_from_file_location("compare_results", ROOT / "tools" / "compare_results.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        runs = tmp / "runs"
        for name, status in (("old", "complete"), ("failed", "failed")):
            d = registry.new_run(name, "dev", runs_dir=runs)
            registry.write_inputs(d, RECS)
            write_jsonl(d / "preds.jsonl", PREDS)
            registry.update_run(d, status=status)
            registry.append_index(d)
        rows = mod.discover_runs(runs)
        self.assertEqual([r["name"] for r in rows], ["old"])


if __name__ == "__main__":
    unittest.main()
