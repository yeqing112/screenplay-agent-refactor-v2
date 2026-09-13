"""Strict, provider-neutral schemas for Director Creative patches.

This module only parses and normalizes the model-facing document.  It does not
decide whether a path is allowed for a particular contract and it never
mutates a ShotPlan.  Those responsibilities belong to the Contract/Validator
and Patch Compiler stages.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.director_patch_normalizer import (
    PatchNormalizationError,
    canonical_path as _canonical_path,
    normalize_value as _normalize_value,
)


PATCH_SCHEMA_VERSION = "director_creative_patch_v1"
# ``patch_fingerprint`` is emitted by ``parse_creative_patch`` as an internal
# normalization artifact.  It is accepted on a second parse so compiler and
# validator stages can safely pass normalized documents through the same
# boundary, but it is never trusted: the value is recomputed and checked.
PATCH_DOCUMENT_KEYS = {"schema_version", "patches", "auxiliary_shot_proposals", "patch_fingerprint", "normalization_metadata"}
PATCH_KEYS = {"patch_id", "plan_shot_id", "changes", "rationale", "confidence", "_source_format"}
# These are the creative fields permitted by the Director Contract.  The
# schema layer only uses them to recognize semantically equivalent provider
# envelopes; authority, type, and path validation remain in the compiler.
CREATIVE_NESTED_FIELDS = {
    "purpose", "dramatic_function", "why_this_shot", "emotion",
    "performance_direction", "camera", "composition", "edit",
    "information_strategy", "visual_emphasis",
}
CAMERA_FIELDS = {"shot_size", "angle", "movement", "speed", "camera_side"}
PATCH_OPERATION_KEYS = {"op", "path", "value"}
AUXILIARY_KEYS = {
    "proposal_id",
    "proposal_type",
    "source_beat_id",
    "insert_after_plan_shot_id",
    "purpose",
    "why_needed",
    "participants",
    "camera",
    "estimated_duration_seconds",
    "rationale",
}
AUXILIARY_TYPES = {"reaction", "insert", "establishing", "transition", "detail"}


class CreativePatchSchemaError(ValueError):
    """Raised when the model response is not the V2.1 patch document."""

    code = "DIRECTOR_PATCH_SCHEMA_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def patch_fingerprint(document: dict[str, Any]) -> str:
    """Return a stable fingerprint for a normalized patch document."""

    return hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest()


def _ensure_string(value: Any, *, label: str, path: str) -> str:
    text = _text(value)
    if not text:
        raise CreativePatchSchemaError(f"{label} is required", path=path)
    return text


def _normalize_changes(raw: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise CreativePatchSchemaError("changes must be a non-empty object", path=path)
    changes: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise CreativePatchSchemaError("every changes key must be a non-empty string", path=path)
        # A path is deliberately kept as supplied (dotted or JSON pointer)
        # until the Contract stage canonicalizes it; the schema only prevents
        # empty/control keys and complete-shot payloads.
        normalized = key.strip()
        if normalized in {"scene_name", "unknowns", "shots", "scene", "treatment", "blocking", "fact_snapshot"}:
            raise CreativePatchSchemaError(
                f"changes path attempts to address an authoritative document field: {normalized}",
                code="DIRECTOR_FACT_OVERRIDE",
                path=f"{path}.changes.{normalized}",
            )
        try:
            normalized_path = _canonical_path(normalized)
        except PatchNormalizationError as exc:
            raise CreativePatchSchemaError(str(exc), code=exc.code, path=f"{path}.changes.{normalized}") from exc
        normalized_value, _ = _normalize_value(normalized_path, value)
        changes[normalized_path] = copy.deepcopy(normalized_value)
    return changes


def _nested_changes(raw: dict[str, Any], *, path: str) -> dict[str, Any]:
    """Convert a provider's nested creative shot object to dotted changes.

    This is deliberately a structural conversion only.  It does not map
    arbitrary keys, infer missing fields, or validate whether a path is
    allowed for a particular contract.
    """
    changes: dict[str, Any] = {}
    for field, value in raw.items():
        if field in {"plan_shot_id", "patch_id", "rationale", "confidence", "source_format", "_source_format"}:
            continue
        if field not in CREATIVE_NESTED_FIELDS:
            # Immutable/provenance fields must remain visible to the strict
            # boundary instead of being silently discarded.
            raise CreativePatchSchemaError(
                f"patch contains forbidden fields: {field}",
                code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                path=path,
            )
        if field in {"camera", "emotion", "composition", "edit", "information_strategy"} and isinstance(value, dict):
            for child, child_value in value.items():
                child_path = f"{field}.{child}"
                try:
                    child_path = _canonical_path(child_path)
                except PatchNormalizationError as exc:
                    raise CreativePatchSchemaError(str(exc), code=exc.code, path=f"{path}.{field}.{child}") from exc
                child_name = child_path.split(".")[-1]
                if field == "camera" and child_name not in CAMERA_FIELDS:
                    raise CreativePatchSchemaError(
                        f"camera contains forbidden fields: {child_name}",
                        code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                        path=f"{path}.{field}",
                    )
                normalized_value, _ = _normalize_value(child_path, child_value)
                changes[child_path] = copy.deepcopy(normalized_value)
        else:
            normalized_value, _ = _normalize_value(field, value)
            changes[field] = copy.deepcopy(normalized_value)
    if not changes:
        raise CreativePatchSchemaError("nested creative patch has no supported fields", path=path)
    return changes


def _pointer_to_change(path_value: Any, *, path: str, plan_shot_id: str = "") -> str:
    """Convert one JSON-Patch operation to a canonical change entry."""
    try:
        return _canonical_path(path_value, plan_shot_id=plan_shot_id)
    except PatchNormalizationError as exc:
        raise CreativePatchSchemaError(str(exc), code=exc.code, path=f"{path}.path") from exc


def _operation_changes(operations: Any, *, path: str, plan_shot_id: str = "") -> dict[str, Any]:
    if not isinstance(operations, list) or not operations:
        raise CreativePatchSchemaError("patch must contain a non-empty operation list", path=f"{path}.patch")
    changes: dict[str, Any] = {}
    for index, operation in enumerate(operations):
        op_path = f"{path}.patch[{index}]"
        if not isinstance(operation, dict):
            raise CreativePatchSchemaError("patch operation must be an object", path=op_path)
        forbidden = sorted(set(operation) - PATCH_OPERATION_KEYS)
        if forbidden:
            raise CreativePatchSchemaError(
                f"patch operation contains forbidden fields: {', '.join(forbidden)}",
                code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                path=op_path,
            )
        op = _text(operation.get("op") or "replace").lower()
        if op not in {"add", "replace"} or "value" not in operation:
            raise CreativePatchSchemaError("only add/replace JSON-Patch operations with value are supported", path=op_path)
        change_path = _pointer_to_change(operation.get("path"), path=op_path, plan_shot_id=plan_shot_id)
        changes[change_path] = copy.deepcopy(operation.get("value"))
    return changes


def _normalize_patch(raw: Any, index: int) -> dict[str, Any]:
    path = f"patches[{index}]"
    if not isinstance(raw, dict):
        raise CreativePatchSchemaError("patch must be an object", path=path)
    plan_shot_id = _ensure_string(raw.get("plan_shot_id"), label="plan_shot_id", path=f"{path}.plan_shot_id")
    source_format = "canonical"
    if "changes" in raw:
        forbidden = sorted(set(raw) - PATCH_KEYS)
        if forbidden:
            raise CreativePatchSchemaError(
                f"patch contains forbidden fields: {', '.join(forbidden)}",
                code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                path=path,
            )
        changes = _normalize_changes(raw.get("changes"), path=f"{path}")
    elif "patch" in raw:
        forbidden = sorted(set(raw) - ({"plan_shot_id", "patch_id", "patch", "rationale", "confidence"}))
        if forbidden:
            raise CreativePatchSchemaError(
                f"patch contains forbidden fields: {', '.join(forbidden)}",
                code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                path=path,
            )
        patch_value = raw.get("patch")
        if isinstance(patch_value, dict) and not {"op", "path", "value"}.intersection(patch_value):
            changes = _nested_changes(patch_value, path=f"{path}.patch")
            source_format = "nested_patch_wrapper"
        else:
            operations = patch_value if isinstance(patch_value, list) else [patch_value]
            changes = _operation_changes(operations, path=path, plan_shot_id=plan_shot_id)
            source_format = "json_patch_wrapper"
    elif "path" in raw and "value" in raw:
        forbidden = sorted(set(raw) - ({"plan_shot_id", "patch_id", "path", "value", "op", "rationale", "confidence"}))
        if forbidden:
            raise CreativePatchSchemaError(
                f"patch contains forbidden fields: {', '.join(forbidden)}",
                code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                path=path,
            )
        changes = _operation_changes([{"op": raw.get("op") or "replace", "path": raw.get("path"), "value": raw.get("value")}], path=path, plan_shot_id=plan_shot_id)
        source_format = "json_patch_operation"
    else:
        changes = _nested_changes(raw, path=path)
        source_format = "nested_creative_fields"
    normalized: dict[str, Any] = {
        "plan_shot_id": plan_shot_id,
        "changes": changes,
    }
    patch_id = _text(raw.get("patch_id"))
    if patch_id:
        normalized["patch_id"] = patch_id
    rationale = _text(raw.get("rationale"))
    if rationale:
        normalized["rationale"] = rationale
    if "confidence" in raw:
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise CreativePatchSchemaError("confidence must be a number between 0 and 1", path=f"{path}.confidence")
        normalized["confidence"] = float(confidence)
    supplied_source = _text(raw.get("_source_format"))
    normalized["_source_format"] = supplied_source or source_format
    return normalized


def _coalesce_patches(patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge non-conflicting duplicate target patches deterministically."""
    result: list[dict[str, Any]] = []
    by_target: dict[str, dict[str, Any]] = {}
    for patch in patches:
        target = patch["plan_shot_id"]
        existing = by_target.get(target)
        if existing is None:
            existing = copy.deepcopy(patch)
            by_target[target] = existing
            result.append(existing)
            continue
        for change_path, value in patch["changes"].items():
            if change_path in existing["changes"] and existing["changes"][change_path] != value:
                raise CreativePatchSchemaError(
                    f"conflicting changes for plan_shot_id: {target}",
                    code="DIRECTOR_PATCH_DUPLICATE_TARGET",
                    path=f"patches[{target}].changes.{change_path}",
                )
            existing["changes"][change_path] = copy.deepcopy(value)
        existing["_source_format"] = "merged_equivalent"
    return result


def _normalize_camera(raw: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise CreativePatchSchemaError("auxiliary camera must be a non-empty object", path=path)
    allowed = {"shot_size", "angle", "movement", "speed", "camera_side"}
    forbidden = sorted(set(raw) - allowed)
    if forbidden:
        raise CreativePatchSchemaError(
            f"auxiliary camera contains forbidden fields: {', '.join(forbidden)}",
            code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
            path=path,
        )
    return {str(key): copy.deepcopy(value) for key, value in raw.items()}


def _normalize_auxiliary(raw: Any, index: int) -> dict[str, Any]:
    path = f"auxiliary_shot_proposals[{index}]"
    if not isinstance(raw, dict):
        raise CreativePatchSchemaError("auxiliary proposal must be an object", path=path)
    forbidden = sorted(set(raw) - AUXILIARY_KEYS)
    if forbidden:
        raise CreativePatchSchemaError(
            f"auxiliary proposal contains forbidden fields: {', '.join(forbidden)}",
            code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
            path=path,
        )
    proposal_type = _ensure_string(raw.get("proposal_type"), label="proposal_type", path=f"{path}.proposal_type").lower()
    if proposal_type not in AUXILIARY_TYPES:
        raise CreativePatchSchemaError(
            f"unsupported auxiliary proposal_type: {proposal_type}",
            code="INVALID_AUXILIARY_TYPE",
            path=f"{path}.proposal_type",
        )
    participants = raw.get("participants")
    if not isinstance(participants, list) or any(not _text(item) for item in participants):
        raise CreativePatchSchemaError("participants must be a list of non-empty IDs", path=f"{path}.participants")
    normalized: dict[str, Any] = {
        "proposal_id": _ensure_string(raw.get("proposal_id"), label="proposal_id", path=f"{path}.proposal_id"),
        "proposal_type": proposal_type,
        "source_beat_id": _ensure_string(raw.get("source_beat_id"), label="source_beat_id", path=f"{path}.source_beat_id"),
        "insert_after_plan_shot_id": _ensure_string(raw.get("insert_after_plan_shot_id"), label="insert_after_plan_shot_id", path=f"{path}.insert_after_plan_shot_id"),
        "purpose": _ensure_string(raw.get("purpose"), label="purpose", path=f"{path}.purpose"),
        "why_needed": _ensure_string(raw.get("why_needed"), label="why_needed", path=f"{path}.why_needed"),
        "participants": [_text(item) for item in participants],
        "camera": _normalize_camera(raw.get("camera"), path=f"{path}.camera"),
    }
    if "estimated_duration_seconds" in raw:
        duration = raw.get("estimated_duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or float(duration) <= 0:
            raise CreativePatchSchemaError("estimated_duration_seconds must be positive", path=f"{path}.estimated_duration_seconds")
        normalized["estimated_duration_seconds"] = float(duration)
    rationale = _text(raw.get("rationale"))
    if rationale:
        normalized["rationale"] = rationale
    return normalized


def parse_creative_patch(raw: Any) -> dict[str, Any]:
    """Parse a strict patch document and return a normalized copy.

    Complete ``shots``/``scene_name``/``unknowns`` responses are intentionally
    rejected here, before a Contract or Patch Compiler can see them.
    """

    if not isinstance(raw, dict):
        raise CreativePatchSchemaError("CreativePatch document must be an object")
    forbidden = sorted(set(raw) - PATCH_DOCUMENT_KEYS)
    if forbidden:
        raise CreativePatchSchemaError(
            f"document contains forbidden fields: {', '.join(forbidden)}",
            code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
        )
    version = _text(raw.get("schema_version"))
    if version != PATCH_SCHEMA_VERSION:
        raise CreativePatchSchemaError(
            f"schema_version must be {PATCH_SCHEMA_VERSION}",
            code="DIRECTOR_PATCH_SCHEMA_VERSION_INVALID",
            path="schema_version",
        )
    patches_raw = raw.get("patches")
    if not isinstance(patches_raw, list):
        raise CreativePatchSchemaError("patches must be a list", path="patches")
    patches = _coalesce_patches([_normalize_patch(item, index) for index, item in enumerate(patches_raw)])
    aux_raw = raw.get("auxiliary_shot_proposals", [])
    if not isinstance(aux_raw, list):
        raise CreativePatchSchemaError("auxiliary_shot_proposals must be a list", path="auxiliary_shot_proposals")
    auxiliary = [_normalize_auxiliary(item, index) for index, item in enumerate(aux_raw)]
    proposal_ids = [item["proposal_id"] for item in auxiliary]
    if len(set(proposal_ids)) != len(proposal_ids):
        raise CreativePatchSchemaError(
            "proposal_id values must be unique",
            code="DIRECTOR_AUXILIARY_DUPLICATE_ID",
            path="auxiliary_shot_proposals",
        )
    source_formats = sorted({str(item.get("_source_format") or "canonical") for item in patches})
    supplied_meta = raw.get("normalization_metadata")
    if supplied_meta is not None and not isinstance(supplied_meta, dict):
        raise CreativePatchSchemaError("normalization_metadata must be an object", path="normalization_metadata")
    normalized = {
        "schema_version": PATCH_SCHEMA_VERSION,
        "patches": patches,
        "auxiliary_shot_proposals": auxiliary,
        "normalization_metadata": {
            "normalization_applied": any(item != "canonical" for item in source_formats),
            "source_formats": source_formats,
        },
    }
    if isinstance(supplied_meta, dict) and supplied_meta != normalized["normalization_metadata"]:
        raise CreativePatchSchemaError(
            "normalization_metadata does not match normalized content",
            code="DIRECTOR_PATCH_NORMALIZATION_MISMATCH",
            path="normalization_metadata",
        )
    expected_fingerprint = patch_fingerprint(normalized)
    supplied_fingerprint = _text(raw.get("patch_fingerprint"))
    if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
        raise CreativePatchSchemaError(
            "patch_fingerprint does not match the normalized document",
            code="DIRECTOR_PATCH_FINGERPRINT_MISMATCH",
            path="patch_fingerprint",
        )
    normalized["patch_fingerprint"] = expected_fingerprint
    return normalized


def parse_creative_patch_partial(raw: Any) -> dict[str, Any]:
    """Salvage valid patch/proposal items while retaining item-level errors.

    The strict :func:`parse_creative_patch` boundary remains the default for
    callers that require an all-or-nothing document.  Contract-First planner
    callers use this opt-in helper after a strict parse failure so one bad
    model item cannot discard unrelated valid patches.  Protocol/version and
    fingerprint errors are reported as fatal; callers should fall back to an
    empty document for those cases.
    """

    errors: list[dict[str, Any]] = []

    def add_error(exc: CreativePatchSchemaError, *, fallback_path: str) -> None:
        errors.append({"code": exc.code, "path": exc.path or fallback_path, "message": str(exc)})

    if not isinstance(raw, dict):
        return {
            "status": "invalid",
            "fatal": True,
            "errors": [{"code": "DIRECTOR_PATCH_SCHEMA_INVALID", "path": "", "message": "CreativePatch document must be an object"}],
            "document": None,
        }

    for key in sorted(set(raw) - PATCH_DOCUMENT_KEYS):
        errors.append({
            "code": "DIRECTOR_PATCH_FIELD_FORBIDDEN",
            "path": str(key),
            "message": f"document contains forbidden fields: {key}",
        })

    if _text(raw.get("schema_version")) != PATCH_SCHEMA_VERSION:
        errors.append({
            "code": "DIRECTOR_PATCH_SCHEMA_VERSION_INVALID",
            "path": "schema_version",
            "message": f"schema_version must be {PATCH_SCHEMA_VERSION}",
        })
        return {"status": "invalid", "fatal": True, "errors": errors, "document": None}

    patches: list[dict[str, Any]] = []
    patch_by_target: dict[str, dict[str, Any]] = {}
    patches_raw = raw.get("patches")
    if not isinstance(patches_raw, list):
        errors.append({"code": "DIRECTOR_PATCH_SCHEMA_INVALID", "path": "patches", "message": "patches must be a list"})
        patches_raw = []
    for index, item in enumerate(patches_raw):
        try:
            normalized = _normalize_patch(item, index)
            target = normalized["plan_shot_id"]
            existing = patch_by_target.get(target)
            if existing is None:
                patch_by_target[target] = normalized
                patches.append(normalized)
            else:
                for change_path, value in normalized["changes"].items():
                    if change_path in existing["changes"] and existing["changes"][change_path] != value:
                        raise CreativePatchSchemaError(
                            f"conflicting changes for plan_shot_id: {target}",
                            code="DIRECTOR_PATCH_DUPLICATE_TARGET",
                            path=f"patches[{index}].changes.{change_path}",
                        )
                    existing["changes"][change_path] = copy.deepcopy(value)
                existing["_source_format"] = "merged_equivalent"
        except CreativePatchSchemaError as exc:
            add_error(exc, fallback_path=f"patches[{index}]")

    auxiliary: list[dict[str, Any]] = []
    seen_proposals: set[str] = set()
    aux_raw = raw.get("auxiliary_shot_proposals", [])
    if not isinstance(aux_raw, list):
        errors.append({"code": "DIRECTOR_PATCH_SCHEMA_INVALID", "path": "auxiliary_shot_proposals", "message": "auxiliary_shot_proposals must be a list"})
        aux_raw = []
    for index, item in enumerate(aux_raw):
        try:
            normalized = _normalize_auxiliary(item, index)
            proposal_id = normalized["proposal_id"]
            if proposal_id in seen_proposals:
                raise CreativePatchSchemaError(
                    "proposal_id values must be unique",
                    code="DIRECTOR_AUXILIARY_DUPLICATE_ID",
                    path=f"auxiliary_shot_proposals[{index}].proposal_id",
                )
            seen_proposals.add(proposal_id)
            auxiliary.append(normalized)
        except CreativePatchSchemaError as exc:
            add_error(exc, fallback_path=f"auxiliary_shot_proposals[{index}]")

    source_formats = sorted({str(item.get("_source_format") or "canonical") for item in patches})
    normalized_document = {
        "schema_version": PATCH_SCHEMA_VERSION,
        "patches": patches,
        "auxiliary_shot_proposals": auxiliary,
        "normalization_metadata": {
            "normalization_applied": any(item != "canonical" for item in source_formats),
            "source_formats": source_formats,
        },
    }
    supplied_meta = raw.get("normalization_metadata")
    if isinstance(supplied_meta, dict) and supplied_meta != normalized_document["normalization_metadata"]:
        errors.append({
            "code": "DIRECTOR_PATCH_NORMALIZATION_MISMATCH",
            "path": "normalization_metadata",
            "message": "normalization_metadata does not match normalized content",
        })
    expected_fingerprint = patch_fingerprint(normalized_document)
    supplied_fingerprint = _text(raw.get("patch_fingerprint"))
    if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
        errors.append({
            "code": "DIRECTOR_PATCH_FINGERPRINT_MISMATCH",
            "path": "patch_fingerprint",
            "message": "patch_fingerprint does not match the normalized document",
        })
    normalized_document["patch_fingerprint"] = expected_fingerprint
    fatal = any(item.get("code") in {"DIRECTOR_PATCH_SCHEMA_VERSION_INVALID", "DIRECTOR_PATCH_FINGERPRINT_MISMATCH"} for item in errors)
    return {
        "status": "invalid" if fatal else ("partial" if errors else "valid"),
        "fatal": fatal,
        "errors": errors,
        "document": normalized_document,
    }


def validate_creative_patch_document(raw: Any) -> dict[str, Any]:
    """Return diagnostics without raising, for API preview/telemetry callers."""

    try:
        document = parse_creative_patch(raw)
    except CreativePatchSchemaError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "document": None}
    return {"status": "valid", "errors": [], "document": document}


normalize_creative_patch = parse_creative_patch
parse_director_creative_patch = parse_creative_patch
normalize_creative_patch_partial = parse_creative_patch_partial
parse_director_creative_patch_partial = parse_creative_patch_partial
validate_patch_document = validate_creative_patch_document


__all__ = [
    "PATCH_SCHEMA_VERSION",
    "PATCH_DOCUMENT_KEYS",
    "PATCH_KEYS",
    "AUXILIARY_KEYS",
    "AUXILIARY_TYPES",
    "CreativePatchSchemaError",
    "patch_fingerprint",
    "parse_creative_patch",
    "parse_creative_patch_partial",
    "normalize_creative_patch",
    "normalize_creative_patch_partial",
    "parse_director_creative_patch",
    "parse_director_creative_patch_partial",
    "validate_creative_patch_document",
    "validate_patch_document",
]
