"""Pure-Python analytics calculations, verdicts, curve summaries, and UQ profiling (no Streamlit)."""
from __future__ import annotations

import math
from typing import Any

from evaluation import report as eval_report


def break_even_precision(error_cost: float, review_cost: float = 1.0) -> float:
    """Return break-even precision E / (E + review_cost) above which automation saves money."""
    e = float(error_cost)
    r = float(review_cost)
    if e + r <= 0:
        return 1.0
    return e / (e + r)


def verdict(
    precision: float | None,
    net_saving: float | None,
    accepted: int,
    tau: float,
) -> str:
    """Classify a run's outcome at threshold `tau`.

    Returns one of: ``"full_success"``, ``"partial"``, ``"fails"``, ``"no_gold"``.
    """
    if precision is None and net_saving is None:
        return "no_gold"
    if net_saving is not None and net_saving < 0:
        return "fails"
    if (
        accepted > 0
        and precision is not None
        and precision >= tau
        and net_saving is not None
        and net_saving > 0
    ):
        return "full_success"
    return "partial"


def curve_net_saving(point: dict[str, Any], error_cost: float = 100.0, review_cost: float = 1.0) -> float:
    """Compute net saving fraction `(review_cost * accepted - error_cost * errors) / n_fields` for a curve point."""
    n_fields = int(point.get("n_fields") or 0)
    if n_fields <= 0:
        return 0.0
    accepted = int(point.get("accepted") or 0)
    errors = int(point.get("wrong") or 0) + int(point.get("hallucinated") or 0)
    return (float(review_cost) * accepted - float(error_cost) * errors) / n_fields


def point_at_threshold(curve: list[dict[str, Any]], tau: float) -> dict[str, Any] | None:
    """Return the curve point closest to `tau` (preferring exact or smallest >= tau)."""
    if not curve:
        return None
    ordered = sorted(curve, key=lambda p: float(p.get("threshold") or 0.0))
    for pt in ordered:
        if float(pt.get("threshold") or 0.0) >= tau - 1e-9:
            return pt
    return ordered[-1]


def summarize_curve(
    score: dict[str, Any],
    tau: float,
    *,
    error_cost: float = 100.0,
) -> dict[str, Any]:
    """Summarize a run's `score.json` at declared `tau` plus curve-wide averages."""
    curve = list(score.get("curve") or [])
    if not curve:
        declared = score.get("declared") or {}
        prec = declared.get("precision")
        cov = declared.get("coverage")
        acc = int(declared.get("accepted") or 0)
        errs = int(declared.get("wrong") or 0) + int(declared.get("hallucinated") or 0)
        net = declared.get("net_saving_pct")
        return {
            "precision_at_tau": prec,
            "coverage_at_tau": cov,
            "accepted_at_tau": acc,
            "errors_at_tau": errs,
            "net_at_tau": net,
            "avg_precision_curve": prec,
            "avg_net_curve": net,
            "robustness_pct": (1.0 if (net is not None and net > 0) else 0.0) if net is not None else None,
            "best_tau": declared.get("threshold"),
            "best_net": net,
            "coverage_at_99": (score.get("coverage_at_precision") or {}).get("0.99"),
            "wilson_error_ub": eval_report.wilson_upper(errs, acc) if acc > 0 else None,
            "verdict": verdict(prec, net, acc, tau),
            "sparkline": [],
        }

    pt = point_at_threshold(curve, tau) or {}
    acc = int(pt.get("accepted") or 0)
    errs = int(pt.get("wrong") or 0) + int(pt.get("hallucinated") or 0)
    prec = pt.get("precision")
    cov = pt.get("coverage")
    net = curve_net_saving(pt, error_cost=error_cost)

    precs_nonzero = [float(p["precision"]) for p in curve if int(p.get("accepted") or 0) > 0 and p.get("precision") is not None]
    avg_prec = (sum(precs_nonzero) / len(precs_nonzero)) if precs_nonzero else None

    nets_all = [curve_net_saving(p, error_cost=error_cost) for p in curve]
    avg_net = (sum(nets_all) / len(nets_all)) if nets_all else None
    robustness = (sum(1 for x in nets_all if x > 0) / len(nets_all)) if nets_all else None

    best_idx = max(range(len(curve)), key=lambda i: nets_all[i])
    best_tau = float(curve[best_idx].get("threshold") or 0.0)
    best_net = nets_all[best_idx]

    cov_at_p = score.get("coverage_at_precision") or {}
    cov_99 = cov_at_p.get("0.99")
    if isinstance(cov_99, dict):
        cov_99 = cov_99.get("coverage")

    spark = [
        round(curve_net_saving(p, error_cost=error_cost), 4)
        for p in sorted(curve, key=lambda x: float(x.get("threshold") or 0.0))
    ]

    return {
        "precision_at_tau": prec,
        "coverage_at_tau": cov,
        "accepted_at_tau": acc,
        "errors_at_tau": errs,
        "net_at_tau": net,
        "avg_precision_curve": avg_prec,
        "avg_net_curve": avg_net,
        "robustness_pct": robustness,
        "best_tau": best_tau,
        "best_net": best_net,
        "coverage_at_99": cov_99,
        "wilson_error_ub": eval_report.wilson_upper(errs, acc) if acc > 0 else None,
        "verdict": verdict(prec, net, acc, tau),
        "sparkline": spark,
    }


def infer_run_profile(bundle_or_row: dict[str, Any]) -> dict[str, Any]:
    """Infer `(uq_method, samples, models, mode, pipeline, source_of_info)` from a bundle or index row."""
    manifest = bundle_or_row.get("manifest") or {}
    run_meta = bundle_or_row.get("run") or bundle_or_row
    diag_map = bundle_or_row.get("diagnostics") or {}

    mpipe = manifest.get("pipeline") if isinstance(manifest.get("pipeline"), dict) else {}
    models = list(manifest.get("models_used") or run_meta.get("models") or [])
    mode = manifest.get("mode") or run_meta.get("mode") or "unknown"

    if mpipe.get("uq_method"):
        return {
            "uq_method": str(mpipe["uq_method"]),
            "samples": int(mpipe.get("samples") or 1),
            "models": models,
            "mode": str(mode),
            "pipeline": str(mpipe.get("pipeline") or "auto"),
            "source_of_info": "manifest",
        }

    # Check diagnostics.jsonl first entry
    if isinstance(diag_map, dict) and diag_map:
        first_diag = next(iter(diag_map.values())) or {}
        if first_diag.get("uq_method") or first_diag.get("expected_k") or first_diag.get("n_samples"):
            k = int(first_diag.get("expected_k") or first_diag.get("n_samples") or 1)
            uq = first_diag.get("uq_method") or first_diag.get("method") or ("k1_grounded" if k == 1 else "k_entropy")
            return {
                "uq_method": str(uq),
                "samples": k,
                "models": models,
                "mode": str(mode),
                "pipeline": "auto",
                "source_of_info": "diagnostics",
            }

    # Heuristic from run_id / name
    name = str(run_meta.get("name") or run_meta.get("run_id") or "").lower()
    if "base_never" in name:
        return {"uq_method": "baseline: never (inferred)", "samples": 0, "models": models, "mode": "offline", "pipeline": "baseline", "source_of_info": "inferred"}
    if "base_common" in name:
        return {"uq_method": "baseline: most common (inferred)", "samples": 0, "models": models, "mode": "offline", "pipeline": "baseline", "source_of_info": "inferred"}
    if "base_offline" in name:
        return {"uq_method": "baseline: offline (inferred)", "samples": 0, "models": models, "mode": "offline", "pipeline": "baseline", "source_of_info": "inferred"}
    if "probly" in name:
        k = 5 if "5" in name else 3
        return {"uq_method": f"probly K={k} (inferred)", "samples": k, "models": models, "mode": str(mode), "pipeline": "eb/cuad", "source_of_info": "inferred"}
    if "llm" in name:
        return {"uq_method": "k1_grounded (inferred)", "samples": 1, "models": models, "mode": str(mode), "pipeline": "eb/cuad", "source_of_info": "inferred"}

    return {
        "uq_method": "unknown (inferred)",
        "samples": 1,
        "models": models,
        "mode": str(mode),
        "pipeline": "unknown",
        "source_of_info": "inferred",
    }


def group_runs_by_method(run_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate run summaries by `(uq_method, samples)` for the Methods leaderboard."""
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in run_summaries:
        key = (str(row.get("uq_method") or "unknown"), int(row.get("samples") or 0))
        groups.setdefault(key, []).append(row)

    out: list[dict[str, Any]] = []
    for (method, k), items in sorted(groups.items()):
        precs = [x["precision_at_tau"] for x in items if x.get("precision_at_tau") is not None]
        covs = [x["coverage_at_tau"] for x in items if x.get("coverage_at_tau") is not None]
        nets = [x["net_at_tau"] for x in items if x.get("net_at_tau") is not None]
        avg_nets = [x["avg_net_curve"] for x in items if x.get("avg_net_curve") is not None]
        out.append({
            "uq_method": method,
            "samples": k,
            "n_runs": len(items),
            "mean_precision": sum(precs) / len(precs) if precs else None,
            "min_precision": min(precs) if precs else None,
            "max_precision": max(precs) if precs else None,
            "mean_coverage": sum(covs) / len(covs) if covs else None,
            "mean_net": sum(nets) / len(nets) if nets else None,
            "min_net": min(nets) if nets else None,
            "max_net": max(nets) if nets else None,
            "mean_avg_net": sum(avg_nets) / len(avg_nets) if avg_nets else None,
        })
    return out


def compute_ece(bins: list[dict[str, Any]]) -> float | None:
    """Compute Expected Calibration Error from reliability bins."""
    total = sum(int(b.get("count") or 0) for b in bins)
    if total <= 0:
        return None
    ece = sum((int(b["count"]) / total) * abs(float(b["precision"]) - float(b["mean_conf"])) for b in bins)
    return round(ece, 4)


def compute_outcome_counts(fields: list[dict[str, Any]]) -> dict[str, int]:
    """Count fields by outcome (`correct`, `wrong`, `hallucinated`, `missed`, `true_null`)."""
    counts = {"correct": 0, "wrong": 0, "hallucinated": 0, "missed": 0, "true_null": 0}
    for r in fields:
        o = str(r.get("outcome") or "")
        if o in counts:
            counts[o] += 1
    return counts


def compute_uq_signal_stats(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute UQ signal quality breakdowns from `fields.jsonl` rows."""
    agree_buckets: dict[str, dict[str, int]] = {
        "1.00 (unanimous)": {"correct": 0, "wrong": 0, "other": 0},
        "0.67–0.99": {"correct": 0, "wrong": 0, "other": 0},
        "< 0.67": {"correct": 0, "wrong": 0, "other": 0},
    }
    entropy_correct: list[float] = []
    entropy_wrong: list[float] = []
    grounded_stats = {"grounded": {"n": 0, "correct": 0}, "ungrounded": {"n": 0, "correct": 0}}
    cross_view_stats = {"agree": {"n": 0, "correct": 0}, "disagree": {"n": 0, "correct": 0}}

    for r in fields:
        if not r.get("pred_present"):
            continue
        outcome = str(r.get("outcome") or "")
        is_correct = outcome == "correct"
        is_wrong = outcome in ("wrong", "hallucinated")

        ag = r.get("agreement")
        if isinstance(ag, (int, float)) and not math.isnan(float(ag)):
            ag_f = float(ag)
            bname = "1.00 (unanimous)" if ag_f >= 0.999 else ("0.67–0.99" if ag_f >= 0.67 else "< 0.67")
            if is_correct:
                agree_buckets[bname]["correct"] += 1
            elif is_wrong:
                agree_buckets[bname]["wrong"] += 1
            else:
                agree_buckets[bname]["other"] += 1

        ent = r.get("entropy_norm")
        if isinstance(ent, (int, float)) and not math.isnan(float(ent)):
            if is_correct:
                entropy_correct.append(float(ent))
            elif is_wrong:
                entropy_wrong.append(float(ent))

        gt = r.get("grounded_text")
        if gt is True:
            grounded_stats["grounded"]["n"] += 1
            if is_correct:
                grounded_stats["grounded"]["correct"] += 1
        elif gt is False:
            grounded_stats["ungrounded"]["n"] += 1
            if is_correct:
                grounded_stats["ungrounded"]["correct"] += 1

        cva = r.get("cross_view_agree")
        if cva is True:
            cross_view_stats["agree"]["n"] += 1
            if is_correct:
                cross_view_stats["agree"]["correct"] += 1
        elif cva is False:
            cross_view_stats["disagree"]["n"] += 1
            if is_correct:
                cross_view_stats["disagree"]["correct"] += 1

    ratio: float | None = None
    if len(entropy_correct) >= 20 and len(entropy_wrong) >= 20:
        mc = sum(entropy_correct) / len(entropy_correct)
        mw = sum(entropy_wrong) / len(entropy_wrong)
        if mc > 1e-6:
            ratio = round(mw / mc, 2)

    return {
        "agreement_buckets": agree_buckets,
        "entropy_correct": entropy_correct,
        "entropy_wrong": entropy_wrong,
        "entropy_ratio": ratio,
        "grounded_stats": grounded_stats,
        "cross_view_stats": cross_view_stats,
    }


def compute_top_missed_savings(fields: list[dict[str, Any]], threshold: float, top_n: int = 15) -> list[dict[str, Any]]:
    """Group correct-but-not-booked fields by `(family, field)` sorted by count descending."""
    groups: dict[tuple[str, str], int] = {}
    for r in fields:
        conf = r.get("conf_out")
        booked = bool(r.get("pred_present") and conf is not None and float(conf) >= threshold)
        if not booked and r.get("outcome") == "correct":
            key = (str(r.get("family") or "unknown"), str(r.get("field") or "unknown"))
            groups[key] = groups.get(key, 0) + 1
    rows = [{"family": fam, "field": fld, "missed_count": cnt} for (fam, fld), cnt in groups.items()]
    rows.sort(key=lambda x: (-x["missed_count"], x["family"], x["field"]))
    return rows[:top_n]


def compute_top_errors(fields: list[dict[str, Any]], threshold: float, top_n: int = 25) -> list[dict[str, Any]]:
    """Return booked fields whose outcome is `wrong` or `hallucinated`."""
    errs: list[dict[str, Any]] = []
    for r in fields:
        conf = r.get("conf_out")
        booked = bool(r.get("pred_present") and conf is not None and float(conf) >= threshold)
        if booked and r.get("outcome") in ("wrong", "hallucinated"):
            errs.append({
                "doc_id": r.get("doc_id"),
                "field": r.get("field"),
                "family": r.get("family") or "unknown",
                "route": r.get("route") or "unknown",
                "pred_value": r.get("pred_value"),
                "conf_out": conf,
                "outcome": r.get("outcome"),
            })
    errs.sort(key=lambda x: (-float(x.get("conf_out") or 0.0), str(x.get("doc_id") or "")))
    return errs[:top_n]
