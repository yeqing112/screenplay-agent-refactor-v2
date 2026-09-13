import pytest

from core.director_auxiliary import (
    AuxiliaryShotValidationError,
    validate_auxiliary_shot_proposal,
    validate_auxiliary_shot_proposals,
)
from core.director_creative_contract import build_director_creative_contract
from core.director_patch_repair import repair_failed_auxiliary_proposal
from core.shot_plan import build_shot_plan
import core.director_patch_repair as repair_module


def _inputs():
    treatment = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "beat_map": [{"beat_id": "B01", "type": "reveal", "event": "林晚发现照片"}],
    }
    blocking = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "participants": [{"character_id": "C1", "name": "林晚"}],
    }
    plan = build_shot_plan(treatment=treatment, blocking=blocking)
    plan["shots"][0]["participants"] = ["C1"]
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    return plan, contract


def _proposal(proposal_id="AUX_001", *, source_beat_id="B01", participants=None):
    return {
        "proposal_id": proposal_id,
        "proposal_type": "reaction",
        "source_beat_id": source_beat_id,
        "insert_after_plan_shot_id": "S01",
        "purpose": "show_reaction",
        "why_needed": "结构镜头没有承载关键反应",
        "participants": participants if participants is not None else ["C1"],
        "camera": {"shot_size": "CU", "angle": "eye_level"},
    }


def test_valid_auxiliary_proposal_is_bound_without_mutating_plan():
    plan, contract = _inputs()
    before = dict(plan)
    result = validate_auxiliary_shot_proposal(_proposal(), plan, contract)
    assert result["source_beat_id"] == "B01"
    assert plan == before


def test_auxiliary_proposal_requires_existing_source_beat_and_anchor():
    plan, contract = _inputs()
    with pytest.raises(AuxiliaryShotValidationError) as error:
        validate_auxiliary_shot_proposal(_proposal(source_beat_id="B99"), plan, contract)
    assert error.value.code == "AUXILIARY_SHOT_UNBOUND_BEAT"

    with pytest.raises(AuxiliaryShotValidationError) as error:
        invalid_anchor = _proposal()
        invalid_anchor["insert_after_plan_shot_id"] = "S99"
        validate_auxiliary_shot_proposal(invalid_anchor, plan, contract)
    assert error.value.code == "UNKNOWN_PLAN_SHOT_ID"


def test_auxiliary_proposal_rejects_unbound_participant_and_invalid_type():
    plan, contract = _inputs()
    with pytest.raises(AuxiliaryShotValidationError) as error:
        validate_auxiliary_shot_proposal(_proposal(participants=["C99"]), plan, contract)
    assert error.value.code == "INVALID_CHARACTER_REFERENCE"

    with pytest.raises(AuxiliaryShotValidationError) as error:
        invalid_type = _proposal()
        invalid_type["proposal_type"] = "new_plot"
        validate_auxiliary_shot_proposal(invalid_type, plan, contract)
    assert error.value.code == "INVALID_AUXILIARY_TYPE"


def test_auxiliary_budget_is_two_per_source_beat_and_partial_mode_keeps_valid():
    plan, contract = _inputs()
    proposals = [_proposal("AUX_001"), _proposal("AUX_002"), _proposal("AUX_003")]
    with pytest.raises(AuxiliaryShotValidationError) as error:
        validate_auxiliary_shot_proposals(proposals, plan, contract)
    assert error.value.code == "AUXILIARY_SHOT_BUDGET_EXCEEDED"

    partial = validate_auxiliary_shot_proposals(proposals, plan, contract, allow_partial=True)
    assert partial["accepted_count"] == 2
    assert partial["rejected_count"] == 1
    assert partial["rejected"][0]["code"] == "AUXILIARY_SHOT_BUDGET_EXCEEDED"


def test_auxiliary_local_repair_keeps_proposal_identity_and_records_ledger(monkeypatch):
    plan, contract = _inputs()
    proposal = _proposal()
    records = []
    monkeypatch.setattr(repair_module, "record_repair_attempt", lambda **kwargs: records.append(kwargs))
    result = repair_failed_auxiliary_proposal(
        structural_shot_plan=plan,
        failed_proposal={**proposal, "why_needed": ""},
        issue={"code": "DIRECTOR_AUXILIARY_MOTIVATION_REQUIRED"},
        contract=contract,
        repair_callable=lambda _request: {**proposal, "why_needed": "补足关键反应"},
        session=object(),
        repair_context={"book_id": 1, "episode": 1, "scene_id": "E01_SC01"},
        model="mock",
        prompt_fingerprint="aux-fp",
    )
    assert result["status"] == "repaired"
    assert result["accepted_proposal"]["proposal_id"] == "AUX_001"
    assert result["accepted_proposal"]["source_beat_id"] == "B01"
    assert len(records) == 1
    assert records[0]["issue"]["target_layer"] == "DIRECTOR_CREATIVE"
    assert records[0]["issue"]["target_id"] == "AUX_001"
    assert records[0]["context"]["proposal_id"] == "AUX_001"


def test_auxiliary_local_repair_cannot_rebind_source_or_exceed_two_attempts():
    plan, contract = _inputs()
    proposal = _proposal()
    calls = []
    result = repair_failed_auxiliary_proposal(
        structural_shot_plan=plan,
        failed_proposal=proposal,
        issue={"code": "AUXILIARY_SHOT_UNBOUND_BEAT"},
        contract=contract,
        repair_callable=lambda _request: calls.append(True) or {**proposal, "source_beat_id": "B99"},
        max_attempts=8,
    )
    assert result["status"] == "fallback"
    assert result["attempt_count"] == 2
    assert len(calls) == 2
