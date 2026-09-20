"""Pure deterministic projection from an authoritative ShotPlan.

Production materialization is strict and provider-free.  A permissive mode is
retained only for creative/legacy callers.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

MATERIALIZER_VERSION = "storyboard_materializer_v2"
MATERIALIZER_POLICY_VERSION = "storyboard_materializer_policy_v1"
MATERIALIZATION_SCHEMA_VERSION = "storyboard_materialization_authority_envelope_v1"
SHOT_PLAN_PROJECTION = "SHOT_PLAN_PROJECTION"
STRUCTURAL_MATERIALIZATION_METADATA = "STRUCTURAL_MATERIALIZATION_METADATA"
COMPILER_OUTPUT = "COMPILER_OUTPUT"
MEDIA_STATE = "MEDIA_STATE"
UNKNOWN_INVALID = "UNKNOWN_INVALID"

from core.storyboard_handoff import (
    HANDOFF_SCHEMA_VERSION,
    HANDOFF_PROJECTION_VERSION,
    project_shot_design_to_storyboard_handoff,
    validate_storyboard_handoff,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strict_contract_errors(plan: dict[str, Any], shots: list[Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not _text(plan.get("scene_id")):
        errors.append({"code": "SCENE_ID_REQUIRED", "message": "Production materialization requires scene_id."})
    if not _text(plan.get("scene_name")):
        errors.append({"code": "SCENE_NAME_REQUIRED", "message": "Production materialization requires scene_name."})
    if not shots:
        errors.append({"code": "SHOT_PLAN_EMPTY", "message": "Production ShotPlan must contain at least one shot."})
    seen: set[str] = set()
    for index, item in enumerate(shots, start=1):
        prefix = f"shot[{index}]"
        if not isinstance(item, dict):
            errors.append({"code": "SHOT_OBJECT_INVALID", "message": f"{prefix} must be an object."})
            continue
        plan_shot_id = _text(item.get("plan_shot_id"))
        if not plan_shot_id:
            errors.append({"code": "PLAN_SHOT_ID_REQUIRED", "message": f"{prefix} requires plan_shot_id."})
        elif plan_shot_id in seen:
            errors.append({"code": "PLAN_SHOT_ID_DUPLICATE", "message": f"Duplicate plan_shot_id: {plan_shot_id}."})
        seen.add(plan_shot_id)
        if not _text(item.get("beat_id")):
            errors.append({"code": "SHOT_PLAN_BEAT_ID_REQUIRED", "message": f"{plan_shot_id or prefix} requires beat_id for PromptIR handoff authority."})
        camera = item.get("camera")
        if not isinstance(camera, dict):
            errors.append({"code": "SHOT_PLAN_CAMERA_REQUIRED", "message": f"{plan_shot_id or prefix} requires an authoritative camera object."})
        else:
            for key in ("shot_size", "angle", "movement", "speed"):
                if not _text(camera.get(key)):
                    errors.append({"code": "SHOT_PLAN_CAMERA_REQUIRED", "message": f"{plan_shot_id or prefix} camera.{key} is required; no creative fallback is allowed."})
        duration = item.get("duration_hint_seconds", item.get("duration_seconds"))
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            errors.append({"code": "SHOT_PLAN_DURATION_REQUIRED", "message": f"{plan_shot_id or prefix} requires a positive duration_hint_seconds."})
        if "action_beats" not in item or not isinstance(item.get("action_beats"), list):
            errors.append({"code": "SHOT_PLAN_ACTION_CONTRACT_INVALID", "message": f"{plan_shot_id or prefix} requires action_beats as an array."})
        for field in ("entry_state", "exit_state", "asset_bindings", "continuity_contract"):
            if field not in item:
                errors.append({"code": f"SHOT_PLAN_{field.upper()}_REQUIRED", "message": f"{plan_shot_id or prefix} requires {field}; Materializer cannot invent it."})
        if "purpose" not in item:
            errors.append({"code": "SHOT_PLAN_PURPOSE_REQUIRED", "message": f"{plan_shot_id or prefix} requires shot purpose; no creative default is allowed."})
    return errors


def _projection_fields(item: dict[str, Any], *, scene_id: str, scene_name: str, ordinal: int, production: bool) -> dict[str, Any]:
    plan_shot_id = _text(item.get("plan_shot_id"))
    camera = item.get("camera") if isinstance(item.get("camera"), dict) else {}
    duration = item.get("duration_hint_seconds", item.get("duration_seconds"))
    action_beats = item.get("action_beats") if isinstance(item.get("action_beats"), list) else []
    asset_bindings = item.get("asset_bindings") if isinstance(item.get("asset_bindings"), dict) else {}
    entry_state = item.get("entry_state")
    exit_state = item.get("exit_state")
    continuity_contract = item.get("continuity_contract") if isinstance(item.get("continuity_contract"), dict) else {}
    projection = {
        "scene_id": scene_id,
        "scene_name": scene_name,
        "plan_shot_id": plan_shot_id,
        "beat_id": _text(item.get("beat_id")),
        "shot_id": ordinal,
        "dialogue": str(item.get("dialogue") or ""),
        "duration": duration if production else max(1, int(float(duration or 3))),
        "camera_angle": _text(camera.get("angle")),
        "camera_movement": _text(camera.get("movement")),
        # Camera speed is intentionally optional.  Phase C has no canonical
        # speed intent; an empty value is preserved as unspecified metadata.
        "camera_speed": _text(camera.get("speed")),
        "shot_purpose": _text(item.get("purpose")),
        "transition": _text(item.get("transition")),
        "lighting": str(item.get("lighting") or ""),
        "start_state": entry_state if isinstance(entry_state, (dict, list)) else str(entry_state or ""),
        "action_process": str(item.get("event") or ""),
        "action_beats": action_beats,
        "end_state": exit_state if isinstance(exit_state, (dict, list)) else str(exit_state or ""),
        "asset_bindings": asset_bindings,
        "continuity_contract": continuity_contract,
        "meta_info": {
            "authority_classes": {
                "shot_plan_projection": ["scene_id", "scene_name", "plan_shot_id", "beat_id", "dialogue", "duration", "camera", "shot_purpose", "transition", "lighting", "start_state", "action_process", "action_beats", "end_state", "asset_bindings", "continuity_contract"],
                "structural_materialization_metadata": ["shot_id", "projection_fingerprint"],
                "compiler_output": [],
                "media_state": [],
            },
            "camera": camera,
            "shot_plan_ref": {"plan_shot_id": plan_shot_id},
        },
    }
    if isinstance(item.get("meta_info"), dict):
        projection["meta_info"].update(item["meta_info"])
    projection["projection_fingerprint"] = _fingerprint({key: projection[key] for key in (
        "scene_id", "scene_name", "plan_shot_id", "beat_id", "dialogue", "duration", "camera_angle", "camera_movement", "camera_speed", "shot_purpose", "transition", "lighting", "start_state", "action_process", "action_beats", "end_state", "asset_bindings", "continuity_contract"
    )})
    projection["meta_info"]["materializer"] = {"version": MATERIALIZER_VERSION, "policy_version": MATERIALIZER_POLICY_VERSION, "projection_fingerprint": projection["projection_fingerprint"]}
    return projection


def materialize_storyboard_from_handoff(handoff: dict[str, Any], *, production: bool = True) -> list[dict[str, Any]]:
    """Materialize a validated ``storyboard_handoff_v1`` object."""
    errors = validate_storyboard_handoff(handoff)
    if errors:
        first = errors[0]
        code = str(first.get("code") or "STORYBOARD_HANDOFF_INVALID")
        raise ValueError(f"{code}: Storyboard handoff failed strict validation.")
    scene_id = _text(handoff.get("scene_id"))
    scene_name = _text(handoff.get("scene_name"))
    projections = []
    for ordinal, item in enumerate(handoff["shots"], start=1):
        projection = _projection_fields(item, scene_id=scene_id, scene_name=scene_name, ordinal=ordinal, production=production)
        projection["meta_info"]["handoff"] = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "projection_version": HANDOFF_PROJECTION_VERSION,
            "handoff_fingerprint": handoff.get("handoff_fingerprint"),
            "storyboard_handoff_shot_fingerprint": item.get("storyboard_handoff_shot_fingerprint"),
        }
        projections.append(projection)
    return projections


def materialize_storyboard_from_shot_plan(approved_shot_plan: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, asset_snapshot: dict[str, Any] | None = None, *, production: bool = False) -> list[dict[str, Any]]:
    """Project ShotPlan intent into StoryboardShot-shaped dictionaries."""
    plan = approved_shot_plan if isinstance(approved_shot_plan, dict) else {}
    if production and plan.get("schema_version") == HANDOFF_SCHEMA_VERSION:
        return materialize_storyboard_from_handoff(plan, production=True)
    # Current Phase C Production input is projected exactly once at this
    # boundary.  Legacy callers without semantic readiness retain the old
    # permissive/strict compatibility path below.
    if production and plan.get("phase_c_semantic_ready") is True and isinstance(plan.get("shots"), list) and any(isinstance(item, dict) and isinstance(item.get("camera_state"), dict) for item in plan["shots"]):
        handoff = project_shot_design_to_storyboard_handoff(plan, blocking=blocking, require_phase_c=True)
        return materialize_storyboard_from_handoff(handoff, production=True)
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    if any(not isinstance(item, dict) for item in shots):
        raise ValueError("Approved ShotPlan contains a non-object shot; materialization is fail-closed.")
    if production:
        errors = _strict_contract_errors(plan, shots)
        if errors:
            error = errors[0]
            raise ValueError(f"{error['code']}: {error['message']}")
    plan_shot_ids = [_text(item.get("plan_shot_id")) for item in shots]
    if any(not value for value in plan_shot_ids) or len(set(plan_shot_ids)) != len(plan_shot_ids):
        raise ValueError("Approved ShotPlan must contain unique plan_shot_id values.")
    scene_id = _text(plan.get("scene_id"))
    scene_name = _text(plan.get("scene_name")) or ("未命名场景" if not production else "")
    return [_projection_fields(item, scene_id=scene_id, scene_name=scene_name, ordinal=index, production=production) for index, item in enumerate(shots, start=1)]


def projection_payload(shot: dict[str, Any]) -> dict[str, Any]:
    return {key: shot.get(key) for key in ("scene_id", "scene_name", "plan_shot_id", "beat_id", "dialogue", "duration", "camera_angle", "camera_movement", "camera_speed", "shot_purpose", "transition", "lighting", "start_state", "action_process", "action_beats", "end_state", "asset_bindings", "continuity_contract")}


def materialization_set_fingerprint(*, authority_envelope: dict[str, Any], projections: list[dict[str, Any]]) -> str:
    return _fingerprint({"schema_version": MATERIALIZATION_SCHEMA_VERSION, "materializer_version": MATERIALIZER_VERSION, "materializer_policy_version": MATERIALIZER_POLICY_VERSION, "authority": authority_envelope, "ordered_projections": [projection_payload(item) for item in projections]})


def build_materialization_authority_envelope(*, script_ir: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any], shot_plan: dict[str, Any], materialization_set: dict[str, Any], stale_status: str = "FRESH", stale_reasons: list[str] | None = None) -> dict[str, Any]:
    envelope = {"schema_version": MATERIALIZATION_SCHEMA_VERSION, "authority_policy_version": MATERIALIZER_POLICY_VERSION, "script_ir": script_ir, "director_treatment": treatment, "scene_blocking": blocking, "shot_plan": shot_plan, "materialization": materialization_set, "stale_status": stale_status, "stale_reasons": sorted(set(stale_reasons or []))}
    envelope["authority_fingerprint"] = _fingerprint(envelope)
    return envelope


def validate_materialization_set(*, expected_plan_shot_ids: list[str], projections: list[dict[str, Any]], set_row: Any | None = None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    actual = [_text(item.get("plan_shot_id")) for item in projections]
    if actual != expected_plan_shot_ids:
        errors.append({"code": "STORYBOARD_CARDINALITY_MISMATCH", "expected": expected_plan_shot_ids, "actual": actual})
    if len(actual) != len(set(actual)):
        errors.append({"code": "STORYBOARD_PLAN_SHOT_ID_DUPLICATE"})
    if set_row is not None and (int(getattr(set_row, "expected_shot_count", -1)) != len(expected_plan_shot_ids) or int(getattr(set_row, "materialized_shot_count", -1)) != len(projections)):
        errors.append({"code": "STORYBOARD_MATERIALIZATION_SET_INCOMPLETE"})
    return errors


def projection_fingerprint(shot: dict[str, Any]) -> str:
    """Fingerprint a canonical projection payload for tamper checks."""
    return _fingerprint(projection_payload(shot))


def _parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _row_projection_payload(row: Any, meta: dict[str, Any]) -> dict[str, Any]:
    stored = meta.get("projection_payload") if isinstance(meta.get("projection_payload"), dict) else None
    if stored:
        return stored
    handoff = meta.get("prompt_compiler_handoff") if isinstance(meta.get("prompt_compiler_handoff"), dict) else {}
    return {
        "scene_id": getattr(row, "scene_id", ""),
        "scene_name": getattr(row, "scene_name", ""),
        "plan_shot_id": getattr(row, "plan_shot_id", "") or handoff.get("plan_shot_id", ""),
        "beat_id": handoff.get("beat_id", ""),
        "dialogue": getattr(row, "dialogue", "") or "",
        "duration": getattr(row, "duration", None),
        "camera_angle": getattr(row, "camera_angle", "") or "",
        "camera_movement": getattr(row, "camera_movement", "") or "",
        "camera_speed": getattr(row, "camera_speed", "") or "",
        "shot_purpose": getattr(row, "shot_purpose", "") or "",
        "transition": getattr(row, "transition", "") or "",
        "lighting": getattr(row, "lighting", "") or "",
        "start_state": _parse_json(getattr(row, "start_state", ""), getattr(row, "start_state", "") or ""),
        "action_process": getattr(row, "action_process", "") or "",
        "action_beats": meta.get("action_beats", []),
        "end_state": _parse_json(getattr(row, "end_state", ""), getattr(row, "end_state", "") or ""),
        "asset_bindings": meta.get("asset_bindings", _parse_json(getattr(row, "asset_links", "{}"), {})),
        "continuity_contract": meta.get("continuity_contract", {}),
    }


def mark_materialization_set_stale(session: Any, set_row: Any, reasons: list[str]) -> None:
    normalized = sorted({_text(item) for item in reasons if _text(item)})
    set_row.status = "STALE"
    set_row.stale_status = "STALE"
    set_row.stale_reasons = json.dumps(normalized, ensure_ascii=False)
    set_row.updated_at = __import__("datetime").datetime.now()
    try:
        from models import StoryboardShot
        session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id).update({"materialization_status": "STALE", "production_status": "blocked"}, synchronize_session=False)
    except Exception:
        pass


def resolve_current_authoritative_materialization(session: Any, *, book_id: int, episode: int, scene_id: str):
    """Resolve and validate the current materialization set, fail-closed."""
    from fastapi import HTTPException
    from models import StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot
    from core.shot_plan_authority import resolve_current_authoritative_shot_plan, shot_plan_payload_from_row

    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=_text(scene_id)).first()
    if not pointer:
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_POINTER_MISSING", "message": "No current StoryboardMaterializationSet pointer exists."})
    set_row = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id, book_id=book_id, episode=episode, scene_id=_text(scene_id)).first()
    if not set_row:
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_SET_MISSING", "message": "Current materialization set does not exist."})
    if set_row.status != "MATERIALIZED" or set_row.stale_status != "FRESH":
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_STALE", "message": "Current materialization set is stale.", "stale_reasons": _parse_json(set_row.stale_reasons, [])})
    try:
        plan, plan_envelope = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=_text(scene_id))
    except HTTPException as exc:
        mark_materialization_set_stale(session, set_row, [str((exc.detail or {}).get("code") if isinstance(exc.detail, dict) else "SHOT_PLAN_AUTHORITY_CHANGED")])
        session.commit()
        raise
    if plan.id != pointer.shot_plan_id or plan.revision != pointer.shot_plan_revision or str(set_row.shot_plan_authority_fingerprint) != str(plan_envelope.get("envelope_fingerprint") or "") or pointer.set_payload_fingerprint != set_row.set_payload_fingerprint:
        mark_materialization_set_stale(session, set_row, ["SHOT_PLAN_POINTER_CHANGED"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_STALE", "message": "ShotPlan authority changed; materialization must be recreated."})
    expected_ids = [_text(item.get("plan_shot_id")) for item in shot_plan_payload_from_row(plan).get("shots", [])]
    rows = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=book_id, episode=episode, scene_id=_text(scene_id)).order_by(StoryboardShot.shot_id).all()
    if len(rows) != len(expected_ids) or [str(row.plan_shot_id or "") for row in rows] != expected_ids or int(set_row.expected_shot_count) != len(expected_ids) or int(set_row.materialized_shot_count) != len(rows):
        mark_materialization_set_stale(session, set_row, ["STORYBOARD_MATERIALIZATION_SET_INCOMPLETE"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_SET_INCOMPLETE", "message": "Materialization set cardinality is incomplete."})
    for row in rows:
        meta = _parse_json(row.meta_info, {})
        stored = str(row.projection_fingerprint or "")
        if not stored or stored != projection_fingerprint(_row_projection_payload(row, meta)):
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_PROJECTION_TAMPERED"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_PROJECTION_TAMPERED", "message": "Storyboard projection payload no longer matches its authority fingerprint."})
    envelope = _parse_json(set_row.authority_envelope_json, {})
    return set_row, rows, envelope


__all__ = ["MATERIALIZER_VERSION", "MATERIALIZER_POLICY_VERSION", "MATERIALIZATION_SCHEMA_VERSION", "SHOT_PLAN_PROJECTION", "STRUCTURAL_MATERIALIZATION_METADATA", "COMPILER_OUTPUT", "MEDIA_STATE", "UNKNOWN_INVALID", "materialize_storyboard_from_shot_plan", "materialize_storyboard_from_handoff", "projection_payload", "projection_fingerprint", "materialization_set_fingerprint", "build_materialization_authority_envelope", "validate_materialization_set", "mark_materialization_set_stale", "resolve_current_authoritative_materialization"]
