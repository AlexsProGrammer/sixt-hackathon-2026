"""Evaluation harness (T03): grouping, frozen splits, field table vs scorer, LOGO whitelist, Wilson bound, run_batch CLI.

No model and no API: the CLI test uses --abstain-all.
    .venv/bin/python -m unittest discover -s tests -p test_harness.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation import docs, field_table, registry, report, run_batch, splits
from evaluation.partitions import group_of

ROOT = Path(__file__).resolve().parent.parent
SCORER = registry.load_scorer()


def schema(*names, kinds=None):
    kinds = kinds or {}
    return {"type": "object", "title": "Fam", "properties": {n: {"type": "string", **kinds.get(n, {})} for n in names}}


def rec(doc, gold, source="extractbench", title="Fam", tags=None):
    sch = schema(*gold)
    if title:
        sch["title"] = title
    else:
        sch.pop("title")
    return {"doc_id": doc, "source_dataset": source, "split": "dev", "pages": ["raw/none.json"], "schema": sch,
            "gold": gold, "tags": tags or []}


def write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def pf(value, conf=0.99):
    return {"value": value, "confidence": conf}


class GroupOfTest(unittest.TestCase):
    def test_pages(self):
        self.assertEqual(group_of("extractbench:short/07021-2016-p0014"), "extractbench:short/07021-2016")

    def test_rerenders(self):
        ids = {group_of(f"extractbench:short/passcoag-2020-w2-p0002-r{i}") for i in (1, 2, 3, 4)}
        self.assertEqual(ids, {"extractbench:short/passcoag-2020-w2"})
        self.assertEqual(group_of("extractbench:short/passcoag-2020-w2-p0003-r1"),
                         group_of("extractbench:short/passcoag-2020-w2-p0002-r4"))

    def test_corrupted_twin(self):
        self.assertEqual(group_of("extractbench:short/ti_spec_sheet_ne555_timer_corrupted"),
                         group_of("extractbench:short/ti_spec_sheet_ne555_timer"))

    def test_plain_ids_untouched(self):
        self.assertEqual(group_of("cuad:Some Agreement"), "cuad:Some Agreement")


def synthetic_dev(n_groups=60):
    """Two sources, two families, multi-doc groups (pages, re-renders, corrupted twins)."""
    out = []
    for i in range(n_groups):
        if i % 3 == 0:
            out.append(rec(f"cuad:Contract{i}", {"a": "x", "b": "y"}, source="cuad", title=None))
        elif i % 3 == 1:
            for p in range(2):
                out.append(rec(f"extractbench:short/form{i}-p{p:04d}", {"a": "x"}, title="Form A"))
        else:
            out.append(rec(f"extractbench:short/spec{i}", {"a": "x"}, title="Spec"))
            out.append(rec(f"extractbench:short/spec{i}_corrupted", {"a": "x"}, title="Spec", tags=["perception:P1"]))
    return out


class SplitsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dev = synthetic_dev()
        write_jsonl(self.root / "dev.jsonl", self.dev)
        (self.root / "results" / "runs").mkdir(parents=True)

    def build(self, seed=13, **kw):
        return splits.build(self.root / "dev.jsonl", self.root / "splits", seed, root=self.root,
                            runs_dir=self.root / "results" / "runs", force=True, **kw)

    def load(self, name):
        return splits.read_jsonl(self.root / "splits" / f"{name}.jsonl")

    def test_no_group_crosses_splits(self):
        self.build()
        names = ("fit", "select", "audit", "audit2")
        groups = {n: {group_of(r["doc_id"]) for r in self.load(n)} for n in names}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self.assertFalse(groups[a] & groups[b], (a, b))

    def test_cover_every_record_once(self):
        self.build()
        ids = [r["doc_id"] for n in ("fit", "select", "audit", "audit2") for r in self.load(n)]
        self.assertEqual(sorted(ids), sorted(r["doc_id"] for r in self.dev))

    def test_twins_and_pages_stay_together(self):
        self.build()
        where = {r["doc_id"]: n for n in ("fit", "select", "audit", "audit2") for r in self.load(n)}
        for d in where:
            if d.endswith("_corrupted"):
                self.assertEqual(where[d], where[d[: -len("_corrupted")]])

    def test_deterministic_and_manifest(self):
        m1 = self.build(seed=5)
        m2 = self.build(seed=5)
        self.assertEqual({k: v["ids_sha256"] for k, v in m1["splits"].items()},
                         {k: v["ids_sha256"] for k, v in m2["splits"].items()})
        m3 = self.build(seed=6)
        self.assertNotEqual(m1["splits"]["audit"]["ids_sha256"], m3["splits"]["audit"]["ids_sha256"])
        for key in ("n_docs", "by_source", "by_family", "by_perception", "file_sha256"):
            self.assertIn(key, m1["splits"]["fit"])

    def test_split_shares_roughly_50_25_25(self):
        m = self.build()
        n = sum(m["splits"][s]["n_docs"] for s in ("fit", "select", "audit", "audit2"))
        self.assertAlmostEqual((m["splits"]["fit"]["n_docs"] + m["splits"]["audit2"]["n_docs"]) / n, 0.5, delta=0.12)
        self.assertGreater(m["splits"]["select"]["n_docs"], 0)
        self.assertGreater(m["splits"]["audit"]["n_docs"], 0)

    def test_seen_documents_never_in_audit(self):
        self.build()
        audit = self.load("audit")
        seen_file = self.root / "seen.jsonl"
        write_jsonl(seen_file, audit)
        self.build(extra_seen=[str(seen_file)])
        audit_groups = {group_of(r["doc_id"]) for r in self.load("audit")}
        self.assertFalse(audit_groups & {group_of(r["doc_id"]) for r in audit})

    def test_audit2_excludes_groups_a_model_run_saw(self):
        m = self.build()
        fit_ids = [r["doc_id"] for r in self.load("fit")] + [r["doc_id"] for r in self.load("audit2")]
        run = registry.new_run("model-run", "x", runs_dir=self.root / "results" / "runs")
        write_jsonl(run / "preds.jsonl", [{"doc_id": d, "fields": {}} for d in fit_ids])
        m2 = self.build()
        self.assertEqual(m2["audit2"]["n_groups"], 0)
        self.assertGreaterEqual(m["audit2"]["n_groups"], 1)

    def test_baseline_runs_do_not_consume_audit2(self):
        run = registry.new_run("base_never", "x", runs_dir=self.root / "results" / "runs")
        write_jsonl(run / "preds.jsonl", [{"doc_id": r["doc_id"], "fields": {}} for r in self.dev])
        m = self.build()
        self.assertGreaterEqual(m["audit2"]["n_groups"], 1)

    def test_refuses_to_overwrite_frozen_manifest(self):
        self.build()
        with self.assertRaises(SystemExit):
            splits.build(self.root / "dev.jsonl", self.root / "splits", 13, root=self.root,
                         runs_dir=self.root / "results" / "runs")

    def test_hash_checked_on_load(self):
        self.build()
        self.assertTrue(splits.load_split("fit", self.root / "splits"))
        with open(self.root / "splits" / "fit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(self.dev[0]) + "\n")
        with self.assertRaises(SystemExit):
            splits.load_split("fit", self.root / "splits")

    def test_stratified_sample(self):
        s1 = splits.stratified_sample(self.dev, 20, seed=3)
        s2 = splits.stratified_sample(self.dev, 20, seed=3)
        self.assertEqual([r["doc_id"] for r in s1], [r["doc_id"] for r in s2])
        self.assertEqual(len(s1), 20)
        self.assertEqual({r["source_dataset"] for r in s1}, {"cuad", "extractbench"})

    def test_family_naming(self):
        self.assertEqual(docs.family_of({"source_dataset": "cuad", "doc_id": "cuad:x", "schema": {}}), "cuad")
        self.assertEqual(docs.family_of(rec("extractbench:short/a", {"a": "1"}, title="Form A")), "Form A")
        r = rec("extractbench:short/census_statab_income", {"a": "1"}, title=None)
        self.assertEqual(docs.family_of(r), "stem:census_statab")
        self.assertEqual(docs.perception_of(rec("x", {"a": "1"}, tags=["perception:P3", "perception:P2"])), "P2+P3")
        self.assertEqual(docs.perception_of(rec("x", {"a": "1"})), "P0")


GOLD_RECS = [
    rec("d1", {"a": "x", "b": "y", "c": None, "d": "z"}),
    rec("d2", {"a": "x", "b": "y", "c": None, "d": "z"}),
]
PREDS = [
    {"doc_id": "d1", "fields": {"a": pf("x"), "b": pf("WRONG"), "c": pf("halluc"), "d": pf(None, 0.0)}},
    {"doc_id": "d2", "fields": {"a": pf("x", 0.5), "b": pf("y"), "c": pf(None, 0.0), "d": pf("z")}},
]


class FieldTableTest(unittest.TestCase):
    def make_run(self, recs=GOLD_RECS, preds=PREDS, threshold=0.0):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        run = registry.new_run("t", "dev", runs_dir=Path(self.tmp.name))
        registry.write_inputs(run, recs)
        write_jsonl(run / "preds.jsonl", preds)
        registry.score_run(run, threshold)
        return run

    def test_labels_equal_scorer_counts(self):
        run = self.make_run()
        rows = field_table.build_field_table(run, text_fn=lambda r: "x y z")
        counts = field_table.outcome_counts(rows)
        z = json.loads((run / "score.json").read_text())["at_threshold_0"]
        self.assertEqual((counts["correct"], counts["wrong"], counts["hallucinated"], counts["missed"], counts["true_null"]),
                         (z["correct"], z["wrong"], z["hallucinated"], z["missed"], z["true_null"]))
        self.assertEqual(len(rows), z["n_fields"])
        self.assertEqual(counts, {"correct": 4, "wrong": 1, "hallucinated": 1, "missed": 1, "true_null": 1})

    def test_row_schema(self):
        run = self.make_run()
        rows = field_table.build_field_table(run, text_fn=lambda r: "x y z")
        row = next(r for r in rows if r["doc_id"] == "d1" and r["field"] == "a")
        for key in ("doc_id group source family perception field kind normalizer route pred_value pred_present "
                    "conf_out model_conf n_views agreement entropy_norm grounded_text grounded_ocr cross_view_agree "
                    "value_len text_quality has_text gold_present match outcome").split():
            self.assertIn(key, row)
        self.assertEqual((row["outcome"], row["conf_out"], row["grounded_text"], row["has_text"]), ("correct", 0.99, True, True))
        miss = next(r for r in rows if r["doc_id"] == "d1" and r["field"] == "d")
        self.assertEqual((miss["outcome"], miss["conf_out"], miss["pred_value"]), ("missed", None, None))
        self.assertTrue(next(r for r in rows if r["doc_id"] == "d1" and r["field"] == "b")["grounded_text"] is False)

    def test_no_text_means_not_grounded(self):
        run = self.make_run()
        rows = field_table.build_field_table(run, text_fn=lambda r: None)
        self.assertFalse(any(r["grounded_text"] for r in rows))
        self.assertTrue(all(r["route"] == "pdf_no_text" for r in rows))

    def test_diagnostics_and_samples_features(self):
        run = self.make_run()
        write_jsonl(run / "diagnostics.jsonl", [{"doc_id": "d1", "diagnostics": {"per_field": {
            "a": {"k_valid": 3, "agreement": 1.0, "entropy_norm": 0.0}}}}])
        write_jsonl(run / "samples.jsonl", [{"doc_id": "d1", "samples": [
            {"fields": {"a": {"status": "present", "model_confidence": 0.9}}},
            {"fields": {"a": {"status": "present", "model_confidence": 0.7}}}]}])
        row = next(r for r in field_table.build_field_table(run, text_fn=lambda r: "x") if r["doc_id"] == "d1" and r["field"] == "a")
        self.assertEqual((row["n_views"], row["agreement"], row["entropy_norm"], row["model_conf"], row["cross_view_agree"]),
                         (3, 1.0, 0.0, 0.7, True))

    def test_written_and_registered(self):
        run = self.make_run()
        field_table.build_field_table(run, text_fn=lambda r: "x")
        self.assertEqual(len(registry.read_jsonl(run / "fields.jsonl")), 8)
        self.assertEqual(registry.read_run(run)["fields_contract_version"], field_table.FIELDS_CONTRACT_VERSION)


def frow(group, family, field, ok, grounded=True, conf=0.99, present=True):
    outcome = "correct" if ok else "wrong"
    if not present:
        outcome = "missed"
    return {"doc_id": f"{group}-p1", "group": group, "source": "extractbench", "family": family, "perception": "P0",
            "field": field, "kind": "string", "route": "text_ok", "pred_present": present,
            "conf_out": conf if present else None, "grounded_text": grounded and present, "grounded_ocr": None,
            "cross_view_agree": None, "match": ok and present, "outcome": outcome, "gold_present": True}


class LogoTest(unittest.TestCase):
    def test_never_uses_own_group(self):
        # three correct rows in groups g1..g3 and one wrong row in g4: g4 sees three clean OTHER groups and is
        # booked (and counted as wrong); g1 sees g4's error and is rejected. A leak (own row included) would
        # reject g4 itself too and book nothing wrong.
        rows = [frow(f"g{i}", "F", "a", True) for i in (1, 2, 3)] + [frow("g4", "F", "a", False)]
        dec = {r["group"]: why for r, why in report.logo_decisions(rows, min_n=3, min_groups=1)}
        self.assertEqual(dec["g4"], "booked")
        self.assertEqual({dec[g] for g in ("g1", "g2", "g3")}, {"cell_has_errors"})

    def test_own_group_error_does_not_block_itself(self):
        # a group with two rows: one wrong, one correct. Neither blocks the other (same group), both see 3 clean groups.
        rows = [frow(f"g{i}", "F", "a", True) for i in (1, 2, 3)] + [frow("g4", "F", "a", False), frow("g4", "F", "a", True)]
        dec = [why for r, why in report.logo_decisions(rows, min_n=3, min_groups=1) if r["group"] == "g4"]
        self.assertEqual(dec, ["booked", "booked"])

    def test_matches_brute_force_recomputation(self):
        import random
        rnd = random.Random(1)
        rows = [frow(f"g{rnd.randrange(8)}", rnd.choice("AB"), rnd.choice("ab"), rnd.random() > 0.15,
                     grounded=rnd.random() > 0.2, conf=rnd.choice([0.5, 0.99])) for _ in range(300)]
        for params in ({"min_n": 2, "min_groups": 1, "evidence": "grounded_text"},
                       {"min_n": 3, "min_groups": 3, "evidence": "none", "conf": 0.9}):
            fast = {id(r): why for r, why in report.logo_decisions(rows, **params)}
            for r in rows:
                cand = [o for o in rows if o["pred_present"] and report.passes_evidence(o, params["evidence"])
                        and o["conf_out"] >= params.get("conf", 0.0)
                        and (o["family"], o["field"]) == (r["family"], r["field"]) and o["group"] != r["group"]]
                is_cand = r["pred_present"] and report.passes_evidence(r, params["evidence"]) and r["conf_out"] >= params.get("conf", 0.0)
                want = (is_cand and len(cand) >= params["min_n"] and len({o["group"] for o in cand}) >= params["min_groups"]
                        and all(o["match"] for o in cand))
                self.assertEqual(fast[id(r)] == "booked", want)

    def test_evidence_requirement(self):
        rows = [frow(f"g{i}", "F", "a", True, grounded=False) for i in range(5)]
        self.assertEqual(report.simulate(rows, evidence="grounded_text", min_n=3)["booked"], 0)
        self.assertEqual(report.simulate(rows, evidence="none", min_n=3)["booked"], 5)

    def test_min_groups(self):
        rows = [frow("g1", "F", "a", True) for _ in range(6)] + [frow("g2", "F", "a", True) for _ in range(3)]
        dec = {r["group"]: why for r, why in report.logo_decisions(rows, min_n=3, min_groups=2)}
        self.assertEqual(dec["g1"], "too_few_groups")  # g1 sees only g2: 3 rows, 1 group
        rows += [frow(f"h{i}", "F", "a", True) for i in range(3)]
        dec = {r["group"]: why for r, why in report.logo_decisions(rows, min_n=3, min_groups=2)}
        self.assertEqual(dec["g1"], "booked")


class StatsTest(unittest.TestCase):
    def test_wilson(self):
        self.assertIsNone(report.wilson_upper(0, 0))
        self.assertAlmostEqual(report.wilson_upper(0, 375), 0.0101, places=3)   # 1.0% for 0 errors in 375
        self.assertAlmostEqual(report.wilson_upper(0, 10), 0.2775, places=3)
        self.assertGreater(report.wilson_upper(5, 100), 0.05)
        self.assertLessEqual(report.wilson_upper(100, 100), 1.0)

    def test_net_saving_matches_scorer(self):
        m = {"threshold": 0.0, "n_fields": 1000, "accepted": 60, "correct": 55, "wrong": 4, "hallucinated": 1}
        for e in (20, 100, 500):
            self.assertAlmostEqual(report.net_saving(60, 5, 1000, e), SCORER.net_saving(m, 1.0, float(e))["saving_pct"])

    def test_missed_savings_reasons(self):
        rows = [frow(f"g{i}", "F", "a", True) for i in range(4)]
        rows += [frow("s1", "Small", "b", True)]                      # cell too small
        rows += [frow("u1", "F", "c", True, grounded=False)]          # no evidence
        rows += [frow("u2", "F", "d", True, conf=0.2)]                # below confidence floor (conf=0.5)
        rows += [frow("n1", "F", "e", True, present=False)]           # no prediction (match False: not counted)
        ms = report.missed_savings(rows, min_n=3, min_groups=1, evidence="grounded_text", conf=0.5)
        self.assertEqual(ms["by_reason"], {"cell_too_small": 1, "no_evidence": 1, "below_confidence": 1})
        self.assertEqual(ms["correct_not_booked"], 3)

    def test_report_on_field_rows(self):
        rows = [frow(f"g{i}", "F", "a", True) for i in range(6)] + [frow("b", "F", "z", False, grounded=False)]
        rep = report.build_report(rows)
        self.assertEqual(rep["whitelist"]["booked"], 6)
        self.assertEqual(rep["whitelist"]["wrong"], 0)
        self.assertIn("Leave-one-group-out", report.to_markdown(rep, "t"))
        self.assertTrue(json.dumps(rep))


class RunBatchCliTest(unittest.TestCase):
    def test_abstain_all_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            dev = synthetic_dev(18)
            write_jsonl(d / "dev.jsonl", dev)
            runs = d / "runs"
            r = subprocess.run([sys.executable, "-m", "evaluation.run_batch", "--input", str(d / "dev.jsonl"),
                                "--random", "7", "--seed", "2", "--name", "cli-test", "--runs-dir", str(runs),
                                "--abstain-all"],
                               cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "EXTRACT_SKIP_DOTENV": "1"})
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            run_dir = next(runs.glob("*-cli-test-*"))
            for f in ("run.json", "preds.jsonl", "gold.jsonl", "score.json", "manifest.json", "fields.jsonl",
                      "report.md", "report.json"):
                self.assertTrue((run_dir / f).exists(), f)
            self.assertEqual(len(registry.read_jsonl(run_dir / "preds.jsonl")), 7)
            self.assertEqual(len(registry.read_jsonl(run_dir / "gold.jsonl")), 7)
            run = registry.read_run(run_dir)
            self.assertEqual(run["status"], "complete")
            self.assertEqual(run["selection"]["random"], 7)
            rows = registry.read_jsonl(run_dir / "fields.jsonl")
            z = json.loads((run_dir / "score.json").read_text())["at_threshold_0"]
            self.assertEqual(len(rows), z["n_fields"])
            self.assertEqual(sum(r["outcome"] == "missed" for r in rows), z["missed"])
            self.assertEqual(len(registry.load_index(runs)), 1)

    def test_rejects_conflicting_forwarded_options(self):
        r = subprocess.run([sys.executable, "-m", "evaluation.run_batch", "--split", "smoke", "--name", "x", "--limit", "1",
                            "--out", "foo"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()


class DiffTest(unittest.TestCase):
    """--diff: per-field outcome transitions between two runs (T06 prompt regression set)."""

    @staticmethod
    def row(doc, field, outcome, value="v", family="Fam", kind="string", route="pdf_text_good"):
        present = outcome not in ("missed", "true_null")
        return {"doc_id": doc, "group": doc.split(":")[0], "source": "extractbench", "family": family,
                "perception": "P0", "field": field, "kind": kind, "route": route, "pred_value": value if present else None,
                "pred_present": present, "conf_out": 0.9 if present else None, "model_conf": None, "n_views": None,
                "agreement": None, "entropy_norm": None, "grounded_text": present, "grounded_ocr": None,
                "cross_view_agree": None, "value_len": 1, "text_quality": 1.0, "text_source": "pdftotext",
                "has_text": True, "gold_present": outcome not in ("hallucinated", "true_null"),
                "match": outcome == "correct", "outcome": outcome}

    def test_transitions_and_regressions(self):
        a = [self.row("d1", "f", "correct", "x"), self.row("d1", "g", "wrong"), self.row("d2", "h", "missed")]
        b = [self.row("d1", "f", "wrong", "y"), self.row("d1", "g", "correct"), self.row("d2", "h", "correct")]
        d = report.diff_field_tables(a, b, name_a="A", name_b="B")
        self.assertEqual(d["transitions"]["correct->wrong"], 1)
        self.assertEqual(d["transitions"]["wrong->correct"], 1)
        self.assertEqual(d["transitions"]["missed->correct"], 1)
        self.assertEqual(d["n_regressions"], 1)
        self.assertEqual(d["regressions"][0]["field"], "f")
        self.assertEqual(d["n_fixes"], 2)
        self.assertEqual(d["by_field"]["f"], {"correct->wrong": 1})
        self.assertEqual(d["at0_b"]["correct"], 2)

    def test_only_in_one_run_counts_as_missed(self):
        a = [self.row("d1", "f", "correct")]
        b = []                       # run B has no prediction for d1:f at all
        d = report.diff_field_tables(a, b, name_a="A", name_b="B")
        self.assertEqual(d["transitions"]["correct->missed"], 1)
        self.assertEqual(d["n_fields_only_a"], 1)

    def test_write_diff_writes_report_files(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        runs = []
        for rows in ([self.row("d1", "f", "correct")], [self.row("d1", "f", "wrong")]):
            run = Path(tmp.name) / f"run{len(runs)}"
            run.mkdir()
            registry.write_jsonl(run / "fields.jsonl", rows)
            runs.append(run)
        d = report.write_diff(*runs)
        self.assertTrue((runs[1] / "diff.md").exists())
        self.assertTrue((runs[1] / "diff.json").exists())
        self.assertEqual(d["n_regressions"], 1)

    def test_run_batch_source_filter(self):
        import argparse
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "in.jsonl"
        recs = [{"doc_id": "extractbench:a", "source_dataset": "extractbench", "pages": ["raw/x.pdf"], "schema": {}},
                {"doc_id": "cuad:x", "source_dataset": "cuad", "pages": [], "schema": {}},
                {"doc_id": "extractbench:b", "source_dataset": "extractbench", "pages": ["raw/y.pdf"], "schema": {}}]
        path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        ns = argparse.Namespace(split=None, input=str(path), random=None, limit=None, seed=13, source="extractbench")
        sel, info = run_batch.select_records(ns)
        self.assertEqual([r["doc_id"] for r in sel], ["extractbench:a", "extractbench:b"])
        self.assertEqual(info["source"], "extractbench")
