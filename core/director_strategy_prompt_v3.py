"""Provider prompt builder for the Fresh Director Strategy V3 contract.

The machine contract is generated from ``director_strategy_provider_spec``;
this module intentionally contains no examples or legacy ``must_preserve``
authority.  Only the evidence suffix varies per scene, keeping the prefix
stable for provider-side caching without changing semantics.
"""
from __future__ import annotations

from typing import Any

from core.prompt_cache import llm_request_fingerprint, model_request_snapshot, canonical_json
from core.director_strategy_provider_spec import (
    STRATEGY_PROVIDER_SPEC_VERSION,
    STRATEGY_SCHEMA_VERSION,
    build_strategy_provider_contract,
)

PROTOCOL_VERSION = "director-quality-v3-strategy-provider-prompt-v1"


def build_scene_strategy_ir_v3_prompt(
    *, evidence: dict[str, Any], model_profile: dict[str, Any] | None = None,
    attempt_type: str = "CREATIVE_GENERATION",
) -> dict[str, Any]:
    safe = dict(evidence) if isinstance(evidence, dict) else {}
    contract = build_strategy_provider_contract(safe)
    system = f"""[DIRECTOR_STRATEGY_V3_PROTOCOL: {PROTOCOL_VERSION}]
You are the scene director for one approved screenplay scene. Return exactly
one JSON object and no Markdown. Make scene-specific directing decisions from
the supplied evidence, while preserving source facts, chronology, blocking and
identity exactly. Do not invent entities or resolve missing evidence by prose.

Machine contract: {STRATEGY_PROVIDER_SPEC_VERSION}; schema_version must be
{STRATEGY_SCHEMA_VERSION}. The program will validate and canonicalize all
references. You must select explicit exact refs from the supplied allowed refs.

Preserve intent is the only machine authority for what must survive into later
layers. Output preserve_intents (not must_preserve) with kind, description,
anchor_refs, subject_refs, object_refs and visibility_requirement. Every
anchor_refs array is required and non-empty; anchors must be copied exactly
from allowed_source_refs or allowed_event_refs. Do not output constraint IDs,
fingerprints, shots, shot IDs, ShotPlan fields, patches or repair instructions.
The optional must_preserve field is not accepted as machine authority.

Return all required top-level fields from the contract. Keep phases and
creative choices grounded in the supplied beat/character/prop/location refs.
""".strip()
    dynamic = {
        "protocol_version": PROTOCOL_VERSION,
        "attempt_type": str(attempt_type or "CREATIVE_GENERATION"),
        "strategy_provider_spec": contract,
        "scene_evidence": safe,
        "output_schema": STRATEGY_SCHEMA_VERSION,
    }
    user = "[DIRECTOR_STRATEGY_V3_EVIDENCE]\n" + canonical_json(dynamic) + "\n[/DIRECTOR_STRATEGY_V3_EVIDENCE]\nReturn one complete director_scene_strategy_ir_v3 JSON object now."
    return {
        "protocol_version": PROTOCOL_VERSION,
        "attempt_type": str(attempt_type or "CREATIVE_GENERATION"),
        "system_prompt": system,
        "user_prompt": user,
        "provider_contract": contract,
        "schema_version": STRATEGY_SCHEMA_VERSION,
        "schema_fingerprint": contract["schema_fingerprint"],
        "system_prompt_fingerprint": __import__("hashlib").sha256(system.encode("utf-8")).hexdigest(),
        "request_fingerprint": llm_request_fingerprint(
            system=system, user=user, profile=model_profile,
            extra={"protocol_version": PROTOCOL_VERSION, "attempt_type": attempt_type},
        ),
        "model_snapshot": model_request_snapshot(model_profile),
        "legacy_machine_authority": False,
    }


__all__ = ["PROTOCOL_VERSION", "build_scene_strategy_ir_v3_prompt"]
