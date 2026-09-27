"""Automatic storyboard draft and fail-closed compiler runtime."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc

from models import ShotPlan, StoryboardPlan, StoryboardPlanShot


STORYBOARD_SCHEMA_VERSION = "automatic_storyboard_v1"
ALLOWED_CAMERA_FIELDS = {"angle", "distance", "lens", "movement", "speed", "strategy"}
ALLOWED_CAMERA_ANGLES = {"eye_level", "high", "low", "overhead", "dutch", "profile", "front", "back", "ms", "ws", "cu", "ecu"}
ALLOWED_CAMERA_MOVEMENTS = {"static", "push-in", "pull-out", "pan", "tilt", "dolly", "zoom", "crane", "handheld", "tracking", "orbit"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


class StoryboardShotPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_id: str = ""
    scene_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    shot_type: str = Field(default="medium", min_length=1)
    camera: dict[str, Any] = Field(default_factory=dict)
    composition: dict[str, Any] = Field(default_factory=dict)
    character_actions: dict[str, Any] = Field(default_factory=dict)
    emotion: str = ""
    duration: float = Field(default=3.0, gt=0, le=60)
    visual_style_id: str = ""
    source_lineage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("shot_id", mode="before")
    @classmethod
    def normalize_shot_id(cls, value: Any) -> str:
        return str(value or "")


class StoryboardPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    status: str = "REVIEW_REQUIRED"
    storyboard_json: dict[str, Any] = Field(default_factory=lambda: {"shots": []})
    director_reasoning_id: int | None = None
    director_reasoning_version: int | None = None
    reasoning_trace: dict[str, Any] = Field(default_factory=dict)
    lineage: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        normalized = str(value or "REVIEW_REQUIRED").upper()
        if normalized not in {"DRAFT", "REVIEW_REQUIRED", "COMPILED", "SUPERSEDED", "ROLLED_BACK", "REJECTED"}:
            raise ValueError("invalid storyboard plan status")
        return normalized


class StoryboardCompileError(ValueError):
    code = "AUTOMATIC_STORYBOARD_COMPILE_BLOCKED"

    def __init__(self, message: str, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _scene_items(script_ir: Mapping[str, Any], scene_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    for source in (script_ir, scene_context):
        values = source.get("scenes") if isinstance(source, Mapping) else None
        if isinstance(values, list):
            return [dict(item) for item in values if isinstance(item, Mapping)]
    return []


def _scene_id(scene: Mapping[str, Any]) -> str:
    return str(scene.get("scene_id") or scene.get("id") or scene.get("key") or "")


def _refs(values: Any) -> list[str]:
    result: list[str] = []
    if isinstance(values, Mapping):
        nested = values.get("characters") or values.get("character_ids") or values.get("refs")
        if isinstance(nested, list):
            values = nested
        else:
            values = [key for key in values if key not in {"action", "actions", "description", "notes", "role"}]
    if isinstance(values, list):
        for item in values:
            if isinstance(item, Mapping):
                value = item.get("character_id") or item.get("id") or item.get("name")
            else:
                value = item
            if str(value or "").strip():
                result.append(str(value))
    return result


def _all_character_ids(episode_context: Mapping[str, Any], scene_context: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for source in (episode_context, scene_context):
        for key in ("character_profiles", "characters", "character_ids"):
            values = source.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                value = item.get("character_id") or item.get("id") or item.get("name") if isinstance(item, Mapping) else item
                if str(value or "").strip():
                    result.add(str(value))
    return result


def _all_style_ids(episode_context: Mapping[str, Any], scene_context: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for source in (episode_context, scene_context):
        for key in ("visual_style_profiles", "visual_styles", "style_profiles"):
            values = source.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                value = item.get("visual_style_id") or item.get("style_id") or item.get("id") or item.get("key") if isinstance(item, Mapping) else item
                if str(value or "").strip():
                    result.add(str(value))
    return result


def _storyboard_shots(payload: Mapping[str, Any]) -> list[StoryboardShotPayload]:
    storyboard = payload.get("storyboard_json") if isinstance(payload, Mapping) else {}
    if isinstance(storyboard, str):
        storyboard = _obj(storyboard)
    values = storyboard.get("shots") if isinstance(storyboard, Mapping) else None
    if not isinstance(values, list) and isinstance(payload, Mapping):
        values = payload.get("shots")
    return [StoryboardShotPayload.model_validate(item) for item in values] if isinstance(values, list) else []


def storyboard_from_reasoning(
    reasoning: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    director_reasoning_id: int | None = None,
    director_reasoning_version: int | None = None,
) -> dict[str, Any]:
    """Deterministically project a validated DirectorReasoningIR into a draft storyboard."""
    episode_id = str(reasoning.get("episode_id") or context.get("episode_id") or "")
    beats = sorted(_list(reasoning.get("beats")), key=lambda item: int(item.get("sequence") or 0))
    decisions = {int(item.get("story_beat_sequence") or 0): item for item in _list(reasoning.get("visual_decisions"))}
    scenes = context.get("scenes") if isinstance(context.get("scenes"), list) else []
    existing_shots = context.get("existing_shots") if isinstance(context.get("existing_shots"), list) else []
    shots: list[dict[str, Any]] = []
    sequence = 1
    for beat in beats:
        scene_id = str(beat.get("scene_id") or "")
        decision = decisions.get(int(beat.get("sequence") or 0), {})
        refs = [str(value) for value in _list(beat.get("shot_refs")) if str(value).strip()]
        if not refs:
            refs = [str(item.get("shot_id") or item.get("id")) for item in existing_shots if isinstance(item, Mapping) and str(item.get("scene_id") or "") == scene_id]
        if not refs:
            refs = [f"{scene_id}:shot-1"]
        for ref in refs:
            shots.append({
                "shot_id": ref,
                "scene_id": scene_id,
                "sequence": sequence,
                "shot_type": "medium",
                "camera": {"angle": "eye_level", "distance": "medium", "lens": "35mm", "movement": "static", "speed": "slow", "strategy": str(decision.get("camera_strategy") or "")},
                "composition": {"strategy": str(decision.get("composition_strategy") or "balanced")},
                "character_actions": {"characters": _list(beat.get("character_refs")), "action": str(beat.get("purpose") or "")},
                "emotion": str(beat.get("emotion") or "neutral"),
                "duration": 3.0,
                "visual_style_id": str(decision.get("visual_style_id") or ""),
                "source_lineage": {"director_reasoning_id": director_reasoning_id, "director_reasoning_version": director_reasoning_version, "story_beat_sequence": int(beat.get("sequence") or 0), "shot_id": ref},
            })
            sequence += 1
    payload = StoryboardPlanPayload(
        episode_id=episode_id,
        status="REVIEW_REQUIRED",
        storyboard_json={"schema_version": STORYBOARD_SCHEMA_VERSION, "shots": shots},
        director_reasoning_id=director_reasoning_id,
        director_reasoning_version=director_reasoning_version,
        reasoning_trace={"mode": "director_reasoning_projection", "human_review_required": True, "source_fact_mutated": False, "script_ir_mutated": False, "media_generation": False},
        lineage={"schema_version": STORYBOARD_SCHEMA_VERSION, "director_reasoning_id": director_reasoning_id, "director_reasoning_version": director_reasoning_version, "source_fact_mutated": False, "script_ir_mutated": False, "human_review_required": True},
    ).model_dump()
    payload["payload_hash"] = _hash(payload)
    return payload


def validate_storyboard_for_compile(
    storyboard: Mapping[str, Any],
    *,
    episode_context: Mapping[str, Any],
    script_ir: Mapping[str, Any],
    scene_context: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_input = dict(storyboard)
    # Persisted rows are flattened by _row_payload for API readability.  Put
    # the nested draft envelope back before strict schema validation.
    if "storyboard_json" not in candidate_input:
        candidate_input = {
            "episode_id": candidate_input.get("episode_id", ""),
            "version": candidate_input.get("version", 1),
            "status": candidate_input.get("status", "REVIEW_REQUIRED"),
            "director_reasoning_id": candidate_input.get("director_reasoning_id"),
            "director_reasoning_version": candidate_input.get("director_reasoning_version"),
            "reasoning_trace": candidate_input.get("reasoning_trace", {}),
            "lineage": candidate_input.get("lineage", {}),
            "storyboard_json": {
                "schema_version": candidate_input.get("schema_version", STORYBOARD_SCHEMA_VERSION),
                "shots": candidate_input.get("shots", []),
            },
        }
    candidate_input.pop("payload_hash", None)
    try:
        candidate = StoryboardPlanPayload.model_validate(candidate_input)
        shots = _storyboard_shots(candidate.model_dump())
    except Exception as exc:
        raise StoryboardCompileError("StoryboardPlan schema validation failed", [{"code": "STORYBOARD_SCHEMA_INVALID", "message": str(exc)}]) from exc
    diagnostics: list[dict[str, Any]] = []
    if not shots:
        diagnostics.append({"code": "STORYBOARD_SHOTS_EMPTY", "message": "StoryboardPlan must contain at least one shot."})
    scenes = _scene_items(script_ir, scene_context)
    scene_ids = {_scene_id(scene) for scene in scenes if _scene_id(scene)}
    character_ids = _all_character_ids(episode_context, scene_context)
    style_ids = _all_style_ids(episode_context, scene_context)
    actual_sequences = [shot.sequence for shot in sorted(shots, key=lambda item: item.sequence)]
    expected_sequences = list(range(1, len(shots) + 1))
    if actual_sequences != expected_sequences:
        diagnostics.append({"code": "SHOT_ORDER_INVALID", "expected": expected_sequences, "actual": actual_sequences})
    if len(set(actual_sequences)) != len(actual_sequences):
        diagnostics.append({"code": "SHOT_SEQUENCE_DUPLICATE", "actual": actual_sequences})
    for shot in shots:
        if shot.scene_id not in scene_ids:
            diagnostics.append({"code": "SCENE_NOT_FOUND", "sequence": shot.sequence, "scene_id": shot.scene_id})
        if not shot.visual_style_id or shot.visual_style_id not in style_ids:
            diagnostics.append({"code": "VISUAL_STYLE_NOT_FOUND", "sequence": shot.sequence, "visual_style_id": shot.visual_style_id})
        refs = _refs(shot.character_actions)
        for character_id in refs:
            if character_id not in character_ids:
                diagnostics.append({"code": "CHARACTER_NOT_FOUND", "sequence": shot.sequence, "character_id": character_id})
        camera = shot.camera
        unknown = sorted(set(camera) - ALLOWED_CAMERA_FIELDS)
        if unknown:
            diagnostics.append({"code": "CAMERA_FIELDS_INVALID", "sequence": shot.sequence, "fields": unknown})
        if not str(camera.get("angle") or "").strip() or not str(camera.get("movement") or "").strip():
            diagnostics.append({"code": "CAMERA_REQUIRED_FIELDS_MISSING", "sequence": shot.sequence, "required": ["angle", "movement"]})
        if str(camera.get("angle") or "").strip().lower() not in ALLOWED_CAMERA_ANGLES:
            diagnostics.append({"code": "CAMERA_ANGLE_INVALID", "sequence": shot.sequence, "angle": camera.get("angle")})
        if str(camera.get("movement") or "").strip().lower() not in ALLOWED_CAMERA_MOVEMENTS:
            diagnostics.append({"code": "CAMERA_MOVEMENT_INVALID", "sequence": shot.sequence, "movement": camera.get("movement")})
        if not math.isfinite(float(shot.duration)) or float(shot.duration) <= 0 or float(shot.duration) > 60:
            diagnostics.append({"code": "DURATION_INVALID", "sequence": shot.sequence, "duration": shot.duration})
        if not shot.shot_id.strip():
            diagnostics.append({"code": "SHOT_ID_MISSING", "sequence": shot.sequence})
    if diagnostics:
        raise StoryboardCompileError("StoryboardPlan compile validation failed", diagnostics)
    return {"status": "PASS", "episode_id": candidate.episode_id, "shot_count": len(shots), "scene_ids": sorted(scene_ids), "character_ids": sorted(character_ids), "visual_style_ids": sorted(style_ids), "checks": {"scene_exists": True, "character_refs_legal": True, "visual_style_exists": True, "shot_order": True, "camera_fields": True, "duration": True}}


def _row_payload(row: StoryboardPlan) -> dict[str, Any]:
    payload = _obj(row.storyboard_json)
    payload.update({"id": row.id, "episode_id": row.episode_id, "version": row.version, "status": row.status, "director_reasoning_id": row.director_reasoning_id, "director_reasoning_version": row.director_reasoning_version, "compiled_shot_plan_ids": _list(row.compiled_shot_plan_ids), "payload_hash": row.payload_hash, "lineage": _obj(row.lineage_json), "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None})
    return payload


def persist_storyboard(session: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    candidate_input = dict(payload)
    candidate_input.pop("payload_hash", None)
    candidate = StoryboardPlanPayload.model_validate(candidate_input)
    shots = _storyboard_shots(candidate.model_dump())
    if not shots:
        raise StoryboardCompileError("StoryboardPlan schema validation failed", [{"code": "STORYBOARD_SHOTS_EMPTY"}])
    latest = session.query(StoryboardPlan).filter_by(episode_id=candidate.episode_id).order_by(desc(StoryboardPlan.version)).first()
    version = int(latest.version) + 1 if latest else 1
    data = candidate.model_dump()
    data["version"] = version
    data["status"] = "REVIEW_REQUIRED" if data["status"] not in {"REJECTED", "ROLLED_BACK"} else data["status"]
    data["lineage"] = {**data.get("lineage", {}), "storyboard_plan_version": version, "human_review_required": True}
    data["payload_hash"] = _hash(data)
    if latest is not None and latest.status not in {"SUPERSEDED", "REJECTED", "ROLLED_BACK"}:
        latest.status = "SUPERSEDED"
    row = StoryboardPlan(episode_id=candidate.episode_id, version=version, status=data["status"], storyboard_json=_canonical({"schema_version": STORYBOARD_SCHEMA_VERSION, "shots": [shot.model_dump() for shot in shots]}), director_reasoning_id=data.get("director_reasoning_id"), director_reasoning_version=data.get("director_reasoning_version"), payload_hash=data["payload_hash"], lineage_json=_canonical(data["lineage"]))
    session.add(row)
    session.flush()
    for shot in shots:
        shot_data = shot.model_dump()
        shot_id = shot_data["shot_id"] or f"{shot_data['scene_id']}:shot-{shot_data['sequence']}"
        session.add(StoryboardPlanShot(storyboard_id=row.id, shot_id=shot_id, scene_id=shot_data["scene_id"], sequence=shot_data["sequence"], shot_type=shot_data["shot_type"], camera=_canonical(shot_data["camera"]), composition=_canonical(shot_data["composition"]), character_actions=_canonical(shot_data["character_actions"]), emotion=shot_data["emotion"], duration=int(round(float(shot_data["duration"]))), visual_style_id=shot_data["visual_style_id"], source_lineage=_canonical({**shot_data.get("source_lineage", {}), "storyboard_plan_id": row.id, "storyboard_plan_version": version})))
    return _row_payload(row)


def get_storyboard(session: Any, episode_id: str, version: int | None = None) -> dict[str, Any] | None:
    query = session.query(StoryboardPlan).filter_by(episode_id=str(episode_id))
    row = query.filter_by(version=int(version)).one_or_none() if version is not None else query.order_by(desc(StoryboardPlan.version)).first()
    return _row_payload(row) if row else None


def compile_storyboard(session: Any, row: StoryboardPlan, *, episode_context: Mapping[str, Any], script_ir: Mapping[str, Any], scene_context: Mapping[str, Any], book_id: int = 0, episode_number: int = 0) -> dict[str, Any]:
    payload = _row_payload(row)
    validation = validate_storyboard_for_compile(payload, episode_context=episode_context, script_ir=script_ir, scene_context=scene_context)
    shots = _storyboard_shots(payload)
    reasoning_id = row.director_reasoning_id
    reasoning_version = row.director_reasoning_version
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    generation_intents: list[dict[str, Any]] = []
    prompt_versions: list[dict[str, Any]] = []
    for shot in sorted(shots, key=lambda item: item.sequence):
        shot_id = shot.shot_id or f"{shot.scene_id}:shot-{shot.sequence}"
        prompt_version_id = f"storyboard-{row.id}-v{row.version}-{shot_id}-prompt-v1"
        intent_id = _hash({"storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "shot_id": shot_id})
        lineage = {"director_reasoning_id": reasoning_id, "director_reasoning_version": reasoning_version, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "sequence": shot.sequence, "shot_id": shot_id, "prompt_version_id": prompt_version_id}
        by_scene[shot.scene_id].append({"plan_shot_id": shot_id, "shot_id": shot_id, "shot_type": shot.shot_type, "camera": shot.camera, "composition": shot.composition, "character_actions": shot.character_actions, "emotion": shot.emotion, "duration": shot.duration, "visual_style_id": shot.visual_style_id, "storyboard_lineage": lineage})
        generation_intents.append({"generation_intent_id": intent_id, "shot_id": shot_id, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "director_reasoning_id": reasoning_id, "director_reasoning_version": reasoning_version, "prompt_version_id": prompt_version_id, "storyboard_lineage": lineage})
        prompt_versions.append({"prompt_version_id": prompt_version_id, "prompt_id": f"shot-{shot_id}-storyboard", "version_number": 1, "created_from": "AUTOMATIC_STORYBOARD", "prompt_fingerprint": _hash({"intent_id": intent_id, "shot_id": shot_id}), "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "storyboard_lineage": lineage})
    scene_items = _scene_items(script_ir, scene_context)
    shot_plan_ids: list[int] = []
    shot_plans: list[dict[str, Any]] = []
    for scene_id, scene_shots in by_scene.items():
        scene_name = next((str(scene.get("scene_name") or scene.get("name") or scene_id) for scene in scene_items if _scene_id(scene) == scene_id), scene_id)
        scene_sequences = {shot.sequence for shot in shots if shot.scene_id == scene_id}
        scene_intents = [item["generation_intent_id"] for item in generation_intents if item["storyboard_lineage"]["sequence"] in scene_sequences]
        plan = ShotPlan(book_id=int(book_id or 0), episode=int(episode_number or episode_context.get("episode") or 0), scene_id=scene_id, scene_name=scene_name, revision=1, status="draft", schema_version="shot_plan_v1", quality_status="storyboard_candidate", production_status="blocked", workflow_profile="creative_draft", shots=_canonical(scene_shots), unknowns="[]", director_reasoning_id=reasoning_id, director_reasoning_version=reasoning_version, storyboard_plan_id=row.id, storyboard_plan_version=row.version, storyboard_lineage=_canonical({"director_reasoning_id": reasoning_id, "director_reasoning_version": reasoning_version, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "generation_intents": scene_intents}), reasoning_lineage=_canonical({"director_reasoning_id": reasoning_id, "director_reasoning_version": reasoning_version, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version}))
        session.add(plan)
        session.flush()
        shot_plan_ids.append(int(plan.id))
        shot_plans.append({"id": plan.id, "scene_id": scene_id, "shots": scene_shots, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "storyboard_lineage": _obj(plan.storyboard_lineage)})
    row.status = "COMPILED"
    row.compiled_shot_plan_ids = _canonical(shot_plan_ids)
    row.updated_at = datetime.utcnow()
    return {"status": "COMPILED", "validation": validation, "storyboard": _row_payload(row), "shot_plans": shot_plans, "generation_intents": generation_intents, "prompt_versions": prompt_versions, "lineage": {"director_reasoning_id": reasoning_id, "director_reasoning_version": reasoning_version, "storyboard_plan_id": row.id, "storyboard_plan_version": row.version, "shot_plan_ids": shot_plan_ids, "generation_intent_ids": [item["generation_intent_id"] for item in generation_intents], "prompt_version_ids": [item["prompt_version_id"] for item in prompt_versions], "human_review_required": True}}


def rollback_storyboard(session: Any, episode_id: str, version: int) -> dict[str, Any]:
    row = session.query(StoryboardPlan).filter_by(episode_id=str(episode_id), version=int(version)).one_or_none()
    if row is None:
        raise StoryboardCompileError("StoryboardPlan version does not exist", [{"code": "STORYBOARD_NOT_FOUND", "episode_id": str(episode_id), "version": version}])
    plan_ids = [int(item) for item in _list(row.compiled_shot_plan_ids) if str(item).isdigit()]
    plans = session.query(ShotPlan).filter(ShotPlan.id.in_(plan_ids)).all() if plan_ids else []
    for plan in plans:
        if plan.status == "draft":
            plan.status = "superseded"
            plan.production_status = "blocked"
            plan.storyboard_lineage = _canonical({**_obj(plan.storyboard_lineage), "rolled_back": True, "rolled_back_storyboard_id": row.id, "rolled_back_storyboard_version": row.version})
    row.status = "ROLLED_BACK"
    row.updated_at = datetime.utcnow()
    return {"status": "ROLLED_BACK", "episode_id": row.episode_id, "version": row.version, "shot_plan_ids": plan_ids, "preserved": True}


__all__ = ["STORYBOARD_SCHEMA_VERSION", "StoryboardShotPayload", "StoryboardPlanPayload", "StoryboardCompileError", "storyboard_from_reasoning", "validate_storyboard_for_compile", "persist_storyboard", "get_storyboard", "compile_storyboard", "rollback_storyboard"]
