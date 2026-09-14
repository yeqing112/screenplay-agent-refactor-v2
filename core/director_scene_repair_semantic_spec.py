"""Independent semantic specification for Scene Repair IR."""
from __future__ import annotations

import copy
from typing import Any

from core.director_scene_repair_scope import SCENE_ALLOWED_DIMENSIONS

SCENE_REPAIR_SEMANTIC_SPEC_VERSION = "director_scene_repair_semantic_spec_v1"
SCENE_REPAIR_IR_SCHEMA_VERSION = "director_scene_repair_ir_v1"
_GROUPS = {"camera", "composition", "performance_direction", "emotion", "edit", "information_strategy"}
_SCALAR = {"why_this_shot", "purpose", "dramatic_function", "visual_emphasis"}


class SceneRepairIRSchemaError(ValueError):
    code = "SCENE_REPAIR_IR_INVALID"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_scene_repair_ir(raw: Any, *, known_plan_shot_ids: set[str] | None = None, allowed_character_ids: set[str] | None = None, allowed_dimensions: set[str] | None = None, max_dimensions: int | None = None, max_shot_decisions: int | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SceneRepairIRSchemaError("Scene Repair IR must be an object")
    required = {"schema_version", "scene_id", "strategy_summary", "target_dimensions", "shot_decisions", "scene_level_intent"}
    unknown = sorted(set(raw) - (required | {"tradeoffs", "ir_fingerprint"}))
    if unknown:
        raise SceneRepairIRSchemaError(f"forbidden IR fields: {', '.join(unknown)}")
    if _text(raw.get("schema_version")) != SCENE_REPAIR_IR_SCHEMA_VERSION:
        raise SceneRepairIRSchemaError(f"schema_version must be {SCENE_REPAIR_IR_SCHEMA_VERSION}")
    dimensions = [str(value).strip().upper() for value in _list(raw.get("target_dimensions")) if _text(value)]
    allowed = allowed_dimensions or set(SCENE_ALLOWED_DIMENSIONS)
    if not dimensions or any(value not in allowed for value in dimensions):
        raise SceneRepairIRSchemaError("target_dimensions must be non-empty and allowed")
    if max_dimensions is not None and len(dict.fromkeys(dimensions)) > max(0, int(max_dimensions)):
        raise SceneRepairIRSchemaError("target_dimensions exceeds the scene dimension budget")
    decisions = _list(raw.get("shot_decisions"))
    if not decisions:
        raise SceneRepairIRSchemaError("shot_decisions must be non-empty")
    if max_shot_decisions is not None and len(decisions) > max(0, int(max_shot_decisions)):
        raise SceneRepairIRSchemaError("shot_decisions exceeds the bounded affected-shot budget")
    known = known_plan_shot_ids or set()
    chars = allowed_character_ids or set()
    normalized = {"schema_version": SCENE_REPAIR_IR_SCHEMA_VERSION, "scene_id": _text(raw.get("scene_id")), "strategy_summary": _text(raw.get("strategy_summary")), "target_dimensions": list(dict.fromkeys(dimensions)), "scene_level_intent": _text(raw.get("scene_level_intent")), "shot_decisions": []}
    if not normalized["scene_id"] or not normalized["strategy_summary"] or not normalized["scene_level_intent"]:
        raise SceneRepairIRSchemaError("scene_id, strategy_summary and scene_level_intent are required")
    seen_shots: set[str] = set()
    for index, item in enumerate(decisions):
        if not isinstance(item, dict):
            raise SceneRepairIRSchemaError(f"shot_decisions[{index}] must be object")
        if set(item) - ({"plan_shot_id", "reason"} | _GROUPS | _SCALAR):
            raise SceneRepairIRSchemaError(f"shot_decisions[{index}] contains forbidden fields")
        sid = _text(item.get("plan_shot_id"))
        if not sid or (known and sid not in known):
            raise SceneRepairIRSchemaError(f"unknown plan_shot_id: {sid}")
        if sid in seen_shots:
            raise SceneRepairIRSchemaError(f"duplicate plan_shot_id: {sid}")
        seen_shots.add(sid)
        out = {"plan_shot_id": sid}
        for key, value in item.items():
            if key in {"plan_shot_id", "reason"}: continue
            if isinstance(value, dict):
                if any(str(child).startswith("/") or "shots." in str(child) for child in value):
                    raise SceneRepairIRSchemaError("Scene Repair IR must not contain canonical paths")
                out[key] = copy.deepcopy(value)
            elif isinstance(value, list):
                out[key] = copy.deepcopy(value)
            elif key in _SCALAR and isinstance(value, str) and value.strip():
                out[key] = value.strip()
            else:
                raise SceneRepairIRSchemaError(f"invalid semantic value for {key}")
            if key == "performance_direction":
                for row in value if isinstance(value, list) else []:
                    if not isinstance(row, dict) or not _text(row.get("character_id")) or not _text(row.get("objective")) or not _text(row.get("visible_behavior")):
                        raise SceneRepairIRSchemaError("performance_direction requires character_id/objective/visible_behavior")
                    if chars and _text(row.get("character_id")) not in chars:
                        raise SceneRepairIRSchemaError("performance_direction character_id is outside contract")
        if len(out) == 1:
            raise SceneRepairIRSchemaError(f"shot_decisions[{index}] has no semantic change")
        normalized["shot_decisions"].append(out)
    return normalized


__all__ = ["SCENE_REPAIR_SEMANTIC_SPEC_VERSION", "SCENE_REPAIR_IR_SCHEMA_VERSION", "SceneRepairIRSchemaError", "validate_scene_repair_ir"]
