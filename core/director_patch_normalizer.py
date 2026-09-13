"""Level 0 canonical normalization for Director Quality patches.

The normalizer handles protocol-equivalent representations only.  It never
chooses a new creative value and never applies a patch to a ShotPlan.  The
authority boundary remains in :mod:`core.director_patch_validator` and the
compiler; this module only converts a provider payload into a deterministic
canonical representation or reports a fail-closed error.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Iterable


NORMALIZER_VERSION = "director-quality-v2-2-level0"
PATCH_SCHEMA_VERSION = "director_creative_patch_v1"

CREATIVE_ROOT_FIELDS = {
    "purpose",
    "dramatic_function",
    "why_this_shot",
    "emotion",
    "performance_direction",
    "camera",
    "composition",
    "edit",
    "information_strategy",
    "visual_emphasis",
}
CAMERA_FIELDS = {"shot_size", "angle", "movement", "speed", "camera_side"}
IMMUTABLE_ROOT_FIELDS = {
    "scene_name",
    "unknowns",
    "scene_id",
    "beat_id",
    "event",
    "dialogue",
    "participants",
    "action_beats",
    "entry_state",
    "exit_state",
    "asset_bindings",
    "continuity_contract",
    "continuity",
    "spatial_source",
}

# Only aliases that are part of the wire protocol are accepted.  Unknown
# spellings are deliberately not guessed.
FIELD_ALIASES = {
    "shotsize": "shot_size",
    "shot-size": "shot_size",
    "shotSize": "shot_size",
    "cameraMovement": "movement",
    "camera_movement": "movement",
    "cameraSpeed": "speed",
    "cameraSide": "camera_side",
    "cameraAngle": "angle",
    "cutReason": "cut_reason",
    "cut-reason": "cut_reason",
    "holdAfterActionSeconds": "hold_after_action_seconds",
    "hold-after-action-seconds": "hold_after_action_seconds",
    "whyThisShot": "why_this_shot",
    "dramaticFunction": "dramatic_function",
    "visualEmphasis": "visual_emphasis",
    "performanceDirection": "performance_direction",
    "informationStrategy": "information_strategy",
}

_ENUM_ALIASES: dict[str, dict[str, str]] = {
    "shot_size": {
        "cu": "CU",
        "close-up": "CU",
        "close_up": "CU",
        "closeup": "CU",
        "close up": "CU",
        "mcu": "MCU",
        "medium-close-up": "MCU",
        "medium_close_up": "MCU",
        "medium close up": "MCU",
        "ecu": "ECU",
        "extreme-close-up": "ECU",
        "extreme_close_up": "ECU",
        "extreme close up": "ECU",
        "ms": "MS",
        "medium-shot": "MS",
        "medium_shot": "MS",
        "medium shot": "MS",
        "ls": "LS",
        "long-shot": "LS",
        "long_shot": "LS",
        "long shot": "LS",
        "ws": "WS",
        "wide-shot": "WS",
        "wide_shot": "WS",
        "wide shot": "WS",
        "els": "ELS",
        "extreme-long-shot": "ELS",
        "extreme_long_shot": "ELS",
        "extreme long shot": "ELS",
        "ts": "TS",
        "two-shot": "TS",
        "two_shot": "TS",
        "two shot": "TS",
    },
    "angle": {
        "eye-level": "eye_level",
        "eye level": "eye_level",
        "high-angle": "high_angle",
        "high angle": "high_angle",
        "low-angle": "low_angle",
        "low angle": "low_angle",
        "overhead-angle": "overhead",
    },
}


class PatchNormalizationError(ValueError):
    """A non-equivalent or unsafe provider representation."""

    code = "DIRECTOR_PATCH_NORMALIZATION_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _alias(value: str) -> str:
    value = _text(value)
    return FIELD_ALIASES.get(value, value)


def _canonical_segment(value: str) -> str:
    value = _text(value)
    if not value:
        return ""
    return _alias(value)


def canonical_path(
    path: Any,
    *,
    plan_shot_id: str = "",
    known_plan_shot_ids: Iterable[str] | None = None,
) -> str:
    """Return a dotted creative path relative to one declared shot.

    Accepted equivalent forms include ``camera.shot_size``,
    ``/shots/S03/camera/shot_size`` and ``/shots/*/camera/shot_size`` when the
    item declares ``plan_shot_id=S03``.  Numeric selectors are resolved when a
    plan id list is supplied; otherwise the declared id remains authoritative
    and the numeric selector is treated as a provider-local equivalent.
    """

    raw = _text(path)
    if not raw:
        raise PatchNormalizationError("patch path is required", code="DIRECTOR_PATCH_PATH_MISSING")
    if ".." in raw or "\\" in raw:
        raise PatchNormalizationError("patch path contains unsafe traversal", code="DIRECTOR_PATCH_PATH_FORBIDDEN", path=raw)
    parts = [_canonical_segment(part) for part in raw.replace(".", "/").split("/") if _text(part)]
    if not parts:
        raise PatchNormalizationError("patch path is empty", code="DIRECTOR_PATCH_PATH_MISSING", path=raw)
    declared = _text(plan_shot_id)
    if parts[0] == "shots":
        if len(parts) < 3:
            raise PatchNormalizationError("shot patch path must address a field", code="DIRECTOR_PATCH_PATH_FORBIDDEN", path=raw)
        selector = parts[1]
        known = [str(item).strip() for item in (known_plan_shot_ids or []) if str(item).strip()]
        if selector == "*":
            if not declared:
                raise PatchNormalizationError("wildcard shot path requires plan_shot_id", code="DIRECTOR_PATCH_TARGET_MISMATCH", path=raw)
        elif selector.isdigit():
            if known and int(selector) >= len(known):
                raise PatchNormalizationError("shot index is out of range", code="DIRECTOR_PATCH_TARGET_MISMATCH", path=raw)
            if known and declared and known[int(selector)] != declared:
                raise PatchNormalizationError("shot path targets a different plan_shot_id", code="DIRECTOR_PATCH_TARGET_MISMATCH", path=raw)
        elif declared and selector != declared:
            raise PatchNormalizationError("shot path targets a different plan_shot_id", code="DIRECTOR_PATCH_TARGET_MISMATCH", path=raw)
        parts = parts[2:]
    # A path written as ``camera.shotSize`` is equivalent to the canonical
    # dotted path.  Canonicalize every segment only through the explicit alias
    # table; arbitrary semantic guessing is prohibited.
    parts = [_canonical_segment(part) for part in parts]
    if not all(parts):
        raise PatchNormalizationError("patch path contains an empty segment", code="DIRECTOR_PATCH_PATH_FORBIDDEN", path=raw)
    return ".".join(parts)


def normalize_value(path: str, value: Any) -> tuple[Any, str | None]:
    """Normalize only values with a schema-declared equivalent form."""

    parts = [part for part in _text(path).split(".") if part]
    leaf = parts[-1] if parts else ""
    if isinstance(value, str):
        trimmed = value.strip()
        if leaf in {"intensity", "hold_after_action_seconds", "estimated_duration_seconds"} and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", trimmed):
            number = float(trimmed)
            if number.is_integer() and leaf == "intensity":
                number = int(number)
            return number, f"numeric_string:{leaf}"
        enum_map = _ENUM_ALIASES.get(leaf)
        if enum_map:
            mapped = enum_map.get(trimmed.lower())
            if mapped is not None:
                return mapped, f"enum_alias:{leaf}"
        if trimmed != value:
            return trimmed, "trim_whitespace"
        return value, None
    if leaf in {"intensity", "hold_after_action_seconds", "estimated_duration_seconds"} and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value, None
    return copy.deepcopy(value), None


def flatten_nested_changes(raw: dict[str, Any], *, path: str = "patch") -> tuple[dict[str, Any], list[str]]:
    """Flatten a nested creative shot object without dropping unknown fields."""

    changes: dict[str, Any] = {}
    reasons: list[str] = []
    for key, value in raw.items():
        key = _canonical_segment(str(key))
        if key in {"plan_shot_id", "patch_id", "rationale", "confidence", "source_format", "_source_format"}:
            continue
        if key in IMMUTABLE_ROOT_FIELDS or key not in CREATIVE_ROOT_FIELDS:
            raise PatchNormalizationError(
                f"patch contains forbidden fields: {key}",
                code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                path=f"{path}.{key}",
            )
        if key == "camera" and isinstance(value, dict):
            for child, child_value in value.items():
                child_key = _canonical_segment(str(child))
                if child_key not in CAMERA_FIELDS:
                    raise PatchNormalizationError(
                        f"camera contains forbidden fields: {child_key}",
                        code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
                        path=f"{path}.camera.{child_key}",
                    )
                cpath = f"camera.{child_key}"
                normalized, reason = normalize_value(cpath, child_value)
                if cpath in changes and changes[cpath] != normalized:
                    raise PatchNormalizationError("conflicting normalized changes", code="DIRECTOR_PATCH_NORMALIZATION_CONFLICT", path=cpath)
                changes[cpath] = normalized
                if reason:
                    reasons.append(reason)
            continue
        if key in {"emotion", "composition", "edit", "information_strategy", "performance_direction"} and isinstance(value, dict):
            for child, child_value in value.items():
                child_key = _canonical_segment(str(child))
                cpath = f"{key}.{child_key}"
                normalized, reason = normalize_value(cpath, child_value)
                if cpath in changes and changes[cpath] != normalized:
                    raise PatchNormalizationError("conflicting normalized changes", code="DIRECTOR_PATCH_NORMALIZATION_CONFLICT", path=cpath)
                changes[cpath] = normalized
                if reason:
                    reasons.append(reason)
            continue
        normalized, reason = normalize_value(key, value)
        if key in changes and changes[key] != normalized:
            raise PatchNormalizationError("conflicting normalized changes", code="DIRECTOR_PATCH_NORMALIZATION_CONFLICT", path=key)
        changes[key] = normalized
        if reason:
            reasons.append(reason)
    if not changes:
        raise PatchNormalizationError("nested creative patch has no supported fields", path=path)
    return changes, reasons


def normalize_operation(operation: dict[str, Any], *, plan_shot_id: str, known_plan_shot_ids: Iterable[str] | None = None) -> tuple[str, Any, str | None]:
    if not isinstance(operation, dict):
        raise PatchNormalizationError("patch operation must be an object", path="patch")
    forbidden = sorted(set(operation) - {"op", "path", "value"})
    if forbidden:
        raise PatchNormalizationError(
            f"patch operation contains forbidden fields: {', '.join(forbidden)}",
            code="DIRECTOR_PATCH_FIELD_FORBIDDEN",
            path="patch",
        )
    op = _text(operation.get("op") or "replace").lower()
    if op not in {"add", "replace"} or "value" not in operation:
        raise PatchNormalizationError("only add/replace operations with value are supported", path="patch")
    normalized_path = canonical_path(operation.get("path"), plan_shot_id=plan_shot_id, known_plan_shot_ids=known_plan_shot_ids)
    value, reason = normalize_value(normalized_path, operation.get("value"))
    return normalized_path, value, reason


def normalize_patch_item(
    raw: Any,
    *,
    index: int = 0,
    known_plan_shot_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Normalize one provider patch into ``plan_shot_id + changes``."""

    path = f"patches[{index}]"
    if not isinstance(raw, dict):
        raise PatchNormalizationError("patch must be an object", path=path)
    plan_shot_id = _text(raw.get("plan_shot_id"))
    if not plan_shot_id:
        raise PatchNormalizationError("plan_shot_id is required", code="DIRECTOR_PATCH_ID_MISSING", path=f"{path}.plan_shot_id")
    reasons: list[str] = []
    source_format = "canonical"
    changes: dict[str, Any]
    if "changes" in raw:
        forbidden = sorted(set(raw) - {"plan_shot_id", "patch_id", "changes", "rationale", "confidence", "_source_format"})
        if forbidden:
            raise PatchNormalizationError(f"patch contains forbidden fields: {', '.join(forbidden)}", code="DIRECTOR_PATCH_FIELD_FORBIDDEN", path=path)
        changes = {}
        if not isinstance(raw.get("changes"), dict) or not raw["changes"]:
            raise PatchNormalizationError("changes must be a non-empty object", path=f"{path}.changes")
        for raw_path, raw_value in raw["changes"].items():
            normalized_path = canonical_path(raw_path, plan_shot_id=plan_shot_id, known_plan_shot_ids=known_plan_shot_ids)
            value, reason = normalize_value(normalized_path, raw_value)
            if normalized_path in changes and changes[normalized_path] != value:
                raise PatchNormalizationError("conflicting normalized changes", code="DIRECTOR_PATCH_NORMALIZATION_CONFLICT", path=normalized_path)
            changes[normalized_path] = value
            if normalized_path != str(raw_path).strip():
                reasons.append("path_canonicalization")
            if reason:
                reasons.append(reason)
        source_format = "canonical" if not reasons else "normalized_changes"
    elif "patch" in raw:
        forbidden = sorted(set(raw) - {"plan_shot_id", "patch_id", "patch", "rationale", "confidence"})
        if forbidden:
            raise PatchNormalizationError(f"patch contains forbidden fields: {', '.join(forbidden)}", code="DIRECTOR_PATCH_FIELD_FORBIDDEN", path=path)
        patch_value = raw.get("patch")
        if isinstance(patch_value, dict) and not {"op", "path", "value"}.intersection(patch_value):
            changes, nested_reasons = flatten_nested_changes(patch_value, path=f"{path}.patch")
            reasons.extend(nested_reasons)
            source_format = "nested_patch_wrapper"
        else:
            operations = patch_value if isinstance(patch_value, list) else [patch_value]
            changes = {}
            for operation in operations:
                normalized_path, value, reason = normalize_operation(operation, plan_shot_id=plan_shot_id, known_plan_shot_ids=known_plan_shot_ids)
                if normalized_path in changes and changes[normalized_path] != value:
                    raise PatchNormalizationError("conflicting normalized changes", code="DIRECTOR_PATCH_NORMALIZATION_CONFLICT", path=normalized_path)
                changes[normalized_path] = value
                reasons.append("path_canonicalization")
                if reason:
                    reasons.append(reason)
            source_format = "json_patch_wrapper"
    elif "path" in raw and "value" in raw:
        forbidden = sorted(set(raw) - {"plan_shot_id", "patch_id", "path", "value", "op", "rationale", "confidence"})
        if forbidden:
            raise PatchNormalizationError(f"patch contains forbidden fields: {', '.join(forbidden)}", code="DIRECTOR_PATCH_FIELD_FORBIDDEN", path=path)
        normalized_path, value, reason = normalize_operation({"op": raw.get("op") or "replace", "path": raw.get("path"), "value": raw.get("value")}, plan_shot_id=plan_shot_id, known_plan_shot_ids=known_plan_shot_ids)
        changes = {normalized_path: value}
        source_format = "json_patch_operation"
        reasons.append("path_canonicalization")
        if reason:
            reasons.append(reason)
    else:
        changes, nested_reasons = flatten_nested_changes(raw, path=path)
        reasons.extend(nested_reasons)
        source_format = "nested_creative_fields"
    normalized: dict[str, Any] = {"plan_shot_id": plan_shot_id, "changes": changes}
    for key in ("patch_id", "rationale"):
        value = _text(raw.get(key))
        if value:
            normalized[key] = value
    if "confidence" in raw:
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise PatchNormalizationError("confidence must be a number between 0 and 1", path=f"{path}.confidence")
        normalized["confidence"] = float(confidence)
    normalized["_source_format"] = _text(raw.get("_source_format")) or source_format
    if reasons:
        normalized["_normalization_reasons"] = sorted(set(reasons))
    return normalized


def normalize_patch_document(
    raw: Any,
    *,
    known_plan_shot_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Normalize a full patch document and return an auditable copy.

    This function does not validate target existence, immutable authority or
    creative semantics.  Those checks deliberately remain downstream.
    """

    if not isinstance(raw, dict):
        raise PatchNormalizationError("CreativePatch document must be an object")
    before = fingerprint(raw)
    version = _text(raw.get("schema_version"))
    if version and version != PATCH_SCHEMA_VERSION:
        raise PatchNormalizationError("unsupported patch schema version", code="DIRECTOR_PATCH_SCHEMA_VERSION_INVALID", path="schema_version")
    patches_raw = raw.get("patches")
    if patches_raw is None and "patch" in raw:
        patches_raw = raw.get("patch")
    if not isinstance(patches_raw, list):
        raise PatchNormalizationError("patches must be a list", path="patches")
    patches = [normalize_patch_item(item, index=index, known_plan_shot_ids=known_plan_shot_ids) for index, item in enumerate(patches_raw)]
    # Preserve all items here; merging is a semantic Level 1 operation.  The
    # normalizer must not silently discard a conflicting duplicate.
    normalized: dict[str, Any] = {
        "schema_version": version or PATCH_SCHEMA_VERSION,
        "patches": patches,
        "auxiliary_shot_proposals": copy.deepcopy(raw.get("auxiliary_shot_proposals") or []),
    }
    events = []
    for item in patches:
        for reason in item.get("_normalization_reasons", []):
            events.append({"plan_shot_id": item["plan_shot_id"], "reason": reason})
    normalized["normalization_metadata"] = {
        "normalizer_version": NORMALIZER_VERSION,
        "normalization_applied": bool(events or any(item.get("_source_format") != "canonical" for item in patches)),
        "events": events,
        "source_formats": sorted({str(item.get("_source_format") or "canonical") for item in patches}),
        "before_fingerprint": before,
    }
    normalized["normalization_metadata"]["after_fingerprint"] = fingerprint(normalized)
    return normalized


# Friendly names for callers and hidden/regression tests.
normalize_path = canonical_path
normalize_patch = normalize_patch_item
normalize_creative_patch_document = normalize_patch_document


__all__ = [
    "NORMALIZER_VERSION",
    "PATCH_SCHEMA_VERSION",
    "PatchNormalizationError",
    "fingerprint",
    "canonical_path",
    "normalize_path",
    "normalize_value",
    "flatten_nested_changes",
    "normalize_operation",
    "normalize_patch_item",
    "normalize_patch",
    "normalize_patch_document",
    "normalize_creative_patch_document",
]
