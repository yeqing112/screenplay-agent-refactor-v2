"""Provider-free DirectorReasoningIR and fail-closed ShotPlan compiler."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc

from models import DirectorReasoning, ScenePlan, ShotPlan, StoryBeat, VisualDecision


REASONING_SCHEMA_VERSION = "director_reasoning_ir_v1"


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


class StoryBeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int = Field(ge=1)
    scene_id: str = Field(min_length=1)
    purpose: str = ""
    emotion: str = ""
    visual_goal: str = ""
    character_refs: list[str] = Field(default_factory=list)
    shot_refs: list[str] = Field(default_factory=list)


class VisualDecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    story_beat_sequence: int = Field(ge=1)
    visual_style_id: str = Field(min_length=1)
    camera_strategy: str = ""
    lighting_strategy: str = ""
    color_strategy: str = ""
    composition_strategy: str = ""


class DirectorReasoningPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    status: str = "DRAFT"
    reasoning_trace: dict[str, Any] = Field(default_factory=dict)
    beats: list[StoryBeatPayload] = Field(default_factory=list)
    visual_decisions: list[VisualDecisionPayload] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        normalized = str(value or "DRAFT").upper()
        if normalized not in {"DRAFT", "REVIEW_REQUIRED", "COMPILED", "SUPERSEDED", "ROLLED_BACK", "REJECTED"}:
            raise ValueError("invalid director reasoning status")
        return normalized


class DirectorReasoningCompileError(ValueError):
    code = "DIRECTOR_REASONING_COMPILE_BLOCKED"

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


def _refs(source: Any, keys: tuple[str, ...]) -> list[str]:
    values: list[Any] = []
    if isinstance(source, list):
        values = source
    elif isinstance(source, Mapping):
        for key in keys:
            if isinstance(source.get(key), list):
                values = source[key]
                break
    result = []
    for item in values:
        if isinstance(item, Mapping):
            result.append(str(item.get("id") or item.get("character_id") or item.get("shot_id") or item.get("plan_shot_id") or item.get("name") or ""))
        elif str(item).strip():
            result.append(str(item))
    return [item for item in result if item]


def _all_character_ids(episode_context: Mapping[str, Any], script_ir: Mapping[str, Any], scene_context: Mapping[str, Any]) -> set[str]:
    values: list[Any] = []
    for source in (episode_context, script_ir, scene_context):
        for key in ("character_profiles", "characters", "character_ids"):
            if isinstance(source.get(key), list):
                values.extend(source[key])
    result = set()
    for item in values:
        if isinstance(item, Mapping):
            value = item.get("character_id") or item.get("id") or item.get("key") or item.get("name")
        else:
            value = item
        if str(value or "").strip():
            result.add(str(value))
    return result


def _all_style_ids(episode_context: Mapping[str, Any], scene_context: Mapping[str, Any]) -> set[str]:
    values: list[Any] = []
    for source in (episode_context, scene_context):
        for key in ("visual_style_profiles", "visual_styles", "style_profiles"):
            if isinstance(source.get(key), list):
                values.extend(source[key])
    result = set()
    for item in values:
        value = item.get("visual_style_id") or item.get("style_id") or item.get("id") or item.get("key") if isinstance(item, Mapping) else item
        if str(value or "").strip():
            result.add(str(value))
    return result


def _all_shot_ids(scenes: list[dict[str, Any]]) -> set[str]:
    result = set()
    for scene in scenes:
        for key in ("shots", "shot_plans", "coverage"):
            values = scene.get(key)
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, Mapping):
                        value = item.get("shot_id") or item.get("id") or item.get("plan_shot_id")
                    else:
                        value = item
                    if str(value or "").strip():
                        result.add(str(value))
    return result


def director_reason(episode_context: Mapping[str, Any] | None, script_ir: Mapping[str, Any] | None, scene_context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic DirectorReasoningIR candidate without an LLM."""
    episode = deepcopy(dict(episode_context or {}))
    script = deepcopy(dict(script_ir or {}))
    scenes_context = deepcopy(dict(scene_context or {}))
    episode_id = str(episode.get("episode_id") or episode.get("id") or script.get("episode_id") or script.get("episode") or "episode-unknown")
    scenes = _scene_items(script, scenes_context)
    source_hash = str(episode.get("source_script_ir_hash") or _hash(script))
    supplied_beats = scenes_context.get("beats") if isinstance(scenes_context.get("beats"), list) else script.get("beats")
    beats: list[dict[str, Any]] = []
    if isinstance(supplied_beats, list) and supplied_beats:
        for index, source in enumerate(supplied_beats, start=1):
            if not isinstance(source, Mapping):
                continue
            scene_id = str(source.get("scene_id") or source.get("scene") or "")
            beats.append(StoryBeatPayload(sequence=int(source.get("sequence") or index), scene_id=scene_id, purpose=str(source.get("purpose") or ""), emotion=str(source.get("emotion") or ""), visual_goal=str(source.get("visual_goal") or ""), character_refs=[str(x) for x in _refs(source, ("character_refs", "characters", "character_ids"))], shot_refs=[str(x) for x in _refs(source, ("shot_refs", "shots", "shot_ids"))]).model_dump())
    else:
        for index, scene in enumerate(scenes, start=1):
            scene_id = _scene_id(scene)
            beats.append(StoryBeatPayload(sequence=index, scene_id=scene_id, purpose=str(scene.get("purpose") or scene.get("dramatic_objective") or ""), emotion=str(scene.get("emotion") or scene.get("mood") or ""), visual_goal=str(scene.get("visual_goal") or scene.get("visual_requirements") or ""), character_refs=[str(x) for x in _refs(scene, ("character_refs", "characters", "participants"))], shot_refs=[str(x) for x in _refs(scene, ("shot_refs", "shots", "shot_plans", "coverage"))]).model_dump())
    style_ids = sorted(_all_style_ids(episode, scenes_context))
    visual_decisions = []
    for beat in beats:
        source_decision = next((item for item in scenes_context.get("visual_decisions", []) if isinstance(item, Mapping) and int(item.get("story_beat_sequence") or item.get("sequence") or 0) == beat["sequence"]), {}) if isinstance(scenes_context.get("visual_decisions"), list) else {}
        visual_decisions.append(VisualDecisionPayload(story_beat_sequence=beat["sequence"], visual_style_id=str(source_decision.get("visual_style_id") or source_decision.get("style_id") or (style_ids[0] if style_ids else "")), camera_strategy=str(source_decision.get("camera_strategy") or ""), lighting_strategy=str(source_decision.get("lighting_strategy") or ""), color_strategy=str(source_decision.get("color_strategy") or ""), composition_strategy=str(source_decision.get("composition_strategy") or "")).model_dump())
    payload = DirectorReasoningPayload(episode_id=episode_id, reasoning_trace={"mode": "deterministic_adapter", "provider": None, "llm_called": False, "human_review_required": True, "source_fact_mutated": False, "script_ir_mutated": False}, beats=beats, visual_decisions=visual_decisions, lineage={"schema_version": REASONING_SCHEMA_VERSION, "source_script_ir_hash": source_hash, "source_fact_mutated": False, "script_ir_mutated": False}).model_dump()
    payload["payload_hash"] = _hash(payload)
    return payload


def validate_reasoning_for_compile(reasoning: Mapping[str, Any], *, episode_context: Mapping[str, Any], script_ir: Mapping[str, Any], scene_context: Mapping[str, Any]) -> dict[str, Any]:
    candidate_input = dict(reasoning)
    candidate_input.pop("payload_hash", None)
    try:
        candidate = DirectorReasoningPayload.model_validate(candidate_input)
    except Exception as exc:
        raise DirectorReasoningCompileError("DirectorReasoningIR schema validation failed", [{"code": "REASONING_SCHEMA_INVALID", "message": str(exc)}]) from exc
    diagnostics: list[dict[str, Any]] = []
    beats = sorted(candidate.beats, key=lambda beat: beat.sequence)
    expected = list(range(1, len(beats) + 1))
    actual = [beat.sequence for beat in beats]
    if actual != expected:
        diagnostics.append({"code": "BEAT_ORDER_INVALID", "expected": expected, "actual": actual})
    scenes = _scene_items(script_ir, scene_context)
    scene_ids = {_scene_id(scene) for scene in scenes if _scene_id(scene)}
    for beat in beats:
        if beat.scene_id not in scene_ids:
            diagnostics.append({"code": "SCENE_NOT_FOUND", "sequence": beat.sequence, "scene_id": beat.scene_id})
    character_ids = _all_character_ids(episode_context, script_ir, scene_context)
    for beat in beats:
        for ref in beat.character_refs:
            if ref not in character_ids:
                diagnostics.append({"code": "CHARACTER_NOT_FOUND", "sequence": beat.sequence, "character_id": ref})
    style_ids = _all_style_ids(episode_context, scene_context)
    if not style_ids:
        diagnostics.append({"code": "VISUAL_STYLE_MISSING", "message": "No VisualStyleProfile is available for compile."})
    for decision in candidate.visual_decisions:
        if decision.story_beat_sequence not in actual:
            diagnostics.append({"code": "VISUAL_DECISION_BEAT_INVALID", "sequence": decision.story_beat_sequence})
        if decision.visual_style_id not in style_ids:
            diagnostics.append({"code": "VISUAL_STYLE_NOT_FOUND", "sequence": decision.story_beat_sequence, "visual_style_id": decision.visual_style_id})
    shot_ids = _all_shot_ids(scenes)
    for beat in beats:
        for ref in beat.shot_refs:
            if ref not in shot_ids:
                diagnostics.append({"code": "SHOT_REFERENCE_INVALID", "sequence": beat.sequence, "shot_id": ref})
    decision_sequences = [item.story_beat_sequence for item in candidate.visual_decisions]
    if decision_sequences != actual:
        diagnostics.append({"code": "VISUAL_DECISION_ORDER_INVALID", "expected": actual, "actual": decision_sequences})
    if diagnostics:
        raise DirectorReasoningCompileError("DirectorReasoningIR compile validation failed", diagnostics)
    return {"status": "PASS", "episode_id": candidate.episode_id, "beat_count": len(beats), "scene_ids": sorted(scene_ids), "character_ids": sorted(character_ids), "visual_style_ids": sorted(style_ids), "shot_ids": sorted(shot_ids), "checks": {"beat_order": True, "scene_exists": True, "character_exists": True, "visual_style_exists": True, "shot_references_legal": True}}


def _row_payload(row: DirectorReasoning) -> dict[str, Any]:
    payload = _obj(row.reasoning_json)
    payload.update({"id": row.id, "episode_id": row.episode_id, "version": row.version, "status": row.status, "payload_hash": row.payload_hash, "compiled_shot_plan_ids": _list(row.compiled_shot_plan_ids), "lineage": _obj(row.lineage_json), "source_script_ir_hash": row.source_script_ir_hash, "source_fact_snapshot_hash": row.source_fact_snapshot_hash, "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None})
    return payload


def persist_reasoning(session: Any, payload: Mapping[str, Any], *, source_fact_snapshot_hash: str = "") -> dict[str, Any]:
    candidate_input = dict(payload)
    candidate_input.pop("payload_hash", None)
    candidate = DirectorReasoningPayload.model_validate(candidate_input)
    latest = session.query(DirectorReasoning).filter_by(episode_id=candidate.episode_id).order_by(desc(DirectorReasoning.version)).first()
    version = int(latest.version) + 1 if latest else 1
    data = candidate.model_dump()
    data["version"] = version
    data["lineage"] = {**data.get("lineage", {}), "director_reasoning_version": version, "human_review_required": True}
    data["payload_hash"] = _hash(data)
    if latest is not None and latest.status not in {"SUPERSEDED", "REJECTED", "ROLLED_BACK"}:
        latest.status = "SUPERSEDED"
    row_status = candidate.status if candidate.status in {"DRAFT", "REVIEW_REQUIRED", "COMPILED", "SUPERSEDED", "ROLLED_BACK", "REJECTED"} else "DRAFT"
    row = DirectorReasoning(episode_id=candidate.episode_id, version=version, status=row_status, reasoning_json=_canonical({**data, "version": version, "status": row_status}), source_script_ir_hash=str(data["lineage"].get("source_script_ir_hash") or ""), source_fact_snapshot_hash=source_fact_snapshot_hash, payload_hash=data["payload_hash"], lineage_json=_canonical(data["lineage"]))
    session.add(row)
    session.flush()
    for beat in data["beats"]:
        session.add(StoryBeat(director_reasoning_id=row.id, sequence=beat["sequence"], scene_id=beat["scene_id"], purpose=beat["purpose"], emotion=beat["emotion"], visual_goal=beat["visual_goal"], character_refs=_canonical(beat["character_refs"]), shot_refs=_canonical(beat["shot_refs"])))
    for decision in data["visual_decisions"]:
        session.add(VisualDecision(director_reasoning_id=row.id, story_beat_sequence=decision["story_beat_sequence"], visual_style_id=decision["visual_style_id"], camera_strategy=decision["camera_strategy"], lighting_strategy=decision["lighting_strategy"], color_strategy=decision["color_strategy"], composition_strategy=decision["composition_strategy"]))
    return _row_payload(row)


def get_reasoning(session: Any, episode_id: str, version: int | None = None) -> dict[str, Any] | None:
    query = session.query(DirectorReasoning).filter_by(episode_id=str(episode_id))
    row = query.filter_by(version=int(version)).one_or_none() if version is not None else query.order_by(desc(DirectorReasoning.version)).first()
    return _row_payload(row) if row else None


def compile_reasoning(session: Any, row: DirectorReasoning, *, episode_context: Mapping[str, Any], script_ir: Mapping[str, Any], scene_context: Mapping[str, Any], book_id: int = 0, episode_number: int = 0) -> dict[str, Any]:
    payload = _obj(row.reasoning_json)
    validation = validate_reasoning_for_compile(payload, episode_context=episode_context, script_ir=script_ir, scene_context=scene_context)
    beats = [StoryBeatPayload.model_validate(item) for item in payload.get("beats", [])]
    decisions = {decision.story_beat_sequence: decision for decision in (VisualDecisionPayload.model_validate(item) for item in payload.get("visual_decisions", []))}
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    intent_candidates: list[dict[str, Any]] = []
    prompt_candidates: list[dict[str, Any]] = []
    for beat in beats:
        decision = decisions[beat.sequence]
        for ref in beat.shot_refs:
            prompt_version_id = f"reasoning-{row.id}-v{row.version}-{ref}-prompt-v1"
            intent_id = _hash({"reasoning_id": row.id, "reasoning_version": row.version, "shot_id": ref})
            lineage = {"director_reasoning_id": row.id, "director_reasoning_version": row.version, "story_beat_sequence": beat.sequence, "shot_id": ref, "prompt_version_id": prompt_version_id}
            by_scene[beat.scene_id].append({"plan_shot_id": ref, "shot_id": ref, "shot_type": "medium", "camera": {"strategy": decision.camera_strategy}, "lighting": decision.lighting_strategy, "color": decision.color_strategy, "composition": decision.composition_strategy, "emotion": beat.emotion, "action": beat.purpose, "director_reasoning_id": row.id, "director_reasoning_version": row.version, "reasoning_lineage": lineage})
            prompt_candidates.append({"prompt_version_id": prompt_version_id, "prompt_id": f"shot-{ref}-reasoning", "version_number": 1, "created_from": "DIRECTOR_REASONING", "prompt_fingerprint": _hash({"intent_id": intent_id, "visual_goal": beat.visual_goal})})
            intent_candidates.append({"generation_intent_id": intent_id, "shot_id": ref, "director_reasoning_id": row.id, "director_reasoning_version": row.version, "prompt_version_id": prompt_version_id, "reasoning_lineage": lineage})
    shot_plan_ids: list[int] = []
    now_rows: list[dict[str, Any]] = []
    for scene_id, shots in by_scene.items():
        scene_name = next((_scene_id(scene) and str(scene.get("scene_name") or scene.get("name") or scene_id) for scene in _scene_items(script_ir, scene_context) if _scene_id(scene) == scene_id), scene_id)
        row_plan = ShotPlan(book_id=int(book_id or 0), episode=int(episode_number or episode_context.get("episode") or 0), scene_id=scene_id, scene_name=scene_name, revision=1, status="draft", quality_status="reasoning_candidate", production_status="blocked", workflow_profile="creative_draft", shots=_canonical(shots), unknowns="[]", director_reasoning_id=row.id, director_reasoning_version=row.version, reasoning_lineage=_canonical({"director_reasoning_id": row.id, "director_reasoning_version": row.version, "story_beats": [beat.sequence for beat in beats if beat.scene_id == scene_id], "generation_intents": [item["generation_intent_id"] for item in intent_candidates]}))
        session.add(row_plan)
        session.flush()
        shot_plan_ids.append(int(row_plan.id))
        now_rows.append({"id": row_plan.id, "scene_id": scene_id, "shots": shots, "director_reasoning_id": row.id, "director_reasoning_version": row.version, "reasoning_lineage": _obj(row_plan.reasoning_lineage)})
    row.status = "COMPILED"
    row.compiled_shot_plan_ids = _canonical(shot_plan_ids)
    row.updated_at = __import__("datetime").datetime.utcnow()
    return {"status": "COMPILED", "validation": validation, "director_reasoning": _row_payload(row), "shot_plans": now_rows, "generation_intents": intent_candidates, "prompt_versions": prompt_candidates, "lineage": {"director_reasoning_id": row.id, "director_reasoning_version": row.version, "shot_plan_ids": shot_plan_ids, "generation_intent_ids": [item["generation_intent_id"] for item in intent_candidates], "prompt_version_ids": [item["prompt_version_id"] for item in prompt_candidates], "human_review_required": True}}


def rollback_reasoning(session: Any, episode_id: str, version: int) -> dict[str, Any]:
    row = session.query(DirectorReasoning).filter_by(episode_id=str(episode_id), version=int(version)).one_or_none()
    if row is None:
        raise DirectorReasoningCompileError("DirectorReasoning version does not exist", [{"code": "DIRECTOR_REASONING_NOT_FOUND", "episode_id": str(episode_id), "version": version}])
    plan_ids = [int(item) for item in _list(row.compiled_shot_plan_ids) if str(item).isdigit()]
    plans = session.query(ShotPlan).filter(ShotPlan.id.in_(plan_ids)).all() if plan_ids else []
    for plan in plans:
        if plan.status == "draft":
            plan.status = "superseded"
            plan.production_status = "blocked"
            plan.reasoning_lineage = _canonical({**_obj(plan.reasoning_lineage), "rolled_back": True, "rolled_back_reasoning_id": row.id, "rolled_back_reasoning_version": row.version})
    row.status = "ROLLED_BACK"
    return {"status": "ROLLED_BACK", "episode_id": row.episode_id, "version": row.version, "shot_plan_ids": plan_ids, "preserved": True}


__all__ = ["DirectorReasoningPayload", "StoryBeatPayload", "VisualDecisionPayload", "DirectorReasoningCompileError", "director_reason", "validate_reasoning_for_compile", "persist_reasoning", "get_reasoning", "compile_reasoning", "rollback_reasoning", "REASONING_SCHEMA_VERSION"]
