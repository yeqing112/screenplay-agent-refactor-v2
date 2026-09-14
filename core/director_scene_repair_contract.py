"""Contract boundary for bounded, multi-shot Scene Repair."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable

from core.director_creative_contract import ALLOWED_PATCH_PATHS, IMMUTABLE_FIELDS
from core.director_repair_value_ceiling import immutable_projection
from core.director_scene_repair_scope import (
    SCENE_ALLOWED_DIMENSIONS, SCENE_IMMUTABLE_FIELDS, SCENE_MUTABLE_FIELDS,
    SCENE_REPAIR_SCOPE_SCHEMA_VERSION,
)

SCENE_REPAIR_CONTRACT_SCHEMA_VERSION = "director_scene_repair_contract_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _shot_id(shot: dict[str, Any], index: int) -> str:
    return _text(shot.get("plan_shot_id") or shot.get("shot_id")) or f"S{index + 1:02d}"


def build_scene_repair_contract(*, candidate: dict[str, Any], base_contract: dict[str, Any] | None = None, scene_id: str = "", allowed_dimensions: Iterable[str] | None = None, affected_shot_ids: Iterable[str] | None = None, allowed_character_ids: Iterable[str] | None = None, source_fingerprint: str = "") -> dict[str, Any]:
    shots = [item for item in _list(candidate.get("shots")) if isinstance(item, dict)]
    shot_ids = [_shot_id(shot, index) for index, shot in enumerate(shots)]
    requested_ids = {_text(value) for value in (affected_shot_ids or shot_ids) if _text(value)}
    allowed_ids = [sid for sid in shot_ids if sid in requested_ids]
    characters = set(_text(value) for value in (allowed_character_ids or ()) if _text(value))
    if not characters:
        for shot in shots:
            characters.update(_text(value) for value in _list(shot.get("participants")) if _text(value))
    paths = list(_dict(base_contract).get("allowed_patch_paths") or ALLOWED_PATCH_PATHS)
    if "/shots/*/purpose" not in paths:
        paths.append("/shots/*/purpose")
    immutable = list(dict.fromkeys([*IMMUTABLE_FIELDS, *SCENE_IMMUTABLE_FIELDS]))
    fact_fp = _fingerprint(immutable_projection(candidate))
    topology_fp = _fingerprint({"shot_ids": shot_ids, "count": len(shot_ids), "order": shot_ids})
    return {
        "schema_version": SCENE_REPAIR_CONTRACT_SCHEMA_VERSION,
        "scope_schema_version": SCENE_REPAIR_SCOPE_SCHEMA_VERSION,
        "scene_id": _text(scene_id) or _text(candidate.get("scene_id")),
        "immutable_fields": immutable,
        "mutable_creative_fields": list(SCENE_MUTABLE_FIELDS),
        "allowed_patch_paths": paths,
        "allowed_shot_ids": allowed_ids,
        "allowed_character_ids": sorted(characters),
        "id_rules": {
            "plan_shot_id_required": True,
            "plan_shot_id_set_frozen": True,
            "unknown_shot_ids_rejected": True,
            "duplicate_shot_ids_rejected": True,
            "character_id_required_for_performance": True,
            "character_ids_must_be_in_scene": True,
        },
        "allowed_dimensions": sorted({_text(value).upper() for value in (allowed_dimensions or SCENE_ALLOWED_DIMENSIONS) if _text(value).upper() in SCENE_ALLOWED_DIMENSIONS}),
        "topology_fingerprint": topology_fp,
        "fact_fingerprint": fact_fp,
        "scene_source_fingerprint": _text(source_fingerprint),
        "topology_rules": {"shot_count_immutable": True, "shot_order_immutable": True, "plan_shot_id_set_immutable": True, "auxiliary_shots_allowed": False},
        "fact_rules": {"dialogue_immutable": True, "event_immutable": True, "participants_immutable": True, "assets_immutable": True, "location_immutable": True},
        "continuity_rules": {"source_truth_immutable": True, "entry_exit_state_immutable": True},
        # `max_shots` is the immutable scene-level ceiling.  The repair
        # opportunity cap (70% of shots) belongs to diagnosis, not to the
        # scene topology contract; conflating the two made a 10-shot scene
        # report a seven-shot scene budget.
        "shot_budget": {
            "max_shots": min(len(shots), 8) if shots else 0,
            "max_affected_shots": min(len(shots), 8, max(0, int((len(shots) * 0.7) + 0.9999))) if shots else 0,
        },
        "dimension_budget": {"max_dimensions": 5},
    }


__all__ = ["SCENE_REPAIR_CONTRACT_SCHEMA_VERSION", "build_scene_repair_contract"]
