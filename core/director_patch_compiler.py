"""Deterministic compiler from CreativePatch documents to ShotPlan candidates."""

from __future__ import annotations

import copy
from typing import Any

from core.director_creative_contract import (
    IMMUTABLE_FIELDS,
    is_allowed_patch_path,
)
from core.director_patch_schema import parse_creative_patch
from core.local_repair import apply_local_repair, fingerprint


class DirectorPatchCompileError(ValueError):
    """Raised when a patch cannot be applied without changing authority."""

    code = "DIRECTOR_PATCH_COMPILE_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "", plan_shot_id: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path
        self.plan_shot_id = plan_shot_id


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _shots(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in plan.get("shots", []) if isinstance(item, dict)] if isinstance(plan.get("shots"), list) else []


def _path_parts(path: str) -> list[str]:
    value = _text(path).replace(".", "/")
    return [part for part in value.split("/") if part]


def _relative_field(path: str) -> str:
    parts = _path_parts(path)
    if parts and parts[0] == "shots":
        parts = parts[2:]
    return parts[0] if parts else ""


def _target_index(plan: dict[str, Any], plan_shot_id: str) -> int:
    for index, shot in enumerate(_shots(plan)):
        if _text(shot.get("plan_shot_id")) == plan_shot_id:
            return index
    raise DirectorPatchCompileError(
        f"unknown plan_shot_id: {plan_shot_id}",
        code="UNKNOWN_PLAN_SHOT_ID",
        plan_shot_id=plan_shot_id,
    )


def _canonical_pointer(path: str, *, plan_shot_id: str, shot_index: int) -> str:
    parts = _path_parts(path)
    if not parts:
        raise DirectorPatchCompileError("patch path is required", code="DIRECTOR_PATCH_PATH_FORBIDDEN", plan_shot_id=plan_shot_id)
    if parts[0] == "shots":
        if len(parts) < 3:
            raise DirectorPatchCompileError("shot patch path must address a creative field", code="DIRECTOR_PATCH_PATH_FORBIDDEN", path=path, plan_shot_id=plan_shot_id)
        selector = parts[1]
        if selector not in {str(shot_index), "*", plan_shot_id}:
            raise DirectorPatchCompileError("patch path targets a different shot", code="DIRECTOR_PATCH_PATH_FORBIDDEN", path=path, plan_shot_id=plan_shot_id)
        parts = ["shots", str(shot_index), *parts[2:]]
    else:
        parts = ["shots", str(shot_index), *parts]
    return "/" + "/".join(parts)


def _validate_value(path: str, value: Any) -> None:
    parts = [part for part in path.split("/") if part]
    field = parts[-1] if parts else ""
    if field in {"shot_size", "angle", "movement", "speed", "camera_side", "why_this_shot", "dramatic_function", "visual_emphasis", "cut_reason", "audience_focus", "objective", "visible_behavior", "start", "end"}:
        if not isinstance(value, str) or not value.strip():
            raise DirectorPatchCompileError("creative text value must be a non-empty string", code="INVALID_PATCH_VALUE", path=path)
    if field == "intensity":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 10:
            raise DirectorPatchCompileError("emotion.intensity must be between 0 and 10", code="INVALID_PATCH_VALUE", path=path)
    if field == "hold_after_action_seconds":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
            raise DirectorPatchCompileError("edit.hold_after_action_seconds must be non-negative", code="INVALID_PATCH_VALUE", path=path)


def _ensure_parent_operations(candidate: dict[str, Any], pointer: str) -> list[dict[str, Any]]:
    """Create only missing object/list containers needed by an allowed path.

    Structural ShotPlans are intentionally sparse: a plan may not have an
    ``emotion`` or ``composition`` object until a creative patch supplies one
    of its fields.  JSON Patch requires every parent to exist, so the
    compiler emits deterministic ``add`` operations for those containers
    before the leaf replacement.  The working copy is updated only while
    planning operations; the caller still applies the complete operation list
    atomically through ``apply_local_repair``.
    """

    parts = [part for part in pointer.split("/") if part]
    if len(parts) < 2:
        return []
    operations: list[dict[str, Any]] = []
    target: Any = candidate
    traversed: list[str] = []
    for index, part in enumerate(parts[:-1]):
        traversed.append(part)
        next_part = parts[index + 1]
        if isinstance(target, dict):
            if part not in target or target[part] is None:
                value: Any = [] if next_part.isdigit() else {}
                operations.append({"op": "add", "path": "/" + "/".join(traversed), "value": value})
                target[part] = value
            target = target[part]
            continue
        if isinstance(target, list):
            try:
                list_index = int(part)
            except (TypeError, ValueError) as exc:
                raise DirectorPatchCompileError(
                    "patch path contains a non-numeric list index",
                    code="INVALID_PATCH_VALUE",
                    path=pointer,
                ) from exc
            if list_index < 0 or list_index > len(target):
                raise DirectorPatchCompileError(
                    "patch path list index is out of range",
                    code="INVALID_PATCH_VALUE",
                    path=pointer,
                )
            if list_index == len(target):
                value = [] if next_part.isdigit() else {}
                operations.append({"op": "add", "path": "/" + "/".join(traversed), "value": value})
                target.append(value)
            else:
                target = target[list_index]
            continue
        raise DirectorPatchCompileError(
            "patch path traverses a non-container value",
            code="INVALID_PATCH_VALUE",
            path=pointer,
        )
    return operations


def _assert_path_authority(path: str, *, contract: dict[str, Any], plan_shot_id: str) -> None:
    field = _relative_field(path)
    if field in IMMUTABLE_FIELDS:
        raise DirectorPatchCompileError(
            f"{plan_shot_id}.{field} is authoritative",
            code="DIRECTOR_FACT_OVERRIDE",
            path=path,
            plan_shot_id=plan_shot_id,
        )
    if not is_allowed_patch_path(path, contract):
        raise DirectorPatchCompileError(
            f"patch path is not allowed: {path}",
            code="DIRECTOR_PATCH_PATH_FORBIDDEN",
            path=path,
            plan_shot_id=plan_shot_id,
        )


def compile_single_patch(
    structural_shot_plan: dict[str, Any],
    patch: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Compile one normalized patch atomically against a structural plan."""

    if not isinstance(structural_shot_plan, dict):
        raise DirectorPatchCompileError("structural_shot_plan must be an object")
    if not isinstance(patch, dict):
        raise DirectorPatchCompileError("patch must be an object")
    plan_shot_id = _text(patch.get("plan_shot_id"))
    if not plan_shot_id:
        raise DirectorPatchCompileError("plan_shot_id is required", code="UNKNOWN_PLAN_SHOT_ID")
    shot_index = _target_index(structural_shot_plan, plan_shot_id)
    changes = patch.get("changes") if isinstance(patch.get("changes"), dict) else {}
    if not changes:
        raise DirectorPatchCompileError("patch changes must be non-empty", code="INVALID_PATCH_VALUE", plan_shot_id=plan_shot_id)
    operations: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    planning_copy = copy.deepcopy(structural_shot_plan)
    for raw_path, value in changes.items():
        raw_path = _text(raw_path)
        pointer = _canonical_pointer(raw_path, plan_shot_id=plan_shot_id, shot_index=shot_index)
        _assert_path_authority(raw_path, contract=contract, plan_shot_id=plan_shot_id)
        _assert_path_authority(pointer, contract=contract, plan_shot_id=plan_shot_id)
        _validate_value(pointer, value)
        parent_operations = _ensure_parent_operations(planning_copy, pointer)
        operations.extend(parent_operations)
        leaf_operation = {"op": "replace", "path": pointer, "value": copy.deepcopy(value)}
        operations.append(leaf_operation)
        # Keep subsequent paths in this patch aware of containers created by
        # the previous operation.  Applying the complete list remains the
        # single mutation point below.
        try:
            planning_copy = apply_local_repair(
                planning_copy,
                {"issue_code": "DIRECTOR_CREATIVE_PATCH_PLANNING", "patch": [*parent_operations, leaf_operation]},
            )["candidate"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise DirectorPatchCompileError(
                "patch value cannot be applied to structural plan",
                code="INVALID_PATCH_VALUE",
                path=pointer,
            ) from exc
        provenance.append({"plan_shot_id": plan_shot_id, "source_path": raw_path, "compiled_path": pointer, "value_fingerprint": fingerprint(value)})
    applied = apply_local_repair(structural_shot_plan, {"issue_code": "DIRECTOR_CREATIVE_PATCH", "target_id": plan_shot_id, "target_layer": "DIRECTOR_CREATIVE", "patch": operations})
    return {
        "candidate": applied["candidate"],
        "patch": copy.deepcopy(patch),
        "operations": operations,
        "provenance": provenance,
        "plan_shot_id": plan_shot_id,
        "before_fingerprint": applied["before_fingerprint"],
        "after_fingerprint": applied["after_fingerprint"],
        "changed": applied["changed"],
    }


def compile_creative_patches(
    structural_shot_plan: dict[str, Any],
    patch_document: dict[str, Any],
    contract: dict[str, Any],
    *,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Compile a patch document in order without mutating the baseline.

    ``allow_partial`` is an explicit hook for the later Partial Acceptance
    stage.  The default remains fail-closed: one invalid patch aborts the
    document and returns no candidate.
    """

    normalized = parse_creative_patch(patch_document)
    baseline = copy.deepcopy(structural_shot_plan)
    current = copy.deepcopy(baseline)
    compiled: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for patch in normalized["patches"]:
        try:
            result = compile_single_patch(current, patch, contract)
        except DirectorPatchCompileError as exc:
            rejected.append({"plan_shot_id": _text(patch.get("plan_shot_id")), "code": exc.code, "path": exc.path, "message": str(exc)})
            if not allow_partial:
                raise
            continue
        current = result["candidate"]
        compiled.append({key: result[key] for key in ("plan_shot_id", "operations", "provenance", "before_fingerprint", "after_fingerprint", "changed")})
    return {
        "status": "compiled" if not rejected else "partial",
        "candidate": current,
        "baseline_fingerprint": fingerprint(baseline),
        "candidate_fingerprint": fingerprint(current),
        "compiled_patches": compiled,
        "rejected_patches": rejected,
        "accepted_patch_count": len(compiled),
        "rejected_patch_count": len(rejected),
        "partial_acceptance": {
            "accepted_patch_count": len(compiled),
            "rejected_patch_count": len(rejected),
            "repaired_patch_count": 0,
            "fallback_patch_count": len(rejected),
        },
        "auxiliary_shot_proposals": copy.deepcopy(normalized.get("auxiliary_shot_proposals", [])),
        "patch_document_fingerprint": normalized["patch_fingerprint"],
    }


__all__ = ["DirectorPatchCompileError", "compile_single_patch", "compile_creative_patches"]
