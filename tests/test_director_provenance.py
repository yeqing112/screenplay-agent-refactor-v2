import pytest
from types import SimpleNamespace

from core.director_provenance import (
    confirmation_event,
    project_legacy_flags,
    proposal_provenance,
    resolve_canonical_origin,
)
from api.director_treatment_api import _validate_llm_candidate
from core.director_treatment_authority import build_treatment_authority_envelope
from core.director_treatment_authority import validate_phase_b_provenance_readiness


def test_human_input_confirms_as_human_authored():
    provenance = proposal_provenance("HUMAN_INPUT", provider={"called": False, "calls": 0}, human_input=True)
    event = confirmation_event(provenance, confirmed_at="2026-09-20T00:00:00Z")
    assert resolve_canonical_origin(provenance, event) == "HUMAN_AUTHORED"
    assert project_legacy_flags(provenance) == {"llm_called": False, "llm_generated": False}


def test_generated_draft_confirms_as_human_authored():
    provenance = proposal_provenance("GENERATED_DRAFT", provider={"called": False, "calls": 0})
    event = confirmation_event(provenance, confirmed_at="2026-09-20T00:00:00Z")
    assert event["source_proposal_origin"] == "GENERATED_DRAFT"
    assert event["canonical_origin"] == "HUMAN_AUTHORED"


def test_provider_proposal_confirms_as_provider_confirmed():
    provenance = proposal_provenance("PROVIDER_PROPOSAL", provider={"called": True, "calls": 1, "profile_id": "p", "model": "m", "request_fingerprint": "rq", "response_fingerprint": "rs"})
    event = confirmation_event(provenance, confirmed_at="2026-09-20T00:00:00Z")
    assert resolve_canonical_origin(provenance, event) == "PROVIDER_PROPOSAL_CONFIRMED"
    assert project_legacy_flags(provenance) == {"llm_called": True, "llm_generated": True}


def test_provider_mismatch_fails_closed():
    with pytest.raises(ValueError, match="DIRECTOR_PROVENANCE_INVALID"):
        proposal_provenance("PROVIDER_PROPOSAL", provider={"called": False, "calls": 0})
    with pytest.raises(ValueError, match="DIRECTOR_PROVENANCE_INVALID"):
        proposal_provenance("HUMAN_INPUT", provider={"called": True, "calls": 1})


def test_invalid_confirmation_boundary_fails_closed():
    provenance = proposal_provenance("HUMAN_INPUT", provider={"called": False, "calls": 0})
    with pytest.raises(ValueError, match="DIRECTOR_PROVENANCE_INVALID"):
        resolve_canonical_origin(provenance, {"confirmed": True, "boundary": "caller"})


def test_candidate_cannot_inject_canonical_origin():
    baseline = {"scene_id": "S1", "scene_name": "Scene", "character_intents": {}, "beat_map": [], "unknowns": [], "constraints": []}
    candidate = {"canonical_origin": "HUMAN_AUTHORED"}
    with pytest.raises(ValueError, match="non-whitelisted"):
        _validate_llm_candidate(candidate, baseline)


def test_authority_envelope_fingerprint_binds_provenance():
    treatment = {"scene_id": "S1", "scene_name": "Scene", "dramatic_objective": "objective", "audience_question": "question", "character_intents": {}, "beat_map": [], "relationship_power_shift": "", "audience_emotion": "", "information_strategy": "", "performance_direction": "", "visual_strategy": "visual", "coverage_strategy": "", "sound_strategy": "", "edit_rhythm": "", "constraints": [], "unknowns": [], "director_contract_version": "director_semantic_contract_v1", "director_beat_decisions": []}
    evidence = {"book_id": 1, "episode": 1, "scene": {"scene_id": "S1", "name": "Scene"}, "scene_id": "S1", "scene_name": "Scene", "characters": [], "locked_references": []}
    version = SimpleNamespace(id=1, revision=1, payload_hash="ir")
    ir_envelope = {"envelope_fingerprint": "ir-env"}
    human = proposal_provenance("HUMAN_INPUT", provider={"called": False, "calls": 0})
    event = confirmation_event(human, confirmed_at="2026-09-20T00:00:00Z")
    provider = proposal_provenance("PROVIDER_PROPOSAL", provider={"called": True, "calls": 1, "profile_id": "p", "model": "m", "request_fingerprint": "rq", "response_fingerprint": "rs"})
    provider_event = confirmation_event(provider, confirmed_at="2026-09-20T00:00:00Z")
    first = build_treatment_authority_envelope(treatment=treatment, evidence=evidence, script_ir={}, script_ir_version=version, script_ir_envelope=ir_envelope, treatment_id=1, treatment_revision=1, provenance=human, confirmation=event, canonical_origin="HUMAN_AUTHORED")
    second = build_treatment_authority_envelope(treatment=treatment, evidence=evidence, script_ir={}, script_ir_version=version, script_ir_envelope=ir_envelope, treatment_id=1, treatment_revision=1, provenance=provider, confirmation=provider_event, canonical_origin="PROVIDER_PROPOSAL_CONFIRMED")
    assert first["envelope_fingerprint"] != second["envelope_fingerprint"]


def test_missing_provenance_is_legacy_readable_but_not_phase_b_ready():
    result = validate_phase_b_provenance_readiness(
        envelope={"semantic_contract": {"version": "director_semantic_contract_v1"}},
        model_info={"mode": "legacy", "llm_called": False},
    )
    assert result["ready"] is False
    assert result["invalid"] is False
    assert result["reasons"] == ["DIRECTOR_PROVENANCE_CONTRACT_MISSING"]


def test_complete_provenance_is_phase_b_ready():
    provenance = proposal_provenance("HUMAN_INPUT", provider={"called": False, "calls": 0}, human_input=True)
    event = confirmation_event(provenance, confirmed_at="2026-09-20T00:00:00Z")
    envelope = {
        "proposal_provenance": provenance,
        "confirmation_event": event,
        "canonical_origin_summary": "HUMAN_AUTHORED",
        "provider_provenance": provenance["provider"],
        "provenance": {"proposal_provenance": provenance, "confirmation_event": event, "canonical_origin": "HUMAN_AUTHORED", "provider": provenance["provider"]},
    }
    result = validate_phase_b_provenance_readiness(
        envelope=envelope,
        model_info={"proposal_provenance": provenance, "confirmation_event": event, "canonical_origin": "HUMAN_AUTHORED", **project_legacy_flags(provenance)},
    )
    assert result["ready"] is True
    assert result["reasons"] == []


def test_invalid_confirmation_and_provider_projection_are_tamper():
    provenance = proposal_provenance("HUMAN_INPUT", provider={"called": False, "calls": 0})
    event = confirmation_event(provenance, confirmed_at="2026-09-20T00:00:00Z")
    event["source_proposal_origin"] = "PROVIDER_PROPOSAL"
    result = validate_phase_b_provenance_readiness(
        envelope={"proposal_provenance": provenance, "confirmation_event": event, "canonical_origin_summary": "HUMAN_AUTHORED", "provider_provenance": {**provenance["provider"], "calls": 1}},
        model_info={},
    )
    assert result["invalid"] is True
    assert result["reasons"] == ["DIRECTOR_PROVENANCE_TAMPERED"]
