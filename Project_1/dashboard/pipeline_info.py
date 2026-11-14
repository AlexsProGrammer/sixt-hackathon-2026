"""Pure-Python pipeline, model, route, and Mermaid diagram builder (no Streamlit)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline import eb_pipeline, extractor, models as model_registry, router

ROOT = Path(__file__).resolve().parent.parent
ROUTER_CONFIG_PATH = ROOT / "pipeline" / "router_config.json"


@dataclass
class PipelineDescription:
    """Resolved description of the active extraction + UQ pipeline."""

    decision_path: str | None
    contract_version: int | None
    abstain_all: bool
    threshold: float | None
    method: str | None
    mode: str
    uq_method: str | None
    samples: int | None
    has_selector: bool = False
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    routes: list[dict[str, Any]] = field(default_factory=list)
    router_gate: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _read_json_safe(path: Path | None) -> dict[str, Any]:
    if not path or not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def _load_router_gate() -> dict[str, Any]:
    raw = _read_json_safe(ROUTER_CONFIG_PATH)
    damaged = raw.get("damaged_families") or []
    return {
        "tau_q": raw.get("tau_q"),
        "damaged_families_count": len(damaged) if isinstance(damaged, list) else 0,
        "tuned_on": (raw.get("tuned_on") or {}).get("file"),
    }


def _resolve_models(dec: dict[str, Any], overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    extractor.load_env(ROOT / ".env")
    env_roles = model_registry.model_roles(os.environ)
    dec_models = dec.get("models") if isinstance(dec.get("models"), dict) else {}
    override_model = (overrides.get("model") or "").strip() if overrides else ""

    resolved: dict[str, dict[str, Any]] = {}
    role_order = ("A", "B", "C", "OCR", "default")
    for role in role_order:
        name: str | None = None
        source = "unset"
        if role == "default" and override_model:
            name = override_model
            source = "override"
        elif dec_models.get(role):
            name = str(dec_models[role])
            source = "decision.json"
        elif role == "OCR" and env_roles.get("ocr"):
            name = str(env_roles["ocr"])
            source = "env"
        elif role in env_roles and env_roles.get(role):
            name = str(env_roles[role])
            source = "env"
        elif role == "A":
            name = eb_pipeline.DEFAULT_MODEL_A
            source = "default"
        elif role == "B":
            name = eb_pipeline.DEFAULT_MODEL_B
            source = "default"

        spec = model_registry.model_spec(name) if name else {}
        resolved[role] = {
            "role": role,
            "name": name,
            "source": source,
            "family": spec.get("family", "unknown") if name else "—",
            "supports": spec.get("supports", {}) if name else {},
            "max_context_chars": spec.get("max_context_chars") if name else None,
            "probed_at": spec.get("probed_at") if name else None,
        }
    return resolved


def describe(decision_path: str | None = None, overrides: dict[str, Any] | None = None) -> PipelineDescription:
    """Describe pipeline, models, routes, and warnings for a decision file + optional overrides."""
    ov = dict(overrides or {})
    dec_p = Path(decision_path) if decision_path else None
    dec = _read_json_safe(dec_p)
    warnings: list[str] = []

    contract_version = dec.get("contract_version") if dec else None
    abstain_all = bool(dec.get("abstain_all", False)) if dec else False
    dec_tau = dec.get("threshold")
    threshold = float(dec_tau) if isinstance(dec_tau, (int, float)) else None
    raw_method = dec.get("method")
    method = (str(raw_method)[:80] + "…") if isinstance(raw_method, str) and len(raw_method) > 80 else raw_method
    has_selector = bool(dec.get("selector") or dec.get("selector_path"))

    if abstain_all:
        warnings.append("abstain_all is enabled in the decision file: nothing will be booked automatically.")

    # Attempt full config resolution via extractor.load_config
    cfg_routes: dict[str, dict[str, Any]] = {}
    cfg_samples = ov.get("samples")
    cfg_uq = ov.get("uq_method")
    cfg_mode = str(ov.get("mode") or "auto")

    try:
        opts = dict(ov)
        if dec_p and dec_p.is_file():
            opts["decision"] = str(dec_p)
        cfg = extractor.load_config(opts)
        cfg_routes = dict(getattr(cfg, "routes", {}) or {})
        cfg_samples = getattr(cfg, "samples", cfg_samples)
        cfg_uq = getattr(cfg, "uq_method", cfg_uq)
        cfg_mode = getattr(cfg, "mode", cfg_mode)
    except BaseException as exc:  # noqa: BLE001 — load_config may raise SystemExit on missing env/invalid combo
        if dec.get("routes") and isinstance(dec["routes"], dict):
            cfg_routes = dec["routes"]
        if exc.__class__ is SystemExit and str(exc):
            warnings.append(f"Config note: {exc}")

    if cfg_samples is None:
        meas = dec.get("measurement") if isinstance(dec.get("measurement"), dict) else {}
        cfg_samples = meas.get("samples") or extractor.DEFAULTS["samples"]
    if cfg_uq is None:
        cfg_uq = "k1_grounded" if int(cfg_samples or 1) == 1 else "k_entropy"

    routes_list: list[dict[str, Any]] = []
    for rname in router.ROUTES:
        rcfg = cfg_routes.get(rname) if isinstance(cfg_routes.get(rname), dict) else {}
        if rname == "cuad":
            default_pipe = "cuad"
            default_views = ["default"]
            default_prompt = "cuad"
        else:
            default_pipe = "eb"
            default_views = list(eb_pipeline.ROUTE_VIEWS.get(rname, ("A-pdf",)))
            default_prompt = "eb"

        if abstain_all:
            active = False
        elif cfg_routes:
            active = rname in cfg_routes
        else:
            active = True

        routes_list.append({
            "route": rname,
            "pipeline": rcfg.get("pipeline") or default_pipe,
            "views": list(rcfg.get("views") or default_views),
            "samples": int(rcfg.get("samples") or cfg_samples or 1),
            "uq_method": rcfg.get("uq_method") or cfg_uq,
            "prompt": rcfg.get("prompt") or default_prompt,
            "active": active,
        })

    return PipelineDescription(
        decision_path=str(dec_p) if dec_p else None,
        contract_version=contract_version,
        abstain_all=abstain_all,
        threshold=threshold,
        method=method if isinstance(method, str) else None,
        mode=cfg_mode,
        uq_method=str(cfg_uq) if cfg_uq else None,
        samples=int(cfg_samples) if cfg_samples is not None else None,
        has_selector=has_selector,
        models=_resolve_models(dec, ov),
        routes=routes_list,
        router_gate=_load_router_gate(),
        warnings=warnings,
    )


def _esc(text: Any) -> str:
    """Escape Mermaid node/edge labels so quotes and parens never break syntax."""
    return str(text).replace('"', "'").replace("\n", " ").strip()


def _short_model(name: str | None) -> str:
    if not name:
        return "unset"
    return str(name).split("/")[-1]


def build_mermaid(
    desc: PipelineDescription,
    *,
    threshold: float,
    route_counts: dict[str, int] | None = None,
) -> str:
    """Build a dynamic Mermaid flowchart reflecting active models, routes, UQ, and τ."""
    tau_q = desc.router_gate.get("tau_q")
    tau_q_str = f"tau_q={tau_q:.2f}" if isinstance(tau_q, (int, float)) else "quality gate"

    model_a = _short_model((desc.models.get("A") or {}).get("name"))
    model_b = _short_model((desc.models.get("B") or {}).get("name"))
    model_def = _short_model((desc.models.get("default") or {}).get("name"))
    if model_def == "unset":
        model_def = model_a

    uq_label = f"{desc.uq_method or 'auto'} · K={desc.samples or 1}"
    sel_label = "Selector" if desc.has_selector else f"Threshold tau = {threshold:.2f}"

    lines = [
        "flowchart LR",
        "    classDef active fill:#FFF1E8,stroke:#FF5F00,color:#0F172A,stroke-width:2px;",
        "    classDef inactive fill:#F1F5F9,stroke:#CBD5E1,color:#94A3B8;",
        "    classDef success fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px;",
        "    classDef human fill:#FEF3C7,stroke:#D97706,color:#78350F,stroke-width:2px;",
        f'    DOC["Document Input"] --> RTR["Router · {_esc(tau_q_str)}"]',
    ]

    route_map = {r["route"]: r for r in desc.routes}
    route_nodes = [
        ("cuad", "R_CUAD", f"CUAD Contract · {_esc(model_def)}"),
        ("pdf_text_good", "R_GOOD", f"PDF Text Good · A:{_esc(model_a)} / B:{_esc(model_b)}"),
        ("pdf_text_damaged", "R_DMG", f"PDF Damaged · Vision A:{_esc(model_a)} / B:{_esc(model_b)}"),
        ("pdf_no_text", "R_NOTXT", f"PDF Scan · Vision A:{_esc(model_a)} / B:{_esc(model_b)}"),
        ("pdf_corrupted", "R_CORR", f"PDF Corrupted · PNG A:{_esc(model_a)}"),
    ]

    for rname, nid, label in route_nodes:
        rinfo = route_map.get(rname, {"active": True})
        cnt = (route_counts or {}).get(rname)
        edge_lbl = f'"{_esc(rname)} · {cnt} docs"' if cnt is not None else f'"{_esc(rname)}"'
        lines.append(f'    RTR -->|{edge_lbl}| {nid}["{_esc(label)}"]')
        lines.append(f'    {nid} --> EV["Evidence & Grounding"]')
        cls = "active" if rinfo.get("active") else "inactive"
        lines.append(f"    class {nid} {cls};")

    lines.append(f'    EV --> UQ["Probly UQ · {_esc(uq_label)}"]')
    lines.append(f'    UQ --> SEL["{_esc(sel_label)}"]')

    if desc.abstain_all:
        lines.append('    SEL -. "disabled (abstain all)" .-> BOOK["Book Automatically"]')
        lines.append('    SEL --> HUM["Route to Human"]')
        lines.append("    class BOOK inactive;")
        lines.append("    class HUM human;")
    else:
        lines.append(f'    SEL -->|"conf >= {threshold:.2f}"| BOOK["Book Automatically"]')
        lines.append(f'    SEL -->|"conf < {threshold:.2f}"| HUM["Route to Human"]')
        lines.append("    class BOOK success;")
        lines.append("    class HUM human;")

    lines.append("    class DOC,RTR,EV,UQ,SEL active;")
    return "\n".join(lines)


def build_dot(desc: PipelineDescription, *, threshold: float) -> str:
    """Build a compact Graphviz DOT fallback of the pipeline."""
    uq_label = f"{desc.uq_method or 'auto'} (K={desc.samples or 1})"
    book_style = 'style=dashed,color="#94A3B8"' if desc.abstain_all else 'color="#16A34A"'
    return (
        "digraph G {\n"
        '  rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#FFF1E8", color="#FF5F00"];\n'
        '  DOC [label="Document"]; RTR [label="Router"]; EV [label="Evidence"];\n'
        f'  UQ [label="Probly UQ\\n{uq_label}"]; SEL [label="Gate tau={threshold:.2f}"];\n'
        '  BOOK [label="Book", fillcolor="#DCFCE7", color="#16A34A"];\n'
        '  HUM [label="To Human", fillcolor="#FEF3C7", color="#D97706"];\n'
        '  DOC -> RTR -> EV -> UQ -> SEL;\n'
        f'  SEL -> BOOK [{book_style}];\n'
        '  SEL -> HUM [color="#D97706"];\n'
        "}\n"
    )
