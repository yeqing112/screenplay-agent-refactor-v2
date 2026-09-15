"""Lossless, deterministic normalization for Director Strategy IR V2."""
from __future__ import annotations

import copy
from typing import Any

from core.director_scene_strategy_semantic_spec_v2 import FLEXIBLE_LIST_FIELDS, INFORMATION_FIELDS, TOP_LEVEL_FIELDS, build_source_ref_contract, normalize_beat_id


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any, *, allow_na_empty: bool = False) -> tuple[list[str], list[dict[str, Any]]]:
    if value is None:
        return [], []
    values = [value] if isinstance(value, str) else value if isinstance(value, list) else None
    if values is None:
        return [], [{"code": "LOSSLESS_SHAPE_UNSUPPORTED", "expected": "string|string[]|null"}]
    out: list[str] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, str):
            errors.append({"code": "LOSSLESS_SHAPE_UNSUPPORTED", "index": index, "expected": "string"}); continue
        text = item.strip()
        if not text or (allow_na_empty and text.upper() == "N/A"):
            continue
        out.append(text)
    return out, errors


def normalize_source_ref(value: Any, *, contract: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    raw = _text(value)
    if not raw:
        return None, {"code": "EMPTY_SOURCE_REFERENCE"}
    kind, sep, ident = raw.partition(":")
    kind = kind.lower() if sep else "beat"
    ident = ident if sep else raw
    allowed = _dict(contract.get("allowed_ids"))
    if kind == "beat":
        canonical = normalize_beat_id(ident, contract.get("beat_alias_table") or {})
        if canonical and canonical in set(_text(x) for x in _list(allowed.get("beat"))):
            return f"beat:{canonical}", None
    elif kind in {"fact", "prop", "character", "location"} and ident in set(_text(x) for x in _list(allowed.get(kind))):
        return f"{kind}:{ident}", None
    return None, {"code": "UNKNOWN_SOURCE_REFERENCE", "reference": raw}


def normalize_power_ref(power: Any, *, contract: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize typed power refs without changing their semantic meaning."""
    item = copy.deepcopy(power) if isinstance(power, dict) else {}
    errors: list[dict[str, Any]] = []
    center = _text(item.get("center_type")).upper()
    raw = item.get("center_ref")
    if center == "CHARACTER":
        ident = _text(raw)
        if ident.lower().startswith("character:"): ident = ident.split(":", 1)[1]
        allowed = {_text(x) for x in _list(_dict(contract.get("allowed_ids")).get("character")) if _text(x)}
        if ident in allowed:
            item["center_ref"] = ident
        else:
            errors.append({"code": "INVALID_POWER_CONTROLLER", "reference": _text(raw)})
    elif center in {"INFORMATION", "OBJECT"} and _text(raw) and _text(raw).upper() != center:
        normalized, error = normalize_source_ref(raw, contract=contract)
        if error: errors.append({"code": "INVALID_POWER_REFERENCE", "reference": _text(raw), **error})
        else: item["center_ref"] = normalized
    elif center in {"NONE", "SHARED", "ENVIRONMENT"}:
        if raw not in (None, ""): item["center_ref"] = None
    # RELATIONSHIP is a semantic relation label; it is not a character ref.
    return item, errors


def normalize_strategy_ir_v2(raw: Any, *, contract: dict[str, Any]) -> dict[str, Any]:
    """Normalize only lossless shapes; no creative or factual content is added."""
    if not isinstance(raw, dict):
        return {"ir": None, "errors": [{"code": "IR_NOT_OBJECT"}]}
    errors: list[dict[str, Any]] = []
    unknown = sorted(set(raw) - set(TOP_LEVEL_FIELDS))
    if unknown:
        errors.append({"code": "UNKNOWN_IR_FIELD", "fields": unknown})
    normalized = copy.deepcopy(raw)
    for field in FLEXIBLE_LIST_FIELDS:
        values, field_errors = _string_list(raw.get(field), allow_na_empty=field == "prop_visual_strategy")
        normalized[field] = values
        errors.extend({"path": field, **item} for item in field_errors)
    phases = raw.get("scene_phases")
    if not isinstance(phases, list):
        errors.append({"code": "NESTED_FIELD_SHAPE_INVALID", "path": "scene_phases", "expected": "array"}); phases = []
    normalized_phases: list[dict[str, Any]] = []
    for pi, phase in enumerate(phases):
        if not isinstance(phase, dict):
            errors.append({"code": "PHASE_NOT_OBJECT", "path": f"scene_phases[{pi}]"}); continue
        item = copy.deepcopy(phase)
        beat_values = phase.get("beat_ids")
        beat_values = [beat_values] if isinstance(beat_values, str) else beat_values
        if not isinstance(beat_values, list):
            errors.append({"code": "LOSSLESS_SHAPE_UNSUPPORTED", "path": f"scene_phases[{pi}].beat_ids", "expected": "string[]"}); beat_values = []
        canonical_beats: list[str] = []
        for bi, beat in enumerate(beat_values):
            canonical = normalize_beat_id(beat, contract.get("beat_alias_table") or {})
            if canonical is None:
                errors.append({"code": "UNKNOWN_BEAT_REFERENCE", "path": f"scene_phases[{pi}].beat_ids[{bi}]", "beat_id": _text(beat)})
            else:
                canonical_beats.append(canonical)
        item["beat_ids"] = canonical_beats
        item["power"], power_errors = normalize_power_ref(phase.get("power"), contract=contract)
        errors.extend({"path": f"scene_phases[{pi}].power.center_ref", **error} for error in power_errors)
        info = _dict(phase.get("information")); normalized_info = {key: [] for key in INFORMATION_FIELDS}
        unknown_info = sorted(set(info) - set(INFORMATION_FIELDS))
        if unknown_info:
            errors.append({"code": "UNKNOWN_INFORMATION_FIELD", "path": f"scene_phases[{pi}].information", "fields": unknown_info})
        for key in ("reveal_refs", "hint_refs", "withhold_refs"):
            values = info.get(key, [])
            values = [values] if isinstance(values, str) else values
            if not isinstance(values, list):
                errors.append({"code": "LOSSLESS_SHAPE_UNSUPPORTED", "path": f"scene_phases[{pi}].information.{key}", "expected": "source_ref[]"}); values = []
            refs: list[str] = []
            for value in values:
                ref, error = normalize_source_ref(value, contract=contract)
                if error: errors.append({"path": f"scene_phases[{pi}].information.{key}", **error})
                elif ref: refs.append(ref)
            normalized_info[key] = refs
        for key in ("audience_suspicions", "director_inferences"):
            values = info.get(key, [])
            if values is None: values = []
            if not isinstance(values, list):
                errors.append({"code": "NESTED_FIELD_SHAPE_INVALID", "path": f"scene_phases[{pi}].information.{key}", "expected": "array"}); values = []
            normalized_info[key] = copy.deepcopy(values)
        item["information"] = normalized_info
        normalized_phases.append(item)
    normalized["scene_phases"] = normalized_phases
    return {"ir": normalized, "errors": errors}


__all__ = ["normalize_strategy_ir_v2", "normalize_source_ref", "normalize_power_ref"]
