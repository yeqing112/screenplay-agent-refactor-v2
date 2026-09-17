"""Semantic registry for fact requirements and authoring boundaries.

The registry is the single source of truth for what a requirement means, who
may establish it, and at which production stage it becomes blocking.  It is
deliberately provider-free: an LLM may propose evidence or an authoring
decision, but this module never treats confidence as authority.
"""
from __future__ import annotations

import copy
from typing import Any

from core.fact_coverage import fingerprint

AUTHORITY_CLASSES = (
    "SOURCE_FACT",
    "DERIVED_SOURCE_FACT",
    "PRODUCTION_AUTHORING_DECISION",
    "PRODUCTION_CONTINUITY_STATE",
)

STAGES = (
    "SCRIPT_IR",
    "DIRECTOR_TREATMENT",
    "SCENE_BLOCKING",
    "VISUAL_ASSET_GENERATION",
    "SHOT_PLAN",
    "STORYBOARD",
    "VIDEO_GENERATION",
)

_STAGE_INDEX = {stage: index for index, stage in enumerate(STAGES)}


def _entry(
    *,
    predicate: str,
    requirement_type: str,
    description: str,
    value_schema: dict[str, Any],
    scope_type: str,
    authority_class: str,
    resolution_policy: str,
    blocking_stage: str,
    retrieval_semantics: dict[str, Any],
    provider_instruction: str,
    validation_policy: dict[str, Any],
    authoring_fallback: str,
) -> dict[str, Any]:
    return {
        "requirement_type": requirement_type,
        "predicate": predicate,
        "description": description,
        "value_schema": value_schema,
        "scope_type": scope_type,
        "authority_class": authority_class,
        "resolution_policy": resolution_policy,
        "blocking_stage": blocking_stage,
        "retrieval_semantics": retrieval_semantics,
        "provider_instruction": provider_instruction,
        "validation_policy": validation_policy,
        "authoring_fallback": authoring_fallback,
    }


_REGISTRY: dict[str, dict[str, Any]] = {
    "visual_identity": _entry(
        predicate="visual_identity",
        requirement_type="CHARACTER_IDENTITY",
        description="Structured physical appearance used to keep a character visually identifiable.",
        value_schema={"type": "object", "properties": {"age": {}, "gender_presentation": {}, "hair": {}, "wardrobe": {}, "persistent_features": {}}, "additionalProperties": True},
        scope_type="entity",
        authority_class="PRODUCTION_AUTHORING_DECISION",
        resolution_policy="source_constraints_then_authoring_decision",
        blocking_stage="VISUAL_ASSET_GENERATION",
        retrieval_semantics={"aliases": ["character", "人物", "角色"], "terms": ["外貌", "年龄", "性别", "发型", "头发", "服装", "穿着", "脸", "特征", "appearance", "age", "hair", "wardrobe", "features"], "source_surfaces": ["narrative", "dialogue", "character_description"]},
        provider_instruction="Only return explicit physical-appearance evidence; a name, action, or occupation is not visual identity.",
        validation_policy={"direct_evidence_required": True, "allow_inference": False, "reject_name_only": True},
        authoring_fallback="AUTHORING_DECISION_REQUIRED",
    ),
    "current_state": _entry(
        predicate="current_state",
        requirement_type="CONFLICT_STATE",
        description="A time-local state of an entity at an episode, scene, beat, or source range.",
        value_schema={"type": ["string", "object", "array"]},
        scope_type="episode_scene_beat",
        authority_class="PRODUCTION_CONTINUITY_STATE",
        resolution_policy="source_fact_or_derived_state_with_explicit_scope",
        blocking_stage="SCENE_BLOCKING",
        retrieval_semantics={"aliases": ["state", "当前状态", "此时", "当下"], "terms": ["正在", "变得", "处于", "受伤", "疲惫", "害怕", "拿着", "打开", "离开", "in", "state", "currently", "while"], "source_surfaces": ["narrative", "action", "dialogue"]},
        provider_instruction="Distinguish a directly stated state from an inferred or continuity state and preserve the narrowest supported scope.",
        validation_policy={"direct_evidence_required": False, "allow_inference": True, "require_scope": True},
        authoring_fallback="CONTINUITY_STATE_INITIALIZATION_REQUIRED",
    ),
    "geometry": _entry(
        predicate="geometry",
        requirement_type="LOCATION_IDENTITY",
        description="Spatial constraints explicitly stated by the source; complete production layout is authored later.",
        value_schema={"type": "object", "properties": {"relations": {"type": "array"}, "dimensions": {}, "surfaces": {}}},
        scope_type="scene",
        authority_class="PRODUCTION_AUTHORING_DECISION",
        resolution_policy="source_spatial_constraints_then_scene_authoring",
        blocking_stage="SCENE_BLOCKING",
        retrieval_semantics={"aliases": ["scene", "location", "空间", "地点", "场景"], "terms": ["门", "窗", "墙", "楼梯", "入口", "走廊", "房间", "左边", "右边", "对面", "狭窄", "宽敞", "layout", "spatial", "room", "door", "window", "wall", "left", "right"], "source_surfaces": ["scene_heading", "environment", "narrative"]},
        provider_instruction="Return only explicit spatial relations or constraints; do not invent dimensions, unseen walls, or camera positions.",
        validation_policy={"direct_evidence_required": False, "allow_inference": False, "production_layout_is_authoring": True},
        authoring_fallback="AUTHORING_DECISION_REQUIRED",
    ),
    "state": _entry(
        predicate="state",
        requirement_type="OBJECT_STATE",
        description="The state or location of an object, scoped to the source moment or production continuity interval.",
        value_schema={"type": ["string", "object"]},
        scope_type="scene_beat_shot",
        authority_class="PRODUCTION_CONTINUITY_STATE",
        resolution_policy="source_object_fact_then_shot_continuity",
        blocking_stage="SHOT_PLAN",
        retrieval_semantics={"aliases": ["object", "prop", "道具", "物件"], "terms": ["拿起", "放下", "放在", "位于", "手里", "桌上", "门口", "打开", "关闭", "掉落", "holding", "placed", "located", "open", "closed"], "source_surfaces": ["narrative", "action", "continuity"]},
        provider_instruction="Return an object state only when the source anchors it; distinguish source state from later shot continuity.",
        validation_policy={"direct_evidence_required": False, "allow_inference": True, "require_scope": True},
        authoring_fallback="CONTINUITY_STATE_INITIALIZATION_REQUIRED",
    ),
}

_DEFAULT = _entry(
    predicate="*",
    requirement_type="EVENT_OCCURRENCE",
    description="A source-grounded story fact required by the current stage.",
    value_schema={"type": ["string", "number", "boolean", "object", "array", "null"]},
    scope_type="declared",
    authority_class="SOURCE_FACT",
    resolution_policy="explicit_source_evidence_or_fail_closed",
    blocking_stage="SCRIPT_IR",
    retrieval_semantics={"aliases": [], "terms": [], "source_surfaces": ["narrative", "dialogue", "action"]},
    provider_instruction="Return only a fact explicitly supported by supplied source anchors.",
    validation_policy={"direct_evidence_required": True, "allow_inference": False},
    authoring_fallback="NONE",
)


def get_requirement_semantics(predicate: str | None, *, requirement: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a defensive copy of the semantic definition for one predicate.

    ``source_required``/``authority_class`` are explicit authoring controls,
    not fixture-specific exceptions.  They let a product workflow require a
    source fact when a domain genuinely needs one while keeping production
    decisions out of the source extractor by default.
    """
    key = str(predicate or "").strip().lower()
    value = copy.deepcopy(_REGISTRY.get(key, _DEFAULT))
    if requirement:
        explicit_class = str(requirement.get("authority_class") or "").strip()
        if explicit_class in AUTHORITY_CLASSES:
            value["authority_class"] = explicit_class
        if bool(requirement.get("source_required")):
            value["authority_class"] = "SOURCE_FACT"
            value["blocking_stage"] = str(requirement.get("blocking_stage") or "SCRIPT_IR")
    return value


def registry() -> dict[str, Any]:
    rows = {key: copy.deepcopy(value) for key, value in _REGISTRY.items()}
    return {"schema_version": "fact_requirement_registry_v1", "provider_calls": 0, "predicates": rows, "default": copy.deepcopy(_DEFAULT), "fingerprint": fingerprint(rows)}


def normalize_scope(requirement: dict[str, Any], semantics: dict[str, Any]) -> tuple[str, str]:
    original = str(requirement.get("scope") or "global").strip() or "global"
    if original != "global" or semantics.get("scope_type") in {"entity", "declared"}:
        return original, original
    # Global is not a valid temporal scope for state/continuity requirements.
    fallback = {"episode_scene_beat": "episode", "scene_beat_shot": "scene", "scene": "scene"}.get(str(semantics.get("scope_type") or ""), original)
    return fallback, original


def classify_requirement(requirement: dict[str, Any]) -> dict[str, Any]:
    item = dict(requirement or {})
    semantics = get_requirement_semantics(item.get("predicate"), requirement=item)
    scope, original_scope = normalize_scope(item, semantics)
    authority = str(semantics.get("authority_class") or "SOURCE_FACT")
    stage = str(item.get("blocking_stage") or semantics.get("blocking_stage") or "SCRIPT_IR")
    if stage not in _STAGE_INDEX:
        stage = "SCRIPT_IR"
    gate_eligible = authority in {"SOURCE_FACT", "DERIVED_SOURCE_FACT"} and _STAGE_INDEX[stage] <= _STAGE_INDEX["SCRIPT_IR"]
    return {
        **item,
        "predicate": str(item.get("predicate") or ""),
        "scope": scope,
        "original_scope": original_scope,
        "authority_class": authority,
        "blocking_stage": stage,
        "scope_type": semantics.get("scope_type"),
        "requirement_semantics": semantics,
        "gate_eligible": gate_eligible,
        "authoring_required": not gate_eligible,
    }


def build_authoring_decision_request(requirement: dict[str, Any], *, source_evidence_refs: list[str] | None = None, locked_source_constraints: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    classified = classify_requirement(requirement)
    semantics = classified["requirement_semantics"]
    freedom = semantics.get("value_schema", {})
    return {
        "schema_version": "authoring_decision_request_v1",
        "decision_key": str(classified.get("fact_key") or ""),
        "decision_type": str(classified.get("predicate") or classified.get("requirement_type") or "authoring"),
        "subject": {"type": str(classified.get("subject_type") or classified.get("semantic_type") or ""), "id": str(classified.get("subject_id") or classified.get("entity") or "")},
        "scope": str(classified.get("scope") or "episode"),
        "required_by_stage": str(classified.get("blocking_stage") or "SCENE_BLOCKING"),
        "authority_class": str(classified.get("authority_class") or "PRODUCTION_AUTHORING_DECISION"),
        "locked_source_constraints": copy.deepcopy(locked_source_constraints or []),
        "source_evidence_refs": [str(ref) for ref in (source_evidence_refs or []) if str(ref).strip()],
        "freedom_dimensions": copy.deepcopy(freedom),
        "prohibited_conflicts": ["Do not contradict locked source constraints", "Do not be treated as source_text authority"],
        "suggested_generation_policy": str(semantics.get("authoring_fallback") or "AUTHORING_DECISION_REQUIRED"),
        "status": "PENDING",
        "evidence_fingerprint": fingerprint({"requirement": classified, "source_evidence_refs": source_evidence_refs or [], "locked_source_constraints": locked_source_constraints or []}),
    }


def stage_gate_requirements(requirements: list[dict[str, Any]], stage: str = "SCRIPT_IR") -> list[dict[str, Any]]:
    target = _STAGE_INDEX.get(str(stage), _STAGE_INDEX["SCRIPT_IR"])
    rows = []
    for requirement in requirements or []:
        classified = classify_requirement(requirement)
        blocking = _STAGE_INDEX.get(classified["blocking_stage"], _STAGE_INDEX["SCRIPT_IR"])
        if classified["authority_class"] in {"SOURCE_FACT", "DERIVED_SOURCE_FACT"} and blocking <= target:
            rows.append(classified)
    return rows


__all__ = [
    "AUTHORITY_CLASSES", "STAGES", "get_requirement_semantics", "registry", "normalize_scope",
    "classify_requirement", "build_authoring_decision_request", "stage_gate_requirements",
]
