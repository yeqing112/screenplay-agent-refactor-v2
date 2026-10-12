"""Provider-free tests for the V7.7.1 claim-aware authoring boundary."""
from __future__ import annotations

from core.director_authoring_claim_contract import (
    make_manifest_claim,
    stage_a_field_semantic_contract,
    stage_b_field_semantic_contract,
    validate_authoring_response,
    validate_claim_manifest,
)
from core.director_claim_aware_support import audit_typed_manifest, resolve_typed_claim_support
from core.director_claim_entity_binding import validate_entity_ref
from core.director_claim_ir import make_claim
from core.director_claim_relation_registry import relation_compatible, validate_relation_registry
from core.director_source_claim_materialization import materialize_source_claims, source_structured_capability
from core.director_claim_extraction import extract_claims


def _source(*, claim_id: str, claim_type: str, subject: dict, predicate: str, object_: dict, qualifiers: dict | None = None, modality: str = "ASSERTED"):
    return make_claim(
        claim_id=claim_id,
        source_path="structured.source",
        raw_text="display text A",
        claim_type=claim_type,
        subject=subject,
        predicate=predicate,
        object_=object_,
        qualifiers=qualifiers,
        modality=modality,
        origin="SOURCE",
        support_status="SUPPORTED_EXPLICIT",
    )


def _manifest(*claims, stage="STAGE_A", slots=None):
    slots = slots or ["beat_0.objective"]
    return {
        "schema_version": "director_authoring_claim_manifest_v1",
        "authoring_stage": stage,
        "semantic_slots": slots,
        "covered_slots": list(slots),
        "claims": list(claims),
    }


def test_manifest_schema_does_not_require_raw_text_or_source_path():
    claim = make_manifest_claim(
        claim_id="AC_1",
        claim_type="DRAMATIC_OBJECTIVE",
        subject={"kind": "BEAT", "ref": "beat_0"},
        predicate="dramatic_task",
        object_={"kind": "TASK", "ref": "organize_information"},
        qualifiers={"semantic_slot": "beat_0.objective"},
    )
    assert "raw_text" not in claim and "source_path" not in claim
    assert validate_claim_manifest(_manifest(claim))["status"] == "PASS"


def test_source_claim_ids_are_stable_and_materialization_refuses_unstructured_units():
    units = [{"unit_id": "UNIT_1", "source_type": "SOURCE_ACTION", "text": "display text A"}]
    capability = source_structured_capability(units)
    result = materialize_source_claims(units)
    assert capability["status"] == "SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED"
    assert result["status"] == "SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED"
    assert result["claims"] == []


def test_structured_source_claim_ids_are_deterministic():
    units = [{
        "unit_id": "UNIT_1", "source_type": "SOURCE_ACTION", "text": "display text A",
        "actor": {"kind": "CHARACTER", "ref": "CHAR_A"},
        "action": {"predicate": "enter_guided"},
        "object": {"kind": "LOCATION", "ref": "LOC_A"},
        "participants": [{"kind": "CHARACTER", "ref": "CHAR_A"}],
        "fact_bindings": [{"claim_type": "CHARACTER_ACTION", "predicate": "enter_guided", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "object": {"kind": "LOCATION", "ref": "LOC_A"}}],
        "entity_refs": ["CHAR_A", "LOC_A"],
    }]
    first = materialize_source_claims(units)
    second = materialize_source_claims(units)
    assert first["status"] == "PASS"
    assert first["claims"][0]["claim_id"] == "SC_UNIT_1_enter_guided_00"
    assert first["claims"][0]["claim_id"] == second["claims"][0]["claim_id"]


def test_stage_a_objective_is_dramatic_objective_and_requires_explicit_intent_claim():
    contract = stage_a_field_semantic_contract()
    assert contract["fields"]["objective"]["allowed_claim_types"] == ["DRAMATIC_OBJECTIVE"]
    assert contract["fields"]["objective"]["character_intent_requires_explicit_manifest_claim"] is True


def test_stage_b_contract_does_not_make_performance_option_canonical():
    contract = stage_b_field_semantic_contract()
    assert "PERFORMANCE_OPTION" in contract["fields"]["performance"]["allowed_claim_types"]
    assert contract["fields"]["performance"]["canonical_fact_creation"] is False


def test_claim_completeness_is_structural_not_keyword_based():
    claim = make_manifest_claim(
        claim_id="AC_2", claim_type="DRAMATIC_OBJECTIVE",
        subject={"kind": "BEAT", "ref": "beat_0"}, predicate="dramatic_task",
        object_={"kind": "TASK", "ref": "organize_information"},
        qualifiers={"semantic_slot": "beat_0.objective"},
    )
    result = validate_authoring_response({"beat_plan_ir": {"beats": [{}]}, "claim_manifest": _manifest(claim)})
    assert result["status"] == "PASS"
    altered = dict(_manifest(claim), covered_slots=[])
    assert validate_authoring_response({"beat_plan_ir": {}, "claim_manifest": altered})["status"] == "BLOCKED"


def test_manifest_omission_cannot_hide_a_structured_stage_a_slot():
    response = {
        "beat_plan_ir": {"beats": [{"beat_ref": "beat_0", "objective": "display text with a risky idea"}]},
        "claim_manifest": _manifest([], slots=[]),
    }
    assert validate_authoring_response(response)["status"] == "BLOCKED"


def test_typed_uncertainty_blocks_certainty_without_uncertainty_wording():
    source = _source(claim_id="SC_VISIT_UNCERTAIN", claim_type="UNCERTAINTY", subject={"kind": "EVENT", "ref": "EVENT_VISIT"}, predicate="status", object_={"kind": "STATE", "ref": "UNRESOLVED"}, modality="UNCERTAIN")
    claim = make_manifest_claim(claim_id="AC_CERTAINTY", claim_type="CERTAINTY_ASSERTION", subject={"kind": "EVENT", "ref": "EVENT_VISIT"}, predicate="status", object_={"kind": "STATE", "ref": "FIRST"}, source_claim_ids=["SC_VISIT_UNCERTAIN"], origin="STAGE_A", qualifiers={"semantic_slot": "beat_0.information_change"})
    result = resolve_typed_claim_support(claim, source_claims=[source])
    assert result["status"] == "BLOCKED"


def test_typed_provenance_blocks_without_prose():
    source = _source(claim_id="SC_LABEL_AUTHOR", claim_type="OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "PROP_LABEL"}, predicate="has_property", object_={"kind": "PROPERTY", "ref": "AUTHORED_BY_PARENT"})
    claim = make_manifest_claim(claim_id="AC_ORIGIN", claim_type="OBJECT_PROVENANCE", subject={"kind": "PERSON", "ref": "PERSON_PARENT"}, predicate="left_by", object_={"kind": "OBJECT", "ref": "PROP_ROOM"}, source_claim_ids=["SC_LABEL_AUTHOR"], qualifiers={"semantic_slot": "beat_0.information_change"})
    assert resolve_typed_claim_support(claim, source_claims=[source])["support_status"] == "UNSUPPORTED"


def test_typed_property_does_not_cross_objects():
    source = _source(claim_id="SC_BOX_PROPERTY", claim_type="OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "PROP_BOX"}, predicate="has_property", object_={"kind": "PROPERTY", "ref": "HANDWRITTEN"})
    claim = make_manifest_claim(claim_id="AC_TICKET_PROPERTY", claim_type="OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "PROP_TICKET"}, predicate="has_property", object_={"kind": "PROPERTY", "ref": "HANDWRITTEN"}, source_claim_ids=["SC_BOX_PROPERTY"], qualifiers={"semantic_slot": "beat_0.information_change"})
    assert resolve_typed_claim_support(claim, source_claims=[source])["status"] == "BLOCKED"


def test_typed_environment_does_not_propagate_between_states():
    source = _source(claim_id="SC_LIGHT_OFF", claim_type="ENVIRONMENT_STATE", subject={"kind": "ENVIRONMENT", "ref": "LOC_A"}, predicate="state_value", object_={"kind": "LIGHT", "ref": "OFF"})
    claim = make_manifest_claim(claim_id="AC_LIGHT_DIM", claim_type="ENVIRONMENT_STATE", subject={"kind": "ENVIRONMENT", "ref": "LOC_A"}, predicate="state_value", object_={"kind": "LIGHT", "ref": "DIM"}, source_claim_ids=["SC_LIGHT_OFF"], qualifiers={"semantic_slot": "beat_0.information_change"})
    assert resolve_typed_claim_support(claim, source_claims=[source])["status"] == "BLOCKED"


def test_typed_possession_is_ambiguous_without_transfer_source_binding():
    source = _source(claim_id="SC_INSERT", claim_type="CHARACTER_ACTION", subject={"kind": "ACTOR", "ref": "ACTOR_UNKNOWN"}, predicate="receive_object", object_={"kind": "OBJECT", "ref": "PROP_TICKET"})
    claim = make_manifest_claim(claim_id="AC_RECEIVE", claim_type="OBJECT_POSSESSION", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="received_by", object_={"kind": "OBJECT", "ref": "PROP_TICKET"}, source_claim_ids=["SC_INSERT"], qualifiers={"semantic_slot": "beat_0.information_change"})
    assert resolve_typed_claim_support(claim, source_claims=[source])["status"] == "BLOCKED"


def test_typed_performance_option_passes_without_source_claim():
    claim = make_manifest_claim(claim_id="AC_OPTION", claim_type="PERFORMANCE_OPTION", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="playable_tone", object_={"kind": "OPTION", "ref": "PROBING"}, canonicality="NON_CANONICAL_PERFORMANCE_OPTION", modality="PLAYABLE_OPTION", authority_required="STAGE_B", origin="STAGE_B", qualifiers={"semantic_slot": "stage_b.performance"})
    assert resolve_typed_claim_support(claim, source_claims=[])["support_status"] == "SUPPORTED_AS_NON_CANONICAL_OPTION"


def test_typed_canonical_intent_blocks_without_source_claim():
    claim = make_manifest_claim(claim_id="AC_INTENT", claim_type="CHARACTER_INTENT", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="probe", object_={"kind": "CHARACTER", "ref": "CHAR_B"}, origin="STAGE_B", qualifiers={"semantic_slot": "stage_b.performance"})
    assert resolve_typed_claim_support(claim, source_claims=[])["status"] == "BLOCKED"


def test_relation_registry_and_entity_binding_are_runtime_typed():
    assert validate_relation_registry()["status"] == "PASS"
    assert validate_entity_ref({"kind": "CHARACTER", "ref": "CHAR_A"})["status"] == "PASS"
    candidate = {"claim_type": "CHARACTER_ACTION", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "lead_into", "object": {"kind": "LOCATION", "ref": "LOC_A"}, "qualifiers": {"destination": "LOC_A"}}
    source = {"claim_type": "CHARACTER_ACTION", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "guide_into", "object": {"kind": "LOCATION", "ref": "LOC_A"}, "qualifiers": {"destination": "LOC_A"}}
    assert relation_compatible(candidate, source)


def test_scene_id_is_bound_from_runtime_input_in_legacy_diagnostic_projection():
    claims = extract_claims({"scene_objective": "display text A"}, origin="STAGE_A", scene_id="RUNTIME_SCENE")
    scene_claim = next(item for item in claims if item["claim_type"] == "DRAMATIC_OBJECTIVE")
    assert scene_claim["subject"]["ref"] == "RUNTIME_SCENE"


def test_participant_identity_is_a_runtime_ref_in_claim_manifest():
    claim = make_manifest_claim(
        claim_id="AC_RUNTIME_PARTICIPANT", claim_type="PERFORMANCE_OPTION",
        subject={"kind": "CHARACTER", "ref": "DECLARED_CHARACTER_1"}, predicate="playable_tone",
        object_={"kind": "OPTION", "ref": "CALM"}, canonicality="NON_CANONICAL_PERFORMANCE_OPTION",
        modality="PLAYABLE_OPTION", authority_required="STAGE_B", origin="STAGE_B",
        qualifiers={"semantic_slot": "stage_b.performance"},
    )
    assert claim["subject"]["ref"] == "DECLARED_CHARACTER_1"
    assert audit_typed_manifest(_manifest(claim, stage="STAGE_B", slots=["stage_b.performance"]), source_claims=[])["status"] == "PASS"


def test_same_display_text_different_typed_claims_have_different_results():
    option = make_manifest_claim(claim_id="AC_DISPLAY_OPTION", claim_type="PERFORMANCE_OPTION", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="playable_tone", object_={"kind": "OPTION", "ref": "PROBING"}, canonicality="NON_CANONICAL_PERFORMANCE_OPTION", modality="PLAYABLE_OPTION", authority_required="STAGE_B", origin="STAGE_B", qualifiers={"semantic_slot": "stage_b.performance"})
    intent = make_manifest_claim(claim_id="AC_DISPLAY_INTENT", claim_type="CHARACTER_INTENT", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="probe", object_={"kind": "CHARACTER", "ref": "CHAR_B"}, origin="STAGE_B", qualifiers={"semantic_slot": "stage_b.performance"})
    assert audit_typed_manifest(_manifest(option, stage="STAGE_B", slots=["stage_b.performance"]), source_claims=[])["status"] == "PASS"
    assert audit_typed_manifest(_manifest(intent, stage="STAGE_B", slots=["stage_b.performance"]), source_claims=[])["status"] == "BLOCKED"
