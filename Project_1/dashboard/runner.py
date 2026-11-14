"""Background runner wrapping `pipeline.extractor.run_file` for session runs."""
from __future__ import annotations

import hashlib
import os
import queue
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dashboard import data
from evaluation import field_table, registry
from pipeline import extractor


def make_session_run_id(name: str = "session") -> str:
    now = datetime.now()
    suffix = hashlib.sha256(f"{name}{now.isoformat()}{os.getpid()}{time.time_ns()}".encode()).hexdigest()[:6]
    return f"{now:%Y%m%d-%H%M%S}-{registry.slug(name)}-{suffix}"


def execute_session_run(
    records: list[dict],
    *,
    run_name: str = "session",
    split: str = "session",
    decision_path: str | Path | None = None,
    config_overrides: dict[str, Any] | None = None,
    threshold: float = registry.DEFAULT_THRESHOLD,
    progress_cb: Callable[[int, int, str, dict], None] | None = None,
    temp_root: Path | None = None,
) -> dict[str, Any]:
    """Run extraction on `records` into an isolated temp T02 run folder (not indexed yet).

    Returns a run bundle dict (with `is_session=True`) ready for Review, Analytics, and
    optional `save_session_run_to_registry`.
    """
    if not records:
        raise ValueError("Cannot run extraction on an empty record list.")

    run_id = make_session_run_id(run_name)
    base_tmp = Path(temp_root) if temp_root else Path(tempfile.gettempdir()) / "project1_dashboard_runs"
    base_tmp.mkdir(parents=True, exist_ok=True)
    run_dir = base_tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    input_path = run_dir / "source_records.jsonl"
    registry.write_jsonl(input_path, [registry.strip_gold(r) for r in records])

    opts: dict[str, Any] = dict(config_overrides or {})
    if decision_path:
        opts["decision"] = str(decision_path)
    config = extractor.load_config(opts)

    registry.init_run_dir(run_dir, name=run_name, split=split, tags=["session"])
    registry.write_inputs(run_dir, records)
    if decision_path and Path(decision_path).is_file():
        registry.update_run(run_dir, decision_sha256=registry.sha256_file(Path(decision_path)))

    out_path = run_dir / "preds.jsonl"
    result = extractor.run_file(
        input_path,
        out_path,
        config,
        run_dir=None,
        run_name=run_name,
        progress=progress_cb,
    )
    for src_name, dst_name in (
        ("preds.diagnostics.jsonl", "diagnostics.jsonl"),
        ("preds.manifest.json", "manifest.json"),
        ("preds.samples.jsonl", "samples.jsonl"),
    ):
        src_p = run_dir / src_name
        if src_p.is_file():
            src_p.replace(run_dir / dst_name)
    manifest = result["manifest"]
    status = "complete" if manifest.get("run_complete") else (
        "failed" if manifest.get("n_written", 0) == 0 else "incomplete"
    )
    registry.finish_run(
        run_dir,
        status,
        n_written=manifest.get("n_written", 0),
        n_requested=manifest.get("n_requested", len(records)),
        models=manifest.get("models_used", []),
        mode=config.mode,
    )

    if (run_dir / "gold.jsonl").is_file() and manifest.get("n_written", 0) > 0:
        registry.score_run(run_dir, threshold=threshold)
        field_table.build_field_table(run_dir, write=True)

    bundle = data.load_run_bundle(run_dir)
    bundle["is_session"] = True
    bundle["saved_to_registry"] = False
    bundle["index_row"] = registry.build_row(run_dir)
    return bundle


def start_session_run_thread(
    records: list[dict],
    **kwargs: Any,
) -> tuple[threading.Thread, queue.Queue]:
    """Start `execute_session_run` in a daemon thread and return `(thread, event_queue)`."""
    q: queue.Queue = queue.Queue()

    def _on_progress(done: int, total: int, doc_id: str, res: dict) -> None:
        q.put(("progress", {"done": done, "total": total, "doc_id": doc_id, "res": res}))

    def _worker() -> None:
        try:
            bundle = execute_session_run(records, progress_cb=_on_progress, **kwargs)
            q.put(("done", bundle))
        except BaseException as exc:
            q.put(("error", f"{type(exc).__name__}: {exc}"))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t, q
