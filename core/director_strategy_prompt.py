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


__all__ = [
    "PHASE1_PROMPT_PROTOCOL_VERSION",
    "STABLE_SYSTEM_PROMPT",
    "OUTPUT_RULES",
    "build_scene_strategy_prompt",
]
