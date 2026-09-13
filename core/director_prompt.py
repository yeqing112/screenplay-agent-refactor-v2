"""Stable, provider-neutral prompts for the Contract-First director planner.

The director planner is intentionally split into a stable instruction prefix
and a scene-specific evidence suffix.  MiMo (and other OpenAI-compatible
providers) may reuse a provider-side prefix when the bytes before the dynamic
evidence remain unchanged.  This module does not opt in to, or invent, any
provider-specific cache parameter; it only exposes deterministic prompt and
fingerprints for telemetry and local de-duplication.

The returned prompts are suitable for a *candidate* CreativePatch call.  They
never grant the model permission to write a ShotPlan, trigger media
generation, or change authoritative facts.  Contract/patch validation remains
the final authority after the model responds.
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.director_creative_contract import ALLOWED_PATCH_PATHS, AUXILIARY_SHOT_POLICY
from core.prompt_cache import canonical_json, llm_request_fingerprint, model_request_snapshot


DIRECTOR_PROMPT_PROTOCOL_VERSION = "director-quality-v2-3-prompt-v1"

# Keep this text literal and versioned.  Do not interpolate scene data here:
# changing the system prompt per scene would defeat prefix reuse and make
# prompt fingerprints harder to compare across a pilot.
STABLE_SYSTEM_PREFIX = """[DIRECTOR_PROMPT_PROTOCOL: director-quality-v2-3-prompt-v1]
SECTION 1 — ROLE
You are a Contract-First Director Creative Planner for a film/television
pre-production system. Return machine-readable JSON only. You propose
creative shot changes; you do not rewrite story facts or perform production.

SECTION 2 — IMMUTABLE CONTRACT RULES
The approved evidence is authoritative. Treat scene identity, beat identity
and order, events, dialogue, participants, character identity and
relationships, asset identity and ownership, entry/exit state, continuity
contracts, spatial source facts, chronology, and plot results as immutable.

SECTION 3 — CREATIVEPATCH SCHEMA
Return exactly one JSON object with this shape:
{"schema_version":"director_creative_patch_v1","patches":[],"auxiliary_shot_proposals":[]}
Each patch targets an existing plan_shot_id and contains changes as
path-to-value entries. Do not return complete shot objects, scenes, treatment,
blocking, or a ShotPlan.

SECTION 4 — ALLOWED PATCH PATHS
/shots/*/camera/shot_size
/shots/*/camera/angle
/shots/*/camera/movement
/shots/*/camera/speed
/shots/*/camera/camera_side
/shots/*/composition/*
/shots/*/composition
/shots/*/why_this_shot
/shots/*/dramatic_function
/shots/*/emotion/*
/shots/*/emotion
/shots/*/performance_direction/*
/shots/*/performance_direction/*/*
/shots/*/performance_direction
/shots/*/edit/*
/shots/*/edit
/shots/*/information_strategy/*
/shots/*/information_strategy
/shots/*/visual_emphasis

FORBIDDEN PATHS
Never write scene identity, beat/event/dialogue facts, beat order,
participants, assets or prop ownership, entry/exit state, continuity,
spatial source facts, chronology, plot result, duration, or any unknown
authoritative field. Never add arbitrary top-level keys.

SECTION 5 — AUXILIARY PROPOSAL SCHEMA / AUXILIARY SHOT POLICY
Auxiliary proposals are separate from patches. Allowed types are reaction,
insert, establishing, transition, and detail. Every proposal must cite an
existing source_beat_id and insert_after_plan_shot_id, use only approved
participants, explain why it is needed, and preserve the story. At most two
proposals may originate from one source beat. Do not introduce a new person,
event, key asset, or plot result.

SECTION 6 — QUALITY RULES
Every change must serve the source beat and the scene strategy. Prefer clear
spatial relationships, motivated camera movement, visible performance, and
information order. Avoid gratuitous movement, random shot-scale changes,
redundant coverage, emotional flatlines, and shot inflation. If evidence is
insufficient, return no change rather than inventing a fact.

SECTION 6A — CANONICAL QUALITY SIGNAL SHAPES
When proposing a change, use the canonical shapes consumed by the deterministic
quality scorer. performance_direction is a list of objects, each with
character_id, objective, and visible_behavior (abstract emotion words alone
are insufficient). emotion uses numeric intensity 0-10 plus optional start/end.
edit uses duration_seconds, cut_reason, and optional hold_after_action_seconds.
information_strategy uses plural reveals/withholds plus audience_focus.
Do not replace these with character-keyed maps, pacing-only text, or singular
provider aliases when the canonical form can be returned.

SECTION 7 — OUTPUT RULES
Return strict JSON only; do not include prose outside the JSON document.
"""

# This portion is also stable across scenes.  It is kept in the user message
# so callers can keep the system role reusable while still separating the
# schema/quality context from dynamic evidence.
SEMI_STABLE_USER_PREFIX = """[DIRECTOR_SEMI_STABLE_CONTEXT: director-quality-v2-3-prompt-v1]
SCENE STRATEGY CONTRACT
Use the supplied Scene Directing Strategy as a scene-level brief. Do not
invent strategy fields or rewrite its beat references.
Required strategy concepts: scene_objective, visual_strategy,
performance_arc, rhythm_curve, emotion_curve, information_plan,
camera_language, forbidden_tendencies. Legacy emotional_curve,
information_strategy, power_curve, rhythm_strategy may be present for
compatibility but beat-bound V2 arrays are authoritative.

Every patch should include strategy_refs when the supplied strategy is V2;
refs must point to the target beat (and approved character where applicable),
for example performance:B04:CHAR_001, emotion:B04:CHAR_001,
information:B04, or rhythm:B04.

DIRECTOR QUALITY DIMENSIONS
Consider dramatic clarity, shot motivation, emotional progression, visual
storytelling, spatial clarity, performance direction, edit rhythm,
information strategy, power dynamics, and shot diversity. These are quality
criteria, not permission to alter authoritative evidence.
"""

TASK_SUFFIX = """TASK
Using only the frozen contract, scene strategy, and structural shot plan below,
return a candidate CreativePatch document for human review. Output strict JSON
only. An empty patches/auxiliary_shot_proposals list is valid when no safe
creative change is justified. Do not describe your reasoning outside JSON.
"""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_director_patch_prompt(
    *,
    contract: dict[str, Any] | None,
    strategy: dict[str, Any] | None,
    structural_shot_plan: dict[str, Any] | None,
    model_profile: dict[str, Any] | None = None,
    stage: str = "director_patch_planner",
    task: str | None = None,
) -> dict[str, Any]:
    """Build deterministic prompts and non-secret fingerprints.

    ``contract``, ``strategy`` and ``structural_shot_plan`` are dynamic scene
    evidence.  They are canonicalized with sorted keys so equivalent payloads
    produce identical prompt bytes.  ``model_profile`` contributes only the
    safe model/parameter snapshot to the request fingerprint; credentials and
    base URLs never appear in returned prompt text or metadata.
    """

    contract_obj = _dict(contract)
    strategy_obj = _dict(strategy)
    plan_obj = _dict(structural_shot_plan)

    # The contract currently emits this same global list.  Keep the stable
    # prefix authoritative and expose a mismatch in the dynamic evidence for
    # diagnostics rather than silently changing the prompt per scene.
    contract_paths = contract_obj.get("allowed_patch_paths")
    contract_paths = contract_paths if isinstance(contract_paths, list) else list(ALLOWED_PATCH_PATHS)
    policy = contract_obj.get("auxiliary_shot_policy")
    policy = policy if isinstance(policy, dict) else AUXILIARY_SHOT_POLICY

    evidence = {
        "protocol_version": DIRECTOR_PROMPT_PROTOCOL_VERSION,
        "stage": str(stage or "director_patch_planner"),
        "contract_fingerprint": str(contract_obj.get("contract_fingerprint") or ""),
        "strategy_fingerprint": str(strategy_obj.get("strategy_fingerprint") or ""),
        "contract": contract_obj,
        "strategy": strategy_obj,
        "structural_shot_plan": plan_obj,
        "contract_allowed_patch_paths": contract_paths,
        "contract_auxiliary_shot_policy": policy,
    }
    dynamic_payload = canonical_json(evidence)
    task_text = task.strip() if isinstance(task, str) and task.strip() else TASK_SUFFIX.strip()
    variable_tail = "\n".join(["EVIDENCE (authoritative, read-only)", dynamic_payload, task_text])
    user_prompt = "\n".join(
        [
            SEMI_STABLE_USER_PREFIX.rstrip(),
            variable_tail,
        ]
    )
    system_prompt = STABLE_SYSTEM_PREFIX.strip()
    stable_prefix = "\n".join([system_prompt, SEMI_STABLE_USER_PREFIX.strip()])
    stable_prefix_fingerprint = _sha256(stable_prefix)
    system_prompt_hash = _sha256(system_prompt)
    user_prompt_hash = _sha256(user_prompt)
    request_fingerprint = llm_request_fingerprint(
        system=system_prompt,
        user=user_prompt,
        profile=model_profile,
        extra={
            "stage": str(stage or "director_patch_planner"),
            "protocol_version": DIRECTOR_PROMPT_PROTOCOL_VERSION,
        },
    )
    return {
        "protocol_version": DIRECTOR_PROMPT_PROTOCOL_VERSION,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "system_prompt_hash": system_prompt_hash,
        "user_prompt_hash": user_prompt_hash,
        "stable_prefix_fingerprint": stable_prefix_fingerprint,
        "prompt_prefix_fingerprint": stable_prefix_fingerprint,
        "stable_prefix_hash": stable_prefix_fingerprint,
        "stable_prefix_length": len(stable_prefix),
        "variable_tail_hash": _sha256(variable_tail),
        "request_fingerprint": request_fingerprint,
        "model_snapshot": model_request_snapshot(model_profile),
        "evidence": evidence,
    }


# Explicit alias for callers that use the longer domain name.
build_director_creative_patch_prompt = build_director_patch_prompt
build_director_prompt = build_director_patch_prompt
PROMPT_PROTOCOL_VERSION = DIRECTOR_PROMPT_PROTOCOL_VERSION


__all__ = [
    "DIRECTOR_PROMPT_PROTOCOL_VERSION",
    "STABLE_SYSTEM_PREFIX",
    "SEMI_STABLE_USER_PREFIX",
    "TASK_SUFFIX",
    "build_director_patch_prompt",
    "build_director_creative_patch_prompt",
    "build_director_prompt",
    "PROMPT_PROTOCOL_VERSION",
]
