"""Authority and quality validation for compiled Director Creative patches."""

from __future__ import annotations

import copy
from typing import Any

from core.director_auxiliary import AuxiliaryShotValidationError, validate_auxiliary_shot_proposals
from core.director_creative_contract import IMMUTABLE_FIELDS, is_allowed_patch_path
from core.director_patch_compiler import DirectorPatchCompileError, compile_creative_patches
from core.director_quality_validator import validate_director_quality


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _shots(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(plan.get("shots")) if isinstance(item, dict)]


def _shot_id(shot: dict[str, Any], index: int) -> str:
    return _text(shot.get("plan_shot_id")) or f"S{index + 1:02d}"


def _error(code: str, message: str, *, path: str = "", target_id: str = "", blocking: bool = True) -> dict[str, Any]:
    return {
        "code": code,
        "issue_code": code,
        "message": message,
        "path": path,
        "target_id": target_id,
        "target_layer": "DIRECTOR_CREATIVE",
        "severity": "error" if blocking else "warning",
        "blocking": blocking,
    }


def _immutable_mismatches(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    baseline_shots = _shots(baseline)
    candidate_shots = _shots(candidate)
    baseline_ids = [_shot_id(item, index) for index, item in enumerate(baseline_shots)]
    candidate_ids = [_shot_id(item, index) for index, item in enumerate(candidate_shots)]
    errors: list[dict[str, Any]] = []
    if len(candidate_shots) > len(baseline_shots):
        errors.append(_error("SHOT_COUNT_EXPANSION", "candidate contains shots outside the structural plan"))
    if candidate_ids[: len(baseline_ids)] != baseline_ids:
        errors.append(_error("DIRECTOR_FACT_OVERRIDE", "baseline plan_shot_id order must be preserved"))
    baseline_by_id = {_shot_id(item, index): item for index, item in enumerate(baseline_shots)}
    for index, shot in enumerate(candidate_shots):
        sid = _shot_id(shot, index)
        original = baseline_by_id.get(sid)
        if original is None:
            continue
        for field in IMMUTABLE_FIELDS:
            if field in shot and shot.get(field) != original.get(field):
                errors.append(_error("DIRECTOR_FACT_OVERRIDE", f"{sid}.{field} is authoritative", path=f"shots/{sid}/{field}", target_id=sid))
    return errors


def validate_compiled_patch_result(
    compilation: dict[str, Any],
    structural_shot_plan: dict[str, Any],
    contract: dict[str, Any],
    *,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a compiler result while keeping quality findings non-blocking."""

    if not isinstance(compilation, dict) or not isinstance(structural_shot_plan, dict):
        return {"status": "invalid", "contract_pass": False, "errors": [_error("DIRECTOR_PATCH_RESULT_INVALID", "compilation and structural plan must be objects")], "warnings": []}
    candidate = compilation.get("candidate")
    if not isinstance(candidate, dict):
        return {"status": "invalid", "contract_pass": False, "errors": [_error("DIRECTOR_PATCH_RESULT_INVALID", "compiled candidate is missing")], "warnings": []}
    errors = _immutable_mismatches(structural_shot_plan, candidate)
    for compiled in _list(compilation.get("compiled_patches")):
        for operation in _list(_dict(compiled).get("operations")):
            path = _text(_dict(operation).get("path"))
            if not is_allowed_patch_path(path, contract):
                errors.append(_error("DIRECTOR_PATCH_PATH_FORBIDDEN", f"compiled path is not allowed: {path}", path=path, target_id=_text(_dict(compiled).get("plan_shot_id"))))
    for rejected in _list(compilation.get("rejected_patches")):
        rejected_obj = _dict(rejected)
        # A rejected patch was never applied.  It is retained as a
        # patch-level diagnostic and may be sent to Local Repair; it must not
        # invalidate the otherwise safe candidate under Partial Acceptance.
        errors.append(_error(_text(rejected_obj.get("code")) or "DIRECTOR_PATCH_REJECTED", _text(rejected_obj.get("message")) or "patch rejected", path=_text(rejected_obj.get("path")), target_id=_text(rejected_obj.get("plan_shot_id")), blocking=False))
    auxiliary_result: dict[str, Any]
    try:
        auxiliary_result = validate_auxiliary_shot_proposals(
            compilation.get("auxiliary_shot_proposals", []), structural_shot_plan, contract, allow_partial=True
        )
    except AuxiliaryShotValidationError as exc:
        auxiliary_result = {"status": "invalid", "accepted": [], "rejected": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "accepted_count": 0, "rejected_count": 1}
    for rejected in _list(auxiliary_result.get("rejected")):
        rejected_obj = _dict(rejected)
        errors.append(_error(_text(rejected_obj.get("code")) or "DIRECTOR_AUXILIARY_INVALID", _text(rejected_obj.get("message")) or "auxiliary proposal rejected", path=_text(rejected_obj.get("path")), target_id=_text(rejected_obj.get("proposal_id")), blocking=False))
    quality_issues = validate_director_quality(candidate, treatment=treatment, blocking=blocking)
    warnings = [copy.deepcopy(item) for item in quality_issues]
    contract_errors = [item for item in errors if item.get("blocking")]
    status = "invalid" if contract_errors else ("partial" if errors else "valid")
    return {
        "status": status,
        "contract_pass": not contract_errors,
        "errors": errors,
        "warnings": warnings,
        "quality_issues": quality_issues,
        "auxiliary": auxiliary_result,
        "accepted_patch_count": int(compilation.get("accepted_patch_count") or 0),
        "rejected_patch_count": int(compilation.get("rejected_patch_count") or 0) + int(auxiliary_result.get("rejected_count") or 0),
        "shot_count": len(_shots(candidate)),
        "baseline_shot_count": len(_shots(structural_shot_plan)),
    }


def compile_and_validate_creative_patches(
    structural_shot_plan: dict[str, Any],
    patch_document: dict[str, Any],
    contract: dict[str, Any],
    *,
    allow_partial: bool = False,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience boundary for callers that want compile + validation."""

    try:
        compilation = compile_creative_patches(structural_shot_plan, patch_document, contract, allow_partial=allow_partial)
    except DirectorPatchCompileError as exc:
        return {"status": "invalid", "contract_pass": False, "errors": [_error(exc.code, str(exc), path=exc.path, target_id=exc.plan_shot_id)], "warnings": [], "compilation": None}
    validation = validate_compiled_patch_result(compilation, structural_shot_plan, contract, treatment=treatment, blocking=blocking)
    return {**validation, "compilation": compilation}


validate_patch_result = validate_compiled_patch_result
validate_director_patch_result = validate_compiled_patch_result


__all__ = [
    "validate_compiled_patch_result",
    "compile_and_validate_creative_patches",
    "validate_patch_result",
    "validate_director_patch_result",
]
