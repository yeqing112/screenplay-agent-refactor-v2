"""Structured DirectorTreatment semantics for the Phase B production gate.

The deterministic gate in this module validates shape, references, origins and
state invariants.  It deliberately does not judge prose quality; that belongs
to ``review_director_creative_quality`` and has no authority side effects.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

DRAMATIC_PURPOSES = frozenset({
    "SETUP_RELATIONSHIP", "INTRODUCE_ANOMALY", "RAISE_SUSPICION", "REDIRECT_SUSPICION",
    "CONFIRM_EVIDENCE", "WITHHOLD_INFORMATION", "DESTABILIZE_CHARACTER_CERTAINTY",
    "RESTORE_CHARACTER_CERTAINTY", "ESCALATE_THREAT", "SHIFT_POWER", "TRIGGER_DECISION",
    "LOCK_SCENE_OUTCOME", "HOOK_NEXT_SCENE",
})
STATE_DIMENSIONS = frozenset({"CERTAINTY", "TRUST", "THREAT_PERCEPTION", "POWER", "INTENTION", "ATTENTION_TARGET", "EMOTIONAL_CONTROL"})
PERFORMANCE_ACTIONS = frozenset({
    "CONCEAL_FEAR", "TEST_OTHER_CHARACTER", "NORMALIZE_FALSE_MEMORY", "CONTROL_EXIT",
    "OBSERVE_REACTION", "REDIRECT_ATTENTION", "WITHHOLD_RESPONSE", "PRESSURE_WITHOUT_OPEN_THREAT",
    "APPROACH", "RETREAT", "PROTECT_PROP", "REVEAL_PROP", "LEAVE_SCENE", "HOLD_POSITION",
})
REACTION_TYPES = frozenset({"HESITATION", "RECOGNITION", "FEAR_RESPONSE", "DECISION", "WITHDRAWAL", "ATTENTION_SHIFT", "RESISTANCE"})
DECISION_ORIGINS = frozenset({"HUMAN_AUTHORED", "PROVIDER_PROPOSAL_CONFIRMED", "DETERMINISTIC_DERIVED", "GENERATED_DRAFT"})
PRODUCTION_ORIGINS = frozenset({"HUMAN_AUTHORED", "PROVIDER_PROPOSAL_CONFIRMED"})
DIRECTOR_CONTRACT_VERSION = "director_semantic_contract_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _beats(scene: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(scene, dict):
        return []
    raw = scene.get("dramatic_beats") if isinstance(scene.get("dramatic_beats"), list) else scene.get("beats")
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def _required_beats(scene: dict[str, Any] | None) -> set[str]:
    return {_text(x.get("beat_id") or x.get("id")) for x in _beats(scene) if str(x.get("importance", "")).lower() == "critical" or x.get("requires_reaction") is True}


def _decision_error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": "blocker", "message": message, **extra}


def validate_director_contract(treatment: dict[str, Any], *, scene: dict[str, Any], production: bool = False) -> dict[str, Any]:
    """Validate only deterministic DirectorBeatDecision invariants."""
    errors: list[dict[str, Any]] = []
    if production:
        version = _text(treatment.get("director_contract_version") if isinstance(treatment, dict) else "")
        if not version:
            errors.append(_decision_error("DIRECTOR_SEMANTIC_CONTRACT_REQUIRED", "director_contract_version is required for Production"))
        elif version != DIRECTOR_CONTRACT_VERSION:
            errors.append(_decision_error("UNSUPPORTED_PRODUCTION_CONTRACT_VERSION", "unsupported Director semantic contract version", version=version))
    decisions = treatment.get("director_beat_decisions") if isinstance(treatment, dict) else None
    if not isinstance(decisions, list):
        return {"status": "blocked", "errors": [_decision_error("DIRECTOR_BEAT_DECISION_MISSING", "director_beat_decisions must be a list")], "warnings": []}
    beats = _beats(scene)
    beat_ids = {_text(x.get("beat_id") or x.get("id")) for x in beats}
    required = _required_beats(scene)
    seen: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            errors.append(_decision_error("DIRECTOR_BEAT_DECISION_SCHEMA_INVALID", "decision must be an object")); continue
        ref = _text(decision.get("beat_ref"))
        if not ref or ref not in beat_ids:
            errors.append(_decision_error("DIRECTOR_BEAT_REF_INVALID", "decision beat_ref is not a ScriptIR beat", beat_ref=ref)); continue
        if ref in seen:
            errors.append(_decision_error("DIRECTOR_BEAT_DECISION_DUPLICATE", "duplicate DirectorBeatDecision", beat_ref=ref))
        seen.add(ref)
        purpose = _text(decision.get("dramatic_purpose"))
        if purpose not in DRAMATIC_PURPOSES:
            errors.append(_decision_error("DIRECTOR_DRAMATIC_PURPOSE_INVALID", "dramatic_purpose is not a controlled value", beat_ref=ref))
        audience = decision.get("audience_state_delta")
        if not isinstance(audience, dict) or any(not isinstance(audience.get(key), list) for key in ("knowledge_added", "knowledge_confirmed", "knowledge_invalidated", "belief_shift", "open_question_added", "open_question_resolved")):
            errors.append(_decision_error("DIRECTOR_AUDIENCE_DELTA_INVALID", "audience_state_delta requires all delta lists", beat_ref=ref))
        for shift in _list(audience.get("belief_shift") if isinstance(audience, dict) else None):
            if not isinstance(shift, dict) or not all(_text(shift.get(key)) for key in ("subject", "from", "to")):
                errors.append(_decision_error("DIRECTOR_AUDIENCE_DELTA_INVALID", "belief_shift requires subject/from/to", beat_ref=ref))
        for delta in _list(decision.get("character_state_deltas")):
            if not isinstance(delta, dict) or _text(delta.get("dimension")) not in STATE_DIMENSIONS or not _text(delta.get("character_ref")) or "from" not in delta or "to" not in delta:
                errors.append(_decision_error("DIRECTOR_CHARACTER_STATE_DELTA_INVALID", "character state delta is malformed", beat_ref=ref))
        for objective in _list(decision.get("performance_objectives")):
            if not isinstance(objective, dict) or _text(objective.get("action")) not in PERFORMANCE_ACTIONS or not _text(objective.get("character_ref")) or not _text(objective.get("target")):
                errors.append(_decision_error("DIRECTOR_PERFORMANCE_OBJECTIVE_INVALID", "performance objective is malformed", beat_ref=ref))
        reactions = _list(decision.get("reaction_contracts"))
        for reaction in reactions:
            if not isinstance(reaction, dict) or not _text(reaction.get("character_ref")) or not _text(reaction.get("trigger_ref")) or _text(reaction.get("reaction_type")) not in REACTION_TYPES or reaction.get("required") is not True:
                errors.append(_decision_error("DIRECTOR_REACTION_CONTRACT_INVALID", "reaction contract is malformed", beat_ref=ref))
        if ref in required and not any(isinstance(x, dict) and x.get("required") is True for x in reactions):
            errors.append(_decision_error("DIRECTOR_REACTION_CONTRACT_MISSING", "reaction-required beat has no required ReactionContract", beat_ref=ref))
        source_refs = _list(decision.get("source_refs"))
        if not source_refs or ref not in {str(x).split(":")[-1] for x in source_refs}:
            errors.append(_decision_error("DIRECTOR_SOURCE_REF_MISSING", "decision must cite its source beat", beat_ref=ref))
        origin = _text(decision.get("decision_origin"))
        if origin not in DECISION_ORIGINS:
            errors.append(_decision_error("DIRECTOR_DECISION_ORIGIN_INVALID", "decision_origin is invalid", beat_ref=ref))
        if production and origin not in PRODUCTION_ORIGINS:
            errors.append(_decision_error("DIRECTOR_DECISION_NOT_ACCEPTED", "generated draft decision cannot enter Production", beat_ref=ref))
    missing = sorted(required - seen)
    if missing:
        errors.append(_decision_error("DIRECTOR_BEAT_DECISION_COVERAGE_INCOMPLETE", "critical/reaction beats lack DirectorBeatDecision", missing=missing))
    return {"status": "qualified" if not errors else "blocked", "errors": errors, "warnings": [], "required_beat_count": len(required), "covered_beat_count": len(required & seen), "decision_count": len(decisions)}


def build_suggested_director_decisions(scene: dict[str, Any], *, origin: str = "GENERATED_DRAFT") -> list[dict[str, Any]]:
    """Create reviewable semantic suggestions from beat type only."""
    purpose_by_type = {"REVEAL": "INTRODUCE_ANOMALY", "QUESTION": "RAISE_SUSPICION", "DECISION": "TRIGGER_DECISION", "ESCALATION": "ESCALATE_THREAT", "HOOK": "HOOK_NEXT_SCENE", "REACTION": "SHIFT_POWER", "ACTION": "SETUP_RELATIONSHIP"}
    actions_by_type = {"REVEAL": "OBSERVE_REACTION", "QUESTION": "TEST_OTHER_CHARACTER", "DECISION": "CONTROL_EXIT", "ESCALATION": "PRESSURE_WITHOUT_OPEN_THREAT", "HOOK": "WITHHOLD_RESPONSE", "REACTION": "OBSERVE_REACTION", "ACTION": "HOLD_POSITION"}
    result: list[dict[str, Any]] = []
    for beat in _beats(scene):
        ref = _text(beat.get("beat_id") or beat.get("id"))
        if not ref:
            continue
        chars = [str(x) for x in _list(beat.get("characters")) if str(x)]
        action = actions_by_type.get(_text(beat.get("beat_type") or beat.get("type")).upper(), "OBSERVE_REACTION")
        required = beat.get("requires_reaction") is True
        result.append({"decision_id": f"DBD_{ref}", "beat_ref": ref, "dramatic_purpose": purpose_by_type.get(_text(beat.get("beat_type") or beat.get("type")).upper(), "SETUP_RELATIONSHIP"), "audience_state_delta": {"knowledge_added": [str(beat.get("information_delta") or "")] if beat.get("information_delta") else [], "knowledge_confirmed": [], "knowledge_invalidated": [], "belief_shift": [], "open_question_added": [], "open_question_resolved": []}, "character_state_deltas": [{"character_ref": chars[0], "dimension": "ATTENTION_TARGET", "from": "UNFOCUSED", "to": "ACTIVE_BEAT"}] if chars else [], "performance_objectives": [{"character_ref": char, "action": action, "target": "ACTIVE_BEAT", "success_condition": "beat action remains legible"} for char in chars], "reaction_contracts": [{"character_ref": chars[0] if chars else "SCENE_CAST", "trigger_ref": ref, "reaction_type": "RECOGNITION", "required": True, "state_delta_ref": ref}] if required else [], "information_policy": {"audience_knows_truth": True, "characters_with_truth": chars, "characters_uncertain": [], "withheld_from": []}, "tempo_function": "HOLD_FOR_DOUBT" if required else "PROGRESS_BEAT", "blocking_requirements": [], "source_refs": [f"ScriptIR:{ref}"], "director_notes": "", "decision_origin": origin, "review_status": "REVIEW_REQUIRED" if origin == "GENERATED_DRAFT" else "CONFIRMED"})
    return result


def review_director_creative_quality(treatment: dict[str, Any]) -> dict[str, Any]:
    """Advisory review; it can never qualify, mutate or move authority."""
    decisions = [x for x in _list(treatment.get("director_beat_decisions")) if isinstance(x, dict)]
    purposes = Counter(_text(x.get("dramatic_purpose")) for x in decisions)
    duplicate_counts = {key: count for key, count in sorted(purposes.items()) if key and count > 1}
    return {"dramatic_purpose_distribution": dict(sorted(purposes.items())), "duplicate_purpose_counts": duplicate_counts, "mutated": False, "authority_write": 0, "pointer_move": 0, "source_fact_write": 0}


__all__ = ["DRAMATIC_PURPOSES", "STATE_DIMENSIONS", "PERFORMANCE_ACTIONS", "REACTION_TYPES", "DIRECTOR_CONTRACT_VERSION", "validate_director_contract", "build_suggested_director_decisions", "review_director_creative_quality"]
