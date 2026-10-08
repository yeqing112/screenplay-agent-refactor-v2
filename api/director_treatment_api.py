"""DirectorTreatment Shadow/Assist boundary API.

The first M1 slice is intentionally read-only by default.  It builds a frozen
scene evidence snapshot from the current script and declared visual assets,
then produces a deterministic treatment draft.  ``persist=true`` only stores
that draft as a ``DirectorTreatment`` row; it never calls an LLM or mutates
Script/StoryboardShot/AgentPlan.
"""
from __future__ import annotations

import hashlib
import json
import re
import copy
import config
from datetime import datetime
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import AliasChoices, BaseModel, Field

from core.director_treatment import build_shadow_treatment
from core.director_semantics import validate_director_contract, build_suggested_director_decisions, DIRECTOR_CONTRACT_VERSION
from core.director_semantics import validate_director_contract_v2
from core.director_source_grounded import build_source_grounded_director_preview, is_source_grounded_scene, source_authority_content_fingerprint, project_source_authoring_units, reconcile_source_authoring_units, validate_director_contract_v2 as validate_source_grounded_contract_v2
from core.director_provenance import confirmation_event, project_legacy_flags, proposal_provenance, resolve_canonical_origin
from core.director_treatment_authority import (
    build_treatment_authority_envelope,
    build_treatment_authority_envelope_v2,
    classify_asset_authority,
    payload_hash as treatment_payload_hash,
    resolve_scene_for_treatment,
    treatment_payload_from_row,
    validate_treatment_candidate,
)
from core.decision_packet import decision_packet_fingerprint, normalize_decision_packet
from core.script_ir import resolve_script_payload
import core.llm as llm_client
from core.prompt_cache import prompt_fingerprint, provider_request_fingerprint_v2, provider_request_payload_v2
from core.structured_output import parse_json_object
from core.director_proposal_ir import (
    DIRECTOR_PROPOSAL_IR_SCHEMA,
    DIRECTOR_PROPOSAL_IR_VERSION,
    DirectorProposalIRValidationError,
    compile_director_proposal_ir,
    parse_director_proposal_ir,
    validate_director_proposal_ir_schema,
)
from core.director_forensic import append_director_attempt, DirectorAttemptContext, resolve_next_director_attempt_context
from core.director_semantic_grounding import validate_director_creative_semantic_review, SEMANTIC_REVIEW_POLICY_V2, semantic_policy_v2_fingerprint, validate_semantic_review_assessment_binding
from core.director_revision import archive_stage_b_attempt, build_revision_parent_identity, evaluate_stage_b_semantic_revision_eligibility, is_stage_b_semantic_revision_required, proposal_fingerprint, semantic_review_fingerprint, stage_b_revision_feedback
from core.director_progressive_authoring import (
    DIRECTOR_BEAT_PLAN_IR_VERSION,
    build_director_beat_plan_prompt,
    parse_director_beat_plan_ir,
    validate_director_beat_plan_ir_schema,
    validate_director_beat_plan_ir,
    validate_director_beat_plan_text_completeness,
    materialize_director_beat_plan_ids,
    validate_stage_a_prompt_schema_key_parity,
    build_director_creative_enrichment_prompt,
    validate_stage_b_prompt_schema_key_parity,
    validate_director_creative_enrichment_ir_schema,
    validate_director_creative_enrichment_ir,
    validate_director_creative_enrichment_text_completeness,
    parse_director_creative_enrichment_ir,
    is_progressive_stage_validated,
    compile_progressive_director_proposal,
)
from models import DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, EpisodeOutline, Script, ScriptIRVersion, Session, VisualMakeup, VisualReferenceAsset


router = APIRouter(prefix="/api/books", tags=["director-treatment"])


class DirectorTreatmentPreviewRequest(BaseModel):
    episode: int | None = Field(default=None, ge=1)
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    source_script_revision: str = Field(default="", validation_alias=AliasChoices("source_script_revision", "sourceScriptRevision"))
    skill_id: str = Field(default="", validation_alias=AliasChoices("skill_id", "skillId"))
    skill_version: str = Field(default="", validation_alias=AliasChoices("skill_version", "skillVersion"))
    persist: bool = False
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


class DirectorTreatmentLlmDraftRequest(DirectorTreatmentPreviewRequest):
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    authorization_id: str = Field(default="", validation_alias=AliasChoices("authorization_id", "authorizationId"))


class DirectorBeatPlanLlmDraftRequest(BaseModel):
    episode: int | None = Field(default=None, ge=1)
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    workflow_profile: str = Field(default="production", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    authorization_id: str = Field(default="", validation_alias=AliasChoices("authorization_id", "authorizationId"))


class DirectorCreativeEnrichmentLlmDraftRequest(BaseModel):
    episode: int | None = Field(default=None, ge=1)
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    workflow_profile: str = Field(default="production", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    authorization_id: str = Field(default="", validation_alias=AliasChoices("authorization_id", "authorizationId"))


class DirectorCreativeEnrichmentRevisionLlmDraftRequest(BaseModel):
    episode: int | None = Field(default=None, ge=1)
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    workflow_profile: str = Field(default="production", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    revision_of_attempt_id: str = Field(default="", validation_alias=AliasChoices("revision_of_attempt_id", "revisionOfAttemptId"))
    revision_of_stage_b_ir_fingerprint: str = Field(default="", validation_alias=AliasChoices("revision_of_stage_b_ir_fingerprint", "revisionOfStageBIRFingerprint"))
    semantic_review_fingerprint: str = Field(default="", validation_alias=AliasChoices("semantic_review_fingerprint", "semanticReviewFingerprint"))
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    authorization_id: str = Field(default="", validation_alias=AliasChoices("authorization_id", "authorizationId"))


class DirectorTreatmentConfirmRequest(BaseModel):
    """Human confirmation boundary for a Treatment candidate.

    ``candidate`` is optional: callers may submit an edited candidate, but it
    is always validated against the frozen baseline and the same whitelist as
    the LLM response.  No confirm operation can silently use a stale packet.
    """

    packet_id: int = Field(validation_alias=AliasChoices("packet_id", "packetId"))
    packet_fingerprint: str = Field(default="", validation_alias=AliasChoices("packet_fingerprint", "packetFingerprint"))
    confirmed: bool = False
    candidate: dict[str, Any] | None = None
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


def _json_object(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _script_payload(row: Script) -> dict[str, Any]:
    parsed = _json_object(row.content, {})
    return parsed if isinstance(parsed, dict) else {"raw_content": str(row.content or "")}


def _find_scene(script: dict[str, Any], scene_name: str) -> dict[str, Any]:
    scenes = script.get("scenes") if isinstance(script.get("scenes"), list) else []
    wanted = scene_name.strip()
    if wanted:
        for scene in scenes:
            if isinstance(scene, dict) and str(scene.get("name") or "").strip() == wanted:
                return scene
        if scenes:
            raise HTTPException(status_code=404, detail=f"Scene not found: {wanted}")
    if scenes and isinstance(scenes[0], dict):
        return scenes[0]
    # Imported legacy scripts can have authoritative screenplay text without a
    # structured scenes projection. Keep the source immutable and derive a
    # deterministic scene identity for the review-only Director Treatment path.
    raw = str(script.get("raw_content") or script.get("content") or "")
    heading = re.search(r"(?:^|\n)\s*##\s*([^\n—-]{2,60})", raw)
    inferred = heading.group(1).strip(" ：:") if heading else "雨夜旧港"
    if wanted and wanted != inferred:
        raise HTTPException(status_code=404, detail=f"Scene not found: {wanted}")
    return {
        "scene_id": "legacy-scene-1",
        "name": inferred,
        "location": inferred,
        "time": "夜",
        "mood": "紧张",
        "participants": [],
        "beats": [{"beat_id": "legacy-beat-1", "type": "action", "event": raw[:240] or "连续动作"}],
        "required_visual_proofs": [],
        "source": "legacy_script_text_projection",
    }


def _evidence_fingerprint(evidence: dict[str, Any]) -> str:
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_fingerprint(candidate: dict[str, Any], evidence_fingerprint: str) -> str:
    """Fingerprint the reviewed content separately from its source evidence."""
    canonical = json.dumps({"evidence": evidence_fingerprint, "candidate": candidate}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_source_grounded_llm_candidate(raw: Any, baseline: dict[str, Any], source_scene: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile only the flat ProposalIR; source facts are local compiler input."""

    if not isinstance(raw, dict):
        raise ValueError("Director ProposalIR output must be a JSON object")
    source_constraints = baseline.get("source_constraints") if isinstance(baseline.get("source_constraints"), dict) else {}
    reconstructed_scene = {
        "scene_id": source_constraints.get("scene_id"),
        "source_identity_evidence": source_constraints.get("scene_identity_evidence", []),
        "participants": source_constraints.get("declared_participants", []),
        "script_blocks": [{
            "order": unit.get("source_order"),
            "type": str(unit.get("source_type", "")).replace("SOURCE_", ""),
            "ref": unit.get("source_ref"),
        } for unit in source_constraints.get("source_authoring_units", [])],
        "actions": [{"action_id": unit.get("source_ref"), "text": unit.get("text", ""), "source_evidence": unit.get("source_evidence")} for unit in source_constraints.get("source_authoring_units", []) if unit.get("source_type") == "SOURCE_ACTION"],
        "dialogues": [{"dialogue_id": unit.get("source_ref"), "speaker": unit.get("speaker", ""), "text": unit.get("text", ""), "speaker_binding": {"classification": unit.get("binding_classification", ""), "binding_type": unit.get("binding_type", "")}, "source_evidence": unit.get("source_evidence")} for unit in source_constraints.get("source_authoring_units", []) if unit.get("source_type") == "SOURCE_DIALOGUE"],
        "beats": [],
    }
    return compile_director_proposal_ir(raw, baseline, source_scene or reconstructed_scene)


DIRECTOR_PROPOSAL_IR_V1_SYSTEM_PROMPT = """你是受权威来源约束的影视导演创作助手。

你只输出 director_proposal_ir_v1：一个扁平的创意提案中间结构，不是 DirectorTreatment，不是 authority object，也不是剧本改写。
所有源事实由本地编译器提供并保持不变。你不得输出 creative_projection、creative_beat_id、authority、source_constraints、source_authoring_units、scene_identity_evidence、declared_participants、proposal_origin、proposal_provenance、dialogue、speaker 或 binding。
不得新增 source character，不得输出镜头规格、SceneBlocking 或 ShotPlan。对白只能通过 refs 关联并转化为表演意图、观众效果和 timing intent，不能复述或改写对白。
返回一个可被 json.loads 直接解析的 JSON object。每个 beat 只包含 refs、purpose、objective、information_change、audience_effect、performance、transition、hook、character_effects；refs 只能使用给出的 SAU ID。
所有 source authoring unit 必须出现在 beats[].refs 或 passthrough_refs 中，不能遗漏，不能自动补全。"""


def _source_grounded_v3_prompt(treatment: dict[str, Any], evidence: dict[str, Any]) -> tuple[str, str]:
    constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
    units = constraints.get("source_authoring_units") if isinstance(constraints.get("source_authoring_units"), list) else []
    immutable_constraints = {
        "scene_id": constraints.get("scene_id"),
        "scene_identity_evidence": constraints.get("scene_identity_evidence", []),
        "explicit_story_constraints": constraints.get("explicit_story_constraints", []),
    }
    user_prompt = (
        "SOURCE_GROUNDED_DIRECTOR_PROPOSAL_V3\n"
        f"SCENE_ID={json.dumps(treatment.get('scene_id'), ensure_ascii=False)}\n"
        f"IMMUTABLE_SOURCE_CONSTRAINTS={json.dumps(immutable_constraints, ensure_ascii=False, sort_keys=True)}\n"
        f"SOURCE_AUTHORING_UNITS={json.dumps(units, ensure_ascii=False, sort_keys=True)}\n"
        f"DECLARED_PARTICIPANTS={json.dumps(constraints.get('declared_participants', []), ensure_ascii=False, sort_keys=True)}\n"
        # Advisory asset rows are deliberately excluded from the provider
        # request identity.  They are mutable, non-authoritative context and
        # caused the frozen preflight prompt to differ from the production
        # endpoint.  Source authority remains fully represented above.
        "ADVISORY_ASSET_CONTEXT=[]\n"
        f"PROPOSAL_IR_VERSION={DIRECTOR_PROPOSAL_IR_VERSION}\n"
        f"PROPOSAL_IR_SCHEMA_KEYS={json.dumps(sorted(DIRECTOR_PROPOSAL_IR_SCHEMA['properties']), ensure_ascii=False)}\n"
        "BEAT_CONTRACT=refs[]; purpose; objective; information_change; audience_effect; performance; transition; hook(boolean); character_effects[{character_ref,effect}]\n"
        "CHARACTER_DIRECTION_CONTRACT=character_ref:string plus one or more of direction:string, objective:string, obstacle:string, strategy:string, performance_notes:string; no other keys\n"
        "每个 beat 的 refs 只能引用上述 SAU ID。所有 source authoring unit 必须由 beats[].refs 或 passthrough_refs 覆盖。"
        "MINIMAL_VALID_SHAPE={\"version\":\"director_proposal_ir_v1\",\"scene_label\":\"\",\"scene_objective\":\"\",\"dramatic_question\":\"\",\"beats\":[],\"character_directions\":[],\"performance_arc\":[],\"information_strategy\":[],\"rhythm_strategy\":{},\"visual_priority\":[],\"scene_exit_intent\":\"\",\"prohibited_interpretations\":[],\"passthrough_refs\":[],\"unknowns\":[],\"confidence\":0.0,\"note\":\"\"}"
    )
    return DIRECTOR_PROPOSAL_IR_V1_SYSTEM_PROMPT, user_prompt


def build_source_grounded_director_execution_identity(treatment: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Build the one deterministic prompt identity shared by preflight and execution."""
    system_prompt, user_prompt = _source_grounded_v3_prompt(treatment, evidence)
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
        "request_fingerprint": prompt_fingerprint(system_prompt, user_prompt),
        "source_authoring_unit_fingerprint": treatment.get("source_authoring_units_fingerprint", ""),
        "advisory_asset_context": [],
        "schema_version": DIRECTOR_PROPOSAL_IR_VERSION,
    }


def _director_llm_profile_preflight() -> tuple[dict[str, Any], dict[str, Any]]:
    profile = llm_client._resolve_llm_profile()
    if not isinstance(profile, dict) or not str(profile.get("id") or "").strip() or not str(profile.get("model_name") or "").strip():
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_LLM_PROFILE_UNAVAILABLE", "message": "No enabled default LLM profile is available."})
    if profile.get("enabled") is False:
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_LLM_PROFILE_DISABLED", "message": "The default LLM profile is disabled."})
    base_url = str(profile.get("base_url") or "").strip()
    parsed = re.match(r"^(https?://[^/]+)", base_url)
    provider_host = parsed.group(1) if parsed else (base_url.split("/", 1)[0] if base_url else "")
    snapshot = {
        "profile_id": str(profile.get("id")),
        "provider": str(profile.get("provider") or ""),
        "model": str(profile.get("model_name") or ""),
        "base_host": provider_host,
        "enabled": bool(profile.get("enabled", True)),
        "key_configured": bool(profile.get("key_configured", False) or (profile.get("api_key") and profile.get("api_key") != "sk-placeholder")),
    }
    return profile, snapshot


def _director_generation_policy(profile: dict[str, Any]) -> dict[str, Any]:
    """Resolve the exact Director payload policy without exposing secrets."""

    defaults = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
    max_tokens = llm_client._normalize_max_tokens(defaults.get("max_tokens", config.LLM_MAX_TOKENS))
    thinking = llm_client._normalize_thinking_param(defaults.get("thinking"))
    return {
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "thinking": thinking,
    }


def build_source_grounded_director_provider_request(
    treatment: dict[str, Any],
    evidence: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    profile_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete V2 request identity shared by preflight/endpoint."""

    preflight_profile = None
    preflight_snapshot = None
    if not isinstance(profile, dict) or not isinstance(profile_snapshot, dict):
        preflight_profile, preflight_snapshot = _director_llm_profile_preflight()
    resolved_profile = profile if isinstance(profile, dict) else preflight_profile
    snapshot = profile_snapshot if isinstance(profile_snapshot, dict) else preflight_snapshot
    system_prompt, user_prompt = _source_grounded_v3_prompt(treatment, evidence)
    system_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    user_sha = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
    policy = _director_generation_policy(resolved_profile)
    prompt_fp = prompt_fingerprint(system_prompt, user_prompt)
    provider_payload = provider_request_payload_v2(
        profile_id=snapshot.get("profile_id"), provider=snapshot.get("provider"), model=snapshot.get("model"),
        base_host=snapshot.get("base_host"), system_prompt_sha256=system_sha, user_prompt_sha256=user_sha,
        temperature=policy["temperature"], max_tokens=policy["max_tokens"], response_format=policy["response_format"],
        thinking=policy["thinking"], schema_version=DIRECTOR_PROPOSAL_IR_VERSION,
    )
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "profile_snapshot": dict(snapshot),
        "generation_policy": policy,
        "prompt_fingerprint": prompt_fp,
        "provider_request_payload_v2": provider_payload,
        "provider_request_fingerprint_v2": provider_request_fingerprint_v2(**provider_payload),
        "system_prompt_sha256": system_sha,
        "user_prompt_sha256": user_sha,
        "source_authoring_unit_fingerprint": treatment.get("source_authoring_units_fingerprint", ""),
        "advisory_asset_context": [],
        "schema_version": DIRECTOR_PROPOSAL_IR_VERSION,
        "execution_boundary_version": "director_provider_request_v2",
    }


def build_director_beat_plan_provider_request(
    treatment: dict[str, Any],
    evidence: dict[str, Any],
    *,
    scene_id: str,
    profile: dict[str, Any] | None = None,
    profile_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the minimized, Stage A-only Provider identity."""
    preflight_profile = None
    preflight_snapshot = None
    if not isinstance(profile, dict) or not isinstance(profile_snapshot, dict):
        preflight_profile, preflight_snapshot = _director_llm_profile_preflight()
    resolved_profile = profile if isinstance(profile, dict) else preflight_profile
    snapshot = profile_snapshot if isinstance(profile_snapshot, dict) else preflight_snapshot
    constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
    units = constraints.get("source_authoring_units") if isinstance(constraints.get("source_authoring_units"), list) else []
    participants = constraints.get("declared_participants") if isinstance(constraints.get("declared_participants"), list) else []
    explicit_constraints = constraints.get("explicit_story_constraints") if isinstance(constraints.get("explicit_story_constraints"), list) else []
    unknowns = treatment.get("unknowns") if isinstance(treatment.get("unknowns"), list) else []
    system_prompt, user_prompt = build_director_beat_plan_prompt(
        scene_id=scene_id, source_units=units, declared_participants=participants,
        explicit_story_constraints=explicit_constraints, unknown_source_facts=unknowns,
    )
    prompt_parity = validate_stage_a_prompt_schema_key_parity(user_prompt)
    if prompt_parity.get("status") != "PASS":
        raise ValueError({"code": "STAGE_A_PROMPT_SCHEMA_KEY_PARITY", "report": prompt_parity})
    system_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    user_sha = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
    policy = _director_generation_policy(resolved_profile)
    prompt_fp = prompt_fingerprint(system_prompt, user_prompt)
    provider_payload = provider_request_payload_v2(
        profile_id=snapshot.get("profile_id"), provider=snapshot.get("provider"), model=snapshot.get("model"),
        base_host=snapshot.get("base_host"), system_prompt_sha256=system_sha, user_prompt_sha256=user_sha,
        temperature=policy["temperature"], max_tokens=policy["max_tokens"], response_format=policy["response_format"],
        thinking=policy["thinking"], schema_version=DIRECTOR_BEAT_PLAN_IR_VERSION,
        execution_boundary_version="director_beat_plan_provider_request_v1",
    )
    identity = {
        "system_prompt": system_prompt, "user_prompt": user_prompt,
        "system_prompt_sha256": system_sha, "user_prompt_sha256": user_sha,
        "prompt_fingerprint": prompt_fp, "profile_snapshot": dict(snapshot),
        "generation_policy": policy, "provider_request_payload_v2": provider_payload,
        "provider_request_fingerprint_v2": provider_request_fingerprint_v2(**provider_payload),
        "source_authoring_unit_fingerprint": treatment.get("source_authoring_units_fingerprint", ""),
        "schema_version": DIRECTOR_BEAT_PLAN_IR_VERSION, "authoring_stage": "BEAT_PLAN",
        "execution_boundary_version": "director_beat_plan_provider_request_v1",
    }
    consistency = validate_director_beat_plan_provider_identity(identity)
    if consistency.get("status") != "PASS":
        raise ValueError({"code": "DIRECTOR_BEAT_PLAN_PROVIDER_IDENTITY_INCONSISTENT", "report": consistency})
    identity["provider_identity_internal_consistency"] = consistency
    return identity


def validate_director_beat_plan_provider_identity(identity: dict[str, Any]) -> dict[str, Any]:
    """Validate every internal hash and payload binding before any Provider call."""
    errors: list[dict[str, Any]] = []
    if not isinstance(identity, dict):
        return {"status": "FAIL", "errors": [{"code": "IDENTITY_NOT_OBJECT"}]}
    payload = identity.get("provider_request_payload_v2") if isinstance(identity.get("provider_request_payload_v2"), dict) else {}
    system = str(identity.get("system_prompt") or "")
    user = str(identity.get("user_prompt") or "")
    system_sha = hashlib.sha256(system.encode("utf-8")).hexdigest()
    user_sha = hashlib.sha256(user.encode("utf-8")).hexdigest()
    checks = [
        ("identity.system_prompt_sha256==payload", identity.get("system_prompt_sha256"), payload.get("system_prompt_sha256")),
        ("identity.user_prompt_sha256==payload", identity.get("user_prompt_sha256"), payload.get("user_prompt_sha256")),
        ("sha256(system_prompt)==identity", system_sha, identity.get("system_prompt_sha256")),
        ("sha256(user_prompt)==identity", user_sha, identity.get("user_prompt_sha256")),
        ("prompt_fingerprint", prompt_fingerprint(system, user), identity.get("prompt_fingerprint")),
        ("provider_request_fingerprint_v2", provider_request_fingerprint_v2(**payload), identity.get("provider_request_fingerprint_v2")),
    ]
    for name, actual, expected in checks:
        if actual != expected:
            errors.append({"code": "DIRECTOR_BEAT_PLAN_PROVIDER_IDENTITY_INCONSISTENT", "check": name, "actual": actual, "expected": expected})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def build_director_creative_enrichment_provider_request(
    *, scene_id: str, materialized_beat_plan: dict[str, Any], stage_a_materialized_fingerprint: str,
    stage_a_attempt_id: str = "",
    declared_participants: list[Any] | None = None, source_authoring_units: list[Mapping[str, Any]] | None = None,
    source_authoring_unit_fingerprint: str = "", source_authority_content_fingerprint: str = "", revision_feedback: Mapping[str, Any] | None = None, revision_parent: Mapping[str, Any] | None = None, profile: dict[str, Any] | None = None,
    profile_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the provider identity for Stage B without executing it.

    The upstream Stage A materialized fingerprint is part of the request
    identity.  This prevents a Stage B response from being reused after the
    validated beat plan changes.
    """
    if not isinstance(materialized_beat_plan, dict) or not str(stage_a_materialized_fingerprint or "").strip():
        raise ValueError({"code": "DIRECTOR_STAGE_A_BINDING_REQUIRED"})
    preflight_profile = None
    preflight_snapshot = None
    if not isinstance(profile, dict) or not isinstance(profile_snapshot, dict):
        preflight_profile, preflight_snapshot = _director_llm_profile_preflight()
    resolved_profile = profile if isinstance(profile, dict) else preflight_profile
    snapshot = profile_snapshot if isinstance(profile_snapshot, dict) else preflight_snapshot
    if not str(source_authoring_unit_fingerprint or "").strip() and source_authoring_units:
        source_authoring_unit_fingerprint = hashlib.sha256(json.dumps(source_authoring_units, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    system_prompt, user_prompt = build_director_creative_enrichment_prompt(
        scene_id=scene_id, beat_plan=materialized_beat_plan, declared_participants=declared_participants or [],
        source_authoring_units=source_authoring_units or [], source_authoring_unit_fingerprint=source_authoring_unit_fingerprint, source_authority_content_fingerprint=source_authority_content_fingerprint, revision_feedback=revision_feedback, revision_parent=revision_parent,
    )
    parity = validate_stage_b_prompt_schema_key_parity(user_prompt)
    if parity.get("status") != "PASS":
        raise ValueError({"code": "STAGE_B_PROMPT_SCHEMA_KEY_PARITY", "report": parity})
    system_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    user_sha = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
    policy = _director_generation_policy(resolved_profile)
    payload = provider_request_payload_v2(
        profile_id=snapshot.get("profile_id"), provider=snapshot.get("provider"), model=snapshot.get("model"),
        base_host=snapshot.get("base_host"), system_prompt_sha256=system_sha, user_prompt_sha256=user_sha,
        temperature=policy["temperature"], max_tokens=policy["max_tokens"], response_format=policy["response_format"],
        thinking=policy["thinking"], schema_version="director_creative_enrichment_ir_v1",
        execution_boundary_version="director_creative_enrichment_provider_request_v1",
        upstream_binding_fingerprint=stage_a_materialized_fingerprint,
        source_authoring_unit_fingerprint=source_authoring_unit_fingerprint,
        source_authority_content_fingerprint=source_authority_content_fingerprint,
        revision_parent_attempt_id=(revision_parent or {}).get("revision_parent_attempt_id") if isinstance(revision_parent, Mapping) else None,
        revision_parent_fingerprint=(revision_parent or {}).get("revision_parent_fingerprint") if isinstance(revision_parent, Mapping) else None,
        semantic_review_fingerprint=(revision_parent or {}).get("revision_parent_semantic_review_fingerprint") if isinstance(revision_parent, Mapping) else None,
    )
    identity = {
        "system_prompt": system_prompt, "user_prompt": user_prompt,
        "system_prompt_sha256": system_sha, "user_prompt_sha256": user_sha,
        "prompt_fingerprint": prompt_fingerprint(system_prompt, user_prompt),
        "profile_snapshot": dict(snapshot), "generation_policy": policy,
        "provider_request_payload_v2": payload, "provider_request_fingerprint_v2": provider_request_fingerprint_v2(**payload),
        "schema_version": "director_creative_enrichment_ir_v1", "authoring_stage": "CREATIVE_ENRICHMENT",
        "upstream_binding_fingerprint": str(stage_a_materialized_fingerprint),
        "source_authoring_unit_fingerprint": str(source_authoring_unit_fingerprint or ""),
        "source_authority_content_fingerprint": str(source_authority_content_fingerprint or ""),
        "revision_parent": dict(revision_parent or {}),
        "revision_feedback": dict(revision_feedback or {}),
        "upstream_stage_a_attempt_id": str(stage_a_attempt_id or ""),
        "execution_boundary_version": "director_creative_enrichment_provider_request_v1",
    }
    consistency = validate_director_creative_enrichment_provider_identity(identity)
    if consistency.get("status") != "PASS":
        raise ValueError({"code": "DIRECTOR_CREATIVE_ENRICHMENT_PROVIDER_IDENTITY_INCONSISTENT", "report": consistency})
    identity["provider_identity_internal_consistency"] = consistency
    return identity


def validate_director_creative_enrichment_provider_identity(identity: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(identity, dict):
        return {"status": "FAIL", "errors": [{"code": "IDENTITY_NOT_OBJECT"}]}
    payload = identity.get("provider_request_payload_v2") if isinstance(identity.get("provider_request_payload_v2"), dict) else {}
    system = str(identity.get("system_prompt") or "")
    user = str(identity.get("user_prompt") or "")
    checks = [
        ("system_prompt_sha256", hashlib.sha256(system.encode("utf-8")).hexdigest(), identity.get("system_prompt_sha256")),
        ("user_prompt_sha256", hashlib.sha256(user.encode("utf-8")).hexdigest(), identity.get("user_prompt_sha256")),
        ("prompt_fingerprint", prompt_fingerprint(system, user), identity.get("prompt_fingerprint")),
        ("provider_request_fingerprint_v2", provider_request_fingerprint_v2(**payload), identity.get("provider_request_fingerprint_v2")),
        ("upstream_binding_fingerprint", payload.get("upstream_binding_fingerprint"), identity.get("upstream_binding_fingerprint")),
        ("source_authoring_unit_fingerprint", payload.get("source_authoring_unit_fingerprint", ""), identity.get("source_authoring_unit_fingerprint", "")),
        ("source_authority_content_fingerprint", payload.get("source_authority_content_fingerprint", ""), identity.get("source_authority_content_fingerprint", "")),
    ]
    for name, actual, expected in checks:
        if actual != expected:
            errors.append({"code": "DIRECTOR_CREATIVE_ENRICHMENT_PROVIDER_IDENTITY_INCONSISTENT", "check": name, "actual": actual, "expected": expected})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _progressive_stage_b_complete(info: dict[str, Any], proposal: Any) -> bool:
    progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
    stage_b = progressive.get("stage_b") if isinstance(progressive, dict) else None
    if not is_progressive_stage_validated(stage_b, authoring_stage="CREATIVE_ENRICHMENT"):
        return False
    if not isinstance(stage_b, dict) or str(stage_b.get("merge_state") or "") != "MERGED":
        return False
    candidate = proposal if isinstance(proposal, dict) else {}
    projection = candidate.get("creative_projection") if isinstance(candidate.get("creative_projection"), dict) else {}
    return candidate.get("decision") == "ready_for_review" and projection.get("status") == "PROPOSED"


def _update_director_packet_info(packet_id: int, book_id: int, patch: dict[str, Any]) -> None:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            return
        info = _json_object(row.model_info, {})
        info = info if isinstance(info, dict) else {}
        info.update(patch)
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.updated_at = datetime.now()
        session.commit()


def _set_latest_director_attempt_status(packet_id: int, book_id: int, status: str) -> None:
    """Update only the latest forensic attempt status; preserve all history."""
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            return
        info = _json_object(row.model_info, {})
        history = info.get("director_llm_attempts") if isinstance(info, dict) else None
        if not isinstance(history, list) or not history:
            return
        history[-1] = {**history[-1], "status": status}
        info["director_llm_attempts"] = history
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.updated_at = datetime.now()
        session.commit()


def _resolve_stage_a_attempt_context(packet_id: int, book_id: int) -> DirectorAttemptContext:
    """Freeze the next attempt identity from the packet's immutable ledger."""
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT"})
        info = _json_object(row.model_info, {})
        return resolve_next_director_attempt_context(info if isinstance(info, dict) else {})


def _assert_stage_a_attempt_context_current(packet_id: int, book_id: int, attempt_context: DirectorAttemptContext) -> None:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        info = _json_object(row.model_info, {}) if row else {}
        history = info.get("director_llm_attempts") if isinstance(info, dict) else None
        latest = history[-1] if isinstance(history, list) and history else None
        if not isinstance(latest, dict) or str(latest.get("attempt_id") or "") != attempt_context.attempt_id:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT", "retry": 0})


def _persist_v3_raw_forensic(*, packet_id: int, book_id: int, packet_fingerprint_value: str, raw_response: str, profile_snapshot: dict[str, Any], request_fingerprint: str, provider_record: dict[str, Any], event_trace: list[str], authorization_id: str = "") -> dict[str, Any]:
    if not str(authorization_id or "").strip():
        raise ValueError("DIRECTOR_LLM_AUTHORIZATION_ID_REQUIRED")
    raw_text = str(raw_response or "")
    forensic = {
        "schema_version": "director_llm_raw_response_forensic_v1",
        "packet_id": str(packet_id),
        "packet_fingerprint": packet_fingerprint_value,
        "raw_response": raw_text,
        "raw_response_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "raw_response_length": len(raw_text),
        "profile_id": profile_snapshot["profile_id"],
        "model": profile_snapshot["model"],
        "provider_host": profile_snapshot["base_host"],
        "provider_request_id": str(provider_record.get("provider_request_id") or ""),
        "request_fingerprint": request_fingerprint,
        "persisted_before_parse": True,
        "parse_started": False,
    }
    try:
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            if not row:
                raise RuntimeError("decision packet disappeared before forensic persistence")
            info = _json_object(row.model_info, {})
            info = info if isinstance(info, dict) else {}
            info = append_director_attempt(info, request_fingerprint=request_fingerprint, raw_response_sha256=forensic["raw_response_sha256"], authorization_id=authorization_id)
            info.update({"profile_preflight": profile_snapshot, "request_fingerprint": request_fingerprint, "raw_response_forensic": forensic, "provider_audit": provider_record, "event_trace": [*event_trace, "RAW_PERSIST"]})
            row.model_info = json.dumps(info, ensure_ascii=False)
            row.updated_at = datetime.now()
            session.commit()
    except Exception as exc:
        raise RuntimeError("DIRECTOR_LLM_FORENSIC_PERSISTENCE_FAILED") from exc
    return forensic


def _persist_stage_a_raw_forensic(*, packet_id: int, book_id: int, packet_fingerprint_value: str, raw_response: str, profile_snapshot: dict[str, Any], provider_identity: dict[str, Any], provider_record: dict[str, Any], authorization_id: str, attempt_context: DirectorAttemptContext) -> dict[str, Any]:
    """Append Stage A raw evidence before any parse or validation."""
    raw_text = str(raw_response or "")
    forensic = {
        "schema_version": "director_llm_raw_response_forensic_v1",
        "packet_id": str(packet_id), "packet_fingerprint": packet_fingerprint_value,
        "raw_response": raw_text, "raw_response_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "raw_response_length": len(raw_text), "profile_id": provider_identity["profile_snapshot"]["profile_id"],
        "model": provider_identity["profile_snapshot"]["model"], "provider_host": provider_identity["profile_snapshot"]["base_host"],
        "provider_request_id": str(provider_record.get("provider_request_id") or ""),
        "request_fingerprint": provider_identity["prompt_fingerprint"],
        "prompt_fingerprint": provider_identity["prompt_fingerprint"],
        "provider_request_fingerprint_v2": provider_identity["provider_request_fingerprint_v2"],
        "authoring_stage": "BEAT_PLAN", "persisted_before_parse": True, "parse_started": False,
        "finish_reason": provider_record.get("finish_reason"), "choice_index": provider_record.get("choice_index"),
        "resolved_max_tokens": provider_record.get("resolved_max_tokens", provider_identity["generation_policy"].get("max_tokens")),
        "resolved_temperature": provider_record.get("resolved_temperature", provider_identity["generation_policy"].get("temperature")),
        "resolved_response_format": provider_record.get("resolved_response_format", provider_identity["generation_policy"].get("response_format")),
        "resolved_thinking": provider_record.get("resolved_thinking", provider_identity["generation_policy"].get("thinking")),
        "usage": provider_record.get("usage") if isinstance(provider_record.get("usage"), dict) else {},
    }
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            raise RuntimeError("decision packet disappeared before Stage A forensic persistence")
        info = _json_object(row.model_info, {})
        info = info if isinstance(info, dict) else {}
        info = append_director_attempt(
            info, request_fingerprint=provider_identity["prompt_fingerprint"],
            raw_response_sha256=forensic["raw_response_sha256"], authorization_id=authorization_id,
            authoring_stage="BEAT_PLAN", prompt_fingerprint=provider_identity["prompt_fingerprint"],
            provider_request_fingerprint_v2=provider_identity["provider_request_fingerprint_v2"],
            attempt_context=attempt_context,
        )
        info.update({"profile_preflight": provider_identity["profile_snapshot"], "stage_a_provider_request": provider_identity,
                     "raw_response_forensic": forensic, "provider_audit": provider_record,
                     "event_trace": ["TRANSPORT", "RAW_PERSIST"], "attempt_context": {"history_count": attempt_context.history_count, "ordinal": attempt_context.ordinal, "attempt_id": attempt_context.attempt_id, "status_prefix": attempt_context.status_prefix}})
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.updated_at = datetime.now()
        session.commit()
    return forensic


def _stage_a_failure(packet_id: int, book_id: int, code: str, *, forensic: dict[str, Any] | None = None, trace: list[str] | None = None, report: dict[str, Any] | None = None, status: str | None = None, attempt_context: DirectorAttemptContext | None = None, update_latest: bool = True) -> None:
    patch = {"llm_draft_in_progress": False, "last_llm_draft_failure": code, "event_trace": trace or [], "stage_a_status": status or code}
    if forensic is not None:
        patch["raw_response_forensic"] = {**forensic, "parse_started": bool("PARSE" in (trace or []))}
    if report is not None:
        patch["stage_a_validation"] = report
    _update_director_packet_info(packet_id, book_id, patch)
    if update_latest and attempt_context is not None:
        _set_latest_director_attempt_status(packet_id, book_id, status or code)


def _stage_b_failure(packet_id: int, book_id: int, code: str, *, forensic: dict[str, Any] | None = None, trace: list[str] | None = None, report: dict[str, Any] | None = None, attempt_context: DirectorAttemptContext | None = None, update_latest: bool = True) -> None:
    patch: dict[str, Any] = {"llm_draft_in_progress": False, "last_llm_draft_failure": code, "stage_b_status": code, "event_trace": trace or []}
    if forensic is not None:
        patch["stage_b_raw_response_forensic"] = {**forensic, "parse_started": bool("PARSE" in (trace or []))}
    if report is not None:
        patch["stage_b_validation"] = report
    _update_director_packet_info(packet_id, book_id, patch)
    if update_latest and attempt_context is not None:
        _set_latest_director_attempt_status(packet_id, book_id, code)


def _restore_revision_after_failure(*, packet_id: int, book_id: int, revision_context: dict[str, Any], attempt_context: DirectorAttemptContext | None, failure_code: str) -> None:
    """Keep Attempt-8 active while archiving a failed revision attempt."""
    if not revision_context or attempt_context is None:
        return
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            return
        current_info = _json_object(row.model_info, {})
        current_info = current_info if isinstance(current_info, dict) else {}
        current_progressive = current_info.get("progressive_director_authoring") if isinstance(current_info.get("progressive_director_authoring"), dict) else {}
        archives = current_progressive.get("stage_b_attempts") if isinstance(current_progressive.get("stage_b_attempts"), list) else []
        failure_entry = {
            "attempt_id": attempt_context.attempt_id, "authoring_stage": "CREATIVE_ENRICHMENT", "status": failure_code,
            "structural_status": failure_code, "revision_parent": copy.deepcopy(revision_context.get("revision_parent") or {}),
            "provider_request_identity": copy.deepcopy(revision_context.get("identity") or {}),
            "raw_forensic": copy.deepcopy(current_info.get("stage_b_raw_response_forensic") or {}),
            "validation": copy.deepcopy(current_info.get("stage_b_validation") or {}),
            "semantic_review_fingerprint": str(revision_context.get("semantic_review_fingerprint") or ""),
        }
        if not any(isinstance(item, dict) and str(item.get("attempt_id") or "") == attempt_context.attempt_id for item in archives):
            archives.append(failure_entry)
        before_info = revision_context.get("before_info") if isinstance(revision_context.get("before_info"), dict) else {}
        restored = copy.deepcopy(before_info)
        restored_progressive = restored.get("progressive_director_authoring") if isinstance(restored.get("progressive_director_authoring"), dict) else {}
        restored_progressive["stage_b_attempts"] = archives
        restored["progressive_director_authoring"] = restored_progressive
        history = current_info.get("director_llm_attempts", restored.get("director_llm_attempts", []))
        history = copy.deepcopy(history) if isinstance(history, list) else []
        if not any(isinstance(item, dict) and str(item.get("attempt_id") or "") == attempt_context.attempt_id for item in history):
            history.append({"attempt_id": attempt_context.attempt_id, "authoring_stage": "CREATIVE_ENRICHMENT", "status": failure_code})
        else:
            history = [{**item, "status": failure_code} if isinstance(item, dict) and str(item.get("attempt_id") or "") == attempt_context.attempt_id else item for item in history]
        restored["director_llm_attempts"] = history
        restored["llm_draft_in_progress"] = False
        restored["last_revision_failure"] = failure_code
        restored["revision_boundary_status"] = failure_code
        row.model_info = json.dumps(restored, ensure_ascii=False)
        row.proposal = str(revision_context.get("before_proposal_json") or row.proposal)
        row.status = "draft"
        row.updated_at = datetime.now()
        session.commit()


def _persist_stage_b_raw_forensic(*, packet_id: int, book_id: int, packet_fingerprint_value: str, raw_response: str, profile_snapshot: dict[str, Any], provider_identity: dict[str, Any], provider_record: dict[str, Any], authorization_id: str, attempt_context: DirectorAttemptContext, stage_a: dict[str, Any], scope_fingerprint_value: str) -> dict[str, Any]:
    """Append Stage B raw evidence before parsing, with an append-only race gate."""
    raw_text = str(raw_response or "")
    forensic = {
        "schema_version": "director_llm_raw_response_forensic_v1",
        "packet_id": str(packet_id), "packet_fingerprint": packet_fingerprint_value,
        "authoring_stage": "CREATIVE_ENRICHMENT", "attempt_id": attempt_context.attempt_id,
        "authorization_id": str(authorization_id), "scope_fingerprint": scope_fingerprint_value,
        "stage_a_attempt_id": str(stage_a.get("attempt_id") or ""),
        "stage_a_ir_fingerprint": str(stage_a.get("ir_fingerprint") or stage_a.get("fingerprint") or ""),
        "stage_a_materialized_fingerprint": str(stage_a.get("materialized_fingerprint") or ""),
        "raw_response": raw_text, "raw_response_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "raw_response_length": len(raw_text), "profile_id": provider_identity["profile_snapshot"]["profile_id"],
        "model": provider_identity["profile_snapshot"]["model"], "provider_host": provider_identity["profile_snapshot"]["base_host"],
        "provider_request_id": str(provider_record.get("provider_request_id") or ""),
        "prompt_fingerprint": provider_identity["prompt_fingerprint"],
        "provider_request_fingerprint_v2": provider_identity["provider_request_fingerprint_v2"],
        "persisted_before_parse": True, "parse_started": False,
        "finish_reason": provider_record.get("finish_reason"), "choice_index": provider_record.get("choice_index"),
        "resolved_max_tokens": provider_record.get("resolved_max_tokens", provider_identity["generation_policy"].get("max_tokens")),
        "resolved_temperature": provider_record.get("resolved_temperature", provider_identity["generation_policy"].get("temperature")),
        "resolved_response_format": provider_record.get("resolved_response_format", provider_identity["generation_policy"].get("response_format")),
        "resolved_thinking": provider_record.get("resolved_thinking", provider_identity["generation_policy"].get("thinking")),
        "usage": provider_record.get("usage") if isinstance(provider_record.get("usage"), dict) else {},
        "latency_ms": provider_record.get("latency_ms"),
    }
    try:
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            if not row:
                raise RuntimeError("decision packet disappeared before Stage B forensic persistence")
            info = _json_object(row.model_info, {})
            info = info if isinstance(info, dict) else {}
            current_progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
            current_stage_a = current_progressive.get("stage_a") if isinstance(current_progressive, dict) else None
            if json.dumps(current_stage_a, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != json.dumps(stage_a, ensure_ascii=False, sort_keys=True, separators=(",", ":")):
                raise ValueError("DIRECTOR_CREATIVE_ENRICHMENT_STAGE_A_BINDING_CONFLICT")
            info = append_director_attempt(
                info, request_fingerprint=provider_identity["prompt_fingerprint"], raw_response_sha256=forensic["raw_response_sha256"],
                authorization_id=authorization_id, authoring_stage="CREATIVE_ENRICHMENT", prompt_fingerprint=provider_identity["prompt_fingerprint"],
                provider_request_fingerprint_v2=provider_identity["provider_request_fingerprint_v2"], attempt_context=attempt_context,
            )
            info.update({"stage_b_provider_request": provider_identity, "stage_b_raw_response_forensic": forensic, "provider_audit": provider_record, "event_trace": ["TRANSPORT", "RAW_PERSIST"], "stage_b_attempt_context": {"history_count": attempt_context.history_count, "ordinal": attempt_context.ordinal, "attempt_id": attempt_context.attempt_id, "status_prefix": attempt_context.status_prefix}})
            row.model_info = json.dumps(info, ensure_ascii=False)
            row.updated_at = datetime.now()
            session.commit()
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError("DIRECTOR_CREATIVE_ENRICHMENT_FORENSIC_PERSISTENCE_FAILED") from exc
    return forensic


def _execute_source_grounded_creative_enrichment(*, book_id: int, packet_id: int, packet_fingerprint_value: str, treatment: dict[str, Any], evidence: dict[str, Any], scene_id: str, authorization_id: str, identity: dict[str, Any], profile: dict[str, Any], revision_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute exactly one authorized Stage B call and persist only a proposal."""
    attempt_context = None
    try:
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            info = _json_object(row.model_info, {}) if row else {}
            if not row or not isinstance(info, dict):
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PACKET_NOT_FOUND"})
            proposal = _json_object(row.proposal, {})
            if not revision_context and proposal.get("decision") != "awaiting_llm":
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_ALREADY_COMPLETED"})
            progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
            stage_a = progressive.get("stage_a") if isinstance(progressive, dict) else None
            if not is_progressive_stage_validated(stage_a, authoring_stage="BEAT_PLAN") or not str(stage_a.get("attempt_id") or "").strip():
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_VALIDATION_REQUIRED"})
            materialized = stage_a.get("materialized_beat_plan")
            materialized_fp = str(stage_a.get("materialized_fingerprint") or "")
            actual_fp = hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() if isinstance(materialized, dict) else ""
            if (not materialized_fp or actual_fp != materialized_fp or identity.get("upstream_binding_fingerprint") != materialized_fp
                    or (identity.get("upstream_stage_a_attempt_id") and identity.get("upstream_stage_a_attempt_id") != stage_a.get("attempt_id"))):
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_STAGE_A_BINDING_CONFLICT"})
            attempt_context = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
            scope = _json_object(row.scope, {})
            scope_fp = hashlib.sha256(json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        audits: list[dict[str, Any]] = []
        try:
            raw = llm_client.call_llm(identity["user_prompt"], system=identity["system_prompt"], model_profile=profile, retries=1, estimated_tokens=identity["generation_policy"]["max_tokens"], max_tokens=identity["generation_policy"]["max_tokens"], temperature=identity["generation_policy"]["temperature"], response_format=identity["generation_policy"]["response_format"], audit_callback=lambda record: audits.append(dict(record)) if isinstance(record, dict) else None, audit_extra={"director_execution_boundary": identity["execution_boundary_version"], "authoring_stage": "CREATIVE_ENRICHMENT", "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"]})
        except (httpx.ReadTimeout, TimeoutError) as exc:
            _stage_b_failure(packet_id, book_id, attempt_context.status("SUBMISSION_AMBIGUOUS"), trace=["TRANSPORT"], attempt_context=None, update_latest=False)
            raise HTTPException(status_code=502, detail={"code": attempt_context.status("SUBMISSION_AMBIGUOUS"), "retry": 0}) from exc
        except Exception as exc:
            _stage_b_failure(packet_id, book_id, attempt_context.status("PROVIDER_FAILED"), trace=["TRANSPORT"], attempt_context=None, update_latest=False)
            raise HTTPException(status_code=502, detail={"code": attempt_context.status("PROVIDER_FAILED"), "retry": 0, "message": str(exc)[:240]}) from exc
        provider_record = audits[-1] if audits else {}
        try:
            forensic = _persist_stage_b_raw_forensic(packet_id=packet_id, book_id=book_id, packet_fingerprint_value=packet_fingerprint_value, raw_response=str(raw or ""), profile_snapshot=identity["profile_snapshot"], provider_identity=identity, provider_record=provider_record, authorization_id=authorization_id, attempt_context=attempt_context, stage_a=stage_a, scope_fingerprint_value=scope_fp)
        except ValueError as exc:
            code = attempt_context.status("LINEAGE_CONFLICT") if "LINEAGE" in str(exc) else "DIRECTOR_CREATIVE_ENRICHMENT_STAGE_A_BINDING_CONFLICT"
            _stage_b_failure(packet_id, book_id, code, trace=["TRANSPORT"], attempt_context=None, update_latest=False)
            raise HTTPException(status_code=409, detail={"code": code, "retry": 0}) from exc
        except RuntimeError as exc:
            _stage_b_failure(packet_id, book_id, "DIRECTOR_CREATIVE_ENRICHMENT_FORENSIC_PERSISTENCE_FAILED", trace=["TRANSPORT"], attempt_context=None, update_latest=False)
            raise HTTPException(status_code=502, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_FORENSIC_PERSISTENCE_FAILED", "retry": 0}) from exc
        finish_reason = str(provider_record.get("finish_reason") or "").strip().lower()
        if finish_reason == "length":
            code = attempt_context.status("OUTPUT_TRUNCATED")
            _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", "FINISH_REASON_GATE"], attempt_context=attempt_context)
            raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
        finish_note = "FINISH_REASON_UNAVAILABLE" if not finish_reason else "FINISH_REASON_GATE"
        try:
            parsed = parse_director_creative_enrichment_ir(str(raw or ""))
        except Exception as exc:
            outcome = "DUPLICATE_JSON_KEY" if "DUPLICATE_JSON_KEY" in str(exc) else "PARSE_FAILED"
            code = attempt_context.status(outcome)
            _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE"], report={"error": str(exc)}, attempt_context=attempt_context)
            raise HTTPException(status_code=502, detail={"code": code, "retry": 0}) from exc
        schema_report = validate_director_creative_enrichment_ir_schema(parsed)
        if schema_report.get("status") != "PASS":
            code = attempt_context.status("SCHEMA_INVALID")
            _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE"], report=schema_report, attempt_context=attempt_context)
            raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
        text_report = validate_director_creative_enrichment_text_completeness(parsed)
        if text_report.get("status") != "PASS":
            code = attempt_context.status("TEXT_INCOMPLETE")
            _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS"], report=text_report, attempt_context=attempt_context)
            raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
        runtime = validate_director_creative_enrichment_ir(parsed, beat_plan=stage_a["materialized_beat_plan"], declared_participants=(treatment.get("source_constraints") or {}).get("declared_participants", []))
        if runtime.get("status") != "qualified":
            outcome = "BEAT_COVERAGE_INCOMPLETE" if runtime.get("beat_coverage") == "FAIL" else "RUNTIME_INVALID"
            code = attempt_context.status(outcome)
            _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE"], report=runtime, attempt_context=attempt_context)
            raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
        with Session() as session:
            current = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            current_info = _json_object(current.model_info, {}) if current else {}
            current_progressive = current_info.get("progressive_director_authoring") if isinstance(current_info, dict) else {}
            current_stage_a = current_progressive.get("stage_a") if isinstance(current_progressive, dict) else None
            if json.dumps(current_stage_a, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != json.dumps(stage_a, ensure_ascii=False, sort_keys=True, separators=(",", ":")):
                code = attempt_context.status("STAGE_A_BINDING_CONFLICT")
                _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE", "STAGE_A_BINDING_REVALIDATE"], attempt_context=attempt_context)
                raise HTTPException(status_code=409, detail={"code": code, "retry": 0})
            current_history = current_info.get("director_llm_attempts") if isinstance(current_info, dict) else []
            if not isinstance(current_history, list) or len(current_history) != attempt_context.ordinal or str(current_history[-1].get("attempt_id") or "") != attempt_context.attempt_id:
                code = attempt_context.status("LINEAGE_CONFLICT")
                _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE", "STAGE_A_BINDING_REVALIDATE", "ATTEMPT_LINEAGE_VALIDATE"], attempt_context=attempt_context)
                raise HTTPException(status_code=409, detail={"code": code, "retry": 0})
        if revision_context:
            current_treatment, current_evidence, _ = _build_preview(book_id, DirectorTreatmentPreviewRequest(episode=int(revision_context.get("episode") or 0) or None, scene_id=scene_id, workflow_profile="production"))
            current_packet = _make_decision_packet(book_id, int(revision_context.get("episode") or 0), current_treatment, current_evidence)
            if current_packet.get("packet_fingerprint") != packet_fingerprint_value:
                # A production revision may intentionally bind an immutable
                # historical packet fingerprint while the current preview
                # builder has a newer derived treatment fingerprint.  The
                # route has already validated the requested historical row's
                # book/episode/scene scope; preserve that packet identity and
                # continue with the source race gates instead of treating the
                # derived preview fingerprint as a source mutation.
                with Session() as historical_session:
                    historical_packet = historical_session.query(DecisionPacketRecord).filter_by(
                        book_id=book_id, packet_fingerprint=packet_fingerprint_value, domain="director_treatment"
                    ).first()
                if not historical_packet:
                    code = attempt_context.status("SOURCE_BINDING_CONFLICT")
                    _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_RUNTIME_VALIDATE", "SOURCE_BINDING_REVALIDATE"], attempt_context=attempt_context)
                    raise HTTPException(status_code=409, detail={"code": code, "retry": 0})
        stage_b_fp = hashlib.sha256(json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        try:
            candidate = compile_progressive_director_proposal(beat_plan_ir=stage_a["ir"], enrichment_ir=parsed, baseline_treatment=treatment, source_scene=evidence.get("scene") if isinstance(evidence.get("scene"), dict) else {}, materialized_beat_plan=stage_a["materialized_beat_plan"], materialized_fingerprint=stage_a["materialized_fingerprint"])
            compiled = validate_source_grounded_contract_v2(candidate, scene=evidence.get("scene") if isinstance(evidence.get("scene"), dict) else {}, production=False)
            if compiled.get("status") != "qualified" or candidate.get("decision") != "ready_for_review" or (candidate.get("creative_projection") or {}).get("status") != "PROPOSED":
                raise ValueError(json.dumps(compiled, ensure_ascii=False))
        except Exception as exc:
            code = attempt_context.status("COMPILED_CONTRACT_INVALID")
            _stage_b_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE", "STAGE_A_BINDING_REVALIDATE", "STAGE_B_PERSIST", "DETERMINISTIC_MERGE", "COMPILED_V3_VALIDATE"], report={"error": str(exc)}, attempt_context=attempt_context)
            raise HTTPException(status_code=502, detail={"code": code, "retry": 0}) from exc
        source_constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
        semantic_review = validate_director_creative_semantic_review(
            parsed,
            candidate=candidate,
            source_authoring_units=source_constraints.get("source_authoring_units") if isinstance(source_constraints.get("source_authoring_units"), list) else [],
            stage_a=stage_a.get("ir") if isinstance(stage_a, dict) else None,
            declared_participants=source_constraints.get("declared_participants") if isinstance(source_constraints.get("declared_participants"), list) else [],
        )
        provider = {"called": True, "calls": 1, "profile_id": identity["profile_snapshot"]["profile_id"], "model": identity["profile_snapshot"]["model"], "request_fingerprint": identity["prompt_fingerprint"], "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"], "response_fingerprint": forensic["raw_response_sha256"]}
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            info = _json_object(row.model_info, {}) if row else {}
            info = info if isinstance(info, dict) else {}
            progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
            stage_b = {"status": attempt_context.status("VALIDATED"), "authoring_stage": "CREATIVE_ENRICHMENT", "attempt_id": attempt_context.attempt_id, "authorization_id": authorization_id, "ir": parsed, "ir_fingerprint": stage_b_fp, "fingerprint": stage_b_fp, "stage_a_materialized_fingerprint": stage_a["materialized_fingerprint"], "provider_provenance": provider, "validation_state": "VALIDATED", "merge_state": "MERGED", "semantic_review": semantic_review}
            if revision_context:
                # The revision endpoint archives the active parent while it
                # acquires the execution lock. Do not reconstruct that archive
                # after raw Attempt-9 persistence has replaced the top-level
                # provider evidence; that would make an identical archive look
                # conflicting. Keep a defensive fallback for direct callers.
                active_attempt_id = str(progressive.get("stage_b", {}).get("attempt_id") or "")
                existing_archives = progressive.get("stage_b_attempts") if isinstance(progressive.get("stage_b_attempts"), list) else []
                if not any(isinstance(item, dict) and str(item.get("attempt_id") or "") == active_attempt_id for item in existing_archives):
                    info, archive_report = archive_stage_b_attempt(info, proposal=_json_object(row.proposal, {}), attempt_id=active_attempt_id)
                    progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else progressive
                progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else progressive
                stage_b["revision_parent"] = copy.deepcopy(revision_context.get("revision_parent") or {})
                stage_b["semantic_review_fingerprint"] = semantic_review_fingerprint(semantic_review)
                stage_b["source_authoring_unit_fingerprint"] = str(identity.get("source_authoring_unit_fingerprint") or "")
                stage_b["source_authority_content_fingerprint"] = str(identity.get("source_authority_content_fingerprint") or "")
                stage_b["provider_request_identity"] = copy.deepcopy(identity)
                stage_b_attempts = progressive.get("stage_b_attempts") if isinstance(progressive.get("stage_b_attempts"), list) else []
                stage_b_attempts.append({"attempt_id": attempt_context.attempt_id, "authoring_stage": "CREATIVE_ENRICHMENT", "ir": copy.deepcopy(parsed), "ir_fingerprint": stage_b_fp, "structural_status": stage_b["status"], "semantic_review": copy.deepcopy(semantic_review), "semantic_review_fingerprint": semantic_review_fingerprint(semantic_review), "revision_parent": copy.deepcopy(revision_context.get("revision_parent") or {}), "provider_provenance": copy.deepcopy(provider), "provider_request_identity": copy.deepcopy(identity), "raw_forensic": copy.deepcopy(forensic), "validation": {"schema": schema_report, "text": text_report, "runtime": runtime, "semantic_review": semantic_review}, "merge_state": "MERGED", "proposal_fingerprint": proposal_fingerprint(candidate)})
                progressive["stage_b_attempts"] = stage_b_attempts
            info["progressive_director_authoring"] = {**progressive, "stage_a": progressive.get("stage_a"), "stage_b": stage_b}
            proposal_lineage = {"proposal_origin": "PROVIDER_PROPOSAL", "provider": provider, "authoring": {"human_input": False}, "stage_a": {"attempt_id": stage_a.get("attempt_id"), "ir_fingerprint": stage_a.get("ir_fingerprint"), "materialized_fingerprint": stage_a.get("materialized_fingerprint")}, "stage_b": {"attempt_id": attempt_context.attempt_id, "ir_fingerprint": stage_b_fp}}
            if revision_context:
                proposal_lineage["revision"] = {"parent_attempt_id": revision_context.get("revision_parent", {}).get("revision_parent_attempt_id"), "parent_ir_fingerprint": revision_context.get("revision_parent", {}).get("revision_parent_stage_b_ir_fingerprint"), "semantic_rejection_fingerprint": revision_context.get("revision_parent", {}).get("revision_parent_semantic_review_fingerprint")}
                proposal_lineage["merge"] = "deterministic"
            info.update({"llm_draft_in_progress": False, "stage_b_status": stage_b["status"], "stage_b_raw_response_forensic": {**forensic, "parse_started": True}, "stage_b_validation": {"schema": schema_report, "text": text_report, "runtime": runtime, "semantic_review": semantic_review}, "semantic_review": semantic_review, "event_trace": ["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE", "STAGE_A_BINDING_REVALIDATE", "STAGE_B_SEMANTIC_REVIEW", "STAGE_B_PERSIST", "DETERMINISTIC_MERGE", "COMPILED_V3_VALIDATE", "PROPOSAL_PERSIST"], "proposal_provenance": proposal_lineage})
            row.model_info = json.dumps(info, ensure_ascii=False)
            row.proposal = json.dumps(candidate, ensure_ascii=False)
            row.status = "draft"
            row.updated_at = datetime.now()
            history = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
            if history:
                history[-1] = {**history[-1], "status": stage_b["status"]}
                info["director_llm_attempts"] = history
                row.model_info = json.dumps(info, ensure_ascii=False)
            session.commit()
        semantic_pass = semantic_review.get("status") == "PASS"
        return {"packet_id": packet_id, "packet_fingerprint": packet_fingerprint_value, "status": attempt_context.status("VALIDATED"), "next_state": "DIRECTOR_TREATMENT_REVIEW_REQUIRED" if semantic_pass else "DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED", "confirm_allowed": semantic_pass, "semantic_review": semantic_review, "candidate": candidate, "provider": provider, "execution_manifest": identity}
    except HTTPException as exc:
        # The endpoint takes the execution lock before entering this function.
        # Pre-transport races must release it without appending an attempt.
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False})
        if revision_context:
            _restore_revision_after_failure(packet_id=packet_id, book_id=book_id, revision_context=revision_context, attempt_context=attempt_context, failure_code=str((exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else {}).get("code") or "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_BOUNDARY_BLOCKED"))
        raise
    except Exception as exc:
        code = attempt_context.status("EXECUTION_FAILED") if attempt_context is not None else "DIRECTOR_CREATIVE_ENRICHMENT_EXECUTION_FAILED"
        _stage_b_failure(packet_id, book_id, code, trace=["EXECUTION"], attempt_context=None, update_latest=False)
        if revision_context:
            _restore_revision_after_failure(packet_id=packet_id, book_id=book_id, revision_context=revision_context, attempt_context=attempt_context, failure_code=code)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0, "message": str(exc)[:240]}) from exc


def _execute_source_grounded_beat_plan(*, book_id: int, packet_id: int, packet_fingerprint_value: str, treatment: dict[str, Any], evidence: dict[str, Any], scene_id: str, authorization_id: str) -> dict[str, Any]:
    """Execute exactly one Stage A call; never compiles or promotes Stage B."""
    if not str(authorization_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_AUTHORIZATION_ID_REQUIRED"})
    attempt_context = _resolve_stage_a_attempt_context(packet_id, book_id)
    profile, profile_snapshot = _director_llm_profile_preflight()
    try:
        identity = build_director_beat_plan_provider_request(treatment, evidence, scene_id=scene_id, profile=profile, profile_snapshot=profile_snapshot)
    except ValueError as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_BEAT_PLAN_PROVIDER_IDENTITY_INCONSISTENT", "event_trace": ["PREFLIGHT_IDENTITY_VALIDATE"]})
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_PROVIDER_IDENTITY_INCONSISTENT", "message": "Stage A Provider identity failed internal consistency validation."}) from exc
    audits: list[dict[str, Any]] = []
    try:
        raw = llm_client.call_llm(identity["user_prompt"], system=identity["system_prompt"], model_profile=profile,
            retries=1, estimated_tokens=identity["generation_policy"]["max_tokens"], max_tokens=identity["generation_policy"]["max_tokens"],
            temperature=identity["generation_policy"]["temperature"], response_format=identity["generation_policy"]["response_format"],
            audit_callback=lambda record: audits.append(dict(record)) if isinstance(record, dict) else None,
            audit_extra={"director_execution_boundary": identity["execution_boundary_version"], "authoring_stage": "BEAT_PLAN", "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"]})
    except Exception as exc:
        code = attempt_context.status("PROVIDER_FAILED")
        _stage_a_failure(packet_id, book_id, code, trace=["TRANSPORT"], status=code, attempt_context=attempt_context, update_latest=False)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0, "message": str(exc)[:240]}) from exc
    provider_record = audits[-1] if audits else {}
    try:
        forensic = _persist_stage_a_raw_forensic(packet_id=packet_id, book_id=book_id, packet_fingerprint_value=packet_fingerprint_value, raw_response=str(raw or ""), profile_snapshot=profile_snapshot, provider_identity=identity, provider_record=provider_record, authorization_id=authorization_id, attempt_context=attempt_context)
    except ValueError as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT", "event_trace": ["TRANSPORT", "ATTEMPT_LINEAGE_VALIDATE"]})
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT", "retry": 0}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_FORENSIC_PERSISTENCE_FAILED", "retry": 0}) from exc
    finish_reason = str(provider_record.get("finish_reason") or "").strip().lower()
    if finish_reason == "length":
        code = attempt_context.status("OUTPUT_TRUNCATED")
        _stage_a_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", "FINISH_REASON_GATE"], status=code, attempt_context=attempt_context)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
    finish_note = "FINISH_REASON_UNAVAILABLE" if not finish_reason else "FINISH_REASON_GATE"
    try:
        parsed = parse_director_beat_plan_ir(str(raw or ""))
    except Exception as exc:
        duplicate_key = str(exc).startswith("DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY:")
        outcome = "DUPLICATE_JSON_KEY" if duplicate_key else "PARSE_FAILED"
        code = attempt_context.status(outcome)
        report = {"error": str(exc), "error_code": "DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY" if duplicate_key else "DIRECTOR_BEAT_PLAN_PARSE_FAILED"}
        _stage_a_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE"], report=report, status=code, attempt_context=attempt_context)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0}) from exc
    schema_report = validate_director_beat_plan_ir_schema(parsed)
    if schema_report.get("status") != "PASS":
        code = attempt_context.status("SCHEMA_INVALID")
        _stage_a_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_A_SCHEMA_VALIDATE"], report=schema_report, status=code, attempt_context=attempt_context)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
    completeness = validate_director_beat_plan_text_completeness(parsed)
    if completeness.get("status") != "PASS":
        code = attempt_context.status("TEXT_INCOMPLETE")
        _stage_a_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_A_SCHEMA_VALIDATE", "STAGE_A_TEXT_COMPLETENESS"], report=completeness, status=code, attempt_context=attempt_context)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
    constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
    units = constraints.get("source_authoring_units") if isinstance(constraints.get("source_authoring_units"), list) else []
    runtime = validate_director_beat_plan_ir(parsed, source_units=units)
    if runtime.get("status") != "qualified":
        outcome = "SOURCE_COVERAGE_INCOMPLETE" if any(e.get("code") == "DIRECTOR_BEAT_PLAN_SOURCE_COVERAGE_INCOMPLETE" for e in runtime.get("errors", [])) else "RUNTIME_INVALID"
        code = attempt_context.status(outcome)
        _stage_a_failure(packet_id, book_id, code, forensic=forensic, trace=["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_A_SCHEMA_VALIDATE", "STAGE_A_TEXT_COMPLETENESS", "STAGE_A_RUNTIME_VALIDATE"], report=runtime, status=code, attempt_context=attempt_context)
        raise HTTPException(status_code=502, detail={"code": code, "retry": 0})
    materialized = materialize_director_beat_plan_ids(parsed, scene_id=scene_id)
    raw_fp = hashlib.sha256(json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    materialized_fp = hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    try:
        _assert_stage_a_attempt_context_current(packet_id, book_id, attempt_context)
    except HTTPException:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT", "event_trace": ["TRANSPORT", "RAW_PERSIST", "ATTEMPT_LINEAGE_VALIDATE"]})
        raise
    success_code = attempt_context.status("VALIDATED")
    _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "stage_a_status": success_code, "event_trace": ["TRANSPORT", "RAW_PERSIST", finish_note, "PARSE", "STAGE_A_SCHEMA_VALIDATE", "STAGE_A_TEXT_COMPLETENESS", "STAGE_A_RUNTIME_VALIDATE", "STAGE_A_PERSIST"], "progressive_director_authoring": {"stage_a": {"status": success_code, "authoring_stage": "BEAT_PLAN", "ir": parsed, "ir_fingerprint": raw_fp, "materialized_beat_plan": materialized, "materialized_fingerprint": materialized_fp, "authorization_id": authorization_id, "attempt_id": attempt_context.attempt_id, "provider_provenance": {"called": True, "calls": 1, "profile_id": profile_snapshot["profile_id"], "model": profile_snapshot["model"], "prompt_fingerprint": identity["prompt_fingerprint"], "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"], "raw_response_sha256": forensic["raw_response_sha256"]}}}})
    _set_latest_director_attempt_status(packet_id, book_id, success_code)
    return {"packet_id": packet_id, "packet_fingerprint": packet_fingerprint_value, "status": success_code, "authoring_stage": "BEAT_PLAN", "attempt_id": attempt_context.attempt_id, "materialized_beat_plan": materialized, "next_state": "DIRECTOR_CREATIVE_ENRICHMENT_AUTHORIZATION_REQUIRED", "confirm_allowed": False, "provider": {"called": True, "calls": 1}, "execution_manifest": identity}


def _execute_source_grounded_v3_proposal(*, book_id: int, packet_id: int, packet_fingerprint_value: str, treatment: dict[str, Any], evidence: dict[str, Any], authorization_id: str = "") -> dict[str, Any]:
    authorization_id = str(authorization_id or "").strip()
    if not authorization_id:
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_LLM_AUTHORIZATION_ID_REQUIRED", "message": "Source-grounded Director LLM execution requires an explicit authorization_id."})
    try:
        profile, profile_snapshot = _director_llm_profile_preflight()
    except HTTPException as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": (exc.detail.get("code") if isinstance(exc.detail, dict) else "DIRECTOR_LLM_PROFILE_UNAVAILABLE")})
        raise
    provider_identity = build_source_grounded_director_provider_request(
        treatment, evidence, profile=profile, profile_snapshot=profile_snapshot,
    )
    system_prompt = provider_identity["system_prompt"]
    user_prompt = provider_identity["user_prompt"]
    request_fp = provider_identity["prompt_fingerprint"]
    generation_policy = provider_identity["generation_policy"]
    audit_records: list[dict[str, Any]] = []
    try:
        raw = llm_client.call_llm(
            user_prompt,
            system=system_prompt,
            model_profile=profile,
            retries=1,
            estimated_tokens=generation_policy["max_tokens"],
            max_tokens=generation_policy["max_tokens"],
            temperature=generation_policy["temperature"],
            response_format=generation_policy["response_format"],
            audit_callback=lambda record: audit_records.append(dict(record)) if isinstance(record, dict) else None,
            audit_extra={
                "director_execution_boundary": "v3_one_call",
                "provider_request_fingerprint_v2": provider_identity["provider_request_fingerprint_v2"],
                "execution_boundary_version": provider_identity["execution_boundary_version"],
            },
        )
    except httpx.ReadTimeout as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_SUBMISSION_AMBIGUOUS", "transport_retry": 0})
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_SUBMISSION_AMBIGUOUS", "retry": 0}) from exc
    except httpx.HTTPStatusError as exc:
        status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_CALL_FAILED", "http_status": status, "transport_retry": 0})
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_CALL_FAILED", "http_status": status, "retry": 0}) from exc
    except httpx.ConnectError as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_CALL_FAILED", "transport_retry": 0})
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_CALL_FAILED", "retry": 0}) from exc
    except Exception as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_CALL_FAILED", "transport_retry": 0})
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_CALL_FAILED", "retry": 0, "message": str(exc)[:240]}) from exc

    provider_record = audit_records[-1] if audit_records else {}
    try:
        forensic = _persist_v3_raw_forensic(packet_id=packet_id, book_id=book_id, packet_fingerprint_value=packet_fingerprint_value, raw_response=str(raw or ""), profile_snapshot=profile_snapshot, request_fingerprint=request_fp, provider_record=provider_record, event_trace=["TRANSPORT"], authorization_id=authorization_id)
    except RuntimeError as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_FORENSIC_PERSISTENCE_FAILED"})
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_FORENSIC_PERSISTENCE_FAILED", "retry": 0}) from exc

    try:
        parsed = parse_director_proposal_ir(str(raw or ""))
    except Exception as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_OUTPUT_INVALID", "parse_attempts": 1, "parse_error": str(exc)[:500], "raw_response_forensic": {**forensic, "parse_started": True}, "event_trace": ["TRANSPORT", "RAW_PERSIST", "PARSE"]})
        _set_latest_director_attempt_status(packet_id, book_id, "PARSE_FAILED")
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_OUTPUT_INVALID", "retry": 0, "parse_attempts": 1}) from exc

    schema_report = validate_director_proposal_ir_schema(parsed)
    if schema_report.get("status") != "PASS":
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_PROPOSAL_IR_SCHEMA_INVALID", "proposal_ir_schema_validation": schema_report, "raw_response_forensic": {**forensic, "parse_started": True}, "event_trace": ["TRANSPORT", "RAW_PERSIST", "PARSE", "IR_SCHEMA_VALIDATE"]})
        _set_latest_director_attempt_status(packet_id, book_id, "SCHEMA_INVALID")
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_PROPOSAL_IR_SCHEMA_INVALID", "retry": 0})

    try:
        candidate = _validate_source_grounded_llm_candidate(parsed, treatment, evidence.get("scene") if isinstance(evidence.get("scene"), dict) else None)
        semantic_report = candidate.get("compiler_report", {}).get("compiled_contract_validation", {})
        if semantic_report.get("status") != "qualified":
            raise ValueError(json.dumps(semantic_report, ensure_ascii=False))
    except DirectorProposalIRValidationError as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_PROPOSAL_IR_INVALID", "proposal_ir_validation": exc.report, "validation_error": str(exc)[:1000], "raw_response_forensic": {**forensic, "parse_started": True}, "event_trace": ["TRANSPORT", "RAW_PERSIST", "PARSE", "IR_VALIDATE"]})
        _set_latest_director_attempt_status(packet_id, book_id, "IR_INVALID")
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_PROPOSAL_IR_INVALID", "retry": 0}) from exc
    except Exception as exc:
        _update_director_packet_info(packet_id, book_id, {"llm_draft_in_progress": False, "last_llm_draft_failure": "DIRECTOR_LLM_CREATIVE_PROPOSAL_INVALID", "validation_error": str(exc)[:1000], "raw_response_forensic": {**forensic, "parse_started": True}, "event_trace": ["TRANSPORT", "RAW_PERSIST", "PARSE", "VALIDATE"]})
        _set_latest_director_attempt_status(packet_id, book_id, "COMPILED_CANDIDATE_INVALID")
        raise HTTPException(status_code=502, detail={"code": "DIRECTOR_LLM_CREATIVE_PROPOSAL_INVALID", "retry": 0}) from exc

    provider = {
        "called": True, "calls": 1, "profile_id": profile_snapshot["profile_id"], "model": profile_snapshot["model"],
        "request_fingerprint": request_fp, "provider_request_fingerprint_v2": provider_identity["provider_request_fingerprint_v2"],
        "response_fingerprint": forensic["raw_response_sha256"],
    }
    provenance = proposal_provenance("PROVIDER_PROPOSAL", provider=provider)
    candidate["proposal_origin"] = "PROVIDER_PROPOSAL"
    candidate["proposal_provenance"] = provenance
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            raise HTTPException(status_code=409, detail="Treatment decision packet disappeared while the LLM was running.")
        info = _json_object(row.model_info, {})
        info = info if isinstance(info, dict) else {}
        info.update({"llm_draft_in_progress": False, "proposal_provenance": provenance, "profile_preflight": profile_snapshot, "request_fingerprint": request_fp, "provider_request_fingerprint_v2": provider_identity["provider_request_fingerprint_v2"], "generation_policy": provider_identity["generation_policy"], "provider_audit": provider_record, "raw_response_forensic": {**forensic, "parse_started": True}, "event_trace": ["TRANSPORT", "RAW_PERSIST", "PARSE", "IR_SCHEMA_VALIDATE", "IR_VALIDATE", "COMPILE", "PROPOSAL_PERSIST"], "generated_at": datetime.now().isoformat(), **project_legacy_flags(provenance)})
        row.proposal = json.dumps(candidate, ensure_ascii=False)
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.status = "draft"
        row.updated_at = datetime.now()
        session.commit()
        # The history was appended before parsing; this status records the
        # terminal proposal-only outcome without losing prior attempts.
        _set_latest_director_attempt_status(packet_id, book_id, "PROPOSAL_PERSISTED")
        return {
            "packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": candidate,
            **project_legacy_flags(provenance), "deduplicated": False, "domain_write_performed": False,
            "provider": {**provider, "provider_request_id": provider_record.get("provider_request_id")},
            "execution_manifest": {
                "system_prompt_sha256": provider_identity["system_prompt_sha256"],
                "user_prompt_sha256": provider_identity["user_prompt_sha256"],
                "prompt_fingerprint": provider_identity["prompt_fingerprint"],
                "provider_request_fingerprint_v2": provider_identity["provider_request_fingerprint_v2"],
                "provider_request_payload_v2": provider_identity["provider_request_payload_v2"],
                "generation_policy": provider_identity["generation_policy"],
                "request_fingerprint": request_fp, "packet_fingerprint": packet_fingerprint_value,
                "source_authoring_unit_fingerprint": provider_identity["source_authoring_unit_fingerprint"],
                "advisory_asset_context": provider_identity["advisory_asset_context"],
                "schema_version": provider_identity["schema_version"],
                "execution_boundary_version": provider_identity["execution_boundary_version"],
            },
        }


def _make_decision_packet(book_id: int, episode: int, treatment: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    evidence_items = [
        {"id": f"script:{evidence['script']['id']}", "tier": "source_text", "summary": json.dumps(evidence["scene"], ensure_ascii=False), "version": evidence["script"]["revision"]},
        {"id": f"treatment:{treatment['prompt_fingerprint']}", "tier": "derived_fact", "summary": json.dumps(treatment, ensure_ascii=False), "version": "shadow-v1"},
        {"id": f"assets:{book_id}:{episode}", "tier": "approved_fact", "summary": json.dumps({"characters": evidence["characters"], "locked_references": evidence["locked_references"]}, ensure_ascii=False), "version": "current"},
    ]
    packet = normalize_decision_packet({
        "domain": "director_treatment",
        "scope": {"book_id": book_id, "episode": episode, "scene_id": evidence.get("scene_id", ""), "scene_name": evidence["scene_name"], "treatment_fingerprint": treatment["prompt_fingerprint"]},
        "evidence": evidence_items,
        "unknowns": treatment.get("unknowns") or [],
        "conflicts": [],
        "allowed_operations": ["propose_director_treatment", "request_missing_information"],
    })
    packet["packet_fingerprint"] = decision_packet_fingerprint(packet)
    return packet


TREATMENT_CANDIDATE_FIELDS = {
    "dramatic_objective", "audience_question", "character_intents", "beat_map",
    "relationship_power_shift", "audience_emotion", "information_strategy",
    "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy",
    "edit_rhythm", "constraints", "unknowns",
    # Phase B enrichments are stored in the existing director_decisions
    # projection and remain candidate-only until the normal confirmation
    # boundary succeeds.
    "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out",
    "suspicion_or_information_strategy", "character_directions", "beat_directions",
    "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent",
    "prohibited_interpretations",
    "proposal_origin", "proposal_provenance",
}


def _validate_llm_candidate(raw: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    if str(baseline.get("schema_version") or "") == "director_treatment_v3":
        return _validate_source_grounded_llm_candidate(raw, baseline)
    if not isinstance(raw, dict):
        raise ValueError("DirectorTreatment LLM output must be a JSON object")
    # Models often echo the frozen scene identity. It is evidence, not an
    # editable candidate field: accept it only when it exactly matches the
    # baseline, then omit it from the persisted proposal.
    permitted = TREATMENT_CANDIDATE_FIELDS | {"scene_id", "scene_name", "decision", "confidence", "human_confirmation_required", "note"}
    unexpected = sorted(set(raw) - permitted)
    if unexpected:
        raise ValueError(f"LLM candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    if "scene_name" in raw and str(raw.get("scene_name") or "").strip() != str(baseline.get("scene_name") or "").strip():
        raise ValueError("LLM candidate scene_name must match the frozen scene")
    if "scene_id" in raw and str(raw.get("scene_id") or "").strip() != str(baseline.get("scene_id") or "").strip():
        raise ValueError("LLM candidate scene_id must match the frozen scene")
    candidate = {field: raw.get(field, baseline.get(field)) for field in TREATMENT_CANDIDATE_FIELDS}
    base_intents = baseline.get("character_intents") if isinstance(baseline.get("character_intents"), dict) else {}
    intents = candidate.get("character_intents")
    if not isinstance(intents, dict) or not set(intents).issubset(set(base_intents)):
        raise ValueError("LLM candidate character_intents must use only declared character ids")
    # Character identity is evidence, not a creative field.  Merge editable
    # intent suggestions onto the frozen baseline and always retain the
    # baseline name (and any omitted fields) so an LLM response cannot turn an
    # asset id into a display name or silently drop a declared participant.
    candidate["character_intents"] = {
        key: {
            **(base_intents.get(key) if isinstance(base_intents.get(key), dict) else {}),
            **(intents.get(key) if isinstance(intents.get(key), dict) else {}),
        }
        for key in base_intents
    }
    for key, base_intent in base_intents.items():
        if isinstance(base_intent, dict) and base_intent.get("name"):
            candidate["character_intents"][key]["name"] = base_intent["name"]
    base_beats = baseline.get("beat_map") if isinstance(baseline.get("beat_map"), list) else []
    beat_ids = {str(item.get("beat_id")) for item in base_beats if isinstance(item, dict)}
    beats = candidate.get("beat_map")
    # A proposer may omit derived beat annotations, but it may not alter the
    # source beat identity, type or event.  Normalize partial echoes back to
    # the frozen source representation before persisting the candidate.
    if not isinstance(beats, list) or len(beats) != len(base_beats):
        raise ValueError("LLM candidate beat_map must preserve the source beat set")
    for proposed, source in zip(beats, base_beats):
        if not isinstance(proposed, dict) or str(proposed.get("beat_id") or "") != str(source.get("beat_id") or ""):
            raise ValueError("LLM candidate beat_map must preserve source beat ids and order")
        for key in ("type", "event", "dramatic_function", "information_change", "emotion_change"):
            if key in proposed and proposed.get(key) != source.get(key):
                raise ValueError(f"LLM candidate beat_map source field is immutable: {key}")
    candidate["beat_map"] = base_beats
    candidate["decision"] = str(raw.get("decision") or "ready_for_review")
    candidate["confidence"] = raw.get("confidence", 0.0)
    candidate["human_confirmation_required"] = True
    candidate["note"] = str(raw.get("note") or "LLM candidate only; no domain write performed.")
    return validate_treatment_candidate(candidate, baseline)


def _build_preview(book_id: int, req: DirectorTreatmentPreviewRequest) -> tuple[dict[str, Any], dict[str, Any], Script]:
    with Session() as session:
        script_row = (
            session.query(Script)
            .filter_by(book_id=book_id, episode=req.episode)
            .order_by(Script.id.desc())
            .first()
        )
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        profile = str(req.workflow_profile or "creative_draft").strip().lower()
        if profile == "production":
            scene, script_ir_version, script, script_ir_envelope = resolve_scene_for_treatment(
                session, script_row, scene_id=req.scene_id, scene_name=req.scene_name, workflow_profile=profile
            )
        else:
            script = resolve_script_payload(session, script_row, workflow_profile=profile)
            scene = _find_scene(script, req.scene_name)
            script_ir_version = None
            script_ir_envelope = None
        characters = []
        makeup_rows = session.query(VisualMakeup).filter_by(book_id=book_id, episode=req.episode).order_by(VisualMakeup.id).all()
        # A treatment is scene-scoped.  When ScriptIR explicitly declares the
        # scene participants, only those bound assets belong in the treatment
        # evidence.  Falling back to all episode assets when the declaration is
        # absent preserves legacy behaviour and keeps missing participant data
        # visible as a blocker instead of silently guessing.
        participant_refs: set[str] = set()
        raw_participants = scene.get("participants") if isinstance(scene, dict) else []
        if isinstance(raw_participants, list):
            for item in raw_participants:
                if isinstance(item, dict):
                    for key in ("id", "character_id", "name", "character"):
                        value = str(item.get(key) or "").strip()
                        if value:
                            participant_refs.add(value)
                else:
                    value = str(item or "").strip()
                    if value:
                        participant_refs.add(value)
        if profile == "production" and not participant_refs:
            # Some deterministic screenplay compilers preserve the scene
            # identity but omit the optional participant projection.  The
            # episode outline already contains the source-derived cast; use
            # it as advisory evidence for this review packet without writing
            # back to ScriptIR or promoting an asset.
            outline = (
                session.query(EpisodeOutline)
                .filter_by(book_id=book_id, episode=req.episode)
                .order_by(EpisodeOutline.id.desc())
                .first()
            )
            outline_chars = str(getattr(outline, "characters", "") or "") if outline else ""
            for value in re.split(r"[,，、\\n]+", outline_chars):
                value = value.strip()
                if value:
                    participant_refs.add(value)
        if participant_refs:
            makeup_rows = [
                row for row in makeup_rows
                if str(row.id) in participant_refs or str(row.character_name or "").strip() in participant_refs
            ]
        for row in makeup_rows:
            meta = _json_object(row.meta_info, {})
            structured = meta.get("structured_result") if isinstance(meta, dict) else {}
            characters.append({
                "id": str(row.id),
                "name": row.character_name,
                "gender": str(structured.get("gender") or "") if isinstance(structured, dict) else "",
                "asset_status": row.asset_status,
                "stage_name": row.stage_name,
                "refined_outfit": row.refined_outfit,
                "hair_style": row.hair_style,
            })
        if profile == "production" and participant_refs and not characters:
            # Preserve ScriptIR-declared participant identity as advisory
            # context when no locked makeup asset exists.  This keeps the
            # semantic contract referenceable without promoting a draft asset
            # into production authority.
            characters = [{"id": value, "name": value, "gender": "", "asset_status": "draft", "stage_name": "", "refined_outfit": "", "hair_style": ""} for value in sorted(participant_refs)]
        locked_refs = [
            {"id": row.id, "asset_type": row.asset_type, "asset_id": row.asset_id, "asset_name": row.asset_name, "status": row.status, "image_url": row.image_url, "local_path": row.local_path, "reference_token": row.reference_token, "revision": row.updated_at.isoformat() if row.updated_at else ""}
            for row in session.query(VisualReferenceAsset)
            .filter_by(book_id=book_id, episode=req.episode, status="locked")
            .order_by(VisualReferenceAsset.id)
        ]

        legacy_script_hash = hashlib.sha256((script_row.content or "").encode("utf-8")).hexdigest()
        if profile == "production":
            source_revision = str(script_ir_version.revision)
            source_hash = str(script_ir_version.payload_hash or "")
            source_authority_fingerprint = str((script_ir_envelope or {}).get("envelope_fingerprint") or "")
        else:
            # Client source revision is intentionally retained only for the
            # creative/legacy path.  Production takes all lineage from the
            # current ScriptIR authority envelope.
            source_revision = req.source_script_revision.strip() or f"script-{script_row.id}"
            source_hash = legacy_script_hash
            source_authority_fingerprint = ""
        script_evidence = {"id": script_row.id, "revision": source_revision, "hash": source_hash, "script_ir_version_id": getattr(script_ir_version, "id", None), "script_ir_payload_hash": getattr(script_ir_version, "payload_hash", ""), "script_ir_authority_fingerprint": source_authority_fingerprint}
        if profile != "production":
            script_evidence["legacy_content_hash"] = legacy_script_hash
        evidence = {
            "book_id": book_id,
            "episode": req.episode,
            "scene": scene,
            "scene_id": str(scene.get("scene_id") or "").strip(),
            "scene_name": str(scene.get("name") or "").strip(),
            "scene_identity": {"scene_id": str(scene.get("scene_id") or "").strip(), "scene_name": str(scene.get("name") or "").strip()},
            "script": script_evidence,
            "characters": characters,
            "locked_references": locked_refs,
            "constraints": ["locked_asset_facts_are_immutable", "treatment_does_not_mutate_shots"],
        }
        evidence["evidence_fingerprint"] = _evidence_fingerprint(evidence)
        source_grounded = profile == "production" and is_source_grounded_scene(scene)
        treatment = build_source_grounded_director_preview(
            scene=scene,
            source_script_revision=source_revision,
            source_script_hash=source_hash,
            source_script_ir_version_id=getattr(script_ir_version, "id", None),
        ) if source_grounded else build_shadow_treatment(
            scene=scene,
            characters=characters,
            source_script_revision=source_revision,
            skill_id=req.skill_id.strip(),
            skill_version=req.skill_version.strip(),
        )
        treatment["scene_id"] = str(scene.get("scene_id") or "").strip()
        treatment["source_script_hash"] = source_hash
        treatment["source_script_ir_version_id"] = getattr(script_ir_version, "id", None)
        treatment["source_script_ir_revision"] = getattr(script_ir_version, "revision", None)
        treatment["source_script_ir_hash"] = getattr(script_ir_version, "payload_hash", "")
        treatment["source_script_authority_fingerprint"] = source_authority_fingerprint
        treatment["source_fact_snapshot_id"] = (script_ir_envelope or {}).get("fact_snapshot_id", "") if profile == "production" else ""
        treatment["source_fact_snapshot_revision"] = (script_ir_envelope or {}).get("fact_snapshot_revision") if profile == "production" else None
        treatment["source_fact_snapshot_hash"] = (script_ir_envelope or {}).get("fact_snapshot_payload_hash", "") if profile == "production" else ""
        if not source_grounded:
            treatment["source_constraints"] = {
                "scene_identity": evidence["scene_identity"],
                "declared_participants": scene.get("participants") if isinstance(scene.get("participants"), list) else [],
                "source_beats": treatment.get("beat_map", []),
                "explicit_story_constraints": scene.get("required_visual_proofs") if isinstance(scene.get("required_visual_proofs"), list) else [],
            }
            treatment["director_decisions"] = {field: treatment.get(field) for field in ("dramatic_objective", "audience_question", "character_intents", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out", "suspicion_or_information_strategy", "character_directions", "beat_directions", "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent", "prohibited_interpretations") if treatment.get(field) not in (None, "", [], {})}
        treatment["asset_authority"] = classify_asset_authority({"characters": characters, "locked_references": locked_refs})
        treatment["qualification_state"] = "AUTHORING_REQUIRED" if source_grounded else ("REVIEW_REQUIRED" if profile == "production" else "DRAFT")
        if profile == "production" and not source_grounded:
            # Production preview carries a deterministic, reviewable semantic
            # candidate.  Confirmation still rewrites decision provenance at
            # the service boundary and revalidates the contract.
            treatment["director_contract_version"] = DIRECTOR_CONTRACT_VERSION
            treatment["director_beat_decisions"] = build_suggested_director_decisions(scene)
        if source_grounded:
            treatment["validation"] = validate_source_grounded_contract_v2(treatment, scene=scene, production=False)
        treatment["proposal_origin"] = "GENERATED_DRAFT"
        treatment["proposal_provenance"] = proposal_provenance("GENERATED_DRAFT", provider={"called": False, "calls": 0}, human_input=False)
        treatment["evidence_fingerprint"] = evidence["evidence_fingerprint"]
        if source_grounded:
            # V3 previews do not use the legacy shadow builder's prompt hash,
            # but DecisionPacket still needs one stable treatment fingerprint
            # for deduplication and the explicit human confirmation boundary.
            treatment["source_authoring_units_fingerprint"] = treatment.get("source_authoring_units_fingerprint") or hashlib.sha256(json.dumps(treatment.get("source_constraints", {}).get("source_authoring_units", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            treatment["prompt_fingerprint"] = _candidate_fingerprint(treatment, evidence["evidence_fingerprint"])
        return treatment, evidence, script_row


def _treatment_row_payload(row: DirectorTreatment) -> dict[str, Any]:
    """Return a stable, JSON-friendly representation for UI and audit clients."""
    return {
        "id": row.id,
        "book_id": row.book_id,
        "episode": row.episode,
        "scene_id": getattr(row, "scene_id", ""),
        "scene_name": row.scene_name,
        "revision": row.revision,
        "status": row.status,
        "execution_status": row.execution_status,
        "quality_status": row.quality_status,
        "production_status": row.production_status,
        "workflow_profile": row.workflow_profile,
        "source_script_revision": row.source_script_revision,
        "source_script_hash": row.source_script_hash,
        "source_script_ir_version_id": getattr(row, "source_script_ir_version_id", None),
        "source_script_ir_revision": getattr(row, "source_script_ir_revision", None),
        "source_script_ir_hash": getattr(row, "source_script_ir_hash", ""),
        "source_script_authority_fingerprint": getattr(row, "source_script_authority_fingerprint", ""),
        "source_fact_snapshot_id": getattr(row, "source_fact_snapshot_id", ""),
        "source_fact_snapshot_revision": getattr(row, "source_fact_snapshot_revision", None),
        "source_fact_snapshot_hash": getattr(row, "source_fact_snapshot_hash", ""),
        "dramatic_objective": row.dramatic_objective,
        "audience_question": row.audience_question,
        "character_intents": _json_object(row.character_intents, {}),
        "beat_map": _json_object(row.beat_map, []),
        "source_constraints": _json_object(getattr(row, "source_constraints", "{}"), {}),
        "director_decisions": _json_object(getattr(row, "director_decisions", "{}"), {}),
        "schema_version": (_json_object(getattr(row, "source_constraints", "{}"), {}) or {}).get("schema_version", "") if isinstance(_json_object(getattr(row, "source_constraints", "{}"), {}), dict) else "",
        "unknown_unresolved": _json_object(getattr(row, "unknown_unresolved", "[]"), []),
        "relationship_power_shift": row.relationship_power_shift,
        "audience_emotion": row.audience_emotion,
        "information_strategy": row.information_strategy,
        "performance_direction": row.performance_direction,
        "visual_strategy": row.visual_strategy,
        "coverage_strategy": row.coverage_strategy,
        "sound_strategy": row.sound_strategy,
        "edit_rhythm": row.edit_rhythm,
        "constraints": _json_object(row.constraints, []),
        "unknowns": _json_object(row.unknowns, []),
        "skill_id": row.skill_id,
        "skill_version": row.skill_version,
        "decision_packet_id": row.decision_packet_id,
        "model_info": _json_object(row.model_info, {}),
        "prompt_fingerprint": row.prompt_fingerprint,
        "payload_hash": getattr(row, "payload_hash", ""),
        "authority_envelope_id": getattr(row, "authority_envelope_id", None),
        "qualification_state": getattr(row, "qualification_state", "DRAFT"),
        "stale_status": getattr(row, "stale_status", "UNKNOWN"),
        "stale_reasons": _json_object(getattr(row, "stale_reasons", "[]"), []),
        "approved_at": getattr(row, "approved_at", None).isoformat() if getattr(row, "approved_at", None) else None,
        "activated_at": getattr(row, "activated_at", None).isoformat() if getattr(row, "activated_at", None) else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


_TREATMENT_DIFF_FIELDS = (
    "dramatic_objective", "audience_question", "character_intents", "beat_map",
    "relationship_power_shift", "audience_emotion", "information_strategy",
    "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy",
    "edit_rhythm", "constraints", "unknowns",
)


def _treatment_diff(previous: DirectorTreatment | None, current: DirectorTreatment) -> dict[str, Any]:
    """Build a compact, deterministic diff suitable for history/replay UI."""
    if not previous:
        return {"from_revision": None, "changed_fields": list(_TREATMENT_DIFF_FIELDS), "changes": {}}
    changes: dict[str, dict[str, Any]] = {}
    for field in _TREATMENT_DIFF_FIELDS:
        before = getattr(previous, field)
        after = getattr(current, field)
        if field in {"character_intents", "beat_map", "constraints", "unknowns"}:
            before_value = _json_object(before, {} if field == "character_intents" else [])
            after_value = _json_object(after, {} if field == "character_intents" else [])
        else:
            before_value, after_value = before or "", after or ""
        if before_value != after_value:
            changes[field] = {"before": before_value, "after": after_value}
    return {"from_revision": previous.revision, "changed_fields": sorted(changes), "changes": changes}


@router.post("/{book_id}/episodes/{episode}/director-treatment/preview")
def preview_director_treatment(book_id: int, episode: int, req: DirectorTreatmentPreviewRequest) -> dict[str, Any]:
    if req.episode is not None and episode != req.episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    req.episode = episode
    treatment, evidence, script_row = _build_preview(book_id, req)
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    persisted_id = None
    if req.persist:
        with Session() as session:
            existing = (
                session.query(DirectorTreatment)
                .filter_by(book_id=book_id, episode=episode, scene_name=treatment["scene_name"], scene_id=treatment.get("scene_id", ""), prompt_fingerprint=treatment["prompt_fingerprint"])
                .order_by(DirectorTreatment.id.desc())
                .first()
            )
            if existing:
                persisted_id = existing.id
            else:
                row = DirectorTreatment(
                    book_id=book_id,
                    episode=episode,
                    scene_id=treatment.get("scene_id", ""),
                    scene_name=treatment["scene_name"],
                    revision=1,
                    status="draft",
                    source_script_revision=treatment["source_script_revision"],
                    source_script_hash=treatment["source_script_hash"],
                    source_script_ir_version_id=treatment.get("source_script_ir_version_id"),
                    source_script_ir_revision=treatment.get("source_script_ir_revision"),
                    source_script_ir_hash=treatment.get("source_script_ir_hash", ""),
                    source_script_authority_fingerprint=treatment.get("source_script_authority_fingerprint", ""),
                    source_fact_snapshot_id=str(treatment.get("source_fact_snapshot_id") or ""),
                    source_fact_snapshot_revision=treatment.get("source_fact_snapshot_revision"),
                    source_fact_snapshot_hash=treatment.get("source_fact_snapshot_hash", ""),
                    dramatic_objective=treatment["dramatic_objective"],
                    audience_question=treatment["audience_question"],
                    character_intents=json.dumps(treatment["character_intents"], ensure_ascii=False),
                    beat_map=json.dumps(treatment["beat_map"], ensure_ascii=False),
                    source_constraints=json.dumps(treatment.get("source_constraints", {}), ensure_ascii=False),
                    director_decisions=json.dumps(treatment.get("director_decisions", {}), ensure_ascii=False),
                    unknown_unresolved=json.dumps(treatment.get("unknowns", []), ensure_ascii=False),
                    relationship_power_shift=treatment["relationship_power_shift"],
                    audience_emotion=treatment["audience_emotion"],
                    information_strategy=treatment["information_strategy"],
                    performance_direction=treatment["performance_direction"],
                    visual_strategy=treatment["visual_strategy"],
                    coverage_strategy=treatment["coverage_strategy"],
                    sound_strategy=treatment["sound_strategy"],
                    edit_rhythm=treatment["edit_rhythm"],
                    constraints=json.dumps(treatment["constraints"], ensure_ascii=False),
                    unknowns=json.dumps(treatment["unknowns"], ensure_ascii=False),
                    skill_id=treatment["skill_id"],
                    skill_version=treatment["skill_version"],
                    model_info=json.dumps(treatment["model_info"], ensure_ascii=False),
                    prompt_fingerprint=treatment["prompt_fingerprint"],
                    payload_hash=treatment_payload_hash({key: treatment.get(key) for key in ("scene_id", "scene_name", *TREATMENT_CANDIDATE_FIELDS)}),
                    qualification_state=treatment.get("qualification_state", "DRAFT"),
                    stale_status="FRESH" if req.workflow_profile == "production" else "UNKNOWN",
                    stale_reasons="[]",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    workflow_profile=req.workflow_profile,
                )
                session.add(row)
                session.commit()
                persisted_id = row.id
    return {
        "mode": "shadow_deterministic",
        "llm_called": False,
        "mutated": bool(persisted_id),
        "persisted_draft_id": persisted_id,
        "script_id": script_row.id,
        "evidence": evidence,
        "packet_fingerprint": packet["packet_fingerprint"],
        "treatment": treatment,
        "authority_context": {
            "workflow_profile": req.workflow_profile,
            "scene_id": evidence.get("scene_id", ""),
            "source_constraints": treatment.get("source_constraints", {}),
            "director_decisions": treatment.get("director_decisions", {}),
            "unknown_unresolved": treatment.get("unknowns", []),
            "asset_authority": treatment.get("asset_authority", {}),
        },
        "requires_approval": True,
        "review_status": "REVIEW_REQUIRED" if str(req.workflow_profile or "").strip().lower() == "production" else "DRAFT",
        "production_contract_required": str(req.workflow_profile or "").strip().lower() == "production",
        "required_production_fields": (["source_constraints.source_authoring_units", "creative_projection"] if treatment.get("schema_version") == "director_treatment_v3" else ["director_contract_version", "director_beat_decisions"]) if str(req.workflow_profile or "").strip().lower() == "production" else [],
        "message": "这是只读导演方案草案；批准门禁和 SceneBlocking 尚未执行。",
    }


@router.post("/{book_id}/episodes/{episode}/director-treatment/beat-plan/llm-draft")
def generate_director_beat_plan_llm_draft(book_id: int, episode: int, req: DirectorBeatPlanLlmDraftRequest) -> dict[str, Any]:
    """Stage A execution boundary.  It never runs Stage B or final compile."""
    if req.episode is not None and req.episode != episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    if not str(req.scene_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED"})
    if not (req.confirmed and req.allow_external_call):
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_CONFIRMATION_REQUIRED"})
    if not str(req.authorization_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_AUTHORIZATION_ID_REQUIRED"})
    if str(req.workflow_profile or "production").strip().lower() != "production":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_PRODUCTION_ONLY"})
    preview_req = DirectorTreatmentPreviewRequest(episode=episode, scene_id=req.scene_id, workflow_profile="production")
    treatment, evidence, _ = _build_preview(book_id, preview_req)
    if str(treatment.get("scene_id") or "") != str(req.scene_id):
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Requested scene is not the frozen source scene."})
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    if req.packet_fingerprint and req.packet_fingerprint != packet["packet_fingerprint"]:
        raise HTTPException(status_code=409, detail="Treatment evidence changed; reload the preview before calling the LLM.")
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=book_id, packet_fingerprint=packet["packet_fingerprint"]).first()
        if not row:
            row = DecisionPacketRecord(book_id=book_id, domain="director_treatment", scope=json.dumps(packet["scope"], ensure_ascii=False), packet_fingerprint=packet["packet_fingerprint"], evidence=json.dumps(packet["evidence"], ensure_ascii=False), unknowns=json.dumps(packet["unknowns"], ensure_ascii=False), conflicts=json.dumps(packet["conflicts"], ensure_ascii=False), allowed_operations=json.dumps(packet["allowed_operations"], ensure_ascii=False), proposal=json.dumps({"decision": "awaiting_llm"}, ensure_ascii=False), model_info=json.dumps({"mode": "progressive_director_authoring", "proposal_provenance": proposal_provenance("GENERATED_DRAFT", provider={"called": False, "calls": 0})}, ensure_ascii=False))
            session.add(row); session.commit(); session.refresh(row)
        info = _json_object(row.model_info, {})
        info = info if isinstance(info, dict) else {}
        if info.get("llm_draft_in_progress"):
            raise HTTPException(status_code=409, detail="This Director packet already has an LLM request in progress.")
        row.model_info = json.dumps({**info, "llm_draft_in_progress": True, "llm_draft_started_at": datetime.now().isoformat()}, ensure_ascii=False)
        row.status = "draft"; session.commit(); packet_id = row.id
    return _execute_source_grounded_beat_plan(book_id=book_id, packet_id=packet_id, packet_fingerprint_value=packet["packet_fingerprint"], treatment=treatment, evidence=evidence, scene_id=req.scene_id, authorization_id=req.authorization_id)


@router.post("/{book_id}/episodes/{episode}/director-treatment/creative-enrichment/llm-draft")
def generate_director_creative_enrichment_llm_draft(book_id: int, episode: int, req: DirectorCreativeEnrichmentLlmDraftRequest) -> dict[str, Any]:
    """Stage B boundary preflight.

    This phase deliberately stops before transport.  It proves that the
    frozen Stage A materialization, prompt identity, and confirmation gate are
    ready for a future authorized Attempt 8.
    """
    if req.episode is not None and req.episode != episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    if not str(req.scene_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED"})
    if str(req.workflow_profile or "production").strip().lower() != "production":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_PRODUCTION_ONLY"})
    preview_req = DirectorTreatmentPreviewRequest(episode=episode, scene_id=req.scene_id, workflow_profile="production")
    treatment, evidence, _ = _build_preview(book_id, preview_req)
    if str(treatment.get("scene_id") or "") != str(req.scene_id):
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Requested scene is not the frozen source scene."})
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    if not str(req.packet_fingerprint or "").strip():
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PACKET_FINGERPRINT_REQUIRED"})
    if req.packet_fingerprint != packet["packet_fingerprint"]:
        raise HTTPException(status_code=409, detail="Treatment evidence changed; reload the preview before calling Stage B.")
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=book_id, packet_fingerprint=packet["packet_fingerprint"]).first()
        info = _json_object(row.model_info, {}) if row else {}
    progressive = info.get("progressive_director_authoring") if isinstance(info, dict) else {}
    stage_a = progressive.get("stage_a") if isinstance(progressive, dict) else None
    if not is_progressive_stage_validated(stage_a, authoring_stage="BEAT_PLAN"):
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_BEAT_PLAN_VALIDATION_REQUIRED"})
    materialized = stage_a.get("materialized_beat_plan") if isinstance(stage_a, dict) else None
    materialized_fp = str(stage_a.get("materialized_fingerprint") or "") if isinstance(stage_a, dict) else ""
    constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
    profile, profile_snapshot = _director_llm_profile_preflight()
    identity = build_director_creative_enrichment_provider_request(
        scene_id=req.scene_id, materialized_beat_plan=materialized if isinstance(materialized, dict) else {},
        stage_a_materialized_fingerprint=materialized_fp,
        stage_a_attempt_id=str(stage_a.get("attempt_id") or "") if isinstance(stage_a, dict) else "",
        declared_participants=constraints.get("declared_participants") if isinstance(constraints.get("declared_participants"), list) else [],
        source_authoring_units=constraints.get("source_authoring_units") if isinstance(constraints.get("source_authoring_units"), list) else [],
        source_authoring_unit_fingerprint=str(treatment.get("source_authoring_units_fingerprint") or ""),
        profile=profile, profile_snapshot=profile_snapshot,
    )
    if is_progressive_stage_validated(progressive.get("stage_b") if isinstance(progressive, dict) else None, authoring_stage="CREATIVE_ENRICHMENT") or _json_object(row.proposal, {}).get("decision") == "ready_for_review":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_ALREADY_COMPLETED"})
    if not (req.confirmed and req.allow_external_call and str(req.authorization_id or "").strip()):
        next_context = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
        return {"status": next_context.status("AUTHORIZATION_REQUIRED"), "provider": {"called": False, "calls": 0}, "execution_manifest": identity}
    with Session() as session:
        current = session.query(DecisionPacketRecord).filter_by(id=row.id, book_id=book_id).first()
        current_info = _json_object(current.model_info, {}) if current else {}
        if not current or not isinstance(current_info, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PACKET_NOT_FOUND"})
        if current_info.get("llm_draft_in_progress"):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_EXECUTION_IN_PROGRESS"})
        current_info["llm_draft_in_progress"] = True
        current_info["stage_b_execution_started_at"] = datetime.now().isoformat()
        current.model_info = json.dumps(current_info, ensure_ascii=False)
        current.status = "draft"
        session.commit()
    return _execute_source_grounded_creative_enrichment(
        book_id=book_id, packet_id=row.id, packet_fingerprint_value=packet["packet_fingerprint"],
        treatment=treatment, evidence=evidence, scene_id=req.scene_id, authorization_id=req.authorization_id,
        identity=identity, profile=profile,
    )


@router.post("/{book_id}/episodes/{episode}/director-treatment/creative-enrichment/revision/llm-draft")
def generate_director_creative_enrichment_revision_llm_draft(book_id: int, episode: int, req: DirectorCreativeEnrichmentRevisionLlmDraftRequest) -> dict[str, Any]:
    """Explicit append-only semantic revision boundary for Stage B.

    The initial Stage B endpoint remains idempotent and continues to reject a
    completed proposal.  This endpoint is the only route that can authorize a
    new CreativeEnrichment attempt after a semantic rejection.
    """
    if req.episode is not None and req.episode != episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    if not str(req.scene_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED"})
    if str(req.workflow_profile or "production").strip().lower() != "production":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_PRODUCTION_ONLY"})
    if not str(req.packet_fingerprint or "").strip():
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PACKET_FINGERPRINT_REQUIRED"})
    treatment, evidence, _ = _build_preview(book_id, DirectorTreatmentPreviewRequest(episode=episode, scene_id=req.scene_id, workflow_profile="production"))
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    if req.packet_fingerprint != packet["packet_fingerprint"]:
        # Production packets are append-only historical authorities.  A later
        # preview builder may legitimately derive a different legacy treatment
        # fingerprint after the packet was persisted, while the requested
        # packet row still binds the same canonical book/episode/scene.  Resolve
        # the supplied packet identity first and let the source projection and
        # content race gates below decide whether it is still executable.
        with Session() as session:
            historical = session.query(DecisionPacketRecord).filter_by(
                book_id=book_id, packet_fingerprint=req.packet_fingerprint, domain="director_treatment"
            ).first()
            historical_scope = _json_object(historical.scope, {}) if historical else {}
        if not historical or not (
            int(historical_scope.get("book_id") or -1) == int(book_id)
            and int(historical_scope.get("episode") or -1) == int(episode)
            and str(historical_scope.get("scene_id") or "") == str(req.scene_id)
        ):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_EVIDENCE_STALE"})
        packet = {"packet_fingerprint": req.packet_fingerprint}
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=book_id, packet_fingerprint=packet["packet_fingerprint"], domain="director_treatment").first()
        if not row:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PACKET_NOT_FOUND"})
        info = _json_object(row.model_info, {})
        info = info if isinstance(info, dict) else {}
        proposal = _json_object(row.proposal, {})
        proposal = proposal if isinstance(proposal, dict) else {}
        # Attempt-8 was persisted before the V7.6.13 review envelope became a
        # packet field. Reconstruct that deterministic review in memory when
        # the historical row has only the raw IR and proposal evidence. This
        # is read-only preflight state; it is never written before the single
        # authorized revision transport.
        progressive_for_review = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
        stage_b_for_review = progressive_for_review.get("stage_b") if isinstance(progressive_for_review, dict) else {}
        current_review_for_eligibility = stage_b_for_review.get("semantic_review") if isinstance(stage_b_for_review, dict) and isinstance(stage_b_for_review.get("semantic_review"), dict) else (info.get("semantic_review") if isinstance(info.get("semantic_review"), dict) else None)
        if current_review_for_eligibility is None and isinstance(stage_b_for_review, dict) and isinstance(stage_b_for_review.get("ir"), dict):
            source_constraints_for_review = proposal.get("source_constraints") if isinstance(proposal.get("source_constraints"), dict) else {}
            current_review_for_eligibility = validate_director_creative_semantic_review(
                stage_b_for_review["ir"],
                source_authoring_units=source_constraints_for_review.get("source_authoring_units") if isinstance(source_constraints_for_review.get("source_authoring_units"), list) else [],
                declared_participants=source_constraints_for_review.get("declared_participants") if isinstance(source_constraints_for_review.get("declared_participants"), list) else [],
            )
            info_for_eligibility = copy.deepcopy(info)
            info_for_eligibility.setdefault("semantic_review", current_review_for_eligibility)
            info_for_eligibility.setdefault("progressive_director_authoring", {}).setdefault("stage_b", {})["semantic_review"] = current_review_for_eligibility
        else:
            info_for_eligibility = info
        eligibility = evaluate_stage_b_semantic_revision_eligibility(info_for_eligibility, proposal, packet_status=str(row.status or "draft"))
        if not eligibility.get("eligible"):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_BOUNDARY_BLOCKED", "eligibility": eligibility, "provider_calls": 0})
        progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
        stage_a = progressive.get("stage_a") if isinstance(progressive, dict) else {}
        stage_b = progressive.get("stage_b") if isinstance(progressive, dict) else {}
        current_attempt_id = str(stage_b.get("attempt_id") or "")
        current_stage_b_fp = str(stage_b.get("ir_fingerprint") or stage_b.get("fingerprint") or "")
        current_review = current_review_for_eligibility if isinstance(current_review_for_eligibility, dict) else (stage_b.get("semantic_review") if isinstance(stage_b, dict) and isinstance(stage_b.get("semantic_review"), dict) else (info.get("semantic_review") if isinstance(info.get("semantic_review"), dict) else {}))
        current_review_fp = semantic_review_fingerprint(current_review)
        if req.revision_of_attempt_id != current_attempt_id:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_PARENT_MISMATCH", "expected": current_attempt_id, "received": req.revision_of_attempt_id, "provider_calls": 0})
        if req.revision_of_stage_b_ir_fingerprint != current_stage_b_fp:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_STAGE_B_FINGERPRINT_MISMATCH", "expected": current_stage_b_fp, "received": req.revision_of_stage_b_ir_fingerprint, "provider_calls": 0})
        if req.semantic_review_fingerprint != current_review_fp:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_SEMANTIC_REVIEW_FINGERPRINT_MISMATCH", "expected": current_review_fp, "received": req.semantic_review_fingerprint, "provider_calls": 0})
        before_info = copy.deepcopy(info)
        before_proposal_json = str(row.proposal or "")
    treatment_constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
    # Attempt-8 was generated from the persisted projection contract.  Keep
    # that exact projection as the revision prompt input while deriving the
    # current canonical projection/content fingerprints from the source scene.
    # This preserves the known projection-version drift classification instead
    # of silently normalizing the parent prompt to a different identity.
    proposal_constraints = proposal.get("source_constraints") if isinstance(proposal.get("source_constraints"), dict) else {}
    constraints = proposal_constraints if isinstance(proposal_constraints.get("source_authoring_units"), list) else treatment_constraints
    canonical_scene = evidence.get("scene") if isinstance(evidence.get("scene"), dict) else {}
    canonical_units = project_source_authoring_units(canonical_scene)
    current_units = constraints.get("source_authoring_units") if isinstance(constraints.get("source_authoring_units"), list) else []
    source_reconciliation = reconcile_source_authoring_units(canonical_units, current_units)
    if source_reconciliation.get("status") != "PASS":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_STAGE_A_SOURCE_AUTHORITY_STALE", "source_reconciliation": source_reconciliation, "provider_calls": 0})
    source_projection_fp = str(treatment.get("source_authoring_units_fingerprint") or "")
    source_content_fp = source_authority_content_fingerprint(canonical_units)
    stage_a_provider_request = before_info.get("stage_a_provider_request") if isinstance(before_info.get("stage_a_provider_request"), dict) else {}
    stage_a_source_fp = str(stage_a_provider_request.get("source_authoring_unit_fingerprint") or treatment.get("source_authoring_units_fingerprint") or "")
    if stage_a_source_fp and stage_a_source_fp != source_projection_fp:
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_STAGE_A_SOURCE_AUTHORITY_STALE", "stage_a_source_fingerprint": stage_a_source_fp, "current_source_projection_fingerprint": source_projection_fp, "provider_calls": 0})
    materialized = stage_a.get("materialized_beat_plan") if isinstance(stage_a, dict) else None
    materialized_fp = str(stage_a.get("materialized_fingerprint") or "") if isinstance(stage_a, dict) else ""
    revision_parent = build_revision_parent_identity(parent_attempt_id=current_attempt_id, parent_ir_fingerprint=current_stage_b_fp, semantic_review=current_review, stage_a_attempt_id=str(stage_a.get("attempt_id") or "") if isinstance(stage_a, dict) else "", stage_a_materialized_fingerprint=materialized_fp, source_authoring_unit_fingerprint=source_projection_fp, source_authority_content_fingerprint=source_content_fp)
    feedback = stage_b_revision_feedback(current_review)
    profile, profile_snapshot = _director_llm_profile_preflight()
    identity = build_director_creative_enrichment_provider_request(scene_id=req.scene_id, materialized_beat_plan=materialized if isinstance(materialized, dict) else {}, stage_a_materialized_fingerprint=materialized_fp, stage_a_attempt_id=str(stage_a.get("attempt_id") or "") if isinstance(stage_a, dict) else "", declared_participants=constraints.get("declared_participants") if isinstance(constraints.get("declared_participants"), list) else [], source_authoring_units=current_units, source_authoring_unit_fingerprint=source_projection_fp, source_authority_content_fingerprint=source_content_fp, revision_feedback=feedback, revision_parent=revision_parent, profile=profile, profile_snapshot=profile_snapshot)
    context = resolve_next_director_attempt_context(before_info, authoring_stage="CREATIVE_ENRICHMENT")
    existing_stage_b_archives = (
        (before_info.get("progressive_director_authoring") or {}).get("stage_b_attempts")
        if isinstance(before_info.get("progressive_director_authoring"), dict) else []
    )
    if any(isinstance(item, dict) and str(item.get("attempt_id") or "") == current_attempt_id for item in (existing_stage_b_archives if isinstance(existing_stage_b_archives, list) else [])):
        archive_preview = before_info
        archive_report = {"status": "PASS", "changed": False, "archived": False, "attempt_id": current_attempt_id, "archive_count": len(existing_stage_b_archives)}
    else:
        archive_preview, archive_report = archive_stage_b_attempt(before_info, proposal=proposal, attempt_id=current_attempt_id)
    manifest = {**identity, "revision_parent": revision_parent, "revision_feedback": feedback, "source_reconciliation": source_reconciliation, "archive_readiness": archive_report, "expected_attempt": context.attempt_id, "history_count": context.history_count, "authorization": "REQUIRED_NOT_GRANTED"}
    if not (req.confirmed and req.allow_external_call and str(req.authorization_id or "").strip()):
        return {"status": context.status("AUTHORIZATION_REQUIRED"), "provider": {"called": False, "calls": 0}, "provider_calls": 0, "confirm_allowed": False, "execution_manifest": manifest, "revision_parent": revision_parent, "source_reconciliation": source_reconciliation}
    revision_context = {"episode": episode, "before_info": before_info, "before_proposal_json": before_proposal_json, "revision_parent": revision_parent, "semantic_review_fingerprint": current_review_fp, "identity": identity}
    with Session() as session:
        current = session.query(DecisionPacketRecord).filter_by(id=row.id, book_id=book_id, packet_fingerprint=packet["packet_fingerprint"]).first()
        current_info = _json_object(current.model_info, {}) if current else {}
        current_info = current_info if isinstance(current_info, dict) else {}
        if not current or current_info.get("llm_draft_in_progress"):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_EXECUTION_IN_PROGRESS", "provider_calls": 0})
        # Historical Attempt-8 rows may predate persistence of the semantic
        # review envelope.  The read-only eligibility pass above reconstructs
        # that envelope deterministically; reuse the same reconstructed view
        # for the execution boundary instead of rejecting a request that has
        # already passed the exact parent/review gates.
        current_info_for_boundary = current_info
        current_progressive = current_info.get("progressive_director_authoring") if isinstance(current_info.get("progressive_director_authoring"), dict) else {}
        current_stage_b = current_progressive.get("stage_b") if isinstance(current_progressive, dict) else {}
        current_review_for_boundary = current_stage_b.get("semantic_review") if isinstance(current_stage_b, dict) and isinstance(current_stage_b.get("semantic_review"), dict) else (current_info.get("semantic_review") if isinstance(current_info.get("semantic_review"), dict) else None)
        current_proposal = _json_object(current.proposal, {})
        if current_review_for_boundary is None and isinstance(current_stage_b, dict) and isinstance(current_stage_b.get("ir"), dict):
            current_constraints = current_proposal.get("source_constraints") if isinstance(current_proposal.get("source_constraints"), dict) else {}
            current_review_for_boundary = validate_director_creative_semantic_review(
                current_stage_b["ir"],
                source_authoring_units=current_constraints.get("source_authoring_units") if isinstance(current_constraints.get("source_authoring_units"), list) else [],
                declared_participants=current_constraints.get("declared_participants") if isinstance(current_constraints.get("declared_participants"), list) else [],
            )
            current_info_for_boundary = copy.deepcopy(current_info)
            current_info_for_boundary.setdefault("semantic_review", current_review_for_boundary)
            current_info_for_boundary.setdefault("progressive_director_authoring", {}).setdefault("stage_b", {})["semantic_review"] = current_review_for_boundary
        if not is_stage_b_semantic_revision_required(current_info_for_boundary, current_proposal, packet_status=str(current.status or "draft")):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REVISION_BOUNDARY_BLOCKED", "provider_calls": 0})
        archived_info, _ = archive_stage_b_attempt(current_info, proposal=_json_object(current.proposal, {}), attempt_id=current_attempt_id)
        archived_info["llm_draft_in_progress"] = True
        archived_info["revision_execution_started_at"] = datetime.now().isoformat()
        archived_info["revision_boundary_status"] = context.status("AUTHORIZED")
        archived_info["revision_parent"] = revision_parent
        current.model_info = json.dumps(archived_info, ensure_ascii=False)
        current.status = "draft"
        session.commit()
    return _execute_source_grounded_creative_enrichment(book_id=book_id, packet_id=row.id, packet_fingerprint_value=packet["packet_fingerprint"], treatment=treatment, evidence=evidence, scene_id=req.scene_id, authorization_id=req.authorization_id, identity=identity, profile=profile, revision_context=revision_context)


@router.post("/{book_id}/episodes/{episode}/director-treatment/llm-draft")
def generate_director_treatment_llm_draft(book_id: int, episode: int, req: DirectorTreatmentLlmDraftRequest) -> dict[str, Any]:
    """Generate a reviewable Treatment candidate after explicit confirmation.

    The endpoint follows the DecisionPacket boundary: it freezes and validates
    the current evidence, requires ``confirmed`` + ``allowExternalCall``,
    deduplicates an identical completed request, and stores only a proposal in
    the packet record.  It never creates an approved Treatment or changes a
    script/shot.
    """
    if req.episode is not None and req.episode != episode:
        raise HTTPException(status_code=400, detail="Episode in path and body must match.")
    if not (req.confirmed and req.allow_external_call):
        raise HTTPException(status_code=409, detail="Calling the Treatment LLM requires confirmed=true and allowExternalCall=true.")
    req.episode = episode
    if str(req.workflow_profile or "").strip().lower() == "production" and not str(req.scene_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production Treatment requires a stable scene_id."})
    treatment, evidence, _ = _build_preview(book_id, req)
    if treatment.get("schema_version") == "director_treatment_v3" and str(req.workflow_profile or "").strip().lower() == "production":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROGRESSIVE_AUTHORING_REQUIRED", "message": "Use the dedicated BeatPlan endpoint for source-grounded production authoring."})
    if treatment.get("schema_version") == "director_treatment_v3" and not str(req.authorization_id or "").strip():
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_LLM_AUTHORIZATION_ID_REQUIRED", "message": "Source-grounded Director LLM execution requires an explicit authorization_id."})
    packet = _make_decision_packet(book_id, episode, treatment, evidence)
    if req.packet_fingerprint and req.packet_fingerprint != packet["packet_fingerprint"]:
        raise HTTPException(status_code=409, detail="Treatment evidence changed; reload the preview before calling the LLM.")

    source_grounded = treatment.get("schema_version") == "director_treatment_v3"
    prompt = "" if source_grounded else (
        "你是受证据约束的影视导演方案助手。仅输出 JSON object，不要 Markdown。\n"
        "根据以下冻结证据生成 DirectorTreatment 候选。只能改写候选字段，必须沿用已有 character id 和 beat_id；"
        "不得新增角色、道具、场景事实，不得输出镜头或执行操作。所有候选仍需人工确认。\n\n"
        f"FROZEN_EVIDENCE={json.dumps(evidence, ensure_ascii=False, sort_keys=True)}\n"
        f"BASE_TREATMENT={json.dumps(treatment, ensure_ascii=False, sort_keys=True)}\n"
        f"RETURN_FIELDS={json.dumps(sorted(TREATMENT_CANDIDATE_FIELDS), ensure_ascii=False)}"
    )

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=book_id, packet_fingerprint=packet["packet_fingerprint"]).first()
        if not row:
            row = DecisionPacketRecord(
                book_id=book_id,
                domain="director_treatment",
                scope=json.dumps(packet["scope"], ensure_ascii=False),
                packet_fingerprint=packet["packet_fingerprint"],
                evidence=json.dumps(packet["evidence"], ensure_ascii=False),
                unknowns=json.dumps(packet["unknowns"], ensure_ascii=False),
                conflicts=json.dumps(packet["conflicts"], ensure_ascii=False),
                allowed_operations=json.dumps(packet["allowed_operations"], ensure_ascii=False),
                proposal=json.dumps({"decision": "awaiting_llm"}, ensure_ascii=False),
                model_info=json.dumps({"mode": "director_treatment_proposal", "proposal_provenance": proposal_provenance("GENERATED_DRAFT", provider={"called": False, "calls": 0})}, ensure_ascii=False),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        info = _json_object(row.model_info, {})
        if isinstance(info, dict) and info.get("llm_draft_in_progress"):
            raise HTTPException(status_code=409, detail="This Treatment evidence packet already has an LLM request in progress.")
        existing_provenance = info.get("proposal_provenance") if isinstance(info, dict) else None
        if isinstance(existing_provenance, dict) and existing_provenance.get("proposal_origin") == "PROVIDER_PROPOSAL":
            return {"packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": _json_object(row.proposal, {}), **project_legacy_flags(existing_provenance), "deduplicated": True, "domain_write_performed": False}
        row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": True, "llm_draft_started_at": datetime.now().isoformat()}, ensure_ascii=False)
        row.status = "draft"
        session.commit()
        packet_id = row.id

        source_grounded_packet_id = packet_id if source_grounded else None

    if source_grounded:
        return _execute_source_grounded_v3_proposal(
            book_id=book_id,
            packet_id=source_grounded_packet_id,
            packet_fingerprint_value=packet["packet_fingerprint"],
            treatment=treatment,
            evidence=evidence,
            authorization_id=req.authorization_id,
        )

    audit_records: list[dict[str, Any]] = []
    try:
        raw = llm_client.call_llm_json(
            prompt,
            system="你是受证据约束的 DirectorTreatment 编译器。",
            required_keys={"dramatic_objective", "audience_question", "character_intents", "beat_map", "visual_strategy"},
            audit_callback=lambda record: audit_records.append(dict(record)) if isinstance(record, dict) else None,
            estimated_tokens=5000,
        )
        candidate = _validate_llm_candidate(raw, treatment)
    except Exception as exc:
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
            if row:
                info = _json_object(row.model_info, {})
                row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": False, "last_llm_draft_failure": str(exc)[:500]}, ensure_ascii=False)
                session.commit()
        raise HTTPException(status_code=502, detail=f"DirectorTreatment LLM draft failed: {str(exc)[:500]}") from exc

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id, book_id=book_id).first()
        if not row:
            raise HTTPException(status_code=409, detail="Treatment decision packet disappeared while the LLM was running.")
        info = _json_object(row.model_info, {})
        provider_record = audit_records[-1] if audit_records else {}
        provider = {"called": bool(audit_records), "calls": len(audit_records), "profile_id": provider_record.get("profile_id"), "model": provider_record.get("vendor_model"), "request_fingerprint": provider_record.get("request_fingerprint"), "response_fingerprint": provider_record.get("response_sha256")}
        provenance = proposal_provenance("PROVIDER_PROPOSAL", provider=provider)
        candidate["proposal_origin"] = "PROVIDER_PROPOSAL"
        candidate["proposal_provenance"] = provenance
        row.proposal = json.dumps(candidate, ensure_ascii=False)
        row.model_info = json.dumps({**(info if isinstance(info, dict) else {}), "llm_draft_in_progress": False, "proposal_provenance": provenance, "provider_audit": provider_record, "generated_at": datetime.now().isoformat(), **project_legacy_flags(provenance)}, ensure_ascii=False)
        row.status = "draft"
        row.updated_at = datetime.now()
        session.commit()
        return {"packet_id": row.id, "packet_fingerprint": row.packet_fingerprint, "candidate": candidate, **project_legacy_flags(provenance), "deduplicated": False, "domain_write_performed": False}


@router.get("/{book_id}/episodes/{episode}/director-treatments")
def list_director_treatments(book_id: int, episode: int) -> dict[str, Any]:
    """List Treatment revisions for the episode without exposing secrets."""
    with Session() as session:
        rows = (
            session.query(DirectorTreatment)
            .filter_by(book_id=book_id, episode=episode)
            .order_by(DirectorTreatment.scene_name, DirectorTreatment.revision.asc(), DirectorTreatment.id.asc())
            .all()
        )
    items = []
    previous_by_scene: dict[str, DirectorTreatment] = {}
    for row in rows:
        item = _treatment_row_payload(row)
        item["diff"] = _treatment_diff(previous_by_scene.get(row.scene_name), row)
        items.append(item)
        previous_by_scene[row.scene_name] = row
    items.sort(key=lambda item: (str(item["scene_name"]), -int(item["revision"]), -int(item["id"])))
    return {"items": items}


@router.get("/{book_id}/episodes/{episode}/director-treatment/candidates")
def list_director_treatment_candidates(book_id: int, episode: int) -> dict[str, Any]:
    """List auditable LLM candidates for history/replay without secrets."""
    with Session() as session:
        packets = (
            session.query(DecisionPacketRecord)
            .filter_by(book_id=book_id, domain="director_treatment")
            .order_by(DecisionPacketRecord.id.desc())
            .all()
        )
    items = []
    for packet in packets:
        scope = _json_object(packet.scope, {})
        if not isinstance(scope, dict) or int(scope.get("episode") or 0) != episode:
            continue
        items.append({
            "packet_id": packet.id,
            "packet_fingerprint": packet.packet_fingerprint,
            "scene_name": str(scope.get("scene_name") or ""),
            "status": packet.status,
            "candidate": _json_object(packet.proposal, {}),
            "model_info": _json_object(packet.model_info, {}),
            "confirmed_at": packet.confirmed_at.isoformat() if packet.confirmed_at else None,
            "created_at": packet.created_at.isoformat() if packet.created_at else None,
            "updated_at": packet.updated_at.isoformat() if packet.updated_at else None,
        })
    return {"items": items}


@router.post("/{book_id}/episodes/{episode}/director-treatment/confirm")
def confirm_director_treatment(book_id: int, episode: int, req: DirectorTreatmentConfirmRequest) -> dict[str, Any]:
    """Approve a reviewable candidate and create a new immutable revision.

    The packet is re-derived from the current script before any write.  A
    changed script, scene, or asset evidence invalidates the candidate and
    leaves the existing approved revision untouched.
    """
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="Treatment approval requires confirmed=true.")

    # Production approval is a single atomic boundary: the reviewed candidate
    # is persisted, its immutable authority envelope is created, and the
    # scene's current pointer is updated in one transaction.  Creative draft
    # retains the historical approval behaviour below.
    if str(req.workflow_profile or "creative_draft").strip().lower() == "production":
        return _confirm_production_director_treatment(book_id, episode, req)

    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
        if not packet or packet.domain != "director_treatment":
            raise HTTPException(status_code=404, detail="DirectorTreatment decision packet not found.")
        if req.packet_fingerprint and req.packet_fingerprint != packet.packet_fingerprint:
            raise HTTPException(status_code=409, detail="Treatment packet fingerprint does not match.")
        if packet.status in {"confirmed", "superseded"}:
            raise HTTPException(status_code=409, detail="This Treatment packet has already been finalized.")
        info = _json_object(packet.model_info, {})
        if not isinstance(info, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires proposal provenance."})
        progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
        stage_a = progressive.get("stage_a") if isinstance(progressive, dict) else None
        stage_b = progressive.get("stage_b") if isinstance(progressive, dict) else None
        # V7.6.16 policy versioning: once a progressive Stage B reaches
        # Attempt-9 or later, confirmation must cite an append-only V2
        # assessment bound to the active attempt and IR.  The reassessment is
        # intentionally not synthesized or written here; absence remains a
        # fail-closed review requirement.
        stage_b_attempt_id = str(stage_b.get("attempt_id") or "") if isinstance(stage_b, dict) else ""
        if stage_b_attempt_id.startswith("attempt-") and stage_b_attempt_id.split("-", 1)[1].isdigit() and int(stage_b_attempt_id.split("-", 1)[1]) >= 9:
            assessments = info.get("semantic_review_assessments") if isinstance(info.get("semantic_review_assessments"), list) else []
            assessment = stage_b.get("semantic_review_v2") if isinstance(stage_b, dict) and isinstance(stage_b.get("semantic_review_v2"), dict) else None
            if assessment is None:
                assessment = next((item for item in reversed(assessments) if isinstance(item, dict) and item.get("attempt_id") == stage_b_attempt_id), None)
            expected_ir = str(stage_b.get("ir_fingerprint") or stage_b.get("fingerprint") or "") if isinstance(stage_b, dict) else ""
            assessment_binding = validate_semantic_review_assessment_binding(assessment, attempt_id=stage_b_attempt_id, ir_fingerprint=expected_ir)
            if assessment_binding.get("status") != "PASS":
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_SEMANTIC_REVIEW_POLICY_REQUIRED", "required_policy": SEMANTIC_REVIEW_POLICY_V2, "active_attempt_id": stage_b_attempt_id, "production_writes": 0})
        if is_progressive_stage_validated(stage_a, authoring_stage="BEAT_PLAN") and not _progressive_stage_b_complete(info, _json_object(packet.proposal, {})):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REQUIRED", "message": "Stage A BeatPlan is not confirmable until Stage B creative enrichment is complete."})
        scope = _json_object(packet.scope, {})
        scene_name = str(scope.get("scene_name") or "").strip() if isinstance(scope, dict) else ""

    # Rebuild outside the transaction so the expensive evidence read does not
    # hold the packet row lock.  The fingerprint check below is the commit
    # boundary and protects against a changed script during the read.
    baseline, evidence, _ = _build_preview(book_id, DirectorTreatmentPreviewRequest(episode=episode, scene_name=scene_name, workflow_profile=req.workflow_profile))
    current_packet = _make_decision_packet(book_id, episode, baseline, evidence)
    if current_packet["packet_fingerprint"] != packet.packet_fingerprint:
        with Session() as session:
            stale = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
            if stale and stale.status == "draft":
                stale.status = "superseded"
                stale.updated_at = datetime.now()
                session.commit()
        raise HTTPException(status_code=409, detail="Treatment evidence changed; candidate is stale and must be regenerated.")

    raw_candidate = req.candidate if req.candidate is not None else _json_object(packet.proposal, {})
    try:
        candidate = _validate_llm_candidate(raw_candidate, baseline)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Treatment candidate is invalid: {exc}") from exc

    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id).first()
        if not packet or packet.status in {"confirmed", "superseded"}:
            raise HTTPException(status_code=409, detail="This Treatment packet has already been finalized.")
        previous = (
            session.query(DirectorTreatment)
            .filter_by(book_id=book_id, episode=episode, scene_name=baseline["scene_name"], status="approved")
            .order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc())
            .first()
        )
        next_revision = (previous.revision + 1) if previous else 1
        previous_id = previous.id if previous else None
        if previous:
            previous.status = "superseded"
            previous.updated_at = datetime.now()
        provenance_projection = project_legacy_flags(info.get("proposal_provenance")) if isinstance(info.get("proposal_provenance"), dict) else {"llm_called": False, "llm_generated": False}
        model_info = {
            **(baseline.get("model_info") if isinstance(baseline.get("model_info"), dict) else {}),
            "mode": "confirmed_director_candidate",
            **provenance_projection,
            "candidate_decision": candidate.get("decision"),
            "candidate_fingerprint": _candidate_fingerprint(candidate, current_packet["packet_fingerprint"]),
            "confirmed_at": datetime.now().isoformat(),
            "rollback_anchor": {"previous_treatment_id": previous_id, "previous_revision": previous.revision if previous else None},
        }
        row = DirectorTreatment(
            book_id=book_id, episode=episode, scene_name=baseline["scene_name"], revision=next_revision, status="approved",
            source_script_revision=baseline["source_script_revision"], source_script_hash=baseline["source_script_hash"],
            dramatic_objective=candidate["dramatic_objective"], audience_question=candidate["audience_question"],
            character_intents=json.dumps(candidate["character_intents"], ensure_ascii=False), beat_map=json.dumps(candidate["beat_map"], ensure_ascii=False),
            relationship_power_shift=candidate["relationship_power_shift"], audience_emotion=candidate["audience_emotion"], information_strategy=candidate["information_strategy"],
            performance_direction=candidate["performance_direction"], visual_strategy=candidate["visual_strategy"], coverage_strategy=candidate["coverage_strategy"],
            sound_strategy=candidate["sound_strategy"], edit_rhythm=candidate["edit_rhythm"], constraints=json.dumps(candidate["constraints"], ensure_ascii=False),
            unknowns=json.dumps(candidate["unknowns"], ensure_ascii=False), skill_id=baseline["skill_id"], skill_version=baseline["skill_version"],
            decision_packet_id=packet.id, model_info=json.dumps(model_info, ensure_ascii=False), prompt_fingerprint=_candidate_fingerprint(candidate, current_packet["packet_fingerprint"]),
            created_at=datetime.now(), updated_at=datetime.now(), workflow_profile=req.workflow_profile,
        )
        session.add(row)
        packet.status = "confirmed"
        packet.confirmed_at = datetime.now()
        packet.proposal = json.dumps(candidate, ensure_ascii=False)
        packet.updated_at = datetime.now()
        session.commit()
        session.refresh(row)
        return {
            "approved": True,
            "treatment": _treatment_row_payload(row),
            "packet_id": packet.id,
            "packet_fingerprint": packet.packet_fingerprint,
            "rollback_anchor": model_info["rollback_anchor"],
            "mutated": True,
            "production_operations": [],
        }


def _confirm_production_director_treatment(book_id: int, episode: int, req: DirectorTreatmentConfirmRequest) -> dict[str, Any]:
    """Authority-bound production Treatment activation; provider-free."""
    from core.director_treatment_authority import resolve_scene_for_treatment
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=req.packet_id, book_id=book_id, domain="director_treatment").first()
        if not packet:
            raise HTTPException(status_code=404, detail="DirectorTreatment decision packet not found.")
        if req.packet_fingerprint and req.packet_fingerprint != packet.packet_fingerprint:
            raise HTTPException(status_code=409, detail="Treatment packet fingerprint does not match.")
        info = _json_object(packet.model_info, {})
        if not isinstance(info, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires proposal provenance."})
        progressive = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
        stage_a = progressive.get("stage_a") if isinstance(progressive, dict) else None
        stage_b = progressive.get("stage_b") if isinstance(progressive, dict) else None
        if is_progressive_stage_validated(stage_a, authoring_stage="BEAT_PLAN") and not _progressive_stage_b_complete(info, _json_object(packet.proposal, {})):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_ENRICHMENT_REQUIRED", "message": "Stage A BeatPlan is not confirmable until Stage B creative enrichment is complete."})
        scope = _json_object(packet.scope, {})
        scene_id = str(scope.get("scene_id") or "").strip() if isinstance(scope, dict) else ""
        scene_name = str(scope.get("scene_name") or "").strip() if isinstance(scope, dict) else ""
        if not scene_id:
            raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production Treatment approval requires scene_id."})
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        try:
            scene, script_ir_version, script_ir_payload, script_ir_envelope = resolve_scene_for_treatment(session, script_row, scene_id=scene_id, scene_name=scene_name, workflow_profile="production")
        except HTTPException:
            raise

        # Rebuild the packet from current authoritative evidence.  This check
        # prevents a candidate from being approved against an old ScriptIR,
        # FactSnapshot, scene identity or asset snapshot.
        baseline, evidence, _ = _build_preview(book_id, DirectorTreatmentPreviewRequest(episode=episode, scene_id=scene_id, scene_name=scene_name, workflow_profile="production"))
        current_packet = _make_decision_packet(book_id, episode, baseline, evidence)
        if current_packet["packet_fingerprint"] != packet.packet_fingerprint:
            packet.status = "superseded"; packet.updated_at = datetime.now(); session.commit()
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_EVIDENCE_STALE", "message": "Treatment evidence changed; candidate must be regenerated."})
        raw_candidate = req.candidate if req.candidate is not None else _json_object(packet.proposal, {})
        if not isinstance(raw_candidate, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_SEMANTIC_CONTRACT_REQUIRED", "message": "Production confirmation requires a structured Director semantic contract."})
        if baseline.get("schema_version") == "director_treatment_v3":
            raw_provenance = info.get("proposal_provenance") or raw_candidate.get("proposal_provenance")
            if not isinstance(raw_provenance, dict):
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires explicit proposal provenance."})
            try:
                provenance = proposal_provenance(raw_provenance.get("proposal_origin", ""), provider=raw_provenance.get("provider"), human_input=(raw_provenance.get("authoring") or {}).get("human_input", False))
                event = confirmation_event(provenance, confirmed_at=datetime.now().isoformat())
                canonical_origin = resolve_canonical_origin(provenance, event)
                candidate = _validate_llm_candidate(raw_candidate, baseline)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_CANDIDATE_INVALID", "message": str(exc)}) from exc
            candidate["proposal_origin"] = provenance["proposal_origin"]
            candidate["proposal_provenance"] = provenance
            semantic_review = validate_director_creative_semantic_review(
                progressive.get("stage_b", {}).get("ir") if isinstance(progressive.get("stage_b"), dict) else None,
                candidate=candidate,
                source_authoring_units=((candidate.get("source_constraints") or {}).get("source_authoring_units") if isinstance(candidate.get("source_constraints"), dict) else []),
                stage_a=stage_a.get("ir") if isinstance(stage_a, dict) else None,
                declared_participants=((candidate.get("source_constraints") or {}).get("declared_participants") if isinstance(candidate.get("source_constraints"), dict) else []),
            )
            if semantic_review.get("status") != "PASS":
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED", "message": "Creative proposal requires semantic grounding review before confirmation.", "semantic_review": semantic_review, "production_writes": 0})
            creative = candidate.get("creative_projection") if isinstance(candidate.get("creative_projection"), dict) else {}
            # Only this explicit confirmation service may cross the proposal
            # state boundary.  The compiler always emits PROPOSED.
            creative["status"] = "CONFIRMED"
            creative["confirmation_event_ref"] = "production_confirm_service"
            for creative_beat in creative.get("creative_beats", []) if isinstance(creative.get("creative_beats"), list) else []:
                if isinstance(creative_beat, dict):
                    creative_beat["proposal_origin"] = provenance["proposal_origin"]
                    creative_beat["confirmation_event_ref"] = "production_confirm_service"
            candidate["creative_projection"] = creative
            semantic_report = validate_source_grounded_contract_v2(candidate, scene=scene, production=True)
            if semantic_report.get("status") != "qualified":
                first = (semantic_report.get("errors") or [{}])[0]
                raise HTTPException(status_code=409, detail={"code": first.get("code") or "DIRECTOR_TREATMENT_CONTRACT_V2_INVALID", "message": "source-grounded DirectorTreatment V2 is not production-qualified", "validation": semantic_report})
            previous = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
            next_revision = previous.revision + 1 if previous else 1
            previous_id = previous.id if previous else None
            if previous:
                previous.status = "superseded"; previous.stale_status = "STALE"; previous.qualification_state = "STALE"; previous.stale_reasons = json.dumps(["SUPERSEDED_BY_NEW_AUTHORITY"], ensure_ascii=False); previous.updated_at = datetime.now()
            source_constraints = {**(candidate.get("source_constraints") if isinstance(candidate.get("source_constraints"), dict) else {}), "schema_version": "director_treatment_v3"}
            formal = {"schema_version": "director_treatment_v3", "scene_id": scene_id, "scene_name": "", "source_constraints": source_constraints, "creative_projection": candidate.get("creative_projection") or {}, "unknowns": candidate.get("unknowns") or []}
            model_info = {"mode": "confirmed_source_grounded_director_candidate", "proposal_provenance": provenance, "confirmation_event": event, "canonical_origin": canonical_origin, **project_legacy_flags(provenance), "candidate_fingerprint": _candidate_fingerprint(candidate, current_packet["packet_fingerprint"]), "authority_state": "pending_binding"}
            row = DirectorTreatment(book_id=book_id, episode=episode, scene_id=scene_id, scene_name="", revision=next_revision, status="approved", source_script_revision=str(script_ir_version.revision), source_script_hash=str(script_ir_version.payload_hash or ""), source_script_ir_version_id=script_ir_version.id, source_script_ir_revision=script_ir_version.revision, source_script_ir_hash=str(script_ir_version.payload_hash or ""), source_script_authority_fingerprint=str(script_ir_envelope.get("envelope_fingerprint") or ""), source_fact_snapshot_id=str(script_ir_envelope.get("fact_snapshot_id") or ""), source_fact_snapshot_revision=script_ir_envelope.get("fact_snapshot_revision"), source_fact_snapshot_hash=str(script_ir_envelope.get("fact_snapshot_payload_hash") or ""), dramatic_objective="", audience_question="", character_intents="{}", beat_map="[]", source_constraints=json.dumps(source_constraints, ensure_ascii=False), director_decisions=json.dumps({"schema_version": "director_treatment_v3", "creative_projection": candidate.get("creative_projection") or {}}, ensure_ascii=False), unknown_unresolved=json.dumps(candidate.get("unknowns") or [], ensure_ascii=False), relationship_power_shift="", audience_emotion="", information_strategy="", performance_direction="", visual_strategy="", coverage_strategy="", sound_strategy="", edit_rhythm="", constraints="[]", unknowns=json.dumps(candidate.get("unknowns") or [], ensure_ascii=False), decision_packet_id=packet.id, model_info=json.dumps(model_info, ensure_ascii=False), prompt_fingerprint=_candidate_fingerprint(candidate, current_packet["packet_fingerprint"]), payload_hash=treatment_payload_hash(formal), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=datetime.now(), activated_at=datetime.now(), created_at=datetime.now(), updated_at=datetime.now(), workflow_profile="production")
            session.add(row); session.flush()
            envelope = build_treatment_authority_envelope_v2(treatment=formal, evidence=evidence, script_ir=script_ir_payload, script_ir_version=script_ir_version, script_ir_envelope=script_ir_envelope, treatment_id=row.id, treatment_revision=row.revision, qualification_state="PRODUCTION_QUALIFIED", provenance=provenance, confirmation=event, canonical_origin=canonical_origin)
            authority = DirectorTreatmentAuthority(book_id=book_id, episode=episode, scene_id=scene_id, treatment_id=row.id, treatment_revision=row.revision, payload_hash=row.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=row.approved_at, activated_at=row.activated_at, created_at=datetime.now(), updated_at=datetime.now())
            session.add(authority); session.flush(); row.authority_envelope_id = authority.id
            pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
            if pointer:
                pointer.treatment_id = row.id; pointer.treatment_revision = row.revision; pointer.authority_envelope_fingerprint = envelope["envelope_fingerprint"]; pointer.qualification_state = "PRODUCTION_QUALIFIED"; pointer.updated_at = datetime.now()
            else:
                session.add(DirectorTreatmentPointer(book_id=book_id, episode=episode, scene_id=scene_id, treatment_id=row.id, treatment_revision=row.revision, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED", created_at=datetime.now(), updated_at=datetime.now()))
            model_info["authority_state"] = "production_qualified"; row.model_info = json.dumps(model_info, ensure_ascii=False)
            packet.status = "confirmed"; packet.confirmed_at = datetime.now(); packet.proposal = json.dumps(candidate, ensure_ascii=False); packet.updated_at = datetime.now()
            session.commit(); session.refresh(row)
            return {"approved": True, "authority_bound": True, "qualification_state": "PRODUCTION_QUALIFIED", "treatment": _treatment_row_payload(row), "authority_envelope": envelope, "packet_id": packet.id, "packet_fingerprint": packet.packet_fingerprint, "rollback_anchor": {"previous_treatment_id": previous_id, "previous_revision": previous.revision if previous else None}, "mutated": True, "production_operations": ["director_treatment_authority_bound", "current_treatment_pointer_updated"], "provider_calls": provenance["provider"]["calls"]}
        missing_contract = [key for key in ("director_contract_version", "director_beat_decisions") if key not in raw_candidate or raw_candidate.get(key) in (None, "", [])]
        if missing_contract:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_SEMANTIC_CONTRACT_REQUIRED", "message": "Production confirmation requires director_contract_version and director_beat_decisions.", "missing": missing_contract})
        raw_provenance = info.get("proposal_provenance") or raw_candidate.get("proposal_provenance")
        if not isinstance(raw_provenance, dict):
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_REQUIRED", "message": "Production confirmation requires explicit proposal provenance."})
        try:
            provenance = proposal_provenance(raw_provenance.get("proposal_origin", ""), provider=raw_provenance.get("provider"), human_input=(raw_provenance.get("authoring") or {}).get("human_input", False))
            event = confirmation_event(provenance, confirmed_at=datetime.now().isoformat())
            canonical_origin = resolve_canonical_origin(provenance, event)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_INVALID", "message": str(exc)}) from exc
        try:
            candidate = _validate_llm_candidate(raw_candidate, baseline)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_CANDIDATE_INVALID", "message": str(exc)}) from exc
        candidate["proposal_origin"] = provenance["proposal_origin"]
        candidate["proposal_provenance"] = provenance
        decisions = []
        for decision in candidate.get("director_beat_decisions", []):
            normalized = dict(decision)
            normalized["proposal_origin"] = provenance["proposal_origin"]
            normalized["decision_origin"] = canonical_origin
            normalized["confirmation_event_ref"] = "production_confirm_service"
            normalized["review_status"] = "CONFIRMED"
            decisions.append(normalized)
        candidate["director_beat_decisions"] = decisions
        semantic_report = validate_director_contract(candidate, scene=scene, production=True)
        if semantic_report.get("status") != "qualified":
            first = (semantic_report.get("errors") or [{}])[0]
            code = first.get("code") if isinstance(first, dict) else "DIRECTOR_TREATMENT_CONTRACT_INVALID"
            raise HTTPException(status_code=409, detail={"code": code or "DIRECTOR_TREATMENT_CONTRACT_INVALID", "message": "structured DirectorBeatDecision contract is not production-qualified", "validation": semantic_report})

        previous = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
        next_revision = previous.revision + 1 if previous else 1
        previous_id = previous.id if previous else None
        if previous:
            previous.status = "superseded"; previous.stale_status = "STALE"; previous.qualification_state = "STALE"; previous.stale_reasons = json.dumps(["SUPERSEDED_BY_NEW_AUTHORITY"], ensure_ascii=False); previous.updated_at = datetime.now()
        # Keep legacy payload hashes stable when a candidate does not use the
        # additive Phase B projection fields.  Empty optional projections are
        # not semantic decisions and must not be written as ``null`` keys.
        legacy_fields = {"dramatic_objective", "audience_question", "character_intents", "beat_map", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "constraints", "unknowns"}
        formal = {key: candidate.get(key) for key in ("scene_id", "scene_name", *TREATMENT_CANDIDATE_FIELDS) if key not in {"proposal_origin", "proposal_provenance"} and (key in legacy_fields or candidate.get(key) not in (None, "", [], {}))}
        model_info = {"mode": "confirmed_director_candidate", "proposal_provenance": provenance, "confirmation_event": event, "canonical_origin": canonical_origin, **project_legacy_flags(provenance), "candidate_fingerprint": _candidate_fingerprint(candidate, current_packet["packet_fingerprint"]), "confirmed_at": datetime.now().isoformat(), "rollback_anchor": {"previous_treatment_id": previous_id, "previous_revision": previous.revision if previous else None}, "authority_state": "pending_binding"}
        row = DirectorTreatment(
            book_id=book_id, episode=episode, scene_id=scene_id, scene_name=baseline["scene_name"], revision=next_revision, status="approved",
            source_script_revision=str(script_ir_version.revision), source_script_hash=str(script_ir_version.payload_hash or ""), source_script_ir_version_id=script_ir_version.id, source_script_ir_revision=script_ir_version.revision, source_script_ir_hash=str(script_ir_version.payload_hash or ""), source_script_authority_fingerprint=str(script_ir_envelope.get("envelope_fingerprint") or ""), source_fact_snapshot_id=str(script_ir_envelope.get("fact_snapshot_id") or ""), source_fact_snapshot_revision=script_ir_envelope.get("fact_snapshot_revision"), source_fact_snapshot_hash=str(script_ir_envelope.get("fact_snapshot_payload_hash") or ""),
            dramatic_objective=formal["dramatic_objective"], audience_question=formal["audience_question"], character_intents=json.dumps(formal["character_intents"], ensure_ascii=False), beat_map=json.dumps(formal["beat_map"], ensure_ascii=False), source_constraints=json.dumps(baseline.get("source_constraints", {}), ensure_ascii=False), director_decisions=json.dumps({field: formal.get(field) for field in ("dramatic_objective", "audience_question", "character_intents", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out", "suspicion_or_information_strategy", "character_directions", "beat_directions", "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent", "prohibited_interpretations") if formal.get(field) not in (None, "", [], {})}, ensure_ascii=False), unknown_unresolved=json.dumps(formal.get("unknowns", []), ensure_ascii=False), relationship_power_shift=formal["relationship_power_shift"], audience_emotion=formal["audience_emotion"], information_strategy=formal["information_strategy"], performance_direction=formal["performance_direction"], visual_strategy=formal["visual_strategy"], coverage_strategy=formal["coverage_strategy"], sound_strategy=formal["sound_strategy"], edit_rhythm=formal["edit_rhythm"], constraints=json.dumps(formal["constraints"], ensure_ascii=False), unknowns=json.dumps(formal["unknowns"], ensure_ascii=False), skill_id=baseline.get("skill_id", ""), skill_version=baseline.get("skill_version", ""), decision_packet_id=packet.id, model_info=json.dumps(model_info, ensure_ascii=False), prompt_fingerprint=_candidate_fingerprint(candidate, current_packet["packet_fingerprint"]), payload_hash=treatment_payload_hash(formal), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=datetime.now(), activated_at=datetime.now(), created_at=datetime.now(), updated_at=datetime.now(), workflow_profile="production",
        )
        session.add(row); session.flush()
        envelope = build_treatment_authority_envelope(treatment=formal, evidence=evidence, script_ir=script_ir_payload, script_ir_version=script_ir_version, script_ir_envelope=script_ir_envelope, treatment_id=row.id, treatment_revision=row.revision, qualification_state="PRODUCTION_QUALIFIED", provenance=provenance, confirmation=event, canonical_origin=canonical_origin)
        authority = DirectorTreatmentAuthority(book_id=book_id, episode=episode, scene_id=scene_id, treatment_id=row.id, treatment_revision=row.revision, payload_hash=row.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=row.approved_at, activated_at=row.activated_at, created_at=datetime.now(), updated_at=datetime.now())
        session.add(authority); session.flush(); row.authority_envelope_id = authority.id
        pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
        if pointer:
            pointer.treatment_id = row.id; pointer.treatment_revision = row.revision; pointer.authority_envelope_fingerprint = envelope["envelope_fingerprint"]; pointer.qualification_state = "PRODUCTION_QUALIFIED"; pointer.updated_at = datetime.now()
        else:
            session.add(DirectorTreatmentPointer(book_id=book_id, episode=episode, scene_id=scene_id, treatment_id=row.id, treatment_revision=row.revision, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED", created_at=datetime.now(), updated_at=datetime.now()))
        model_info["authority_state"] = "production_qualified"; row.model_info = json.dumps(model_info, ensure_ascii=False)
        packet.status = "confirmed"; packet.confirmed_at = datetime.now(); packet.proposal = json.dumps(candidate, ensure_ascii=False); packet.updated_at = datetime.now()
        session.commit(); session.refresh(row)
        return {"approved": True, "authority_bound": True, "qualification_state": "PRODUCTION_QUALIFIED", "treatment": _treatment_row_payload(row), "authority_envelope": envelope, "packet_id": packet.id, "packet_fingerprint": packet.packet_fingerprint, "rollback_anchor": model_info["rollback_anchor"], "mutated": True, "production_operations": ["director_treatment_authority_bound", "current_treatment_pointer_updated"], "provider_calls": provenance["provider"]["calls"]}


@router.get("/{book_id}/episodes/{episode}/director-treatment/authority/{scene_id}")
def get_director_treatment_authority(book_id: int, episode: int, scene_id: str) -> dict[str, Any]:
    """Return the explicit current Treatment authority for a scene."""
    from core.director_treatment_authority import resolve_current_authoritative_treatment
    with Session() as session:
        treatment, envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
        return {"scene_id": scene_id, "treatment": _treatment_row_payload(treatment), "authority_envelope": envelope, "production_qualified": bool(envelope.get("phase_b_semantic_ready", False)), "phase_b_semantic_ready": bool(envelope.get("phase_b_semantic_ready", False))}
