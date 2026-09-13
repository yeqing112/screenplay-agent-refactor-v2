"""Bounded, non-secret evidence traces for rejected Director patches.

The trace is captured immediately after provider JSON parsing and before any
normalization or contract validation mutates the item.  It deliberately keeps
structured patch evidence (with bounded text values) while retaining only
fingerprints for large/unstructured payloads such as prompts or responses.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from core.director_patch_path_resolver import PatchPathResolutionError, resolve_patch_path


TRACE_SCHEMA_VERSION = "director_rejection_trace_v1"
REJECTION_STAGES = {
    "RAW_PARSE",
    "PATH_PARSE",
    "PATH_RESOLUTION",
    "ALLOWED_PATH_CHECK",
    "VALUE_SCHEMA",
    "CONTRACT_VALIDATION",
    "PATCH_MERGE",
    "DETERMINISTIC_REPAIR",
    "LLM_REPAIR",
    "QUALITY_VALIDATION",
    "FINAL_FALLBACK",
}
FALLBACK_CLASSIFICATIONS = {
    "TRUE_FORBIDDEN",
    "SAFE_ALIAS",
    "SAFE_ENVELOPE_VARIANT",
    "CONTRACT_MISMATCH",
    "COMPILER_BUG",
    "AMBIGUOUS",
    "INVALID_VALUE",
    "FACT_OVERRIDE",
    "UNKNOWN_SHOT",
    "QUALITY_REPAIR_EXHAUSTED",
    "UNKNOWN",
}
_SHOT_SELECTOR_RE = re.compile(r"(?:^|[/.])shots?[/.]([^/.]+)", re.IGNORECASE)
_IMMUTABLE_ROOTS = {
    "scene_name", "unknowns", "scene_id", "beat_id", "event", "dialogue",
    "participants", "action_beats", "entry_state", "exit_state",
    "asset_bindings", "continuity_contract", "continuity", "spatial_source",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bounded(value: Any, *, depth: int = 0) -> Any:
    """Copy structured evidence without retaining unbounded text payloads."""

    if depth > 5:
        return "<truncated>"
    if isinstance(value, str):
        return value[:1024]
    if isinstance(value, dict):
        return {str(key)[:120]: _bounded(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_bounded(item, depth=depth + 1) for item in value[:64]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1024]


def _raw_paths(raw_patch: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    changes = raw_patch.get("changes")
    if isinstance(changes, dict):
        paths.extend(_text(path) for path in changes if _text(path))
    patch = raw_patch.get("patch")
    if isinstance(patch, dict) and not {"op", "path", "value"}.intersection(patch):
        for key, value in patch.items():
            if isinstance(value, dict):
                paths.extend(f"{key}.{child}" for child in value if _text(child))
            elif _text(key):
                paths.append(_text(key))
    else:
        operations = patch if isinstance(patch, list) else ([patch] if patch is not None else [])
        for operation in operations:
            if isinstance(operation, dict) and _text(operation.get("path")):
                paths.append(_text(operation.get("path")))
    if _text(raw_patch.get("path")):
        paths.append(_text(raw_patch.get("path")))
    if not paths:
        ignored = {"plan_shot_id", "patch_id", "rationale", "confidence", "op", "value", "_source_format"}
        for key, value in raw_patch.items():
            if key in ignored:
                continue
            if isinstance(value, dict):
                paths.extend(f"{key}.{child}" for child in value if _text(child))
            elif _text(key):
                paths.append(_text(key))
    # Preserve provider order while avoiding duplicate trace aliases.
    return list(dict.fromkeys(path for path in paths if path))


def _raw_value_type(raw_patch: dict[str, Any], paths: list[str]) -> str:
    value: Any = raw_patch.get("value")
    if value is None and isinstance(raw_patch.get("changes"), dict) and paths:
        value = raw_patch["changes"].get(paths[0])
    if value is None and isinstance(raw_patch.get("patch"), list) and raw_patch["patch"]:
        value = raw_patch["patch"][0].get("value") if isinstance(raw_patch["patch"][0], dict) else None
    if value is None:
        return "null_or_missing"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _selector(raw_path: str) -> str:
    match = _SHOT_SELECTOR_RE.search(_text(raw_path))
    return _text(match.group(1)) if match else ""


def _rule(source_format: str, raw_path: str) -> str:
    selector = _selector(raw_path)
    if selector.isdigit():
        return "numeric_index"
    if source_format == "json_pointer":
        return "slash_shot_selector"
    if source_format == "shots_prefix":
        return "shots_prefix"
    if source_format == "shot_prefix":
        return "shot_id_prefix"
    if source_format == "relative":
        return "relative_path"
    return source_format or "unknown"


def _first_path(raw_patch: dict[str, Any]) -> str:
    return (_raw_paths(raw_patch) or [""])[0]


def _trace_id(scene_id: str, episode: Any, index: int, raw_patch: dict[str, Any]) -> str:
    seed = f"{scene_id}|{episode}|{index}|{_fingerprint(raw_patch)}"
    return "rtrace_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def capture_raw_patch_trace(
    raw_patch: Any,
    *,
    scene_id: str = "",
    episode: int | str | None = None,
    provider_patch_index: int = 0,
    known_plan_shot_ids: Iterable[str] | None = None,
    allowed_patch_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Capture one raw provider item before normalization.

    Resolver failures are represented in the trace rather than raised.  A
    second parse without the allow-list preserves a canonical candidate when
    possible, allowing the later classifier to distinguish path parsing from
    whitelist rejection without relaxing the actual pipeline.
    """

    item = raw_patch if isinstance(raw_patch, dict) else {"raw_value": _bounded(raw_patch)}
    raw_id = _text(item.get("plan_shot_id"))
    paths = _raw_paths(item)
    raw_path = paths[0] if paths else ""
    parsed: dict[str, Any] = {"plan_shot_id": raw_id, "path": ""}
    canonical: dict[str, Any] = {"plan_shot_id": raw_id, "path": ""}
    source_format = ""
    alias_hit = False
    allowed_match = False
    resolution_error = ""
    resolution_code = ""
    if raw_path:
        try:
            resolved = resolve_patch_path(
                raw_path,
                plan_shot_id=raw_id,
                known_plan_shot_ids=known_plan_shot_ids,
                allowed_patch_paths=allowed_patch_paths,
            )
            parsed = {"plan_shot_id": resolved.plan_shot_id, "path": resolved.path}
            canonical = dict(parsed)
            source_format = resolved.source_format
            alias_hit = bool(resolved.alias_hit)
            allowed_match = True
        except PatchPathResolutionError as exc:
            resolution_error = str(exc)[:400]
            resolution_code = exc.code
            try:
                parsed_resolved = resolve_patch_path(
                    raw_path,
                    plan_shot_id=raw_id,
                    known_plan_shot_ids=known_plan_shot_ids,
                    allowed_patch_paths=None,
                )
                parsed = {"plan_shot_id": parsed_resolved.plan_shot_id, "path": parsed_resolved.path}
                canonical = dict(parsed)
                source_format = parsed_resolved.source_format
                alias_hit = bool(parsed_resolved.alias_hit)
            except PatchPathResolutionError as parse_exc:
                resolution_code = resolution_code or parse_exc.code
                resolution_error = resolution_error or str(parse_exc)[:400]

    now = datetime.now(timezone.utc).isoformat()
    trace = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": _trace_id(_text(scene_id), episode, int(provider_patch_index), item),
        "created_at": now,
        "scene_id": _text(scene_id),
        "episode": episode,
        "provider_patch_index": int(provider_patch_index),
        "raw_patch": _bounded(item),
        "raw_patch_fingerprint": _fingerprint(item),
        "raw_plan_shot_id": raw_id,
        "raw_selector": _selector(raw_path),
        "raw_path": raw_path,
        "raw_paths": paths[:32],
        "raw_value_type": _raw_value_type(item, paths),
        "parsed": parsed,
        "canonical": canonical,
        "canonical_path": _text(canonical.get("path")),
        "path_resolution_rule": _rule(source_format, raw_path),
        "path_source_format": source_format,
        "path_alias_hit": alias_hit,
        "allowed_path_match": allowed_match,
        "normalization": {"applied": False, "rules": []},
        "resolution_error": resolution_error,
        "resolution_code": resolution_code,
        "compiler_stage": "",
        "validator_issue_code": "",
        "rejection_stage": "",
        "rejection_reason": "",
        "repair_attempts": [],
        "final_action": "",
        "fallback_classification": None,
    }
    return trace


def capture_raw_patch_traces(
    raw_output: Any,
    *,
    scene_id: str = "",
    episode: int | str | None = None,
    known_plan_shot_ids: Iterable[str] | None = None,
    allowed_patch_paths: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Capture every raw patch item in provider order before normalization."""

    if not isinstance(raw_output, dict):
        return []
    raw_patches = raw_output.get("patches") if isinstance(raw_output.get("patches"), list) else []
    traces: list[dict[str, Any]] = []
    for index, item in enumerate(raw_patches):
        traces.append(capture_raw_patch_trace(
            item,
            scene_id=scene_id,
            episode=episode,
            provider_patch_index=index,
            known_plan_shot_ids=known_plan_shot_ids,
            allowed_patch_paths=allowed_patch_paths,
        ))
    # Auxiliary proposals are provider items too.  Capture them at the same
    # pre-normalization boundary so an auxiliary schema rejection cannot be
    # accidentally associated with an unrelated ordinary patch.  Keep a
    # disjoint provider index while retaining the stable JSON item path.
    raw_auxiliary = raw_output.get("auxiliary_shot_proposals") if isinstance(raw_output.get("auxiliary_shot_proposals"), list) else []
    provider_offset = len(raw_patches)
    for index, item in enumerate(raw_auxiliary):
        trace = capture_raw_patch_trace(
            item,
            scene_id=scene_id,
            episode=episode,
            provider_patch_index=provider_offset + index,
            known_plan_shot_ids=known_plan_shot_ids,
            allowed_patch_paths=allowed_patch_paths,
        )
        trace["raw_item_type"] = "auxiliary_shot_proposal"
        trace["raw_item_index"] = index
        trace["raw_item_path"] = f"auxiliary_shot_proposals[{index}]"
        trace["raw_anchor_plan_shot_id"] = _text(item.get("insert_after_plan_shot_id"))
        traces.append(trace)
    return traces


def classify_rejection_trace(
    trace: dict[str, Any],
    *,
    issue_code: str = "",
    rejection_stage: str = "",
    final_action: str = "FALLBACK",
) -> str:
    """Classify from captured evidence only; never infer a creative value."""

    code = _text(issue_code).upper()
    stage = _text(rejection_stage).upper()
    if trace.get("raw_item_type") == "auxiliary_shot_proposal" and code == "DIRECTOR_PATCH_FIELD_FORBIDDEN":
        # Auxiliary proposals have their own explicit schema.  A field
        # rejected by that schema is forbidden for this proposal type; it is
        # not a creative patch alias and must remain fail-closed.
        return "TRUE_FORBIDDEN"
    if code in {"DIRECTOR_FACT_OVERRIDE", "FACT_OVERRIDE", "IMMUTABLE_VIOLATION"}:
        return "FACT_OVERRIDE"
    if code in {"UNKNOWN_PLAN_SHOT_ID", "DIRECTOR_PATCH_ID_MISSING", "UNKNOWN_SHOT"}:
        return "UNKNOWN_SHOT"
    if code in {"INVALID_PATCH_VALUE", "VALUE_SCHEMA", "REPAIR_INVALID_VALUE"}:
        return "INVALID_VALUE"
    if code in {"DIRECTOR_PATCH_PATH_AMBIGUOUS", "AMBIGUOUS_PATCH_PATH"} or trace.get("resolution_code") == "AMBIGUOUS_PATCH_PATH":
        return "AMBIGUOUS"
    if trace.get("allowed_path_match"):
        if trace.get("path_alias_hit"):
            return "SAFE_ALIAS"
        if trace.get("path_source_format") not in {"", "relative"}:
            return "SAFE_ENVELOPE_VARIANT"
        if stage in {"VALUE_SCHEMA", "LLM_REPAIR"}:
            return "INVALID_VALUE"
    if code in {"DIRECTOR_PATCH_FIELD_FORBIDDEN", "DIRECTOR_PATCH_PATH_FORBIDDEN"}:
        canonical_path = _text(trace.get("canonical_path"))
        root = canonical_path.split(".", 1)[0]
        if root in _IMMUTABLE_ROOTS or any(root == item for item in _IMMUTABLE_ROOTS):
            return "TRUE_FORBIDDEN"
        if trace.get("canonical_path") and not trace.get("allowed_path_match"):
            return "CONTRACT_MISMATCH"
    if code in {"QUALITY_REPAIR_EXHAUSTED", "LLM_REPAIR_CONTRACT_FAILURE"} or final_action == "FALLBACK" and stage == "LLM_REPAIR":
        return "QUALITY_REPAIR_EXHAUSTED"
    if code in {"COMPILER_BUG", "DIRECTOR_PATCH_COMPILE_INVALID"}:
        return "COMPILER_BUG"
    return "UNKNOWN"


def finalize_rejection_trace(
    trace: dict[str, Any],
    *,
    issue_code: str,
    rejection_stage: str,
    rejection_reason: str = "",
    final_action: str = "FALLBACK",
    repair_attempts: list[dict[str, Any]] | None = None,
    fallback_classification: str | None = None,
    normalization_rules: list[str] | None = None,
) -> dict[str, Any]:
    """Return an immutable-style completed trace envelope."""

    result = copy.deepcopy(trace)
    stage = _text(rejection_stage).upper()
    if stage not in REJECTION_STAGES:
        raise ValueError(f"unknown rejection stage: {rejection_stage}")
    classification = fallback_classification or classify_rejection_trace(
        result, issue_code=issue_code, rejection_stage=stage, final_action=final_action,
    )
    if classification not in FALLBACK_CLASSIFICATIONS:
        raise ValueError(f"unknown fallback classification: {classification}")
    result.update({
        "validator_issue_code": _text(issue_code),
        "rejection_stage": stage,
        "rejection_reason": _text(rejection_reason)[:1024],
        "repair_attempts": _bounded(repair_attempts or []),
        "final_action": _text(final_action).upper() or "FALLBACK",
        "fallback_classification": classification,
        "normalization": {
            "applied": bool(normalization_rules),
            "rules": list(dict.fromkeys(_text(item) for item in (normalization_rules or []) if _text(item))),
        },
    })
    return result


def find_trace_for_rejection(
    traces: Iterable[dict[str, Any]],
    *,
    plan_shot_id: str = "",
    raw_path: str = "",
    provider_patch_index: int | None = None,
) -> dict[str, Any] | None:
    """Find the best raw trace without fuzzy path guessing."""

    candidates = [item for item in traces if isinstance(item, dict)]
    if provider_patch_index is not None:
        exact = [item for item in candidates if item.get("provider_patch_index") == provider_patch_index]
        if exact:
            return copy.deepcopy(exact[0])
    if plan_shot_id:
        candidates = [item for item in candidates if _text(item.get("raw_plan_shot_id")) == _text(plan_shot_id)]
    if raw_path:
        exact_item = [item for item in candidates if _text(item.get("raw_item_path")) == _text(raw_path)]
        if exact_item:
            return copy.deepcopy(exact_item[0])
        exact = [item for item in candidates if _text(item.get("raw_path")) == _text(raw_path) or raw_path in (item.get("raw_paths") or [])]
        if exact:
            return copy.deepcopy(exact[0])
    return copy.deepcopy(candidates[0]) if candidates else None


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "REJECTION_STAGES",
    "FALLBACK_CLASSIFICATIONS",
    "capture_raw_patch_trace",
    "capture_raw_patch_traces",
    "classify_rejection_trace",
    "finalize_rejection_trace",
    "find_trace_for_rejection",
]
