"""Deterministic Storyboard visual-semantic projection and diffing.

Phase D keeps Storyboard as a projection of the canonical ShotPlan.  This
module intentionally deals only in stable references and enum-like values;
it never creates prompt prose, camera decisions, asset variants, or media.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION = "storyboard_visual_semantic_handoff_v1"
VISUAL_SEMANTIC_PROJECTION_VERSION = "storyboard_materialization_semantic_projection_v1"
PROJECTION_ORIGIN = "STORYBOARD_MATERIALIZATION_PROJECTION"

SHOT_PLAN_PROJECTION = "SHOT_PLAN_PROJECTION"
PRODUCTION_CONTINUITY_STATE = "PRODUCTION_CONTINUITY_STATE"
ASSET_IDENTITY_BINDING = "ASSET_IDENTITY_BINDING"
STRUCTURAL_MATERIALIZATION_METADATA = "STRUCTURAL_MATERIALIZATION_METADATA"
DOWNSTREAM_HANDOFF_METADATA = "DOWNSTREAM_HANDOFF_METADATA"
MEDIA_STATE = "MEDIA_STATE"
UNKNOWN_INVALID = "UNKNOWN_INVALID"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def semantic_fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _asset_identity_bindings(raw: Any, *, scene_id: str, subjects: list[Any], props: list[Any]) -> dict[str, Any]:
    """Normalize only identity references; never select a visual variant."""
    source = _dict(raw)
    canonical = _dict(source.get("canonical_asset_identity"))
    scene = canonical.get("scene") or source.get("scene") or source.get("scene_asset_id") or scene_id
    characters = canonical.get("characters") if isinstance(canonical.get("characters"), list) else source.get("characters")
    if not isinstance(characters, list):
        characters = source.get("character_asset_ids") if isinstance(source.get("character_asset_ids"), list) else list(subjects)
    prop_values = canonical.get("props") if isinstance(canonical.get("props"), list) else source.get("props")
    if not isinstance(prop_values, list):
        prop_values = source.get("prop_asset_ids") if isinstance(source.get("prop_asset_ids"), list) else list(props)
    return {
        "canonical_asset_identity": {
            "scene": scene,
            "characters": list(characters),
            "props": list(prop_values),
        },
        "identity_source": "SHOT_PLAN_ASSET_BINDINGS",
    }


def _semantic_payload(*, scene_id: str, plan_shot_id: str, shot_plan_id: Any, handoff_shot: dict[str, Any], source_authority_fingerprint: str = "", blocking_authority_fingerprint: str = "", materialization_set_id: Any = None, storyboard_shot_id: Any = None, projection_fingerprint: str = "") -> dict[str, Any]:
    refs = _dict(handoff_shot.get("shot_design_refs"))
    if not refs and isinstance(handoff_shot.get("meta_info"), dict):
        refs = _dict(handoff_shot["meta_info"].get("shot_design_refs"))
    camera_state = _dict(handoff_shot.get("camera_state"))
    camera = _dict(handoff_shot.get("camera"))
    spatial = _dict(handoff_shot.get("spatial_binding"))
    axis = _dict(handoff_shot.get("axis_contract"))
    subjects = _list(handoff_shot.get("subjects"))
    prop_refs = _list(spatial.get("prop_refs"))
    semantic = {
        "schema_version": VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION,
        "projection_version": VISUAL_SEMANTIC_PROJECTION_VERSION,
        "scene_id": scene_id,
        "plan_shot_id": plan_shot_id,
        "shot_design_ref": {"shot_plan_id": shot_plan_id, "plan_shot_id": plan_shot_id},
        "beat_refs": _list(handoff_shot.get("beat_refs")) or [_text(handoff_shot.get("beat_id"))],
        "director_decision_refs": _list(refs.get("director_decision_refs")),
        "requirement_refs": _list(refs.get("requirement_refs")),
        "information_refs": _list(refs.get("information_refs")),
        "reaction_contract_refs": _list(refs.get("reaction_contract_refs")),
        "coverage_roles": _list(refs.get("coverage_roles")),
        "subjects": subjects,
        "props": prop_refs,
        "asset_identity_bindings": _asset_identity_bindings(handoff_shot.get("asset_bindings"), scene_id=scene_id, subjects=subjects, props=prop_refs),
        "camera": {
            "framing_class": camera_state.get("framing_class") or camera.get("shot_size"),
            "orientation": camera_state.get("orientation") or camera.get("angle"),
            "support": camera_state.get("support") or camera.get("support"),
            "movement": camera_state.get("movement") or camera.get("movement"),
            "movement_trigger": camera_state.get("movement_trigger"),
            "movement_target": camera_state.get("movement_target"),
            "movement_end_condition": camera_state.get("movement_end_condition"),
        },
        "temporal_intent": _dict(handoff_shot.get("temporal_intent")),
        "information_visibility": handoff_shot.get("information_visibility"),
        "continuity": {
            "axis_ref": axis.get("axis_ref"),
            "axis_refs": _list(axis.get("axis_refs")),
            "axis_policy": axis.get("axis_policy"),
            "axis_applicability": axis.get("axis_applicability"),
            "screen_side_assignments": _dict(axis.get("screen_side_assignments")),
            "look_direction": _dict(axis.get("look_direction")),
            "continuous_take": handoff_shot.get("continuous_take") is True,
            "cut_events": _list(handoff_shot.get("cut_events")),
        },
        "spatial": {
            "blocking_state_refs": _list(spatial.get("blocking_state_refs")) or _list(_dict(handoff_shot.get("continuity_contract")).get("blocking_state_refs")),
            "entry_state_ref": _text((_dict(handoff_shot.get("entry_state"))).get("state_ref")) or (_list(spatial.get("blocking_state_refs")) or [""])[0],
            "exit_state_ref": _text((_dict(handoff_shot.get("exit_state"))).get("state_ref")) or (_list(spatial.get("blocking_state_refs")) or [""])[-1],
            "subject_zones": _dict(spatial.get("subject_zones")),
            "prop_refs": prop_refs,
        },
        "projection_origin": PROJECTION_ORIGIN,
    }
    # These fields identify provenance and downstream rows; they are still
    # structured metadata and are deliberately excluded from creative truth.
    provenance = {
        "source_shot_plan_authority_fingerprint": source_authority_fingerprint,
        "blocking_authority_fingerprint": blocking_authority_fingerprint,
        "handoff_fingerprint": _text(handoff_shot.get("handoff_fingerprint")),
        "storyboard_handoff_shot_fingerprint": _text(handoff_shot.get("storyboard_handoff_shot_fingerprint")),
    }
    if materialization_set_id is not None:
        provenance["materialization_set_id"] = materialization_set_id
    if storyboard_shot_id is not None:
        provenance["storyboard_shot_id"] = storyboard_shot_id
    if projection_fingerprint:
        provenance["projection_fingerprint"] = projection_fingerprint
    semantic["projection_provenance"] = provenance
    return semantic


def build_visual_semantic_handoff(*, scene_id: str, plan_shot_id: str, handoff_shot: dict[str, Any], shot_plan_id: Any = None, source_authority_fingerprint: str = "", blocking_authority_fingerprint: str = "", materialization_set_id: Any = None, storyboard_shot_id: Any = None, projection_fingerprint: str = "") -> dict[str, Any]:
    return _semantic_payload(scene_id=scene_id, plan_shot_id=plan_shot_id or plan_shot_id, shot_plan_id=shot_plan_id, handoff_shot=handoff_shot, source_authority_fingerprint=source_authority_fingerprint, blocking_authority_fingerprint=blocking_authority_fingerprint, materialization_set_id=materialization_set_id, storyboard_shot_id=storyboard_shot_id, projection_fingerprint=projection_fingerprint)


def build_visual_semantic_handoff_set(*, scene_id: str, handoff: dict[str, Any], shot_plan_id: Any = None, source_authority_fingerprint: str = "", blocking_authority_fingerprint: str = "", materialization_set_id: Any = None) -> list[dict[str, Any]]:
    return [build_visual_semantic_handoff(scene_id=scene_id, plan_shot_id=_text(item.get("plan_shot_id")), handoff_shot=item, shot_plan_id=shot_plan_id, source_authority_fingerprint=source_authority_fingerprint, blocking_authority_fingerprint=blocking_authority_fingerprint, materialization_set_id=materialization_set_id) for item in _list(handoff.get("shots")) if isinstance(item, dict)]


def semantic_projection_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical semantic fields, excluding mutable row metadata."""
    payload = dict(value) if isinstance(value, dict) else {}
    payload.pop("projection_provenance", None)
    return payload


def semantic_projection_fingerprint(value: dict[str, Any]) -> str:
    return semantic_fingerprint(semantic_projection_payload(value))


def _paths(expected: Any, actual: Any, prefix: str, missing: list[str], extra: list[str], changed: list[str]) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            changed.append(prefix or "$")
            return
        for key, value in expected.items():
            path = f"{prefix}.{key}" if prefix else key
            if key not in actual:
                missing.append(path)
            else:
                _paths(value, actual[key], path, missing, extra, changed)
        for key in actual:
            if key not in expected:
                extra.append(f"{prefix}.{key}" if prefix else key)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or expected != actual:
            changed.append(prefix or "$")
        return
    if expected != actual:
        changed.append(prefix or "$")


def semantic_diff(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_payload = semantic_projection_payload(expected)
    actual_payload = semantic_projection_payload(actual)
    missing: list[str] = []
    extra: list[str] = []
    changed: list[str] = []
    _paths(expected_payload, actual_payload, "", missing, extra, changed)
    camera_mismatch = [path for path in changed if path == "camera" or path.startswith("camera.")]
    continuity_mismatch = [path for path in changed + missing + extra if path == "continuity" or path.startswith("continuity.") or path.startswith("spatial.")]
    asset_mismatch = [path for path in changed + missing + extra if path.startswith("asset_identity_bindings") or path == "subjects" or path == "props"]
    return {
        "missing_semantic": sorted(set(missing)),
        "extra_semantic": sorted(set(extra)),
        "changed_semantic": sorted(set(changed)),
        "camera_mismatch": sorted(set(camera_mismatch)),
        "continuity_mismatch": sorted(set(continuity_mismatch)),
        "asset_binding_mismatch": sorted(set(asset_mismatch)),
        "empty": not (missing or extra or changed),
    }


def _coerce_semantic(item: dict[str, Any]) -> dict[str, Any]:
    if _text(item.get("schema_version")) == VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION:
        return item
    nested = item.get("visual_semantic_handoff") if isinstance(item.get("visual_semantic_handoff"), dict) else None
    if nested and _text(nested.get("schema_version")) == VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION:
        return nested
    # Accept a raw canonical ShotPlan shot for audit callers.  This is a
    # structural normalization only; no values are inferred.
    spatial = _dict(item.get("spatial_binding"))
    axis = _dict(item.get("axis_contract"))
    camera_state = _dict(item.get("camera_state"))
    pseudo = {
        "plan_shot_id": item.get("plan_shot_id"),
        "beat_id": item.get("beat_id"),
        "beat_refs": _list(item.get("beat_refs")),
        "subjects": _list(item.get("subjects")),
        "camera_state": camera_state,
        "camera": item.get("camera", {}),
        "axis_contract": axis,
        "spatial_binding": spatial,
        "temporal_intent": _dict(item.get("temporal_intent")),
        "information_visibility": item.get("information_visibility"),
        "continuous_take": item.get("continuous_take"),
        "cut_events": _list(item.get("cut_events")),
        "entry_state": item.get("entry_state"),
        "exit_state": item.get("exit_state"),
        "asset_bindings": item.get("asset_bindings"),
        "shot_design_refs": {key: _list(item.get(key)) for key in ("director_decision_refs", "requirement_refs", "information_refs", "reaction_contract_refs", "coverage_roles")},
    }
    return build_visual_semantic_handoff(scene_id=_text(item.get("scene_id")), plan_shot_id=_text(item.get("plan_shot_id")), handoff_shot=pseudo)


def compare_shotplan_storyboard_semantics(expected: Iterable[dict[str, Any]], actual: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compare canonical semantic projections by stable ``plan_shot_id``."""
    if isinstance(expected, dict):
        expected = expected.get("shots") if isinstance(expected.get("shots"), list) else [expected]
    if isinstance(actual, dict):
        actual = actual.get("shots") if isinstance(actual.get("shots"), list) else [actual]
    expected_by_id = {_text(item.get("plan_shot_id")): _coerce_semantic(item) for item in expected if isinstance(item, dict) and _text(item.get("plan_shot_id"))}
    actual_by_id = {_text(item.get("plan_shot_id")): _coerce_semantic(item) for item in actual if isinstance(item, dict) and _text(item.get("plan_shot_id"))}
    missing_shots = sorted(set(expected_by_id) - set(actual_by_id))
    extra_shots = sorted(set(actual_by_id) - set(expected_by_id))
    per_shot: dict[str, Any] = {}
    for shot_id in sorted(set(expected_by_id) & set(actual_by_id)):
        per_shot[shot_id] = semantic_diff(expected_by_id[shot_id], actual_by_id[shot_id])
    aggregate = {key: sorted({f"{shot_id}:{value}" for shot_id, diff in per_shot.items() for value in diff[key]}) for key in ("missing_semantic", "extra_semantic", "camera_mismatch", "continuity_mismatch", "asset_binding_mismatch")}
    aggregate["missing_shots"] = missing_shots
    aggregate["extra_shots"] = extra_shots
    aggregate["per_shot"] = per_shot
    aggregate["empty"] = not missing_shots and not extra_shots and all(diff.get("empty") for diff in per_shot.values())
    return aggregate


def validate_asset_identity_bindings(*, semantic: dict[str, Any], required_subjects: list[Any], required_props: list[Any], scene_id: str) -> list[dict[str, Any]]:
    bindings = _dict(semantic.get("asset_identity_bindings"))
    canonical = _dict(bindings.get("canonical_asset_identity"))
    errors: list[dict[str, Any]] = []
    if not _text(canonical.get("scene")):
        errors.append({"code": "ASSET_BINDING_REQUIRED", "field": "scene"})
    if _text(canonical.get("scene")) != scene_id:
        errors.append({"code": "ASSET_BINDING_MISMATCH", "field": "scene"})
    chars = {_text(item) for item in _list(canonical.get("characters")) if _text(item)}
    props = {_text(item) for item in _list(canonical.get("props")) if _text(item)}
    for item in required_subjects:
        if _text(item) and _text(item) not in chars:
            errors.append({"code": "ASSET_BINDING_REQUIRED", "field": "character", "identity": item})
    for item in required_props:
        if _text(item) and _text(item) not in props:
            errors.append({"code": "ASSET_BINDING_REQUIRED", "field": "prop", "identity": item})
    return errors


__all__ = [
    "VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION", "VISUAL_SEMANTIC_PROJECTION_VERSION", "PROJECTION_ORIGIN",
    "SHOT_PLAN_PROJECTION", "PRODUCTION_CONTINUITY_STATE", "ASSET_IDENTITY_BINDING", "STRUCTURAL_MATERIALIZATION_METADATA", "DOWNSTREAM_HANDOFF_METADATA", "MEDIA_STATE", "UNKNOWN_INVALID",
    "semantic_fingerprint", "build_visual_semantic_handoff", "build_visual_semantic_handoff_set", "semantic_projection_payload", "semantic_projection_fingerprint", "semantic_diff", "compare_shotplan_storyboard_semantics", "validate_asset_identity_bindings",
]
