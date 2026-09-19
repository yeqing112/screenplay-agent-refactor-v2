import copy
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from api.shot_plan_api import _confirm_phase_c_provenance
from core.phase_c_shot_plan import build_phase_c_contract, build_shot_requirements, validate_shot_design
from core.shot_plan_authority import shot_plan_payload_from_row
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
