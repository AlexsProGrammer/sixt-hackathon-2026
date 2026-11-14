"""Whitelisted CLI generate actions for the dashboard (pure Python, no Streamlit)."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "results" / "runs"
SESSION_TMP_ROOT = Path(tempfile.gettempdir()) / "project1_dashboard_runs"

_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


@dataclass(frozen=True)
class Action:
    """Definition of a whitelisted CLI action."""

    id: str
    label: str
    icon: str
    help: str
    argv: Callable[[dict[str, Any]], list[str]]
    timeout_s: int
    produces: Callable[[dict[str, Any]], list[Path]]
    confirm: bool = False


def resolve_safe_run_arg(
    run_id_or_dir: str,
    *,
    runs_dir: Path | None = None,
    check_exists: bool = True,
) -> str:
    """Validate a run_id or session run_dir and return a safe argument string."""
    raw = str(run_id_or_dir or "").strip()
    if not raw or ".." in raw:
        raise ValueError(f"Invalid run identifier: {run_id_or_dir!r}")

    rdir = Path(runs_dir) if runs_dir else RUNS_DIR
    if _SAFE_RUN_ID_RE.match(raw):
        target = rdir / raw
        if check_exists and not target.is_dir():
            raise ValueError(f"Run folder not found: {target}")
        return str(target) if runs_dir else raw

    # Allow only resolved paths inside RUNS_DIR or SESSION_TMP_ROOT
    candidate = Path(raw).resolve()
    allowed_roots = (rdir.resolve(), SESSION_TMP_ROOT.resolve())
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ValueError(f"Run path outside allowed roots: {run_id_or_dir!r}")
    if check_exists and not candidate.is_dir():
        raise ValueError(f"Run folder not found: {candidate}")
    return str(candidate)


def _run_target_dir(p: dict[str, Any]) -> Path:
    raw = str(p.get("run_dir") or p.get("run_id") or "")
    if _SAFE_RUN_ID_RE.match(raw):
        return (Path(p["runs_dir"]) if p.get("runs_dir") else RUNS_DIR) / raw
    return Path(raw)


def _arg_run(p: dict[str, Any], key: str = "run_id") -> str:
    val = str(p.get("run_dir") or p.get(key) or "") if key == "run_id" else str(p.get(key) or "")
    return resolve_safe_run_arg(
        val,
        runs_dir=Path(p["runs_dir"]) if p.get("runs_dir") else None,
        check_exists=not bool(p.get("dry_run")),
    )


ACTIONS: dict[str, Action] = {
    "field_table": Action(
        id="field_table",
        label="Build field table",
        icon=":material/table_chart:",
        help="Run `python -m evaluation.field_table <run>` to generate `fields.jsonl`.",
        argv=lambda p: ["-m", "evaluation.field_table", _arg_run(p)],
        timeout_s=900,
        produces=lambda p: [_run_target_dir(p) / "fields.jsonl"],
    ),
    "score_run": Action(
        id="score_run",
        label="Re-score at τ",
        icon=":material/calculate:",
        help="Run `python -m evaluation.registry score <run> --threshold τ`.",
        argv=lambda p: [
            "-m", "evaluation.registry", "score", _arg_run(p),
            "--threshold", f"{float(p.get('threshold', 0.99)):.4f}",
        ],
        timeout_s=600,
        produces=lambda p: [_run_target_dir(p) / "score.json"],
        confirm=True,
    ),
    "report": Action(
        id="report",
        label="Generate report",
        icon=":material/summarize:",
        help="Run `python -m evaluation.report --run <run>` to write `report.md` and `report.json`.",
        argv=lambda p: ["-m", "evaluation.report", "--run", _arg_run(p)],
        timeout_s=900,
        produces=lambda p: [_run_target_dir(p) / "report.md", _run_target_dir(p) / "report.json"],
    ),
    "diff": Action(
        id="diff",
        label="Generate diff report",
        icon=":material/compare_arrows:",
        help="Run `python -m evaluation.report --run <B> --diff <A> <B>` to write `diff.md`.",
        argv=lambda p: [
            "-m", "evaluation.report", "--run", _arg_run(p, "run_b"),
            "--diff", _arg_run(p, "run_a"), _arg_run(p, "run_b"),
        ],
        timeout_s=900,
        produces=lambda p: [_run_target_dir({"run_id": p.get("run_b"), "runs_dir": p.get("runs_dir")}) / "diff.md"],
    ),
    "rebuild_index": Action(
        id="rebuild_index",
        label="Rebuild index",
        icon=":material/sync:",
        help="Run `python -m evaluation.registry rebuild` to refresh `results/runs/index.jsonl`.",
        argv=lambda p: ["-m", "evaluation.registry", "rebuild"],
        timeout_s=300,
        produces=lambda p: [RUNS_DIR / "index.jsonl"],
        confirm=True,
    ),
    "import_legacy": Action(
        id="import_legacy",
        label="Import legacy runs",
        icon=":material/archive:",
        help="Run `python tools/import_legacy_runs.py` to import older runs into the registry.",
        argv=lambda p: ["tools/import_legacy_runs.py"],
        timeout_s=600,
        produces=lambda p: [RUNS_DIR / "index.jsonl"],
        confirm=True,
    ),
    "compare_plots": Action(
        id="compare_plots",
        label="Generate comparison plots",
        icon=":material/bar_chart:",
        help="Run `python tools/compare_results.py` to regenerate `results/plots/*`.",
        argv=lambda p: ["tools/compare_results.py"],
        timeout_s=300,
        produces=lambda p: [ROOT / "results" / "plots"],
    ),
}


def run_action(
    action_id: str,
    params: dict[str, Any] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute a whitelisted action with `shell=False` and return structured results."""
    if action_id not in ACTIONS:
        raise ValueError(f"Unknown action: {action_id!r}")
    action = ACTIONS[action_id]
    p = dict(params or {})
    argv = action.argv(p)

    if p.get("dry_run"):
        return {
            "ok": True,
            "returncode": 0,
            "argv": [sys.executable, *argv],
            "stdout_tail": "",
            "stderr_tail": "",
            "elapsed_s": 0.0,
            "produced": [],
        }

    t0 = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, *argv],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    stdout_lines: list[str] = []
    stderr_text = ""
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                clean = line.rstrip("\n")
                stdout_lines.append(clean)
                if on_line is not None:
                    on_line(clean)
        rc = proc.wait(timeout=action.timeout_s)
        if proc.stderr is not None:
            stderr_text = proc.stderr.read()
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = -1
        stderr_text = f"Timed out after {action.timeout_s}s"

    elapsed = round(time.monotonic() - t0, 2)
    produced = [str(path) for path in action.produces(p) if path.exists()]
    return {
        "ok": rc == 0,
        "returncode": rc,
        "argv": [sys.executable, *argv],
        "stdout_tail": "\n".join(stdout_lines[-40:]),
        "stderr_tail": "\n".join(stderr_text.splitlines()[-30:]),
        "elapsed_s": elapsed,
        "produced": produced,
    }
