"""Provider-free AI Director runtime foundation.

This module turns already available ScriptIR/evidence into a deterministic,
reviewable production-plan candidate.  It never imports an LLM client and it
never executes image/video generation.  All generated values are candidates
with explicit source lineage; a human may revise them before downstream
authorities are activated.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc

from models import DirectorPlan, ScenePlan, ShotPlan, ScriptIRVersion


RUNTIME_SCHEMA_VERSION = "ai_director_runtime_v1"


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


class ScenePlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(min_length=1)
    location: str = ""
    time: str = ""
    mood: str = ""
    characters: list[Any] = Field(default_factory=list)
    visual_requirements: dict[str, Any] = Field(default_factory=dict)
    source_lineage: dict[str, Any] = Field(default_factory=dict)


class ShotPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shot_id: str = Field(min_length=1)
    shot_type: str = "medium"
    camera: dict[str, Any] = Field(default_factory=dict)
    lens: str = "35mm"
    movement: str = "static"
    composition: dict[str, Any] = Field(default_factory=dict)
    emotion: str = ""
    action: str = ""
    source_lineage: dict[str, Any] = Field(default_factory=dict)


class GenerationIntentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation_intent_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    character_requirements: dict[str, Any] = Field(default_factory=dict)
    scene_requirements: dict[str, Any] = Field(default_factory=dict)
    camera_requirements: dict[str, Any] = Field(default_factory=dict)
    style_requirements: dict[str, Any] = Field(default_factory=dict)
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_lineage: dict[str, Any] = Field(default_factory=dict)


class DirectorPlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    status: str = "DRAFT"
    created_by: str = "director-runtime"
    reasoning_trace: dict[str, Any] = Field(default_factory=dict)
    scene_plans: list[ScenePlanPayload] = Field(default_factory=list)
    shot_plans: list[ShotPlanPayload] = Field(default_factory=list)
    shot_directions: list[dict[str, Any]] = Field(default_factory=list)
    generation_intents: list[GenerationIntentPayload] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        normalized = str(value or "DRAFT").upper()
        if normalized not in {"DRAFT", "REVIEW_REQUIRED", "APPROVED", "SUPERSEDED", "REJECTED"}:
            raise ValueError("invalid director plan status")
        return normalized


def _scene_source_items(script_ir: Mapping[str, Any], episode_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    for source in (script_ir, episode_context):
        scenes = source.get("scenes") if isinstance(source, Mapping) else None
        if isinstance(scenes, list):
            return [dict(item) for item in scenes if isinstance(item, Mapping)]
    return []


def _shot_source_items(scene: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("shots", "shot_plans", "coverage"):
        values = scene.get(key)
        if isinstance(values, list):
            return [dict(item) for item in values if isinstance(item, Mapping)]
    return []


def director_plan(script_ir: Mapping[str, Any] | None, episode_context: Mapping[str, Any] | None, character_profiles: list[Mapping[str, Any]] | None, scene_profiles: list[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Return deterministic structured JSON for the Director Adapter contract."""
    script = deepcopy(dict(script_ir or {}))
    context = deepcopy(dict(episode_context or {}))
    characters = [dict(item) for item in (character_profiles or []) if isinstance(item, Mapping)]
    profiles = [dict(item) for item in (scene_profiles or []) if isinstance(item, Mapping)]
    episode_id = str(context.get("episode_id") or context.get("id") or script.get("episode_id") or script.get("episode") or "episode-unknown")
    source_script_hash = str(context.get("source_script_ir_hash") or _hash(script))
    scene_plans: list[dict[str, Any]] = []
    shot_plans: list[dict[str, Any]] = []
    shot_directions: list[dict[str, Any]] = []
    intents: list[dict[str, Any]] = []
    for scene_index, source_scene in enumerate(_scene_source_items(script, context), start=1):
        scene_id = str(source_scene.get("scene_id") or source_scene.get("id") or f"{episode_id}:scene-{scene_index}")
        profile = next((p for p in profiles if str(p.get("scene_id") or p.get("id")) == scene_id), {})
        scene_lineage = {"source": "ScriptIR", "source_scene_id": scene_id, "source_script_ir_hash": source_script_hash}
        scene_plan = ScenePlanPayload(
            scene_id=scene_id,
            location=str(source_scene.get("location") or source_scene.get("scene_name") or profile.get("location") or ""),
            time=str(source_scene.get("time") or source_scene.get("time_of_day") or profile.get("time") or ""),
            mood=str(source_scene.get("mood") or profile.get("mood") or ""),
            characters=source_scene.get("characters") if isinstance(source_scene.get("characters"), list) else ([*source_scene.get("participants", [])] if isinstance(source_scene.get("participants"), list) else []),
            visual_requirements={**_obj(profile.get("visual_requirements")), **_obj(source_scene.get("visual_requirements"))},
            source_lineage=scene_lineage,
        ).model_dump()
        scene_plans.append(scene_plan)
        for shot_index, source_shot in enumerate(_shot_source_items(source_scene), start=1):
            shot_id = str(source_shot.get("shot_id") or source_shot.get("id") or f"{scene_id}:shot-{shot_index}")
            camera = _obj(source_shot.get("camera")) or {"angle": "eye_level", "distance": "medium", "speed": "slow"}
            composition = _obj(source_shot.get("composition"))
            shot = ShotPlanPayload(
                shot_id=shot_id,
                shot_type=str(source_shot.get("shot_type") or source_shot.get("shot_size") or "medium"),
                camera=camera,
                lens=str(source_shot.get("lens") or camera.get("lens") or "35mm"),
                movement=str(source_shot.get("movement") or camera.get("movement") or "static"),
                composition=composition,
                emotion=str(source_shot.get("emotion") or source_shot.get("emotion_arc") or ""),
                action=str(source_shot.get("action") or source_shot.get("action_process") or ""),
                source_lineage={**scene_lineage, "source_shot_id": shot_id},
            ).model_dump()
            shot_plans.append(shot)
            direction = {
                "shot_id": shot_id,
                "shot_type": shot["shot_type"],
                "camera_profile": {**shot["camera"], "lens": shot["lens"], "distance": shot["camera"].get("distance", "medium"), "angle": shot["camera"].get("angle", "eye_level"), "movement": shot["movement"], "speed": shot["camera"].get("speed", "slow")},
                "movement_profile": {"movement": shot["movement"]},
                "composition_profile": shot["composition"],
                "performance_profile": {"action": shot["action"]},
                "emotion_profile": {"emotion": shot["emotion"]},
                "direction_fingerprint": _hash({"shot_id": shot_id, "shot": shot}),
                "source_lineage": {**scene_lineage, "source_shot_id": shot_id, "authority": "ShotDirection"},
            }
            shot_directions.append(direction)
            intent_id = _hash({"episode_id": episode_id, "shot_id": shot_id, "source_script_ir_hash": source_script_hash})
            intents.append(GenerationIntentPayload(
                generation_intent_id=intent_id,
                shot_id=shot_id,
                character_requirements={"characters": scene_plan["characters"]},
                scene_requirements={"scene_id": scene_id, "location": scene_plan["location"], "time": scene_plan["time"], "mood": scene_plan["mood"]},
                camera_requirements={"camera": shot["camera"], "lens": shot["lens"], "movement": shot["movement"]},
                style_requirements=_obj(profile.get("style_requirements")),
                constraint_snapshot={"source_fact_immutable": True, "script_ir_immutable": True, "human_review_required": True},
                source_lineage={"source_script_ir_hash": source_script_hash, "scene_id": scene_id, "shot_id": shot_id, "prompt_lineage_id": _hash({"shot_id": shot_id, "intent_id": intent_id})},
            ).model_dump())
    reasoning = {"mode": "deterministic_adapter", "provider": None, "llm_called": False, "llm_generated": False, "human_review_required": True, "source_fact_mutated": False}
    lineage = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "source_script_ir_hash": source_script_hash,
        "source_fact_mutated": False,
        "script_ir_mutated": False,
    }
    for key in ("book_id", "source_script_ir_version_id", "source_script_ir_hash"):
        if context.get(key) not in {None, ""}:
            lineage[key] = context[key]
    payload = DirectorPlanPayload(
        episode_id=episode_id,
        reasoning_trace=reasoning,
        scene_plans=scene_plans,
        shot_plans=shot_plans,
        shot_directions=shot_directions,
        generation_intents=intents,
        lineage=lineage,
    ).model_dump()
    payload["payload_hash"] = _hash(payload)
    return payload


def _json(value: Any) -> str:
    return _canonical(value)


def _row_payload(row: DirectorPlan) -> dict[str, Any]:
    return {
        "id": row.id, "episode_id": row.episode_id, "version": row.version, "status": row.status,
        "created_by": row.created_by, "reasoning_trace": _obj(row.reasoning_trace),
        "scene_plans": _list(row.scene_plans), "shot_plans": _list(row.shot_plans),
        "shot_directions": _list(row.shot_directions),
        "generation_intents": _list(row.generation_intents), "payload_hash": row.payload_hash,
        "lineage": _obj(row.lineage_json), "source_script_ir_version_id": row.source_script_ir_version_id,
        "source_script_ir_hash": row.source_script_ir_hash, "source_fact_snapshot_hash": row.source_fact_snapshot_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def persist_director_plan(session: Any, payload: Mapping[str, Any], *, created_by: str = "director-runtime", source_script_ir_version_id: int | None = None, source_fact_snapshot_hash: str = "") -> dict[str, Any]:
    candidate_input = dict(payload)
    # ``payload_hash`` is an envelope field computed by the runtime rather
    # than part of the user-editable DirectorPlan schema.
    candidate_input.pop("payload_hash", None)
    candidate = DirectorPlanPayload.model_validate(candidate_input)
    episode_id = candidate.episode_id
    latest = session.query(DirectorPlan).filter_by(episode_id=episode_id).order_by(desc(DirectorPlan.version)).first()
    version = (int(latest.version) + 1) if latest else 1
    data = candidate.model_dump()
    lineage = {**data.get("lineage", {})}
    canonical_source_id = source_script_ir_version_id or lineage.get("source_script_ir_version_id")
    source_ir = None
    if canonical_source_id not in {None, ""}:
        try:
            source_ir = session.get(ScriptIRVersion, int(canonical_source_id))
        except (TypeError, ValueError):
            source_ir = None
        if source_ir is None:
            raise ValueError("source_script_ir_version_id does not resolve to ScriptIRVersion")
        canonical_source_id = int(source_ir.id)
        lineage["book_id"] = int(source_ir.book_id)
        lineage["source_script_ir_version_id"] = canonical_source_id
        lineage["source_script_ir_hash"] = str(source_ir.payload_hash or "")
    elif lineage.get("book_id") not in {None, ""}:
        try:
            lineage["book_id"] = int(lineage["book_id"])
        except (TypeError, ValueError):
            raise ValueError("lineage.book_id must be an integer")
    data["version"] = version
    data["created_by"] = created_by or candidate.created_by
    data["lineage"] = {**lineage, "director_plan_version": version, "human_review_required": True}
    data["payload_hash"] = _hash(data)
    if latest is not None and latest.status not in {"SUPERSEDED", "REJECTED"}:
        latest.status = "SUPERSEDED"
    row = DirectorPlan(
        episode_id=episode_id, version=version, status=data["status"], created_by=data["created_by"],
        reasoning_trace=_json(data["reasoning_trace"]), scene_plans=_json(data["scene_plans"]), shot_plans=_json(data["shot_plans"]), shot_directions=_json(data["shot_directions"]),
        generation_intents=_json(data["generation_intents"]), source_script_ir_version_id=canonical_source_id,
        source_script_ir_hash=str(data["lineage"].get("source_script_ir_hash") or ""), source_fact_snapshot_hash=source_fact_snapshot_hash,
        source_immutable_raw_hash=str(data["lineage"].get("source_immutable_raw_hash") or ""), payload_hash=data["payload_hash"], lineage_json=_json(data["lineage"]),
    )
    session.add(row)
    session.flush()
    for scene in data["scene_plans"]:
        session.add(ScenePlan(director_plan_id=row.id, episode_id=episode_id, version=version, scene_id=scene["scene_id"], location=scene["location"], time=scene["time"], mood=scene["mood"], characters=_json(scene["characters"]), visual_requirements=_json(scene["visual_requirements"]), source_lineage=_json(scene["source_lineage"]), payload_hash=_hash(scene)))
    return _row_payload(row)


def get_director_plan(session: Any, episode_id: str, version: int | None = None) -> dict[str, Any] | None:
    query = session.query(DirectorPlan).filter_by(episode_id=str(episode_id))
    row = query.filter_by(version=int(version)).one_or_none() if version is not None else query.order_by(desc(DirectorPlan.version)).first()
    return _row_payload(row) if row else None


def revise_shot(session: Any, shot_id: str, patch: Mapping[str, Any], *, created_by: str = "human-review") -> dict[str, Any]:
    rows = session.query(DirectorPlan).order_by(desc(DirectorPlan.version)).all()
    for row in rows:
        shots = _list(row.shot_plans)
        for index, shot in enumerate(shots):
            if str(shot.get("shot_id")) != str(shot_id):
                continue
            allowed = {"shot_type", "camera", "lens", "movement", "composition", "emotion", "action"}
            unknown = set(patch) - allowed
            if unknown:
                raise ValueError("shot revision contains non-whitelisted fields: " + ", ".join(sorted(unknown)))
            revised = {**shot, **{key: deepcopy(value) for key, value in patch.items()}}
            revised["source_lineage"] = {**_obj(revised.get("source_lineage")), "revised_by": created_by, "parent_director_plan_id": row.id, "parent_version": row.version}
            shots[index] = revised
            directions = _list(row.shot_directions)
            for direction in directions:
                if str(direction.get("shot_id")) == str(shot_id):
                    direction["source_lineage"] = {**_obj(direction.get("source_lineage")), "revised_by": created_by, "parent_director_plan_id": row.id, "parent_version": row.version}
            payload = {"episode_id": row.episode_id, "status": "DRAFT", "created_by": created_by, "reasoning_trace": {"mode": "human_revision", "llm_called": False, "source_fact_mutated": False}, "scene_plans": _list(row.scene_plans), "shot_plans": shots, "shot_directions": directions, "generation_intents": _list(row.generation_intents), "lineage": {**_obj(row.lineage_json), "revision_of": {"id": row.id, "version": row.version}, "human_review_required": True}}
            return persist_director_plan(session, payload, created_by=created_by, source_script_ir_version_id=row.source_script_ir_version_id, source_fact_snapshot_hash=row.source_fact_snapshot_hash)
    raise ValueError("shot does not exist in a DirectorPlan")


__all__ = ["DirectorPlanPayload", "ScenePlanPayload", "ShotPlanPayload", "GenerationIntentPayload", "director_plan", "persist_director_plan", "get_director_plan", "revise_shot", "RUNTIME_SCHEMA_VERSION"]
