"""Compile semantic Scene Repair IR to the existing canonical patch schema."""
from __future__ import annotations

import copy
from typing import Any

from core.director_patch_schema import parse_creative_patch
from core.director_scene_repair_contract import build_scene_repair_contract
from core.director_scene_repair_semantic_spec import validate_scene_repair_ir


def compile_scene_repair_ir(ir: dict[str, Any], *, contract: dict[str, Any]) -> dict[str, Any]:
    known = set(str(value) for value in contract.get("allowed_shot_ids", []))
    chars = set(str(value) for value in contract.get("allowed_character_ids", []))
    normalized = validate_scene_repair_ir(ir, known_plan_shot_ids=known, allowed_character_ids=chars, allowed_dimensions=set(contract.get("allowed_dimensions") or []))
    patches: list[dict[str, Any]] = []
    def flatten(prefix: str, value: Any) -> dict[str, Any]:
        # Existing canonical compiler validates leaf paths.  Keep semantic IR
        # group objects intact at the IR boundary, then deterministically
        # flatten them here; lists (performance direction) remain one field.
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for child, child_value in value.items():
                result.update(flatten(f"{prefix}.{child}", child_value))
            return result
        return {prefix: copy.deepcopy(value)}
    for decision in normalized["shot_decisions"]:
        changes: dict[str, Any] = {}
        for field, value in decision.items():
            if field in {"plan_shot_id", "reason"}: continue
            if field not in {"camera", "composition", "performance_direction", "emotion", "edit", "information_strategy", "why_this_shot", "purpose", "dramatic_function", "visual_emphasis"}:
                raise ValueError(f"unsupported scene semantic field: {field}")
            changes.update(flatten(field, value))
        patches.append({"plan_shot_id": decision["plan_shot_id"], "changes": changes, "rationale": decision.get("reason", normalized["strategy_summary"])})
    document = parse_creative_patch({"schema_version": "director_creative_patch_v1", "patches": patches, "auxiliary_shot_proposals": []})
    return {"schema_version": "director_scene_repair_compiled_patch_v1", "scene_id": normalized["scene_id"], "source_ir": normalized, "patch_document": document, "patch_count": len(document["patches"]), "canonical_paths_generated_by": "director_scene_repair_ir_compiler"}


compile_director_scene_repair_ir = compile_scene_repair_ir

__all__ = ["compile_scene_repair_ir", "compile_director_scene_repair_ir"]
