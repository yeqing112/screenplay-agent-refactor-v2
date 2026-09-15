"""Stable provider prompt for the V3 Scene Director Strategy canary.

The prompt deliberately stops at ``SceneDirectingStrategy``.  It contains no
ShotPlan examples, scorer weights, repair answers, or provider credentials.
Only the final scene-specific evidence suffix changes between requests so an
OpenAI-compatible provider can reuse the fixed prefix.
"""
from __future__ import annotations

import hashlib
from typing import Any

from core.prompt_cache import canonical_json, llm_request_fingerprint, model_request_snapshot
from core.director_scene_strategy import SCENE_STRATEGY_SCHEMA_VERSION, STRATEGY_FIELDS
from core.director_scene_strategy_semantic_spec import IR_SCHEMA_VERSION, build_provider_skeleton, semantic_spec


PHASE1_PROMPT_PROTOCOL_VERSION = "director-quality-v3-phase1-strategy-prompt-v1"

STABLE_SYSTEM_PROMPT = f"""[DIRECTOR_STRATEGY_PROTOCOL: {PHASE1_PROMPT_PROTOCOL_VERSION}]
ROLE
You are the scene director for a film/television pre-production system. Your
task is to design one coherent SceneDirectingStrategy, not to fill fields and
not to design a shot list. Return exactly one JSON object and no Markdown or
explanation outside it.

AUTHORITY
The supplied FactSnapshot and ScriptIR scene are source facts. Approved
DirectorTreatment is the dramatic and visual intent already chosen upstream.
Approved SceneBlocking is authoritative for spatial facts, entry/exit and
continuity truth. Character, location and prop records are canonical only
when supplied. You may make DIRECTOR_CREATIVE_DECISIONs about how to stage
the scene, but you may not alter or invent source facts, dialogue, events,
characters, props, locations, chronology or blocking truth. If evidence is
missing, write N/A and cite the missing evidence; do not guess.

DIRECTOR TASK
First understand why the scene exists, what the audience should know,
suspect, feel and misunderstand, and when that changes. Then express one
scene-specific dramatic objective, scene question, audience knowledge arc,
emotion arc, power arc (or N/A when unsupported), performance progression,
edit logic, visual grammar, motivated camera principles, information reveal
plan, spatial/prop strategy and shot-architecture guidance. Inherit the
Treatment instead of paraphrasing it. Make every principle operational by
binding it to supplied beat IDs, characters, phases or source facts.

SCHEMA
Use schema_version={SCENE_STRATEGY_SCHEMA_VERSION}. Required top-level fields
are exactly: {", ".join(STRATEGY_FIELDS)}.
The object must include authority and source_refs plus a strategy_fingerprint
computed from the final object without its strategy_fingerprint field.
audience_experience, audience_knowledge_arc, emotional_arc, power_arc and
information_reveal_plan are ordered by the source beat sequence. Every arc
entry must bind to beat_ids; emotion entries require trigger and
transition_reason; performance entries require objective, tactic_progression,
visible_behavior_progression and turning_point. Visual grammar and camera
principles are whole-scene principles, not a WS/MS/CU list.

NO SHOTPLAN LEAKAGE
Do not output plan_shot_id, shot IDs, a complete shot list, camera settings
per shot, duration ladders, canonical patches or repair instructions.
shot_architecture_guidance may only describe required functions and principles
such as establishing, relationship, reveal, insert or reaction; topology is
not defined by this strategy.

NO SCORER GAMING
Do not optimize deterministic quality scores. Do not use DQ weights,
scorer formulas, historical repair outputs or baseline ShotPlan decisions.
Scene-specific evidence and intentional directing choices matter more than
field quantity. Do not use generic phrases such as “enhance emotion” or
“use different shot sizes” without a beat, character, phase, trigger or
audience-state reference.

OUTPUT RULES
Strict JSON object only. No extra top-level keys. No invented IDs. Preserve
the supplied beat order and authority boundaries exactly.
""".strip()


OUTPUT_RULES = {
    "schema_version": SCENE_STRATEGY_SCHEMA_VERSION,
    "required_fields": list(STRATEGY_FIELDS),
    "forbidden_top_level_fields": [
        "shots", "plan_shot_id", "shot_ids", "patches", "duration_ladder",
        "repair", "dq_score", "quality_score",
    ],
    "authority_types": ["SOURCE_FACT", "TREATMENT_INTENT", "BLOCKING_FACT", "DIRECTOR_CREATIVE_DECISION"],
}

PHASE1_1_PROMPT_PROTOCOL_VERSION = "director-quality-v3-phase1-1-strategy-ir-prompt-v1"


def build_scene_strategy_ir_prompt(
    *,
    evidence: dict[str, Any],
    model_profile: dict[str, Any] | None = None,
    attempt_type: str = "CREATIVE_GENERATION",
    raw_output: str | None = None,
) -> dict[str, Any]:
    """Build the Phase 1.1 provider contract from the semantic SSOT.

    This function deliberately excludes computed fingerprints and all ShotPlan
    topology.  ``evidence`` is expected to carry the authoritative contract
    projection; the skeleton is generated from its allowed IDs.
    """
    safe = dict(evidence) if isinstance(evidence, dict) else {}
    contract = safe.get("strategy_contract") if isinstance(safe.get("strategy_contract"), dict) else safe.get("contract")
    contract = contract if isinstance(contract, dict) else {}
    skeleton = build_provider_skeleton(
        scene_id=str(safe.get("scene_id") or contract.get("scene_id") or ""),
        beat_ids=[str(x) for x in (contract.get("beat_ids") or safe.get("allowed_beat_ids") or [])],
        character_ids=[str(x) for x in (contract.get("character_ids") or safe.get("allowed_character_ids") or [])],
        fact_ids=[str(x) for x in (contract.get("fact_ids") or safe.get("allowed_fact_ids") or [])],
    )
    dynamic = {
        "protocol_version": PHASE1_1_PROMPT_PROTOCOL_VERSION,
        "attempt_type": str(attempt_type or "CREATIVE_GENERATION"),
        "semantic_spec": semantic_spec(),
        "provider_contract": skeleton,
        "scene_inputs": safe,
        "computed_by_program": ["strategy_fingerprint", "creative_core_fingerprint", "dq_score", "cv_score"],
    }
    if raw_output is not None:
        dynamic["failed_output_for_format_repair"] = str(raw_output)[:100000]
        dynamic["format_repair_rule"] = "Repair protocol shape, IDs and types only; preserve valid creative semantics."
    system = (
        f"[DIRECTOR_STRATEGY_IR_PROTOCOL: {PHASE1_1_PROMPT_PROTOCOL_VERSION}]\n"
        "You are a scene director. Return one phase-centric semantic IR JSON object only.\n"
        "Express directing decisions, not a shot list. Use only allowed beat/character/fact IDs.\n"
        "Group source beats into 2–6 coherent phases (prefer 3–5). Assign every beat exactly once.\n"
        "Do not output fingerprints, scores, shot IDs, ShotPlan fields, patches or invented facts.\n"
        "Power may center on CHARACTER, SHARED, RELATIONSHIP, INFORMATION, OBJECT, ENVIRONMENT or NONE; "
        "non-character centers must remain grounded in supplied evidence.\n"
        "Missing unsupported information is represented as N/A or an empty list according to the supplied skeleton."
    )
    user = "[DIRECTOR_STRATEGY_IR_DYNAMIC_EVIDENCE]\n" + canonical_json(dynamic) + "\n[/DIRECTOR_STRATEGY_IR_DYNAMIC_EVIDENCE]\n"
    user += "Return one complete director_scene_strategy_ir_v1 JSON object now."
    return {
        "protocol_version": PHASE1_1_PROMPT_PROTOCOL_VERSION,
        "attempt_type": str(attempt_type or "CREATIVE_GENERATION"),
        "system_prompt": system,
        "user_prompt": user,
        "semantic_spec_version": semantic_spec()["schema_version"],
        "ir_schema_version": IR_SCHEMA_VERSION,
        "provider_contract": skeleton,
        "computed_fields_excluded": ["strategy_fingerprint", "creative_core_fingerprint"],
        "system_prompt_fingerprint": _sha256(system),
        "schema_fingerprint": _sha256(canonical_json(skeleton)),
        "scene_input_fingerprint": _sha256(canonical_json(safe)),
        "request_fingerprint": llm_request_fingerprint(system=system, user=user, profile=model_profile, extra={"protocol_version": PHASE1_1_PROMPT_PROTOCOL_VERSION, "attempt_type": attempt_type}),
        "model_snapshot": model_request_snapshot(model_profile),
    }


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_scene_strategy_prompt(
    *,
    evidence: dict[str, Any],
    model_profile: dict[str, Any] | None = None,
    attempt_type: str = "CREATIVE_GENERATION",
    raw_output: str | None = None,
) -> dict[str, Any]:
    """Return stable system prompt and a scene-specific evidence suffix.

    ``evidence`` must already be independently sourced by the canary runner.
    This function intentionally does not accept a baseline ShotPlan; the
    absence of that parameter is a hard boundary against answer imitation.
    """

    safe_evidence = dict(evidence) if isinstance(evidence, dict) else {}
    dynamic = {
        "protocol_version": PHASE1_PROMPT_PROTOCOL_VERSION,
        "attempt_type": str(attempt_type or "CREATIVE_GENERATION"),
        "output_rules": OUTPUT_RULES,
        "scene_inputs": safe_evidence,
    }
    if raw_output is not None:
        dynamic["failed_output_for_format_repair"] = str(raw_output)[:100000]
        dynamic["format_repair_rule"] = (
            "Repair protocol shape only. Preserve all semantic content that is valid; "
            "do not newly direct the scene, add facts, or change evidence references."
        )
    evidence_json = canonical_json(dynamic)
    user_prompt = (
        "[DIRECTOR_STRATEGY_DYNAMIC_EVIDENCE]\n"
        + evidence_json
        + "\n[/DIRECTOR_STRATEGY_DYNAMIC_EVIDENCE]\n"
        + (
            "Return one complete SceneDirectingStrategy JSON object now."
            if attempt_type == "CREATIVE_GENERATION"
            else "Return the same strategy as a protocol-valid JSON object; format repair only."
        )
    )
    stable_prefix_fingerprint = _sha256(STABLE_SYSTEM_PROMPT + "\n" + canonical_json(OUTPUT_RULES))
    return {
        "protocol_version": PHASE1_PROMPT_PROTOCOL_VERSION,
        "attempt_type": str(attempt_type or "CREATIVE_GENERATION"),
        "system_prompt": STABLE_SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "system_prompt_fingerprint": _sha256(STABLE_SYSTEM_PROMPT),
        "schema_fingerprint": _sha256(canonical_json(OUTPUT_RULES)),
        "stable_prefix_fingerprint": stable_prefix_fingerprint,
        "scene_input_fingerprint": _sha256(canonical_json(safe_evidence)),
        "request_fingerprint": llm_request_fingerprint(
            system=STABLE_SYSTEM_PROMPT,
            user=user_prompt,
            profile=model_profile,
            extra={"protocol_version": PHASE1_PROMPT_PROTOCOL_VERSION, "attempt_type": attempt_type},
        ),
        "model_snapshot": model_request_snapshot(model_profile),
    }


def build_scene_strategy_ir_v2_prompt(*, evidence: dict[str, Any], model_profile: dict[str, Any] | None = None, attempt_type: str = "CREATIVE_GENERATION", raw_output: str | None = None) -> dict[str, Any]:
    """Provider preview for the final, reference-first IR V2 contract."""
    from core.director_scene_strategy_semantic_spec_v2 import IR_SCHEMA_VERSION, build_provider_skeleton, semantic_spec
    safe = dict(evidence) if isinstance(evidence, dict) else {}
    contract = safe.get("strategy_contract") if isinstance(safe.get("strategy_contract"), dict) else safe.get("contract") or {}
    skeleton = build_provider_skeleton(scene_id=str(contract.get("scene_id") or safe.get("scene_id") or ""), beat_ids=[str(x) for x in contract.get("beat_ids", [])], character_ids=[str(x) for x in contract.get("character_ids", [])], fact_ids=[str(x) for x in contract.get("fact_ids", [])], prop_ids=[str(x) for x in contract.get("prop_ids", [])], location_ids=[str(x) for x in contract.get("location_ids", [])], runtime_contract=contract if contract.get("runtime_contract_version") else None)
    system = ("[DIRECTOR_STRATEGY_IR_V2]\nYou are the scene director. Return exactly one JSON object with schema_version=director_scene_strategy_ir_v2. Express scene phases and directing choices, never a shot list. Use only supplied beat, character and source references. Source facts are authoritative and cannot be added or rewritten.\n\n" "Information is reference-first: information.reveal_refs, hint_refs and withhold_refs contain only allowed source refs. audience_suspicions and director_inferences are interpretive claims and must include support_refs; they are never source facts. Flexible list fields may be string, string[] or null; the deterministic program will normalize them without changing meaning. Do not output fingerprints, scores, source_fact claims, ShotPlan fields or patches. Preserve beat order and assign every beat exactly once. If evidence is absent, use N/A only where the contract allows it.")
    dynamic = {"protocol_version": "director-quality-v3-final-recanary-strategy-ir-v2-prompt-v1", "attempt_type": attempt_type, "semantic_spec": semantic_spec(), "provider_contract": skeleton, "scene_inputs": safe}
    if raw_output is not None:
        dynamic["failed_output_for_format_repair"] = str(raw_output)[:100000]
        dynamic["format_repair_rule"] = "Repair protocol shape/references only; preserve valid creative semantics and do not re-direct the scene."
    user = "[DIRECTOR_STRATEGY_IR_V2_EVIDENCE]\n" + canonical_json(dynamic) + "\n[/DIRECTOR_STRATEGY_IR_V2_EVIDENCE]\nReturn one complete director_scene_strategy_ir_v2 JSON object now."
    source_ref_contract = skeleton.get("source_ref_contract") if isinstance(skeleton.get("source_ref_contract"), dict) else {}
    provider_projection = {"scene_id": skeleton.get("scene_id"), "allowed_beat_ids": skeleton.get("allowed_beat_ids"), "allowed_character_ids": skeleton.get("allowed_character_ids"), "source_ref_contract": source_ref_contract, "allowed_source_refs": skeleton.get("allowed_source_refs")}
    return {"protocol_version": "director-quality-v3-final-recanary-strategy-ir-v2-prompt-v1", "attempt_type": attempt_type, "system_prompt": system, "user_prompt": user, "provider_contract": skeleton, "provider_visible_contract_fingerprint": _sha256(canonical_json(provider_projection)), "source_ref_contract_fingerprint": _sha256(canonical_json(source_ref_contract)), "beat_alias_table_fingerprint": _sha256(canonical_json(source_ref_contract.get("beat_alias_table"))), "allowed_source_refs_fingerprint": _sha256(canonical_json(skeleton.get("allowed_source_refs"))), "system_prompt_fingerprint": _sha256(system), "schema_fingerprint": _sha256(canonical_json(skeleton)), "scene_input_fingerprint": _sha256(canonical_json(safe)), "request_fingerprint": llm_request_fingerprint(system=system, user=user, profile=model_profile, extra={"protocol_version": "director-quality-v3-final-recanary-strategy-ir-v2-prompt-v1", "attempt_type": attempt_type}), "model_snapshot": model_request_snapshot(model_profile)}


__all__ = [
    "PHASE1_PROMPT_PROTOCOL_VERSION",
    "STABLE_SYSTEM_PROMPT",
    "OUTPUT_RULES",
    "build_scene_strategy_prompt",
    "PHASE1_1_PROMPT_PROTOCOL_VERSION",
    "build_scene_strategy_ir_prompt",
    "build_scene_strategy_ir_v2_prompt",
]
