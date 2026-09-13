"""Contract-first authority boundary for director creative planning.

The contract is a deterministic, read-only projection of already approved
facts.  It does not call a model and it does not apply a patch.  Its purpose is
to give the Patch Compiler and Validator one explicit source of truth for
immutable fields, editable fields, source beats and auxiliary-shot policy.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


CONTRACT_SCHEMA_VERSION = "director_creative_contract_v1"
DIRECTOR_CREATIVE_CONTRACT_VERSION = CONTRACT_SCHEMA_VERSION

# These are semantic field names, not JSON pointer paths.  The pointer forms
# are derived below and are the only paths that the future Patch Compiler may
# apply.  Identity, story, asset and chronology facts are deliberately listed
# explicitly so adding a creative field cannot silently make a fact editable.
IMMUTABLE_FIELDS = (
    "scene_id",
    "scene_name",
    "plan_shot_id",
    "beat_id",
    "beat_order",
    "event",
    "dialogue",
    "participants",
    "action_beats",
    "entry_state",
    "exit_state",
    "asset_bindings",
    "prop_ownership",
    "continuity_contract",
    "continuity",
    "spatial_source",
    "source_facts",
    "plot_result",
    "chronology",
)

EDITABLE_FIELDS = (
    "camera.shot_size",
    "camera.angle",
    "camera.movement",
    "camera.speed",
    "camera.camera_side",
    "composition.*",
    "why_this_shot",
    "dramatic_function",
    "emotion.*",
    "performance_direction.*",
    "edit.*",
    "information_strategy.*",
    "visual_emphasis",
)

# JSON-pointer patterns are intentionally explicit.  ``*`` means one shot
# index/plan_shot_id component and is resolved by the patch compiler; it does
# not grant access to arbitrary top-level paths.
ALLOWED_PATCH_PATHS = (
    "/shots/*/camera/shot_size",
    "/shots/*/camera/angle",
    "/shots/*/camera/movement",
    "/shots/*/camera/speed",
    "/shots/*/camera/camera_side",
    "/shots/*/composition/*",
    "/shots/*/composition",
    "/shots/*/why_this_shot",
    "/shots/*/dramatic_function",
    "/shots/*/emotion/*",
    "/shots/*/emotion",
    "/shots/*/performance_direction/*",
    "/shots/*/performance_direction/*/*",
    "/shots/*/performance_direction",
    "/shots/*/edit/*",
    "/shots/*/edit",
    "/shots/*/information_strategy/*",
    "/shots/*/information_strategy",
    "/shots/*/visual_emphasis",
)

IMMUTABLE_PATCH_PATHS = tuple(
    "/shots/*/" + field.replace(".", "/")
    for field in IMMUTABLE_FIELDS
    if field not in {"scene_id", "scene_name", "beat_order", "source_facts", "plot_result", "chronology"}
)

AUXILIARY_SHOT_TYPES = ("reaction", "insert", "establishing", "transition", "detail")
AUXILIARY_SHOT_POLICY = {
    "allowed_types": list(AUXILIARY_SHOT_TYPES),
    "max_per_source_beat": 2,
    "requires": [
        "proposal_id",
        "proposal_type",
        "source_beat_id",
        "insert_after_plan_shot_id",
        "purpose",
        "why_needed",
        "participants",
        "camera",
    ],
    "forbidden_mutations": [
        "scene_id",
        "scene_name",
        "beat_order",
        "event",
        "dialogue",
        "plot_result",
        "new_participants",
        "new_asset_facts",
        "prop_ownership",
    ],
    "allow_new_participants": False,
    "allow_new_plot_events": False,
    "allow_new_key_assets": False,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def contract_fingerprint(value: Any) -> str:
    """Return a stable fingerprint without including volatile object identity."""

    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _scene_id(script_scene: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any], plan: dict[str, Any]) -> str:
    return _first_text(
        script_scene.get("scene_id"),
        treatment.get("scene_id"),
        blocking.get("scene_id"),
        plan.get("scene_id"),
        plan.get("scene_name"),
        treatment.get("scene_name"),
        script_scene.get("name"),
    )


def _scene_name(script_scene: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any], plan: dict[str, Any]) -> str:
    return _first_text(
        script_scene.get("name"),
        script_scene.get("scene_name"),
        treatment.get("scene_name"),
        blocking.get("scene_name"),
        plan.get("scene_name"),
    ) or "未命名场景"


def _beat_entries(*sources: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge treatment and ScriptIR beats while preserving first-seen order."""

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        raw_beats = source.get("beat_map")
        if not isinstance(raw_beats, list):
            raw_beats = source.get("beats") if isinstance(source.get("beats"), list) else []
        for index, raw in enumerate(raw_beats, start=1):
            if not isinstance(raw, dict):
                continue
            beat_id = _first_text(raw.get("beat_id"), raw.get("id")) or f"B{len(entries) + 1:02d}"
            if beat_id in seen:
                continue
            seen.add(beat_id)
            entries.append(
                {
                    "beat_id": beat_id,
                    "order": len(entries) + 1,
                    "type": _text(raw.get("type")),
                    "event": _text(raw.get("event") or raw.get("description") or raw.get("content")),
                    "dramatic_function": _text(raw.get("dramatic_function")),
                    "information_change": _text(raw.get("information_change")),
                    "emotion_change": _text(raw.get("emotion_change")),
                }
            )
    return entries


def _participant_ids(*sources: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for source in sources:
        values = source.get("participants")
        if not isinstance(values, list):
            values = source.get("characters") if isinstance(source.get("characters"), list) else []
        for raw in values:
            if isinstance(raw, dict):
                value = _first_text(raw.get("character_id"), raw.get("id"), raw.get("name"), raw.get("character"))
            else:
                value = _text(raw)
            if value and value not in result:
                result.append(value)
    return result


def _asset_projection(*, plan: dict[str, Any], script_scene: dict[str, Any], blocking: dict[str, Any], asset_bindings: Any) -> dict[str, Any]:
    scene_ids: list[str] = []
    character_ids: list[str] = []
    prop_ids: list[str] = []
    for raw in _list(plan.get("shots")):
        if not isinstance(raw, dict):
            continue
        bindings = _dict(raw.get("asset_bindings"))
        for key, target in (("scene_asset_id", scene_ids), ("scene", scene_ids)):
            value = _text(bindings.get(key))
            if value and value not in target:
                target.append(value)
        for key, target in (("character_asset_ids", character_ids), ("characters", character_ids)):
            values = bindings.get(key)
            if isinstance(values, list):
                for value in values:
                    value = _text(value.get("id") if isinstance(value, dict) else value)
                    if value and value not in target:
                        target.append(value)
        for key, target in (("prop_asset_ids", prop_ids), ("props", prop_ids)):
            values = bindings.get(key)
            if isinstance(values, list):
                for value in values:
                    value = _text(value.get("id") if isinstance(value, dict) else value)
                    if value and value not in target:
                        target.append(value)
    for source in (script_scene, blocking, _dict(asset_bindings)):
        scene_value = _first_text(source.get("scene_asset_id"), source.get("scene"))
        if scene_value and scene_value not in scene_ids:
            scene_ids.append(scene_value)
        for raw in _list(source.get("character_asset_ids") or source.get("characters")):
            value = _text(raw.get("id") if isinstance(raw, dict) else raw)
            if value and value not in character_ids:
                character_ids.append(value)
        for raw in _list(source.get("prop_asset_ids") or source.get("props")):
            value = _text(raw.get("id") if isinstance(raw, dict) else raw)
            if value and value not in prop_ids:
                prop_ids.append(value)
    return {"scene": scene_ids, "characters": character_ids, "props": prop_ids}


def _shot_projection(plan: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(_list(plan.get("shots")), start=1):
        if not isinstance(raw, dict):
            continue
        projection = {key: copy.deepcopy(raw.get(key)) for key in IMMUTABLE_FIELDS if key in raw}
        projection["plan_shot_id"] = _first_text(raw.get("plan_shot_id")) or f"S{index:02d}"
        result.append(projection)
    return result


def _normalise_pointer(path: Any) -> str:
    value = _text(path)
    if not value:
        return ""
    relative = not value.startswith("/") and not value.startswith("shots.") and not value.startswith("shots/")
    if value.startswith("/"):
        parts = [part for part in value.split("/") if part]
    else:
        value = value.replace(".", "/")
        parts = [part for part in value.split("/") if part]
    if relative:
        parts = ["shots", "*", *parts]
    return "/" + "/".join(parts)


def _path_matches(pattern: str, path: str) -> bool:
    pattern_parts = [part for part in pattern.split("/") if part]
    path_parts = [part for part in path.split("/") if part]
    if len(pattern_parts) != len(path_parts):
        return False
    return all(expected == "*" or expected == actual for expected, actual in zip(pattern_parts, path_parts))


def is_allowed_patch_path(path: Any, contract: dict[str, Any] | None = None) -> bool:
    """Check a JSON pointer or dotted creative path against the contract."""

    pointer = _normalise_pointer(path)
    if not pointer:
        return False
    patterns = _list((contract or {}).get("allowed_patch_paths")) or list(ALLOWED_PATCH_PATHS)
    for pattern in patterns:
        if _path_matches(_normalise_pointer(pattern), pointer):
            return True
    return False


def _contract_payload(
    *,
    facts: dict[str, Any],
    scene: dict[str, Any],
    beats: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    assets: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "immutable_fields": list(IMMUTABLE_FIELDS),
        "editable_fields": list(EDITABLE_FIELDS),
        "allowed_patch_paths": list(ALLOWED_PATCH_PATHS),
        "auxiliary_shot_policy": copy.deepcopy(AUXILIARY_SHOT_POLICY),
        "source_beat_map": {item["beat_id"]: item for item in beats},
        "scene": scene,
        "immutable_projection": {
            "facts": facts,
            "shots": shots,
            "assets": assets,
            "chronology": [item["beat_id"] for item in beats],
        },
    }


def build_director_creative_contract(
    *,
    fact_snapshot: dict[str, Any] | None = None,
    script_scene: dict[str, Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    structural_shot_plan: dict[str, Any] | None = None,
    scene_canonical: dict[str, Any] | None = None,
    asset_bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic immutable contract from approved evidence.

    The function intentionally accepts incomplete optional evidence so callers
    can construct a contract for validation and receive a stable fingerprint;
    it never invents missing facts or calls an external service.
    """

    snapshot = _dict(fact_snapshot)
    script = _dict(script_scene)
    treatment_obj = _dict(treatment)
    blocking_obj = _dict(blocking)
    plan = _dict(structural_shot_plan)
    canonical = _dict(scene_canonical)
    scene_id = _scene_id(script, treatment_obj, blocking_obj, plan)
    scene_name = _scene_name(script, treatment_obj, blocking_obj, plan)
    beats = _beat_entries(treatment_obj, script)
    participants = _participant_ids(script, treatment_obj, blocking_obj)
    source_records = [copy.deepcopy(item) for item in _list(snapshot.get("records")) if isinstance(item, dict)]
    source_facts = [copy.deepcopy(item) for item in _list(blocking_obj.get("source_spatial_facts")) if isinstance(item, dict)]
    facts = {
        "fact_snapshot_records": source_records,
        "source_spatial_facts": source_facts,
        "scene_canonical": copy.deepcopy(canonical),
        "participants": participants,
        "scene_state_in": copy.deepcopy(script.get("state_in") if isinstance(script.get("state_in"), dict) else {}),
        "scene_state_out": copy.deepcopy(script.get("state_out") if isinstance(script.get("state_out"), dict) else {}),
    }
    scene = {
        "scene_id": scene_id,
        "scene_name": scene_name,
        "episode": script.get("episode") or treatment_obj.get("episode") or blocking_obj.get("episode"),
        "time_of_day": _first_text(script.get("time_of_day"), canonical.get("time_of_day")),
        "weather": _first_text(script.get("weather"), canonical.get("weather")),
    }
    shots = _shot_projection(plan)
    assets = _asset_projection(plan=plan, script_scene=script, blocking=blocking_obj, asset_bindings=asset_bindings)
    payload = _contract_payload(facts=facts, scene=scene, beats=beats, shots=shots, assets=assets)
    fingerprint = contract_fingerprint(payload)
    return {
        **payload,
        "contract_fingerprint": fingerprint,
        "source_fingerprint": _first_text(snapshot.get("payload_hash"), snapshot.get("source_fingerprint")),
        "structural_plan_fingerprint": _first_text(plan.get("evidence_fingerprint")),
        "status": "ready" if scene_id and scene_name and shots else "needs_information",
    }


# Friendly aliases for callers and future hidden/regression tests.
build_immutable_director_contract = build_director_creative_contract
build_director_contract = build_director_creative_contract
build_contract = build_director_creative_contract


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "DIRECTOR_CREATIVE_CONTRACT_VERSION",
    "IMMUTABLE_FIELDS",
    "IMMUTABLE_PATCH_PATHS",
    "EDITABLE_FIELDS",
    "ALLOWED_PATCH_PATHS",
    "AUXILIARY_SHOT_TYPES",
    "AUXILIARY_SHOT_POLICY",
    "contract_fingerprint",
    "is_allowed_patch_path",
    "build_director_creative_contract",
    "build_immutable_director_contract",
    "build_director_contract",
    "build_contract",
]
