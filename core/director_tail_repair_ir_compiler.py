"""Deterministic compiler from semantic Repair IR to canonical patches."""
from __future__ import annotations

import copy
from typing import Any

from core.director_creative_contract import is_allowed_patch_path
from core.director_tail_repair_ir import ALLOWED_FIELDS, ROOT_CAUSE_TYPES, REPAIR_IR_SCHEMA_VERSION, RepairIRSchemaError, validate_repair_ir

CANONICAL_SCHEMA_VERSION = "director_creative_patch_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_path(plan_shot_id: str, group: str, field: str) -> str:
    return f"shots/{plan_shot_id}/{group}/{field}"


def compile_repair_ir(ir: dict[str, Any], *, structural_shot_plan: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(structural_shot_plan, dict) or not isinstance(contract, dict):
        raise RepairIRSchemaError("structural_shot_plan and contract must be objects")
    known = {_text(item.get("plan_shot_id")) for item in (structural_shot_plan.get("shots") or []) if isinstance(item, dict)}
    normalized = validate_repair_ir(ir, known_plan_shot_ids=known)
    repair_type = normalized["repair_type"]
    root = normalized.get("root_cause")
    if root in ROOT_CAUSE_TYPES and repair_type not in ROOT_CAUSE_TYPES[root]:
        raise RepairIRSchemaError("repair_type is incompatible with root_cause", code="REPAIR_TYPE_ROOT_CAUSE_MISMATCH")
    allowed_groups = ALLOWED_FIELDS[repair_type]
    patches: list[dict[str, Any]] = []
    for decision in normalized["shot_decisions"]:
        sid = decision["plan_shot_id"]
        changes: dict[str, Any] = {}
        for group in allowed_groups:
            if group not in decision:
                continue
            value = decision[group]
            if group == "performance_emphasis":
                # This is semantic guidance, not a canonical field.  Map it
                # to the contract's existing performance_direction field.
                changes[_canonical_path(sid, "performance_direction", "emphasis")] = [{"emphasis": value}]
            elif group == "performance_direction":
                changes[_canonical_path(sid, group, "")[:-1]] = copy.deepcopy(value)
            else:
                for field, field_value in value.items():
                    path = _canonical_path(sid, group, field)
                    if not is_allowed_patch_path(path, contract):
                        raise RepairIRSchemaError(f"compiled path is outside contract: {path}", code="DIRECTOR_PATCH_PATH_FORBIDDEN", path=path)
                    changes[path] = copy.deepcopy(field_value)
        if not changes:
            raise RepairIRSchemaError("semantic decision compiled to no changes")
        patch: dict[str, Any] = {"plan_shot_id": sid, "changes": changes}
        if _text(decision.get("reason")):
            patch["rationale"] = decision["reason"]
        patches.append(patch)
    document = {"schema_version": CANONICAL_SCHEMA_VERSION, "patches": patches, "auxiliary_shot_proposals": []}
    # Canonical path values are only emitted by this deterministic compiler;
    # the model-facing protocol never receives or authors them.
    return document


compile_director_tail_repair_ir = compile_repair_ir

__all__ = ["CANONICAL_SCHEMA_VERSION", "compile_repair_ir", "compile_director_tail_repair_ir"]
