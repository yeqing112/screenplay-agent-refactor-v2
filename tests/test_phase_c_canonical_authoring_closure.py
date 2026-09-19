import copy
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from api.shot_plan_api import _confirm_phase_c_provenance
from core.phase_c_shot_plan import build_phase_c_contract, build_shot_requirements, compile_shot_continuity, compile_shot_coverage, validate_shot_design
from core.shot_plan_authority import shot_plan_payload_from_row, shot_plan_payload_hash
from core.storyboard_materializer import materialize_storyboard_from_shot_plan


ART = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"


def _pilot_docs():
    read = lambda name: json.loads((ART / name).read_text(encoding="utf-8"))
    treatment = read("episode_01_director_treatment_phase_b.json")
    blocking = read("episode_01_scene_blocking_phase_b.json")
    fixture = read("episode_01_shot_design_human_input_fixture.json")
    return treatment["scenes"], blocking["scenes"], fixture["scenes"]


def test_phase_c_contract_is_metadata_only_and_fixture_is_canonical():
    treatments, blockings, proposals = _pilot_docs()
    for treatment, blocking, proposal in zip(treatments, blockings, proposals):
        requirements = build_shot_requirements(treatment=treatment, blocking=blocking)
        contract = build_phase_c_contract(requirements=requirements)
        assert "shots" not in contract
        result = validate_shot_design(
            shots=proposal["shots"],
            requirements=contract,
            treatment=treatment,
            blocking=blocking,
            authoring_provenance=proposal["authoring_provenance"],
        )
        assert result["valid"] is True
        assert all("plan_shot_id" in shot and "shot_id" not in shot for shot in proposal["shots"])


def test_wrong_reaction_character_and_missing_reaction_ref_fail_closed():
    treatments, blockings, proposals = _pilot_docs()
    treatment, blocking, proposal = treatments[0], blockings[0], proposals[0]
    requirements = build_shot_requirements(treatment=treatment, blocking=blocking)
    shot = next(item for item in proposal["shots"] if item["reaction_contract_refs"])

    wrong_character = copy.deepcopy(proposal["shots"])
    target = next(item for item in wrong_character if item["plan_shot_id"] == shot["plan_shot_id"])
    target["subjects"] = ["INVENTED_CHARACTER"]
    assert not validate_shot_design(
        shots=wrong_character,
        requirements=requirements,
        treatment=treatment,
        blocking=blocking,
        authoring_provenance=proposal["authoring_provenance"],
    )["valid"]

    missing_ref = copy.deepcopy(proposal["shots"])
    target = next(item for item in missing_ref if item["plan_shot_id"] == shot["plan_shot_id"])
    target["reaction_contract_refs"] = []
    assert not validate_shot_design(
        shots=missing_ref,
        requirements=requirements,
        treatment=treatment,
        blocking=blocking,
        authoring_provenance=proposal["authoring_provenance"],
    )["valid"]


def test_missing_required_prop_axis_and_unconfirmed_generated_draft_fail_closed():
    treatments, blockings, proposals = _pilot_docs()
    treatment, blocking, proposal = treatments[0], blockings[0], proposals[0]
    requirements = build_shot_requirements(treatment=treatment, blocking=blocking)
    prop_shot = next(item for item in proposal["shots"] if item["spatial_binding"]["prop_refs"])
    missing_prop = copy.deepcopy(proposal["shots"])
    target = next(item for item in missing_prop if item["plan_shot_id"] == prop_shot["plan_shot_id"])
    target["spatial_binding"]["prop_refs"] = []
    result = validate_shot_design(shots=missing_prop, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert not result["valid"]

    axis_shots = copy.deepcopy(proposal["shots"])
    axis_shot = next(item for item in axis_shots if item["axis_contract"]["axis_applicability"] == "REQUIRED")
    axis_shot["axis_contract"]["axis_ref"] = "AXIS_UNSPECIFIED"
    result = validate_shot_design(shots=axis_shots, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert any(error["code"] == "SHOT_AXIS_REF_INVALID" for error in result["errors"])

    provenance = {"proposal_origin": "GENERATED_DRAFT", "confirmed": False}
    result = validate_shot_design(shots=proposal["shots"], requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=provenance)
    assert any(error["code"] == "SHOT_AUTHORING_PROVENANCE_INVALID" for error in result["errors"])


def test_provenance_confirmation_requires_real_provider_and_matching_canonical_origin():
    with pytest.raises(ValueError, match="PROVIDER_PROPOSAL requires a provider call"):
        _confirm_phase_c_provenance({"proposal_origin": "PROVIDER_PROPOSAL", "provider": {"called": False, "calls": 0}}, confirmed_at="now")
    with pytest.raises(ValueError, match="canonical origin"):
        _confirm_phase_c_provenance({"proposal_origin": "HUMAN_INPUT", "canonical_origin": "PROVIDER_PROPOSAL_CONFIRMED"}, confirmed_at="now")
    with pytest.raises(ValueError, match="GENERATED_DRAFT requires explicit confirmation"):
        _confirm_phase_c_provenance({"proposal_origin": "GENERATED_DRAFT", "confirmed": False}, confirmed_at="now")


def test_shot_plan_payload_reads_canonical_shots_only():
    canonical = [{"plan_shot_id": "SH_CANONICAL", "beat_id": "B01", "purpose": "reveal", "camera": {"angle": "eye_level", "movement": "static"}}]
    legacy = [{"plan_shot_id": "SH_LEGACY"}]
    row = SimpleNamespace(
        scene_id="E01_SC001",
        scene_name="station",
        schema_version="shot_plan_v2",
        shots=json.dumps(canonical, ensure_ascii=False),
        unknowns="[]",
        model_info=json.dumps({"phase_c_plan": {"shots": legacy, "contract_version": "legacy"}, "phase_c_semantic_ready": True, "shot_design_status": "CANONICAL_CONFIRMED"}),
    )
    payload = shot_plan_payload_from_row(row)
    assert payload["shots"] == canonical
    assert payload["shots"] != legacy
    assert payload["phase_c_contract"]["contract_version"] == "legacy"
    assert "shots" not in payload["phase_c_contract"]
    projected = materialize_storyboard_from_shot_plan(payload)
    assert [item["plan_shot_id"] for item in projected] == [item["plan_shot_id"] for item in canonical]


def test_information_refs_are_semantic_and_aggregate_across_shots():
    treatments, blockings, proposals = _pilot_docs()
    treatment, blocking, proposal = treatments[1], blockings[1], proposals[1]
    requirements = build_shot_requirements(treatment=treatment, blocking=blocking)
    info_shot = next(item for item in proposal["shots"] if item.get("information_refs"))

    missing = copy.deepcopy(proposal["shots"])
    target = next(item for item in missing if item["plan_shot_id"] == info_shot["plan_shot_id"])
    target["information_refs"] = []
    result = validate_shot_design(shots=missing, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert any(error["code"] == "SHOT_INFORMATION_COVERAGE_MISSING" for error in result["errors"])

    wrong = copy.deepcopy(proposal["shots"])
    target = next(item for item in wrong if item["plan_shot_id"] == info_shot["plan_shot_id"])
    target["information_refs"] = ["INFO_WRONG_BEAT"]
    result = validate_shot_design(shots=wrong, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert any(error["code"] == "SHOT_INFORMATION_COVERAGE_MISSING" for error in result["errors"])

    contract = {"requirement_id": "REQ_B03", "beat_ref": "B03", "required_coverages": ["PRIMARY_BEAT_COVERAGE"], "required_subjects": [], "required_information": [{"information_ref": "INFO_A", "content": "fact"}], "required_information_refs": ["INFO_A"]}
    shots = [
        {"plan_shot_id": "SH_A", "beat_refs": ["B03"], "coverage_roles": ["PRIMARY_BEAT_COVERAGE"], "subjects": [], "information_refs": ["INFO_A"], "information_visibility": "AUDIENCE_ONLY", "spatial_binding": {}},
        {"plan_shot_id": "SH_B", "beat_refs": ["B03"], "coverage_roles": [], "subjects": [], "information_refs": [], "information_visibility": "AUDIENCE_ONLY", "spatial_binding": {}},
    ]
    first = compile_shot_coverage(treatment={}, blocking={}, shots=shots, requirements=[contract])
    second = compile_shot_coverage(treatment={}, blocking={}, shots=shots, requirements=[contract])
    assert first == second
    assert first[0]["complete"] is True
    assert first[0]["information_results"][0]["information_ref"] == "INFO_A"
    plan = {"scene_id": "E01_SC002", "schema_version": "shot_plan_v2", "shots": proposal["shots"], "phase_c_contract": build_phase_c_contract(requirements=requirements), "phase_c_semantic_ready": True}
    changed = copy.deepcopy(plan)
    changed["shots"][0]["information_refs"] = list(changed["shots"][0].get("information_refs", [])) + ["INFO_TAMPER"]
    assert shot_plan_payload_hash(plan) != shot_plan_payload_hash(changed)


def test_continuity_is_a_canonical_hard_gate_and_cross_requires_both_fields():
    treatments, blockings, proposals = _pilot_docs()
    treatment, blocking, proposal = treatments[1], blockings[1], proposals[1]
    requirements = build_shot_requirements(treatment=treatment, blocking=blocking)
    broken = copy.deepcopy(proposal["shots"])
    axis_shots = [item for item in broken if item["axis_contract"].get("axis_applicability") == "REQUIRED"]
    assert len(axis_shots) >= 2
    axis_shots[1]["axis_contract"]["screen_side_assignments"] = {"林晚": "RIGHT", "陆叔": "LEFT"}
    continuity = compile_shot_continuity(shots=broken, blocking=blocking)
    assert continuity["valid"] is False
    result = validate_shot_design(shots=broken, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert result["valid"] is False
    assert any(error["code"] == "SHOT_AXIS_CONTINUITY_INVALID" for error in result["errors"])

    cross = copy.deepcopy(proposal["shots"])
    cross_shot = next(item for item in cross if item["axis_contract"].get("axis_applicability") == "REQUIRED")
    cross_shot["axis_contract"].update({"axis_policy": "MOTIVATED_CROSS", "cross_motivation": "director reveals exit control", "reorientation_strategy": "re-establish both screen sides"})
    valid_cross = validate_shot_design(shots=cross, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert not any(error["code"] == "SHOT_AXIS_CROSS_INVALID" for error in valid_cross["errors"])
    cross_shot["axis_contract"].pop("reorientation_strategy")
    invalid_cross = validate_shot_design(shots=cross, requirements=requirements, treatment=treatment, blocking=blocking, authoring_provenance=proposal["authoring_provenance"])
    assert any(error["code"] == "SHOT_AXIS_CROSS_INVALID" for error in invalid_cross["errors"])


def test_pilot_gaslighting_uses_upstream_reactions_and_explicit_information_refs():
    _, _, proposals = _pilot_docs()
    proposal = proposals[1]
    claim = next(item for item in proposal["shots"] if item["beat_refs"] == ["SC02-B03"])
    doubt = next(item for item in proposal["shots"] if item["beat_refs"] == ["SC02-B04"])
    assert claim["subjects"] == ["陆叔", "林晚"]
    assert claim["reaction_contract_refs"] == ["RC_SC02-B03_陆叔"]
    assert claim["information_refs"] == ["INFO_SC02_B03_001"]
    assert doubt["subjects"] == ["林晚"]
    assert doubt["reaction_contract_refs"] == ["RC_SC02-B04_林晚"]
    assert doubt["information_visibility"] == "AUDIENCE_OBSERVES_CHARACTER_DOUBT"
