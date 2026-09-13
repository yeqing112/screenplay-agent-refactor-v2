"""Level 1 deterministic repair for Director Quality patch documents.

Only repairs with one unambiguous answer live here.  Creative choices remain
untouched and are routed to the Level 2 local LLM repairer by the caller.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable

from core.director_patch_normalizer import (
    PatchNormalizationError,
    collect_path_resolution_metrics,
    fingerprint,
    normalize_patch_document,
)


DETERMINISTIC_REPAIR_VERSION = "director-quality-v2-2-level1"
PATH_ORDER = {
    "camera.shot_size": 10,
    "camera.angle": 20,
    "camera.movement": 30,
    "camera.speed": 40,
    "camera.camera_side": 50,
    "composition": 60,
    "why_this_shot": 70,
    "dramatic_function": 80,
    "emotion": 90,
    "performance_direction": 100,
    "edit": 110,
    "information_strategy": 120,
    "visual_emphasis": 130,
}


class DeterministicRepairError(ValueError):
    code = "DIRECTOR_DETERMINISTIC_REPAIR_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "", path_metrics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path
        self.path_metrics = copy.deepcopy(path_metrics or {})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _path_order(path: str) -> tuple[int, str]:
    value = _text(path)
    root = value.split(".", 1)[0]
    return PATH_ORDER.get(value, PATH_ORDER.get(root, 1000)), value


def _sort_key(patch: dict[str, Any]) -> tuple[str, tuple[int, str], str]:
    changes = patch.get("changes") if isinstance(patch.get("changes"), dict) else {}
    first_path = min((_path_order(str(path)) for path in changes), default=(1000, ""))
    return _text(patch.get("plan_shot_id")), first_path, str(patch.get("patch_id") or "")


def merge_duplicate_patches(patches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Merge duplicate targets while rejecting only conflicting paths.

    The first value wins for identical duplicates; non-conflicting values are
    combined.  A conflicting path is rejected as an item and never rewritten
    by inference.
    """

    merged: list[dict[str, Any]] = []
    by_target: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, incoming in enumerate(patches):
        if not isinstance(incoming, dict):
            rejected.append({"index": index, "code": "DIRECTOR_PATCH_SCHEMA_INVALID", "message": "patch must be an object"})
            continue
        target = _text(incoming.get("plan_shot_id"))
        if not target:
            rejected.append({"index": index, "code": "UNKNOWN_PLAN_SHOT_ID", "message": "plan_shot_id is required"})
            continue
        existing = by_target.get(target)
        if existing is None:
            existing = copy.deepcopy(incoming)
            by_target[target] = existing
            merged.append(existing)
            continue
        changes = incoming.get("changes") if isinstance(incoming.get("changes"), dict) else {}
        existing_changes = existing.get("changes") if isinstance(existing.get("changes"), dict) else {}
        conflict = None
        for path, value in changes.items():
            if path in existing_changes and existing_changes[path] != value:
                conflict = (str(path), existing_changes[path], value)
                break
        if conflict:
            rejected.append({
                "index": index,
                "plan_shot_id": target,
                "path": conflict[0],
                "code": "CROSS_PATCH_CONFLICT",
                "message": f"conflicting changes for plan_shot_id {target} at {conflict[0]}",
            })
            continue
        identical = True
        for path, value in changes.items():
            if path not in existing_changes:
                identical = False
            existing_changes[path] = copy.deepcopy(value)
        existing["changes"] = existing_changes
        existing["_source_format"] = "merged_equivalent"
        events.append({
            "plan_shot_id": target,
            "kind": "DUPLICATE_IDENTICAL_PATCH" if identical else "NON_CONFLICTING_DUPLICATE_PATCH",
            "source_index": index,
        })
    merged.sort(key=_sort_key)
    return {"patches": merged, "rejected": rejected, "events": events}


def deterministic_repair_document(
    raw: dict[str, Any],
    *,
    known_plan_shot_ids: Iterable[str] | None = None,
    allowed_patch_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Normalize then apply only Level 1 deterministic repairs.

    ``document`` is the rich, auditable representation.  ``schema_document``
    is the same content with only the V2.1 parser metadata shape, allowing the
    existing strict schema/compiler to remain the authority boundary.
    """

    path_metrics = collect_path_resolution_metrics(
        raw,
        known_plan_shot_ids=known_plan_shot_ids,
        allowed_patch_paths=allowed_patch_paths,
    )
    try:
        normalized = normalize_patch_document(
            raw,
            known_plan_shot_ids=known_plan_shot_ids,
            allowed_patch_paths=allowed_patch_paths,
        )
    except PatchNormalizationError as exc:
        raise DeterministicRepairError(str(exc), code=exc.code, path=exc.path, path_metrics=path_metrics) from exc
    merged = merge_duplicate_patches(normalized.get("patches") or [])
    document = copy.deepcopy(normalized)
    document["patches"] = merged["patches"]
    metadata = document.setdefault("normalization_metadata", {})
    events = list(metadata.get("events") or [])
    events.extend(merged["events"])
    metadata.update({
        "deterministic_repair_version": DETERMINISTIC_REPAIR_VERSION,
        "deterministic_repair_applied": bool(merged["events"]),
        "events": events,
        "rejected": copy.deepcopy(merged["rejected"]),
        "path_resolution": copy.deepcopy(path_metrics),
    })
    metadata["after_fingerprint"] = fingerprint(document)
    schema_document = {
        "schema_version": document.get("schema_version") or "director_creative_patch_v1",
        "patches": copy.deepcopy(document.get("patches") or []),
        "auxiliary_shot_proposals": copy.deepcopy(document.get("auxiliary_shot_proposals") or []),
    }
    return {
        "status": "partial" if merged["rejected"] else ("repaired" if events else "valid"),
        "document": document,
        "schema_document": schema_document,
        "events": events,
        "rejected": copy.deepcopy(merged["rejected"]),
        "normalization_events": sum(1 for event in events if "kind" not in event),
        "deterministic_repair_events": len(merged["events"]),
        "llm_required": False,
        "before_fingerprint": metadata.get("before_fingerprint") or fingerprint(raw),
        "after_fingerprint": metadata["after_fingerprint"],
    }


def repair_patch_document(raw: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return deterministic_repair_document(raw, **kwargs)


def run_deterministic_repair(raw: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return deterministic_repair_document(raw, **kwargs)


deterministic_repair = deterministic_repair_document
merge_patches = merge_duplicate_patches


__all__ = [
    "DETERMINISTIC_REPAIR_VERSION",
    "PATH_ORDER",
    "DeterministicRepairError",
    "merge_duplicate_patches",
    "merge_patches",
    "deterministic_repair_document",
    "repair_patch_document",
    "run_deterministic_repair",
    "deterministic_repair",
]
