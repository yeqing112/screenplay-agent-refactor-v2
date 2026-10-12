"""Provider-free V7.7.2 SourceClaim authority tests."""
from __future__ import annotations

from core.source_semantic_claim_authority import (
    FACT_VALUE_VERSION,
    candidate_contract,
    fact_claim_mapping_registry,
    materialize_dialogue_speech_act_claim,
    materialize_source_claim_from_fact_authority,
    materialize_source_claim_set,
    source_claim_coverage,
    source_claim_fingerprint,
    source_semantic_fact_value_contract,
    validate_candidate,
    validate_fact_value,
    validate_evidence_binding,
)
from core.fact_semantic_verifier import compile_semantic_authority


FP = "source-fingerprint-A"
ENTITY_REGISTRY = {
    "CHAR_A": {"kind": "CHARACTER"},
    "CHAR_B": {"kind": "CHARACTER"},
    "LOC_X": {"kind": "LOCATION"},
    "PROP_A": {"kind": "OBJECT"},
    "PROP_B": {"kind": "OBJECT"},
    "LIGHT_OFF": {"kind": "LIGHT"},
}
EVIDENCE = {"anchors": [{"anchor_ref": "EV_ACTION_1", "source_fingerprint": FP}, {"anchor_ref": "EV_DIALOGUE_1", "source_fingerprint": FP}]}


def _typed_fact(*, fact_id="FACT_ACTION", predicate="enter_guided", subject_id="CHAR_A", value_object=None, evidence=None, authority="source_text", status="confirmed"):
    return {
        "fact_id": fact_id,
        "subject_type": "CHARACTER",
        "subject_id": subject_id,
        "predicate": predicate,
        "value": {"schema_version": FACT_VALUE_VERSION, "object": value_object or {"kind": "LOCATION", "ref": "LOC_X"}, "qualifiers": {"destination": "LOC_X"}, "polarity": "POSITIVE", "modality": "ASSERTED"},
        "scope": "scene",
        "authority": authority,
        "status": status,
        "evidence": evidence or ["EV_ACTION_1"],
    }


def _overlay(fact_id="FACT_ACTION", *, disposition="WORLD_FACT_CONFIRMED", downstream=True, review=False):
    return {"fact_id": fact_id, "semantic_disposition": disposition, "downstream_eligible": downstream, "review_required": review, "semantic_authority_fingerprint": "semantic-fingerprint-A"}


def test_candidate_contract_rejects_offsets_and_provider_authority():
    candidate = {"schema_version": "source_semantic_claim_candidate_v1", "candidate_id": "SCC_1", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "enter_guided", "object": {"kind": "LOCATION", "ref": "LOC_X"}, "qualifiers": {}, "polarity": "POSITIVE", "modality": "ASSERTED", "evidence_refs": ["EV_ACTION_1"], "source_unit_refs": ["UNIT_1"], "char_start": 0, "source_claim_supported": True}
    assert validate_candidate(candidate)["status"] == "BLOCKED"
    assert "provider_may_not_supply" in candidate_contract()


def test_typed_fact_value_schema_is_closed_to_arbitrary_dicts():
    assert validate_fact_value(_typed_fact()["value"])["status"] == "PASS"
    assert validate_fact_value({"object": {"kind": "LOCATION", "ref": "LOC_X"}})["status"] == "BLOCKED"
    assert source_semantic_fact_value_contract()["display_prose_allowed"] is False


def test_world_fact_confirmed_materializes_deterministically():
    result = materialize_source_claim_from_fact_authority(fact=_typed_fact(), semantic_overlay=_overlay(), entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="semantic-fingerprint-A")
    assert result["status"] == "PASS"
    claim = result["claim"]
    assert claim["claim_id"] == "SC_FACT_ACTION"
    assert claim["source_fact_id"] == "FACT_ACTION"
    assert claim["fact_snapshot_id"] == "49"


def test_confirmed_fact_without_semantic_overlay_blocks():
    result = materialize_source_claim_from_fact_authority(fact=_typed_fact(), semantic_overlay=None, entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="x")
    assert result["status"] == "BLOCKED"
    assert "SEMANTIC_AUTHORITY_NOT_WORLD_FACT_CONFIRMED" in result["eligibility"]["errors"]


def test_provider_entailed_cannot_override_evidence_or_machine_guard():
    result = materialize_source_claim_from_fact_authority(fact=_typed_fact(), semantic_overlay={**_overlay(), "verifier_verdict": "ENTAILED"}, entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint="different-fingerprint", fact_snapshot_id=49, semantic_authority_fingerprint="x")
    assert result["status"] == "BLOCKED"
    assert any(item.startswith("EVIDENCE_STALE") for item in result["eligibility"]["errors"])


def test_existing_semantic_overlay_compiler_keeps_entailed_non_authoritative_when_guarded():
    overlay = compile_semantic_authority(
        facts=[{"fact_id": "FACT_ACTION", "subject_id": "CHAR_A", "predicate": "enter_guided", "value": {"object": "LOC_X"}}],
        verifier_results=[{"fact_id": "FACT_ACTION", "verdict": "ENTAILED", "supported_components": ["action"], "unsupported_components": [], "rationale": "typed mock"}],
        machine_guards={"FACT_ACTION": {"hard_blockers": ["EVIDENCE_AUTHORITY_NOT_PASS"], "confirmation_ceilings": []}},
        evidence_authority_status="BLOCKED",
    )
    row = overlay["facts"][0]
    assert row["semantic_disposition"] == "CLAIM_SUPPORTED"
    assert row["effective_authority"] == "model_observation"
    assert row["downstream_eligible"] is False


def test_derived_and_model_observation_facts_do_not_materialize():
    derived = materialize_source_claim_from_fact_authority(fact=_typed_fact(authority="derived_fact"), semantic_overlay=_overlay(), entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="x")
    observed = materialize_source_claim_from_fact_authority(fact=_typed_fact(authority="model_observation"), semantic_overlay=_overlay(), entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="x")
    assert derived["status"] == "BLOCKED" and observed["status"] == "BLOCKED"


def test_entity_relation_and_qualifier_mismatch_block():
    unknown = _typed_fact(value_object={"kind": "LOCATION", "ref": "UNKNOWN_LOCATION"})
    assert materialize_source_claim_from_fact_authority(fact=unknown, semantic_overlay=_overlay(), entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="x")["status"] == "BLOCKED"
    mismatch = _typed_fact(predicate="unknown_relation", value_object={"kind": "OBJECT", "ref": "PROP_B"})
    assert materialize_source_claim_from_fact_authority(fact=mismatch, semantic_overlay=_overlay(), entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="x")["status"] == "BLOCKED"


def test_dialogue_speech_act_is_deterministic_but_not_world_fact():
    result = materialize_dialogue_speech_act_claim(dialogue={"dialogue_id": "DIALOGUE_1", "speaker_ref": "CHAR_A", "speaker_binding": "DECLARED", "evidence_refs": ["EV_DIALOGUE_1"]}, evidence_index=EVIDENCE, source_fingerprint=FP, entity_registry=ENTITY_REGISTRY, fact_snapshot_id=49, semantic_authority_fingerprint="x")
    assert result["status"] == "PASS"
    assert result["world_fact_created"] is False
    assert result["claim"]["claim_type"] == "SOURCE_SPEECH_ACT"


def test_source_claim_set_and_coverage_are_typed():
    fact = _typed_fact()
    set_result = materialize_source_claim_set(facts=[fact], semantic_overlay={"facts": [_overlay()]}, entity_registry=ENTITY_REGISTRY, evidence_index=EVIDENCE, source_fingerprint=FP, fact_snapshot_id=49, semantic_authority_fingerprint="x")
    assert set_result["status"] == "PASS"
    coverage = source_claim_coverage(source_units=[{"unit_id": "UNIT_1"}] * 12, source_claims=set_result["claims"], required_semantic_types=["ACTION", "SPEECH_ACT", "OBJECT_PROPERTY", "UNCERTAINTY"], typed_requirement_manifest_present=True)
    assert coverage["status"] == "INSUFFICIENT"


def test_fingerprint_ignores_display_prose_but_changes_with_typed_fact():
    first = {"claim_type": "CHARACTER_ACTION", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "enter_guided", "object": {"kind": "LOCATION", "ref": "LOC_X"}, "qualifiers": {}, "polarity": "POSITIVE", "modality": "ASSERTED", "source_fact_id": "FACT_1", "evidence_refs": ["EV_ACTION_1"], "display_prose": "display A"}
    second = {**first, "display_prose": "unrelated display B"}
    changed = {**first, "predicate": "different_relation"}
    assert source_claim_fingerprint(first) == source_claim_fingerprint(second)
    assert source_claim_fingerprint(first) != source_claim_fingerprint(changed)


def test_evidence_ref_duplicate_and_stale_are_rejected():
    assert validate_evidence_binding(evidence_refs=["EV_ACTION_1", "EV_ACTION_1"], evidence_index=EVIDENCE, source_fingerprint=FP)["status"] == "BLOCKED"
    assert validate_evidence_binding(evidence_refs=["EV_ACTION_1"], evidence_index=EVIDENCE, source_fingerprint="stale")["status"] == "BLOCKED"


def test_mapping_registry_is_versioned_and_not_phrase_driven():
    registry = fact_claim_mapping_registry()
    assert registry["schema_version"] == "source_fact_claim_mapping_registry_v1"
    assert registry["raw_text_semantics"] is False


def test_snapshot_49_read_only_coverage_audit_is_insufficient():
    import json
    from pathlib import Path
    path = Path("docs/canonical-canary/v7_7_2-source-semantic-claim-authority/CURRENT_SOURCE_CLAIM_AUTHORITY_GAP.json")
    if not path.exists():
        return
    audit = json.loads(path.read_text(encoding="utf-8-sig"))
    assert audit["fact_snapshot_id"] == 49
    assert audit["fact_snapshot_record_count"] == 2
    assert audit["eligible_source_claim_count"] == 0
    assert audit["status"] == "INSUFFICIENT"
