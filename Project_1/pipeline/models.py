"""Model capability registry (models.json) and input-kind selection. Pure functions, no network.

Input kinds, in order of preference: pdf_file, pdf_image_url, png, text. A capability counts only when it is
True in models.json; null (untested) is treated as unsupported, except for text which defaults to supported.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MODELS_PATH = HERE / "models.json"
INPUT_KINDS = ("pdf_file", "pdf_image_url", "png", "text")  # preference order
ROLE_VARS = {"A": "LLM_MODEL_A", "B": "LLM_MODEL_B", "ocr": "LLM_MODEL_OCR"}

_FALLBACK_DEFAULTS = {
    "family": "unknown",
    "supports": {"text": True, "pdf_file": None, "pdf_image_url": None, "png": None},
    "max_context_chars": 200000,
    "timeout_s": 300,
    "temperature_ok": True,
}


def _read(path: Path | None) -> dict:
    p = Path(path) if path else MODELS_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"defaults": copy.deepcopy(_FALLBACK_DEFAULTS), "models": {}}
    if not isinstance(data, dict):
        return {"defaults": copy.deepcopy(_FALLBACK_DEFAULTS), "models": {}}
    data.setdefault("defaults", copy.deepcopy(_FALLBACK_DEFAULTS))
    data.setdefault("models", {})
    return data


def _merge(defaults: dict, spec: dict) -> dict:
    out = copy.deepcopy(defaults)
    for k, v in (spec or {}).items():
        if k == "supports" and isinstance(v, dict):
            out["supports"] = {**out.get("supports", {}), **v}
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_models(path: Path | None = None) -> dict[str, dict]:
    """All known models with defaults filled in: {model: {family, supports, max_context_chars, timeout_s, temperature_ok}}."""
    data = _read(path)
    return {name: _merge(data["defaults"], spec) for name, spec in data["models"].items()}


def model_spec(model: str, path: Path | None = None) -> dict:
    """Spec of one model. Unknown models get the defaults (text only)."""
    data = _read(path)
    return _merge(data["defaults"], data["models"].get(model, {}))


def supported_kinds(model: str, path: Path | None = None) -> list[str]:
    sup = model_spec(model, path).get("supports", {})
    return [k for k in INPUT_KINDS if sup.get(k) is True]


def fallback_order(model: str, available: list[str] | tuple[str, ...], path: Path | None = None) -> list[str]:
    """Input kinds to try, best first: those the model supports and the caller can provide. Text is the last resort and is
    always appended when available, even if the registry has no entry for it."""
    sup = model_spec(model, path).get("supports", {})
    order = [k for k in INPUT_KINDS if k in available and sup.get(k) is True]
    if "text" in available and "text" not in order and sup.get("text") is not False:
        order.append("text")
    return order


def pick_input_kind(model: str, available: list[str] | tuple[str, ...], path: Path | None = None) -> str | None:
    """Best input kind for the model among `available`. None when nothing fits."""
    order = fallback_order(model, available, path)
    return order[0] if order else None


def update_supports(updates: dict[str, dict[str, bool]], path: Path | None = None, *, probed_at: str | None = None) -> None:
    """Write probed capabilities {model: {kind: bool}} into models.json (new models are added)."""
    p = Path(path) if path else MODELS_PATH
    data = _read(p)
    for model, sup in updates.items():
        spec = data["models"].setdefault(model, {})
        spec.setdefault("supports", {}).update(sup)
        if probed_at:
            spec["probed_at"] = probed_at
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def model_roles(env: dict | None = None) -> dict[str, str | None]:
    """Default model plus the optional roles LLM_MODEL_A / LLM_MODEL_B / LLM_MODEL_OCR.
    A falls back to LLM_MODEL; B and ocr stay None when unset."""
    env = os.environ if env is None else env

    def get(name: str) -> str | None:
        v = (env.get(name) or "").strip()
        return v or None

    default = get("LLM_MODEL")
    return {"default": default, "A": get(ROLE_VARS["A"]) or default,
            "B": get(ROLE_VARS["B"]), "ocr": get(ROLE_VARS["ocr"])}
