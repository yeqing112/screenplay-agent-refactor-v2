"""Deterministic AutomaticKeyframePlan planning, review, and compilation.

This layer is deliberately narrow.  It reads the current storyboard
materialization and its existing downstream authorities, stores a reviewable
plan, and delegates production rows to the existing Keyframe Authoring
Runtime.  It never calls a provider and never mutates source or storyboard
authority rows.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from models import (
    AutomaticKeyframePlan,
    Keyframe,
    KeyframeSequence,
    ProductionGenerationIntent,
    ProductionPromptVersion,
    ShotCharacterBinding,
    ShotSceneBinding,
    ShotStyleBinding,
    ShotDirection,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardShot,
)


AUTOMATIC_KEYFRAME_SCHEMA_VERSION = "automatic_keyframe_plan_v1"
FRAME_TYPES = {"start", "middle", "end"}


class AutomaticKeyframePlanError(ValueError):
    status_code = 409
    code = "AUTOMATIC_KEYFRAME_PLAN_INVALID"

    def __init__(self, message: str, *, code: str | None = None, diagnostics: Sequence[Mapping[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.diagnostics = [dict(item) for item in (diagnostics or ())]

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = []
    return list(parsed) if isinstance(parsed, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise AutomaticKeyframePlanError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def _active_materialization(session: Any, shot: StoryboardShot) -> tuple[StoryboardMaterializationSet, StoryboardMaterializationPointer]:
    scene_id = _text(shot.scene_id)
    if not scene_id or shot.materialization_set_id is None:
        raise AutomaticKeyframePlanError("a production StoryboardShot must identify its materialization", code="MATERIALIZATION_REQUIRED")
    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), scene_id=scene_id).one_or_none()
    if pointer is None:
        raise AutomaticKeyframePlanError("active materialization pointer is required", code="MATERIALIZATION_POINTER_REQUIRED")
    set_row = session.query(StoryboardMaterializationSet).filter_by(id=int(pointer.materialization_set_id)).one_or_none()
    if set_row is None:
        raise AutomaticKeyframePlanError("active materialization set is missing", code="MATERIALIZATION_SET_MISSING")
    if int(shot.materialization_set_id) != int(set_row.id) or int(pointer.materialization_set_id) != int(set_row.id):
        raise AutomaticKeyframePlanError("shot is not part of the active materialization", code="MATERIALIZATION_NOT_ACTIVE")
    if _text(pointer.set_payload_fingerprint) != _text(set_row.set_payload_fingerprint):
        raise AutomaticKeyframePlanError("materialization pointer fingerprint is stale", code="MATERIALIZATION_FINGERPRINT_STALE")
    if _text(set_row.status).upper() != "MATERIALIZED" or _text(set_row.stale_status).upper() != "FRESH":
        raise AutomaticKeyframePlanError("materialization set is stale", code="MATERIALIZATION_STALE")
    if _text(shot.materialization_status).upper() not in {"MATERIALIZED", "ACTIVE"}:
        raise AutomaticKeyframePlanError("storyboard shot is not active", code="STORYBOARD_SHOT_INACTIVE")
    return set_row, pointer


def _direction(session: Any, shot: StoryboardShot) -> ShotDirection:
    row = session.query(ShotDirection).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").one_or_none()
    if row is None:
        raise AutomaticKeyframePlanError("active ShotDirection is required", code="SHOT_DIRECTION_REQUIRED")
    if not _text(row.direction_fingerprint):
        raise AutomaticKeyframePlanError("ShotDirection fingerprint is missing", code="SHOT_DIRECTION_INVALID")
    return row


def _intent(session: Any, shot: StoryboardShot) -> ProductionGenerationIntent:
    rows = session.query(ProductionGenerationIntent).filter_by(shot_id=int(shot.id)).order_by(ProductionGenerationIntent.id.desc()).all()
    row = rows[0] if rows else None
    if row is None:
        raise AutomaticKeyframePlanError("production GenerationIntent is required", code="GENERATION_INTENT_REQUIRED")
    constraints = _obj(row.constraint_snapshot)
    if constraints.get("production_eligible") is False:
        raise AutomaticKeyframePlanError("GenerationIntent is not production eligible", code="GENERATION_INTENT_INELIGIBLE")
    if not _text(row.shot_requirement_fingerprint):
        raise AutomaticKeyframePlanError("GenerationIntent fingerprint is missing", code="GENERATION_INTENT_INVALID")
    return row


def _prompt_for_shot(session: Any, shot: StoryboardShot, intent: ProductionGenerationIntent) -> ProductionPromptVersion:
    candidates = session.query(ProductionPromptVersion).order_by(ProductionPromptVersion.id.desc()).all()
    matches: list[ProductionPromptVersion] = []
    for row in candidates:
        # Keyframe compile appends immutable frame prompt versions carrying
        # the same generation-intent lineage.  They are downstream children,
        # never the source prompt authority for a subsequent stale check.
        if "AUTOMATIC_KEYFRAME_PLAN" in _text(row.created_from):
            continue
        structure = _obj(row.prompt_structure)
        lineage = _obj(row.storyboard_lineage)
        if _text(structure.get("generation_intent_id")) == _text(intent.generation_intent_id):
            matches.append(row)
            continue
        if str(lineage.get("storyboard_shot_id")) == str(shot.id) or str(structure.get("storyboard_shot_id")) == str(shot.id):
            matches.append(row)
    if not matches:
        raise AutomaticKeyframePlanError("current ProductionPromptVersion is required", code="PROMPT_LINEAGE_REQUIRED")
    # A prompt_id's highest version is its current immutable version.
    row = matches[0]
    latest = session.query(ProductionPromptVersion).filter_by(prompt_id=row.prompt_id).order_by(ProductionPromptVersion.version_number.desc()).first()
    if latest is None:
        raise AutomaticKeyframePlanError("current ProductionPromptVersion is missing", code="PROMPT_LINEAGE_REQUIRED")
    return latest


def _direction_payload(row: ShotDirection) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "revision": int(row.revision),
        "direction_fingerprint": _text(row.direction_fingerprint),
        "shot_type": _text(row.shot_type),
        "camera_profile": _obj(row.camera_profile),
        "movement_profile": _obj(row.movement_profile),
        "composition_profile": _obj(row.composition_profile),
        "performance_profile": _obj(row.performance_profile),
        "emotion_profile": _obj(row.emotion_profile),
    }


def _continuity_bindings(session: Any, shot: StoryboardShot) -> dict[str, list[dict[str, Any]]]:
    """Snapshot existing character, scene, and style binding authorities."""
    result: dict[str, list[dict[str, Any]]] = {}
    for key, model in (("characters", ShotCharacterBinding), ("scenes", ShotSceneBinding)):
        rows = session.query(model).filter_by(storyboard_shot_id=int(shot.id)).order_by(model.id.asc()).all()
        if rows and not any(_text(row.status).upper() == "ACTIVE" for row in rows):
            raise AutomaticKeyframePlanError(f"{key} binding is stale", code=f"{key.upper()}_BINDING_STALE")
        result[key] = [{"id": int(row.id), "status": _text(row.status), "binding_fingerprint": _text(row.binding_fingerprint), "asset_authority_id": _text(getattr(row, "asset_authority_id", "")), "asset_version_id": _text(getattr(row, "asset_version_id", ""))} for row in rows if _text(row.status).upper() == "ACTIVE"]
    rows = session.query(ShotStyleBinding).filter((ShotStyleBinding.storyboard_shot_id == int(shot.id)) | ((ShotStyleBinding.book_id == int(shot.book_id)) & (ShotStyleBinding.episode == int(shot.episode)))).order_by(ShotStyleBinding.id.asc()).all()
    active = [row for row in rows if _text(row.status).upper() == "ACTIVE"]
    if rows and not active:
        raise AutomaticKeyframePlanError("visual style binding is stale", code="STYLE_BINDING_STALE")
    result["styles"] = [{"id": int(row.id), "style_id": int(row.style_id), "scope": _text(row.scope), "status": _text(row.status), "binding_fingerprint": _text(row.binding_fingerprint), "asset_authority_id": _text(getattr(row, "asset_authority_id", "")), "asset_version_id": _text(getattr(row, "asset_version_id", ""))} for row in active]
    return result


def _state(value: Any, fallback: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    parsed = _obj(value)
    if parsed:
        return parsed
    text = _text(value)
    return {"description": text or fallback}


def _motion_profile(direction: Mapping[str, Any]) -> dict[str, str]:
    camera = direction.get("camera_profile") if isinstance(direction.get("camera_profile"), Mapping) else {}
    movement = direction.get("movement_profile") if isinstance(direction.get("movement_profile"), Mapping) else {}
    performance = direction.get("performance_profile") if isinstance(direction.get("performance_profile"), Mapping) else {}
    emotion = direction.get("emotion_profile") if isinstance(direction.get("emotion_profile"), Mapping) else {}
    return {
        "camera_motion": _text(camera.get("movement") or movement.get("camera_motion") or movement.get("trajectory") or "static"),
        "character_motion": _text(performance.get("body_motion") or performance.get("gesture") or movement.get("subject_motion") or "still"),
        "environment_motion": _text(movement.get("environment_motion") or movement.get("trajectory") or "static"),
        "emotion_transition": _text(emotion.get("transition") or emotion.get("arc") or "stable"),
    }


def _plan_frames(shot: StoryboardShot, direction: Mapping[str, Any], duration: float) -> list[dict[str, Any]]:
    start_state = _state(shot.start_state, "镜头进入时保持稳定姿态")
    end_state = _state(shot.end_state, "镜头结束时保持终止姿态")
    emotion_arc = _state(shot.emotion_arc, "情绪保持")
    scene_state = {"scene_id": _text(shot.scene_id), "scene_name": _text(shot.scene_name), "lighting": _text(shot.lighting)}
    motion = _motion_profile(direction)
    moving = any(value.lower() not in {"", "static", "still", "hold", "stable"} for value in motion.values())
    # Three-second production shots still receive a midpoint when there is a
    # meaningful timed beat.  The planner may emit only start/end for shorter,
    # genuinely static shots.
    complex_motion = duration >= 3 or (moving and (_text(shot.action_process) or _text(emotion_arc.get("transition") or emotion_arc.get("end"))))
    frames: list[dict[str, Any]] = [
        {
            "type": "start", "time": 0.0,
            "description": "镜头进入时的稳定视觉状态：" + _canonical(start_state),
            "camera_state": deepcopy(direction.get("camera_profile") or {}),
            "character_state": start_state, "scene_state": scene_state,
            "emotion_state": {"arc": emotion_arc, "phase": "start"}, "motion_intent": motion,
        }
    ]
    if complex_motion:
        midpoint = round(duration / 2.0, 4)
        frames.append({
            "type": "middle", "time": midpoint,
            "description": "镜头运动中的连续状态：" + (_text(shot.action_process) or _canonical(end_state)),
            "camera_state": deepcopy(direction.get("camera_profile") or {}),
            "character_state": {"from": start_state, "action": _text(shot.action_process) or motion["character_motion"]},
            "scene_state": scene_state, "emotion_state": {"arc": emotion_arc, "phase": "middle"}, "motion_intent": motion,
        })
    frames.append({
        "type": "end", "time": duration,
        "description": "镜头结束时的稳定视觉状态：" + _canonical(end_state),
        "camera_state": deepcopy(direction.get("camera_profile") or {}),
        "character_state": end_state, "scene_state": scene_state,
        "emotion_state": {"arc": emotion_arc, "phase": "end"}, "motion_intent": motion,
    })
    return frames


def _authority_context(session: Any, shot: StoryboardShot) -> dict[str, Any]:
    materialization, pointer = _active_materialization(session, shot)
    direction = _direction(session, shot)
    intent = _intent(session, shot)
    prompt = _prompt_for_shot(session, shot, intent)
    bindings = _continuity_bindings(session, shot)
    shot_plan_id = int(getattr(shot, "source_shot_plan_id", 0) or materialization.shot_plan_id or 0)
    shot_plan_revision = int(getattr(shot, "source_shot_plan_revision", 0) or materialization.shot_plan_revision or 1)
    direction_payload = _direction_payload(direction)
    authority_basis = {
        "materialization_set_id": int(materialization.id),
        "materialization_version": int(materialization.id),
        "materialization_set_fingerprint": _text(materialization.set_payload_fingerprint),
        "pointer_fingerprint": _text(pointer.set_payload_fingerprint),
        "storyboard_shot_id": int(shot.id),
        "shot_projection_fingerprint": _text(shot.projection_fingerprint),
        "shot_plan_id": shot_plan_id,
        "shot_plan_revision": shot_plan_revision,
        "shot_direction_id": int(direction.id),
        "shot_direction_revision": int(direction.revision),
        "shot_direction_fingerprint": _text(direction.direction_fingerprint),
        "generation_intent_id": _text(intent.generation_intent_id),
        "generation_intent_fingerprint": _text(intent.shot_requirement_fingerprint),
        "production_prompt_version_id": _text(prompt.prompt_version_id),
        "production_prompt_fingerprint": _text(prompt.prompt_fingerprint),
        "continuity_bindings": bindings,
    }
    return {"materialization": materialization, "pointer": pointer, "direction": direction, "intent": intent, "prompt": prompt, "bindings": bindings, "direction_payload": direction_payload, "authority_basis": authority_basis, "authority_fingerprint": _fingerprint(authority_basis), "shot_plan_id": shot_plan_id, "shot_plan_revision": shot_plan_revision}


def _row_dict(row: AutomaticKeyframePlan, *, session: Any | None = None) -> dict[str, Any]:
    sequence = None
    if session is not None and row.compiled_sequence_id:
        sequence = session.query(KeyframeSequence).filter_by(id=row.compiled_sequence_id).one_or_none()
    return {
        "id": int(row.id), "episode_id": row.episode_id, "storyboard_shot_id": int(row.storyboard_shot_id),
        "storyboard_materialization_set_id": int(row.storyboard_materialization_set_id), "storyboard_materialization_version": int(row.storyboard_materialization_version),
        "materialization_set_fingerprint": row.materialization_set_fingerprint, "shot_plan_id": int(row.shot_plan_id), "shot_plan_revision": int(row.shot_plan_revision),
        "shot_direction_id": int(row.shot_direction_id), "shot_direction_revision": int(row.shot_direction_revision), "shot_direction_fingerprint": row.shot_direction_fingerprint,
        "generation_intent_id": row.generation_intent_id, "generation_intent_fingerprint": row.generation_intent_fingerprint,
        "production_prompt_version_id": row.production_prompt_version_id, "production_prompt_fingerprint": row.production_prompt_fingerprint,
        "version": int(row.version), "status": row.status, "duration": float(row.duration), "plan": _obj(row.plan_json), "source_fingerprint": row.source_fingerprint,
        "source_lineage": _obj(row.source_lineage_json), "created_by": row.created_by, "reviewed_by": row.reviewed_by, "reviewed_at": _iso(row.reviewed_at),
        "review_lineage": _obj(row.review_lineage_json), "compiled_sequence_id": row.compiled_sequence_id, "compiled_sequence_fingerprint": row.compiled_sequence_fingerprint,
        "stale_reasons": _list(row.stale_reasons), "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at),
        "compiled_sequence": {"id": int(sequence.id), "revision": int(sequence.revision), "fingerprint": sequence.sequence_fingerprint, "status": sequence.status} if sequence else None,
    }


def _mark_stale(row: AutomaticKeyframePlan, reasons: Sequence[str]) -> None:
    row.status = "STALE"
    row.stale_reasons = _canonical(sorted({_text(item) for item in reasons if _text(item)}))
    row.updated_at = datetime.utcnow()


def _currentness(session: Any, row: AutomaticKeyframePlan) -> dict[str, Any]:
    try:
        shot = _resolve_shot(session, row.storyboard_shot_id)
        context = _authority_context(session, shot)
    except AutomaticKeyframePlanError as exc:
        reason = "MATERIALIZATION_POINTER_CHANGED" if exc.code in {"MATERIALIZATION_NOT_ACTIVE", "MATERIALIZATION_FINGERPRINT_STALE", "MATERIALIZATION_STALE"} else exc.code
        return {"current": False, "reasons": [reason], "context": None}
    reasons: list[str] = []
    expected = context["authority_basis"]
    if int(row.storyboard_materialization_set_id) != int(expected["materialization_set_id"]): reasons.append("MATERIALIZATION_POINTER_CHANGED")
    if _text(row.materialization_set_fingerprint) != _text(expected["materialization_set_fingerprint"]): reasons.append("MATERIALIZATION_FINGERPRINT_CHANGED")
    if int(row.storyboard_shot_id) != int(expected["storyboard_shot_id"]): reasons.append("STORYBOARD_SHOT_CHANGED")
    if _text(row.shot_direction_fingerprint) != _text(expected["shot_direction_fingerprint"]): reasons.append("SHOT_DIRECTION_CHANGED")
    if int(row.shot_direction_revision) != int(expected["shot_direction_revision"]): reasons.append("SHOT_DIRECTION_REVISION_CHANGED")
    if _text(row.generation_intent_id) != _text(expected["generation_intent_id"]) or _text(row.generation_intent_fingerprint) != _text(expected["generation_intent_fingerprint"]): reasons.append("GENERATION_INTENT_CHANGED")
    if _text(row.production_prompt_version_id) != _text(expected["production_prompt_version_id"]) or _text(row.production_prompt_fingerprint) != _text(expected["production_prompt_fingerprint"]): reasons.append("PROMPT_VERSION_CHANGED")
    stored_authority = _obj(row.source_lineage_json).get("authority_fingerprint")
    if _text(stored_authority) != _text(context["authority_fingerprint"]): reasons.append("SOURCE_FINGERPRINT_CHANGED")
    return {"current": not reasons, "reasons": sorted(set(reasons)), "context": context}


def is_stale(session: Any, plan: AutomaticKeyframePlan | int) -> dict[str, Any]:
    row = plan if isinstance(plan, AutomaticKeyframePlan) else session.query(AutomaticKeyframePlan).filter_by(id=int(plan)).one_or_none()
    if row is None:
        raise AutomaticKeyframePlanError("automatic keyframe plan does not exist", code="PLAN_NOT_FOUND")
    result = _currentness(session, row)
    if not result["current"] and row.status != "STALE":
        _mark_stale(row, result["reasons"])
    return {"is_stale": not result["current"], "reasons": result["reasons"], "plan": _row_dict(row, session=session)}


def _insert_plan(session: Any, *, shot: StoryboardShot, context: dict[str, Any], plan_payload: dict[str, Any], version: int, created_by: str, source_fingerprint: str | None = None) -> AutomaticKeyframePlan:
    basis = {"authority_fingerprint": context["authority_fingerprint"], "plan": plan_payload}
    source_fp = source_fingerprint or _fingerprint(basis)
    row = AutomaticKeyframePlan(
        episode_id=f"{shot.episode}", storyboard_shot_id=shot.id, storyboard_materialization_set_id=context["materialization"].id,
        storyboard_materialization_version=int(context["materialization"].id), materialization_set_fingerprint=context["materialization"].set_payload_fingerprint,
        shot_plan_id=context["shot_plan_id"], shot_plan_revision=context["shot_plan_revision"], shot_direction_id=context["direction"].id,
        shot_direction_revision=context["direction"].revision, shot_direction_fingerprint=context["direction"].direction_fingerprint,
        generation_intent_id=context["intent"].generation_intent_id, generation_intent_fingerprint=context["intent"].shot_requirement_fingerprint,
        production_prompt_version_id=context["prompt"].prompt_version_id, production_prompt_fingerprint=context["prompt"].prompt_fingerprint,
        version=int(version), status="REVIEW_REQUIRED", duration=float(plan_payload["duration"]), plan_json=_canonical(plan_payload), source_fingerprint=source_fp,
        source_lineage_json=_canonical({"schema_version": AUTOMATIC_KEYFRAME_SCHEMA_VERSION, "authority_fingerprint": context["authority_fingerprint"], "authority": context["authority_basis"], "prompt_ir_pointer_status": "READ_ONLY_NOT_CREATED", "provider_calls": {"llm": 0, "image": 0, "video": 0}}),
        created_by=created_by or "automatic-keyframe-planner", stale_reasons="[]",
    )
    session.add(row)
    session.flush()
    return row


def plan_keyframes(session: Any, *, shot_id: int, created_by: str = "automatic-keyframe-planner") -> dict[str, Any]:
    """Create or return a deterministic REVIEW_REQUIRED plan for an active shot."""
    shot = _resolve_shot(session, shot_id)
    context = _authority_context(session, shot)
    try:
        duration = float(shot.duration)
    except (TypeError, ValueError):
        raise AutomaticKeyframePlanError("shot duration is invalid", code="DURATION_INVALID") from None
    if duration <= 0:
        raise AutomaticKeyframePlanError("shot duration must be positive", code="DURATION_INVALID")
    frames = _plan_frames(shot, context["direction_payload"], duration)
    payload = {"schema_version": AUTOMATIC_KEYFRAME_SCHEMA_VERSION, "duration": duration, "frames": frames, "motion_profile": _motion_profile(context["direction_payload"]), "shot_context": {"shot_purpose": _text(shot.shot_purpose), "action": _text(shot.action_process), "start_state": _state(shot.start_state, ""), "end_state": _state(shot.end_state, "")}, "continuity_bindings": context["bindings"], "source": {"shot_direction": context["direction_payload"], "generation_intent_id": context["intent"].generation_intent_id}}
    source_fp = _fingerprint({"authority_fingerprint": context["authority_fingerprint"], "plan": payload})
    existing = session.query(AutomaticKeyframePlan).filter_by(source_fingerprint=source_fp).one_or_none()
    if existing is not None:
        return _row_dict(existing, session=session)
    latest = session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=shot.id).order_by(AutomaticKeyframePlan.version.desc()).first()
    row = _insert_plan(session, shot=shot, context=context, plan_payload=payload, version=(int(latest.version) + 1 if latest else 1), created_by=created_by, source_fingerprint=source_fp)
    return _row_dict(row, session=session)


def get_keyframe_plan(session: Any, *, shot_id: int, version: int | None = None) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    query = session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=shot.id)
    row = query.filter_by(version=int(version)).one_or_none() if version is not None else query.order_by(AutomaticKeyframePlan.version.desc()).first()
    if row is None:
        raise AutomaticKeyframePlanError("automatic keyframe plan does not exist", code="PLAN_NOT_FOUND")
    current = _currentness(session, row)
    if not current["current"] and row.status != "STALE":
        _mark_stale(row, current["reasons"])
    return _row_dict(row, session=session)


def review_keyframe_plan(session: Any, *, shot_id: int, version: int, decision: str, reviewer: str, note: str = "", frames: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    row = session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=shot.id, version=int(version)).one_or_none()
    if row is None:
        raise AutomaticKeyframePlanError("automatic keyframe plan does not exist", code="PLAN_NOT_FOUND")
    action = _text(decision).upper()
    current = _currentness(session, row)
    if not current["current"]:
        _mark_stale(row, current["reasons"])
        raise AutomaticKeyframePlanError("automatic keyframe plan source is stale", code="PLAN_STALE", diagnostics=[{"reason": item} for item in current["reasons"]])
    if action == "APPROVE":
        row.status = "APPROVED"
        row.reviewed_by = _text(reviewer) or "human-review"
        row.reviewed_at = datetime.utcnow()
        row.review_lineage_json = _canonical({"decision": "APPROVE", "reviewer": row.reviewed_by, "note": note, "human_approved": True, "source_fingerprint": row.source_fingerprint})
    elif action == "REJECT":
        row.status = "REJECTED"
        row.reviewed_by = _text(reviewer) or "human-review"
        row.reviewed_at = datetime.utcnow()
        row.review_lineage_json = _canonical({"decision": "REJECT", "reviewer": row.reviewed_by, "note": note, "human_approved": False})
    elif action in {"REVISE", "REVISION"}:
        source = _obj(row.plan_json)
        revised = deepcopy(source)
        if frames is not None:
            revised["frames"] = [dict(item) for item in frames]
        revised["revision_note"] = note
        revised["schema_version"] = AUTOMATIC_KEYFRAME_SCHEMA_VERSION
        revised_fp = _fingerprint({"authority_fingerprint": current["context"]["authority_fingerprint"], "plan": revised})
        latest = session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=shot.id).order_by(AutomaticKeyframePlan.version.desc()).first()
        if row.status != "COMPILED":
            row.status = "SUPERSEDED"
        new_row = _insert_plan(session, shot=shot, context=current["context"], plan_payload=revised, version=int(latest.version) + 1, created_by=_text(reviewer) or "human-review", source_fingerprint=revised_fp)
        return _row_dict(new_row, session=session)
    else:
        raise AutomaticKeyframePlanError("review decision must be APPROVE, REJECT, or REVISE", code="REVIEW_DECISION_INVALID")
    row.updated_at = datetime.utcnow()
    session.flush()
    return _row_dict(row, session=session)


def compile_keyframe_plan(session: Any, *, shot_id: int, version: int) -> dict[str, Any]:
    """Compile atomically through the existing Keyframe Authoring Runtime."""
    shot = _resolve_shot(session, shot_id)
    row = session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=shot.id, version=int(version)).one_or_none()
    if row is None:
        raise AutomaticKeyframePlanError("automatic keyframe plan does not exist", code="PLAN_NOT_FOUND")
    current = _currentness(session, row)
    if not current["current"]:
        _mark_stale(row, current["reasons"])
        session.flush()
        raise AutomaticKeyframePlanError("automatic keyframe plan source is stale", code="PLAN_STALE", diagnostics=[{"reason": item} for item in current["reasons"]])
    if row.status == "COMPILED" and row.compiled_sequence_id:
        sequence = session.query(KeyframeSequence).filter_by(id=row.compiled_sequence_id).one_or_none()
        if sequence is not None:
            return {"plan": _row_dict(row, session=session), "sequence": _sequence_payload(session, sequence), "video_compatibility": validate_video_compatibility(session, shot_id=shot.id, sequence_id=sequence.id), "idempotent": True, "provider_calls": {"llm": 0, "image": 0, "video": 0}}
    if row.status != "APPROVED":
        raise AutomaticKeyframePlanError("human approval is required before compile", code="REVIEW_REQUIRED", diagnostics=[{"status": row.status}])
    payload = _obj(row.plan_json)
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
    if not frames:
        raise AutomaticKeyframePlanError("automatic keyframe plan has no frames", code="PLAN_FRAMES_REQUIRED")
    normalized: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            raise AutomaticKeyframePlanError("automatic keyframe frame must be an object", code="PLAN_FRAME_INVALID")
        motion = frame.get("motion_intent") if isinstance(frame.get("motion_intent"), Mapping) else {}
        normalized.append({"type": frame.get("type"), "time": frame.get("time"), "description": frame.get("description"), "camera_state": frame.get("camera_state") or {}, "character_state": frame.get("character_state") or {}, "scene_state": frame.get("scene_state") or {}, "emotion_state": frame.get("emotion_state") or {}, "camera_motion": motion.get("camera_motion", ""), "character_motion": motion.get("character_motion", ""), "environment_motion": motion.get("environment_motion", ""), "emotion_transition": motion.get("emotion_transition", "")})
    from core.keyframe_authoring import KeyframeAuthoringError, create_keyframe_sequence
    from core.production_prompt_lineage import create_production_prompt_version

    # The savepoint includes the existing sequence supersede operation and all
    # prompt rows.  Any validator or lineage error rolls back every production
    # row written by this compile.
    with session.begin_nested():
        try:
            sequence = create_keyframe_sequence(session, shot_id=shot.id, duration=float(row.duration), frame_plan={"automatic_keyframe_plan_id": int(row.id), "automatic_keyframe_plan_version": int(row.version), "source_fingerprint": row.source_fingerprint, "motion_profile": payload.get("motion_profile") or {}}, frames=normalized)
        except KeyframeAuthoringError as exc:
            raise AutomaticKeyframePlanError(str(exc), code=exc.code, diagnostics=exc.diagnostics) from exc
        sequence_row = session.query(KeyframeSequence).filter_by(id=int(sequence["id"])).one()
        frame_rows = session.query(Keyframe).filter_by(keyframe_sequence_id=sequence_row.id, status="ACTIVE").order_by(Keyframe.order_index.asc()).all()
        prompt_ids: list[str] = []
        base_prompt = current["context"]["prompt"]
        for frame_row in frame_rows:
            try:
                prompt = create_production_prompt_version(
                    session,
                    prompt_id=f"{base_prompt.prompt_id}:automatic-keyframe-plan-{row.id}-frame-{frame_row.order_index}",
                    prompt_text=base_prompt.prompt_text,
                    prompt_structure={"automatic_keyframe_plan": {"id": int(row.id), "version": int(row.version), "source_fingerprint": row.source_fingerprint}, "frame": {"id": int(frame_row.id), "type": frame_row.frame_type, "time": float(frame_row.time_seconds)}, "generation_intent_id": row.generation_intent_id, "source_lineage": _obj(row.source_lineage_json)},
                    created_from="AUTOMATIC_KEYFRAME_PLAN",
                    direction_shot_id=shot.id,
                    keyframe_id=frame_row.id,
                )
            except Exception as exc:
                raise AutomaticKeyframePlanError("keyframe prompt lineage compilation failed", code="PROMPT_LINEAGE_COMPILE_FAILED", diagnostics=[{"error": str(exc)}]) from exc
            prompt_ids.append(prompt["prompt_version_id"])
        row.compiled_sequence_id = sequence_row.id
        row.compiled_sequence_fingerprint = sequence_row.sequence_fingerprint
        row.status = "COMPILED"
        row.review_lineage_json = _canonical({**_obj(row.review_lineage_json), "compiled": True, "compiled_sequence_id": int(sequence_row.id), "prompt_version_ids": prompt_ids})
        row.updated_at = datetime.utcnow()
        session.flush()
    return {"plan": _row_dict(row, session=session), "sequence": _sequence_payload(session, sequence_row), "video_compatibility": validate_video_compatibility(session, shot_id=shot.id, sequence_id=sequence_row.id), "prompt_version_ids": prompt_ids, "idempotent": False, "provider_calls": {"llm": 0, "image": 0, "video": 0}}


def _sequence_payload(session: Any, row: KeyframeSequence) -> dict[str, Any]:
    frames = session.query(Keyframe).filter_by(keyframe_sequence_id=row.id, status="ACTIVE").order_by(Keyframe.order_index.asc()).all()
    return {"id": int(row.id), "shot_id": int(row.storyboard_shot_id), "duration": float(row.duration), "revision": int(row.revision), "status": row.status, "sequence_fingerprint": row.sequence_fingerprint, "frames": [{"id": int(item.id), "type": item.frame_type, "time": float(item.time_seconds), "description": item.description, "camera_motion": item.camera_motion, "character_motion": item.character_motion, "environment_motion": item.environment_motion, "emotion_transition": item.emotion_transition} for item in frames]}


def validate_video_compatibility(session: Any, *, shot_id: int, sequence_id: int | None = None) -> dict[str, Any]:
    """Validate the structural contract consumed by VideoGenerationIntent.

    Asset binding and PromptIR activation remain downstream concerns; this
    check only proves that the existing video runtime can read duration,
    first/last frame boundaries, and the four motion fields from the sequence.
    """
    shot = _resolve_shot(session, shot_id)
    query = session.query(KeyframeSequence).filter_by(storyboard_shot_id=shot.id, status="ACTIVE")
    if sequence_id is not None:
        query = query.filter_by(id=int(sequence_id))
    sequence = query.order_by(KeyframeSequence.revision.desc()).first()
    if sequence is None:
        return {"status": "BLOCKED", "compatible": False, "errors": ["KEYFRAME_SEQUENCE_MISSING"]}
    frames = session.query(Keyframe).filter_by(keyframe_sequence_id=sequence.id, status="ACTIVE").order_by(Keyframe.time_seconds.asc()).all()
    errors: list[str] = []
    if not frames or frames[0].frame_type != "start" or abs(float(frames[0].time_seconds)) > 1e-6:
        errors.append("VIDEO_FIRST_FRAME_BOUNDARY_INVALID")
    if not frames or frames[-1].frame_type != "end" or abs(float(frames[-1].time_seconds) - float(sequence.duration)) > 1e-6:
        errors.append("VIDEO_LAST_FRAME_BOUNDARY_INVALID")
    required = ("camera_motion", "character_motion", "environment_motion", "emotion_transition")
    if frames and any(not _text(getattr(frames[-1], field, "")) for field in required):
        errors.append("VIDEO_MOTION_PROFILE_INCOMPLETE")
    return {"status": "PASS" if not errors else "BLOCKED", "compatible": not errors, "errors": errors, "sequence_id": int(sequence.id), "duration": float(sequence.duration), "first_frame_id": int(frames[0].id) if frames else None, "last_frame_id": int(frames[-1].id) if frames else None, "motion_profile": {field: _text(getattr(frames[-1], field, "")) for field in required}}


__all__ = ["AUTOMATIC_KEYFRAME_SCHEMA_VERSION", "AutomaticKeyframePlanError", "plan_keyframes", "get_keyframe_plan", "review_keyframe_plan", "compile_keyframe_plan", "is_stale", "validate_video_compatibility"]
