"""Internal contract version 2: field observations, samples and plan checks (PROBLY_INTEGRATION_PLAN, section 1).

Pure functions. No I/O, no API calls.

Field statuses
- present     explicit non-null value with a valid confidence, consistent across relevant chunks
- absent      explicit, valid null in every relevant chunk (the only way to say "not in the document")
- invalid     reply without explicit value/confidence, bad confidence, or conflicting values across chunks
- missing     a planned job returned, but the field was not in its reply, or a planned job has no result
- error       the planned job failed (HTTP, timeout, parse, stop)
- unsupported a non-null value that is not grounded in the document text (set by the policy)
- unreadable  the document has no usable text layer (set by the policy)

A failed request or a missing field is never "absent".
"""
from __future__ import annotations

import math

CONTRACT_VERSION = 2
FIELD_STATUSES = ("present", "absent", "invalid", "missing", "error", "unsupported", "unreadable")
VALID_STATUSES = ("present", "absent", "unsupported")  # observations that can take part in a vote


class ContractError(ValueError):
    """A violated internal contract: unplanned/duplicate job results, wrong version, wrong field set."""


def valid_confidence(c: object) -> float | None:
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        return None
    c = float(c)
    return c if math.isfinite(c) and 0.0 <= c <= 1.0 else None


def check_plan(planned_jobs: list[dict], schema: dict) -> None:
    """Planned jobs must have unique ids, integer sample indices and only schema fields."""
    props = schema.get("properties", {})
    seen: set[str] = set()
    for j in planned_jobs:
        jid = j.get("job_id")
        if not isinstance(jid, str) or jid in seen:
            raise ContractError(f"planned job id missing or duplicated: {jid!r}")
        seen.add(jid)
        if not isinstance(j.get("sample_idx"), int) or isinstance(j.get("sample_idx"), bool):
            raise ContractError(f"{jid}: sample_idx must be an integer")
        unknown = [f for f in j.get("field_names", []) if f not in props]
        if unknown:
            raise ContractError(f"{jid}: fields not in schema: {unknown}")


def check_sample(sample: dict, schema: dict) -> list[str]:
    """Structural check of one V2 sample. Returns a list of problems (empty = valid)."""
    problems = []
    if not isinstance(sample, dict):
        return ["sample is not an object"]
    if sample.get("contract_version") != CONTRACT_VERSION:
        problems.append(f"contract_version is {sample.get('contract_version')!r}, expected {CONTRACT_VERSION}")
    if not isinstance(sample.get("sample_idx"), int) or isinstance(sample.get("sample_idx"), bool):
        problems.append("sample_idx must be an integer")
    if not isinstance(sample.get("complete"), bool):
        problems.append("complete must be a boolean")
    fields = sample.get("fields")
    props = set(schema.get("properties", {}))
    if not isinstance(fields, dict):
        return problems + ["fields must be an object"]
    if set(fields) != props:
        problems.append(f"field set differs from schema: missing={sorted(props - set(fields))} "
                        f"extra={sorted(set(fields) - props)}")
    for name, obs in fields.items():
        if not isinstance(obs, dict) or obs.get("status") not in FIELD_STATUSES:
            problems.append(f"{name}: invalid status")
        elif not isinstance(obs.get("complete"), bool):
            problems.append(f"{name}: complete must be a boolean")
    return problems


def check_job_results(job_results: list[dict], planned_jobs: list[dict], sample_idx: int) -> dict[str, dict]:
    """Map job_id -> result for one sample. Unplanned or duplicated results are contract errors."""
    planned_ids = {j["job_id"] for j in planned_jobs if j["sample_idx"] == sample_idx}
    by_id: dict[str, dict] = {}
    for r in job_results:
        if r.get("sample_idx") != sample_idx:
            continue
        jid = r.get("job_id")
        if jid not in planned_ids:
            raise ContractError(f"unplanned job result for sample {sample_idx}: {jid!r}")
        if jid in by_id:
            raise ContractError(f"duplicate job result: {jid!r}")
        by_id[jid] = r
    return by_id
