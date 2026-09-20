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
from core.storyboard_visual_semantics import (
    ASSET_IDENTITY_BINDING,
    DOWNSTREAM_HANDOFF_METADATA,
    PRODUCTION_CONTINUITY_STATE,
    VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION,
    VISUAL_SEMANTIC_PROJECTION_VERSION,
    build_visual_semantic_handoff,
    build_visual_semantic_handoff_set,
    semantic_projection_fingerprint,
)

# Phase D authority classes.  ``COMPILER_OUTPUT`` is retained as a
# compatibility alias for older callers; Production materialization never
# writes compiler output.
ASSET_IDENTITY_BINDING = ASSET_IDENTITY_BINDING
PRODUCTION_CONTINUITY_STATE = PRODUCTION_CONTINUITY_STATE
DOWNSTREAM_HANDOFF_METADATA = DOWNSTREAM_HANDOFF_METADATA


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
                "production_continuity_state": ["start_state", "end_state", "continuity_contract"],
                "asset_identity_binding": ["asset_bindings"],
                "structural_materialization_metadata": ["shot_id", "projection_fingerprint"],
                "downstream_handoff_metadata": ["visual_semantic_handoff"],
                "compiler_output": [],
                "media_state": [],
            },
            "camera": camera,
            "shot_plan_ref": {"plan_shot_id": plan_shot_id},
        },
    }
    if isinstance(item.get("meta_info"), dict):
        projection["meta_info"].update(item["meta_info"])
    semantic = build_visual_semantic_handoff(
        scene_id=scene_id,
        plan_shot_id=plan_shot_id,
        handoff_shot=item,
        shot_plan_id=item.get("shot_plan_id"),
    )
    projection["visual_semantic_handoff"] = semantic
    projection["meta_info"]["visual_semantic_handoff"] = semantic
    projection["meta_info"]["semantic_projection_fingerprint"] = semantic_projection_fingerprint(semantic)
    projection["projection_fingerprint"] = _fingerprint({key: projection[key] for key in (
        "scene_id", "scene_name", "plan_shot_id", "beat_id", "dialogue", "duration", "camera_angle", "camera_movement", "camera_speed", "shot_purpose", "transition", "lighting", "start_state", "action_process", "action_beats", "end_state", "asset_bindings", "continuity_contract"
    )} | {"visual_semantic_handoff": semantic})
    projection["meta_info"]["materializer"] = {"version": MATERIALIZER_VERSION, "policy_version": MATERIALIZER_POLICY_VERSION, "projection_fingerprint": projection["projection_fingerprint"]}
    return projection


def materialize_storyboard_from_handoff(handoff: dict[str, Any], *, production: bool = True, shot_plan_id: Any = None, source_authority_fingerprint: str = "", blocking_authority_fingerprint: str = "", materialization_set_id: Any = None) -> list[dict[str, Any]]:
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
        semantic = build_visual_semantic_handoff(
            scene_id=scene_id,
            plan_shot_id=_text(item.get("plan_shot_id")),
            handoff_shot=item,
            shot_plan_id=shot_plan_id,
            source_authority_fingerprint=source_authority_fingerprint,
            blocking_authority_fingerprint=blocking_authority_fingerprint,
            materialization_set_id=materialization_set_id,
        )
        projection["visual_semantic_handoff"] = semantic
        projection["meta_info"]["visual_semantic_handoff"] = semantic
        projection["meta_info"]["semantic_projection_fingerprint"] = semantic_projection_fingerprint(semantic)
        projection["meta_info"]["handoff"] = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "projection_version": HANDOFF_PROJECTION_VERSION,
            "handoff_fingerprint": handoff.get("handoff_fingerprint"),
            "storyboard_handoff_shot_fingerprint": item.get("storyboard_handoff_shot_fingerprint"),
        }
        # Include the complete structured semantic payload in the protected
        # projection fingerprint.  Prompt/media fields are intentionally not
        # part of this payload.
        projection["projection_fingerprint"] = _fingerprint({key: projection[key] for key in (
            "scene_id", "scene_name", "plan_shot_id", "beat_id", "dialogue", "duration", "camera_angle", "camera_movement", "camera_speed", "shot_purpose", "transition", "lighting", "start_state", "action_process", "action_beats", "end_state", "asset_bindings", "continuity_contract", "visual_semantic_handoff"
        )})
        projection["meta_info"]["materializer"] = {"version": MATERIALIZER_VERSION, "policy_version": MATERIALIZER_POLICY_VERSION, "projection_fingerprint": projection["projection_fingerprint"]}
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
    payload = {key: shot.get(key) for key in ("scene_id", "scene_name", "plan_shot_id", "beat_id", "dialogue", "duration", "camera_angle", "camera_movement", "camera_speed", "shot_purpose", "transition", "lighting", "start_state", "action_process", "action_beats", "end_state", "asset_bindings", "continuity_contract")}
    semantic = shot.get("visual_semantic_handoff")
    if not isinstance(semantic, dict) and isinstance(shot.get("meta_info"), dict):
        semantic = shot["meta_info"].get("visual_semantic_handoff")
    payload["visual_semantic_handoff"] = semantic if isinstance(semantic, dict) else {}
    return payload


def materialization_set_fingerprint(*, authority_envelope: dict[str, Any], projections: list[dict[str, Any]]) -> str:
    return _fingerprint({"schema_version": MATERIALIZATION_SCHEMA_VERSION, "materializer_version": MATERIALIZER_VERSION, "materializer_policy_version": MATERIALIZER_POLICY_VERSION, "authority": authority_envelope, "ordered_projections": [projection_payload(item) for item in projections]})


def build_materialization_authority_envelope(*, script_ir: dict[str, Any], treatment: dict[str, Any], blocking: dict[str, Any], shot_plan: dict[str, Any], materialization_set: dict[str, Any], stale_status: str = "FRESH", stale_reasons: list[str] | None = None) -> dict[str, Any]:
    envelope = {"schema_version": MATERIALIZATION_SCHEMA_VERSION, "authority_policy_version": MATERIALIZER_POLICY_VERSION, "script_ir": script_ir, "director_treatment": treatment, "scene_blocking": blocking, "shot_plan": shot_plan, "materialization": materialization_set, "stale_status": stale_status, "stale_reasons": sorted(set(stale_reasons or []))}
    envelope["authority_fingerprint"] = authority_envelope_fingerprint(envelope)
    return envelope


def authority_envelope_fingerprint(envelope: dict[str, Any]) -> str:
    """Fingerprint an authority envelope after all nested bindings are set."""
    payload = dict(envelope) if isinstance(envelope, dict) else {}
    payload.pop("authority_fingerprint", None)
    return _fingerprint(payload)


def build_storyboard_production_snapshot(*, materialization_set: Any, rows: list[Any], authority_envelope: dict[str, Any]) -> dict[str, Any]:
    """Build a read-only Phase D → Phase E boundary snapshot.

    The snapshot is assembled at runtime from the already-resolved current
    Set; it is not persisted as another authority table and contains no
    prompt prose or media payload.
    """
    ordered = []
    for row in rows:
        meta = _parse_json(getattr(row, "meta_info", "{}"), {})
        semantic = meta.get("visual_semantic_handoff") if isinstance(meta, dict) else {}
        ordered.append({
            "plan_shot_id": _text(getattr(row, "plan_shot_id", "")),
            "storyboard_shot_id": getattr(row, "id", None),
            "projection_fingerprint": _text(getattr(row, "projection_fingerprint", "")),
            "visual_semantic_handoff": semantic,
        })
    return {
        "schema_version": "storyboard_production_snapshot_v1",
        "storyboard_materialization_authority": {
            "materialization_set_id": getattr(materialization_set, "id", None),
            "set_payload_fingerprint": _text(getattr(materialization_set, "set_payload_fingerprint", "")),
            "status": getattr(materialization_set, "status", ""),
            "stale_status": getattr(materialization_set, "stale_status", ""),
        },
        "authority_envelope": authority_envelope if isinstance(authority_envelope, dict) else {},
        "ordered_shots": ordered,
        "prompt_prose": False,
        "media_state": "NOT_GENERATED",
    }


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


def _live_row_projection_payload(row: Any, meta: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct projection fields from mutable StoryboardShot columns.

    ``projection_payload`` is the immutable snapshot used for the fingerprint;
    this companion payload intentionally reads the live row columns so a
    direct SQL/ORM edit cannot remain fresh merely because the protected JSON
    snapshot was left untouched.
    """
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
        "visual_semantic_handoff": _parse_json(meta.get("visual_semantic_handoff"), {}),
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


def _resolve_current_authoritative_materialization(session: Any, *, book_id: int, episode: int, scene_id: str, materialization_set_id: int | None = None):
    """Resolve and validate the current materialization set, fail-closed."""
    from fastapi import HTTPException
    from models import StoryboardMaterializationPointer, StoryboardMaterializationSet, StoryboardShot
    from core.shot_plan_authority import resolve_current_authoritative_shot_plan, shot_plan_payload_from_row
    from core.scene_blocking_authority import blocking_payload_from_row, resolve_current_authoritative_scene_blocking
    from core.director_treatment_authority import resolve_current_authoritative_treatment
    from core.storyboard_visual_semantics import compare_shotplan_storyboard_semantics, semantic_diff, validate_asset_identity_bindings

    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=_text(scene_id)).first()
    if not pointer and materialization_set_id is not None:
        candidate = session.query(StoryboardMaterializationSet).filter_by(id=materialization_set_id, book_id=book_id, episode=episode, scene_id=_text(scene_id)).first()
        if candidate is not None:
            from types import SimpleNamespace
            pointer = SimpleNamespace(materialization_set_id=candidate.id, shot_plan_id=candidate.shot_plan_id, shot_plan_revision=candidate.shot_plan_revision, set_payload_fingerprint=candidate.set_payload_fingerprint)
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
    try:
        blocking, blocking_envelope = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=_text(scene_id))
        treatment, treatment_envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=_text(scene_id))
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = str(detail.get("code") or "BLOCKING_AUTHORITY_CHANGED")
        mark_materialization_set_stale(session, set_row, [code, "BLOCKING_POINTER_CHANGED"])
        session.commit()
        raise
    if pointer.set_payload_fingerprint != set_row.set_payload_fingerprint:
        mark_materialization_set_stale(session, set_row, ["STORYBOARD_MATERIALIZATION_FINGERPRINT_MISMATCH"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_FINGERPRINT_MISMATCH", "message": "Current pointer does not match the materialization set fingerprint."})
    if plan.id != pointer.shot_plan_id or plan.revision != pointer.shot_plan_revision or str(set_row.shot_plan_authority_fingerprint) != str(plan_envelope.get("envelope_fingerprint") or ""):
        mark_materialization_set_stale(session, set_row, ["SHOT_PLAN_POINTER_CHANGED"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_STALE", "message": "ShotPlan authority changed; materialization must be recreated."})
    plan_payload = shot_plan_payload_from_row(plan)
    if plan_payload.get("phase_c_semantic_ready") is not True:
        mark_materialization_set_stale(session, set_row, ["SHOT_PLAN_PHASE_C_NOT_READY"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_PHASE_C_NOT_READY", "message": "Current ShotPlan is not Phase C semantic-ready."})
    try:
        blocking_payload = blocking_payload_from_row(blocking)
        current_handoff = project_shot_design_to_storyboard_handoff(plan_payload, blocking=blocking_payload, require_phase_c=True)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        code = str(exc).split(":", 1)[0] if ":" in str(exc) else "STORYBOARD_HANDOFF_INVALID"
        mark_materialization_set_stale(session, set_row, [code])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": code, "message": str(exc)})
    set_envelope = _parse_json(set_row.authority_envelope_json, {})
    stored_handoff = set_envelope.get("storyboard_handoff") if isinstance(set_envelope.get("storyboard_handoff"), dict) else {}
    envelope_errors: list[str] = []
    if not set_envelope or _text(set_envelope.get("authority_fingerprint")) != authority_envelope_fingerprint(set_envelope):
        envelope_errors.append("STORYBOARD_AUTHORITY_ENVELOPE_TAMPERED")
    if _text(stored_handoff.get("schema_version")) != _text(current_handoff.get("schema_version")) or _text(stored_handoff.get("projection_version")) != _text(current_handoff.get("projection_version")):
        envelope_errors.append("STORYBOARD_HANDOFF_SCHEMA_CHANGED")
    if _text(stored_handoff.get("source_shot_plan_fingerprint")) != _text(current_handoff.get("source_shot_plan_fingerprint")) or _text(stored_handoff.get("handoff_fingerprint")) != _text(current_handoff.get("handoff_fingerprint")):
        envelope_errors.append("STORYBOARD_HANDOFF_FINGERPRINT_INVALID")
    # The authority envelope uses the canonical ``scene_blocking`` key.  The
    # short ``blocking`` spelling is accepted only for older envelopes so the
    # resolver remains current-pointer-only without manufacturing a second
    # lineage source.
    blocking_meta = set_envelope.get("scene_blocking") if isinstance(set_envelope.get("scene_blocking"), dict) else (set_envelope.get("blocking") if isinstance(set_envelope.get("blocking"), dict) else {})
    if str(blocking_meta.get("id")) != str(blocking.id) or str(blocking_meta.get("revision")) != str(blocking.revision) or _text(blocking_meta.get("authority_fingerprint")) != _text(blocking_envelope.get("envelope_fingerprint")):
        envelope_errors.append("BLOCKING_POINTER_CHANGED")
    if envelope_errors:
        mark_materialization_set_stale(session, set_row, envelope_errors)
        session.commit()
        code = envelope_errors[0]
        raise HTTPException(status_code=409, detail={"code": code, "message": "Storyboard materialization authority envelope is stale or tampered.", "stale_reasons": envelope_errors})

    expected_ids = [_text(item.get("plan_shot_id")) for item in plan_payload.get("shots", [])]
    stored_ids = _parse_json(set_row.ordered_plan_shot_ids, [])
    if stored_ids != expected_ids:
        mark_materialization_set_stale(session, set_row, ["STORYBOARD_MATERIALIZATION_SET_INCOMPLETE"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_SET_INCOMPLETE", "message": "Materialization set order or cardinality is invalid."})
    rows = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=book_id, episode=episode, scene_id=_text(scene_id)).order_by(StoryboardShot.shot_id).all()
    if len(rows) != len(expected_ids) or [str(row.plan_shot_id or "") for row in rows] != expected_ids or int(set_row.expected_shot_count) != len(expected_ids) or int(set_row.materialized_shot_count) != len(rows):
        mark_materialization_set_stale(session, set_row, ["STORYBOARD_MATERIALIZATION_SET_INCOMPLETE"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_SET_INCOMPLETE", "message": "Materialization set cardinality is incomplete."})
    expected_semantics = build_visual_semantic_handoff_set(scene_id=_text(scene_id), handoff=current_handoff, shot_plan_id=plan.id, source_authority_fingerprint=str(plan_envelope.get("envelope_fingerprint") or ""), blocking_authority_fingerprint=str(blocking_envelope.get("envelope_fingerprint") or ""), materialization_set_id=set_row.id)
    expected_by_id = {_text(item.get("plan_shot_id")): item for item in expected_semantics}
    actual_semantics: list[dict[str, Any]] = []
    row_projections: list[dict[str, Any]] = []
    for row in rows:
        meta = _parse_json(row.meta_info, {})
        stored = str(row.projection_fingerprint or "")
        stored_payload = meta.get("projection_payload") if isinstance(meta.get("projection_payload"), dict) else None
        live_row_payload = _live_row_projection_payload(row, meta)
        if stored_payload is not None:
            # Semantic handoff edits are reported by the structured semantic
            # diff below; this comparison covers the mutable StoryboardShot
            # projection columns themselves.
            live_row_columns = dict(live_row_payload)
            stored_row_columns = dict(stored_payload)
            live_row_columns.pop("visual_semantic_handoff", None)
            stored_row_columns.pop("visual_semantic_handoff", None)
        else:
            live_row_columns = live_row_payload
            stored_row_columns = None
        if stored_row_columns is not None and _canonical(live_row_columns) != _canonical(stored_row_columns):
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_PROJECTION_TAMPERED"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_PROJECTION_TAMPERED", "message": "Storyboard projection columns no longer match their immutable projection payload."})
        if not stored or stored != projection_fingerprint(_row_projection_payload(row, meta)):
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_PROJECTION_TAMPERED"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_PROJECTION_TAMPERED", "message": "Storyboard projection payload no longer matches its authority fingerprint."})
        if str(getattr(row, "source_shot_plan_authority_fingerprint", "") or "") != str(plan_envelope.get("envelope_fingerprint") or ""):
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_PROJECTION_TAMPERED"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_PROJECTION_TAMPERED", "message": "StoryboardShot source authority fingerprint changed."})
        if any(str(getattr(row, field, "") or "").strip() for field in ("visual_prompt_static", "visual_prompt_motion", "visual_prompt_final")):
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_PROMPT_PREMATURE_MUTATION"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_PROMPT_PREMATURE_MUTATION", "message": "Prompt fields must remain uncompiled during Phase D."})
        semantic = meta.get("visual_semantic_handoff") if isinstance(meta.get("visual_semantic_handoff"), dict) else {}
        if _text(semantic.get("schema_version")) != VISUAL_SEMANTIC_HANDOFF_SCHEMA_VERSION:
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_VISUAL_SEMANTIC_HANDOFF_MISSING"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_VISUAL_SEMANTIC_HANDOFF_MISSING", "message": "StoryboardShot has no Phase D visual semantic handoff."})
        actual_semantics.append(semantic)
        row_projections.append(_row_projection_payload(row, meta))
    semantic_result = compare_shotplan_storyboard_semantics(expected=expected_semantics, actual=actual_semantics)
    if not semantic_result.get("empty"):
        reasons = ["STORYBOARD_SEMANTIC_MISMATCH"]
        if semantic_result.get("camera_mismatch"): reasons.append("STORYBOARD_CAMERA_SEMANTIC_MISMATCH")
        if semantic_result.get("continuity_mismatch"): reasons.append("STORYBOARD_CONTINUITY_SEMANTIC_MISMATCH")
        if semantic_result.get("asset_binding_mismatch"): reasons.append("STORYBOARD_ASSET_BINDING_MISMATCH")
        mark_materialization_set_stale(session, set_row, reasons)
        session.commit()
        raise HTTPException(status_code=409, detail={"code": reasons[0], "message": "Storyboard visual semantic projection does not match the current ShotPlan.", "semantic_diff": semantic_result})
    # Required identities are checked against the canonical ShotPlan fields;
    # missing identity bindings fail closed without requiring a reference image.
    for source, semantic in zip(plan_payload.get("shots", []), actual_semantics):
        spatial = source.get("spatial_binding") if isinstance(source.get("spatial_binding"), dict) else {}
        asset_errors = validate_asset_identity_bindings(semantic=semantic, required_subjects=list(source.get("subjects") or []), required_props=list(spatial.get("prop_refs") or []), scene_id=_text(scene_id))
        if asset_errors:
            mark_materialization_set_stale(session, set_row, ["STORYBOARD_ASSET_BINDING_MISMATCH"])
            session.commit()
            raise HTTPException(status_code=409, detail={"code": "STORYBOARD_ASSET_BINDING_MISMATCH", "message": "Storyboard asset identity bindings do not satisfy the ShotPlan.", "errors": asset_errors})
    expected_set_fp = materialization_set_fingerprint(authority_envelope={"shot_plan": plan_envelope, "treatment": treatment_envelope, "blocking": blocking_envelope, "storyboard_handoff": current_handoff}, projections=row_projections)
    if _text(set_row.set_payload_fingerprint) != expected_set_fp:
        mark_materialization_set_stale(session, set_row, ["STORYBOARD_MATERIALIZATION_FINGERPRINT_MISMATCH"])
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "STORYBOARD_MATERIALIZATION_FINGERPRINT_MISMATCH", "message": "Materialization set fingerprint no longer matches its canonical projection."})
    resolved_envelope = dict(set_envelope)
    resolved_envelope["storyboard_semantic_ready"] = True
    resolved_envelope["semantic_projection_count"] = len(actual_semantics)
    return set_row, rows, resolved_envelope




def validate_current_materialization_authority(session: Any, *, book_id: int, episode: int, scene_id: str, materialization_set_id: int | None = None) -> dict[str, Any]:
    """Validate current materialization authority through one canonical path."""
    try:
        set_row, rows, envelope = _resolve_current_authoritative_materialization(
            session, book_id=book_id, episode=episode, scene_id=scene_id, materialization_set_id=materialization_set_id
        )
        return {
            "valid": True, "reusable": True, "errors": [], "set": set_row,
            "rows": rows, "current_handoff": (envelope or {}).get("storyboard_handoff", {}),
            "set_fingerprint": _text(getattr(set_row, "set_payload_fingerprint", "")),
            "current_envelope": envelope,
            "storyboard_semantic_ready": bool((envelope or {}).get("storyboard_semantic_ready")),
        }
    except Exception as exc:
        from fastapi import HTTPException
        if isinstance(exc, HTTPException):
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            return {"valid": False, "reusable": False,
                    "errors": [str(detail.get("code") or "STORYBOARD_MATERIALIZATION_INVALID")],
                    "detail": detail, "exception": exc}
        raise


def resolve_current_authoritative_materialization(session: Any, *, book_id: int, episode: int, scene_id: str):
    """Resolve the current Set through the shared canonical validator."""
    result = validate_current_materialization_authority(session, book_id=book_id, episode=episode, scene_id=scene_id)
    if not result.get("valid"):
        raise result["exception"]
    return result["set"], result["rows"], result["current_envelope"]
__all__ = ["MATERIALIZER_VERSION", "MATERIALIZER_POLICY_VERSION", "MATERIALIZATION_SCHEMA_VERSION", "SHOT_PLAN_PROJECTION", "PRODUCTION_CONTINUITY_STATE", "ASSET_IDENTITY_BINDING", "STRUCTURAL_MATERIALIZATION_METADATA", "DOWNSTREAM_HANDOFF_METADATA", "COMPILER_OUTPUT", "MEDIA_STATE", "UNKNOWN_INVALID", "materialize_storyboard_from_shot_plan", "materialize_storyboard_from_handoff", "projection_payload", "projection_fingerprint", "materialization_set_fingerprint", "build_materialization_authority_envelope", "authority_envelope_fingerprint", "build_storyboard_production_snapshot", "validate_materialization_set", "mark_materialization_set_stale", "resolve_current_authoritative_materialization", "validate_current_materialization_authority"]
