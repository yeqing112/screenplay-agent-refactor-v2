import pytest
from core.director_semantics import DIRECTOR_CONTRACT_VERSION, validate_director_contract, review_director_creative_quality
from core.blocking_state_compiler import COMPILER_VERSION, compile_blocking_states
from api.scene_blocking_api import _validate_blocking_candidate


def scene():
    return {"dramatic_beats": [{"beat_id": "B1", "importance": "critical", "requires_reaction": True, "characters": ["C1"]}]}


def decision(origin="HUMAN_AUTHORED"):
    return {"decision_id":"D1", "beat_ref":"B1", "dramatic_purpose":"TRIGGER_DECISION", "audience_state_delta":{"knowledge_added":[],"knowledge_confirmed":[],"knowledge_invalidated":[],"belief_shift":[],"open_question_added":[],"open_question_resolved":[]}, "character_state_deltas":[], "performance_objectives":[], "reaction_contracts":[{"character_ref":"C1","trigger_ref":"B1","reaction_type":"DECISION","required":True}], "source_refs":["ScriptIR:B1"], "decision_origin":origin}


def blocking():
    initial={"characters":{},"props":{},"exit_access":{}}
    compiled=compile_blocking_states(initial,[{"beat_id":"B1"}],[],valid_zones=set())
    return {"initial_state":initial,"blocking_transitions":[],"compiler_version":COMPILER_VERSION,"compiled_states_hash":compiled["compiled_states_hash"],"beat_spatial_states":compiled["states"],"scene_name":"S","participants":[],"beat_transitions":[{"beat_id":"B1"}],"spatial_rules":[],"unknowns":[]}


def test_director_production_requires_contract_and_supported_version():
    report=validate_director_contract({"director_beat_decisions":[decision()]},scene=scene(),production=True)
    assert report["status"]=="blocked"
    assert any(x["code"]=="DIRECTOR_SEMANTIC_CONTRACT_REQUIRED" for x in report["errors"])
    report=validate_director_contract({"director_contract_version":"old","director_beat_decisions":[decision()]},scene=scene(),production=True)
    assert any(x["code"]=="UNSUPPORTED_PRODUCTION_CONTRACT_VERSION" for x in report["errors"])
    report=validate_director_contract({"director_contract_version":DIRECTOR_CONTRACT_VERSION,"director_beat_decisions":[decision()]},scene=scene(),production=True)
    assert report["status"]=="qualified"


def test_generated_origin_cannot_confirm():
    report=validate_director_contract({"director_contract_version":DIRECTOR_CONTRACT_VERSION,"director_beat_decisions":[decision("GENERATED_DRAFT")]},scene=scene(),production=True)
    assert any(x["code"]=="DIRECTOR_DECISION_NOT_ACCEPTED" for x in report["errors"])


def test_blocking_requires_all_canonical_fields():
    candidate=blocking()
    for key in ("initial_state","blocking_transitions","compiler_version","compiled_states_hash"):
        missing=dict(candidate); missing.pop(key)
        with pytest.raises(ValueError,match="BLOCKING_SEMANTIC_CONTRACT_REQUIRED"):
            _validate_blocking_candidate(missing,candidate,production=True)


def test_reviewer_is_statistics_only():
    out=review_director_creative_quality({"director_beat_decisions":[{"dramatic_purpose":"TRIGGER_DECISION"}]*8})
    assert "status" not in out
    assert out["dramatic_purpose_distribution"]=={"TRIGGER_DECISION":8}
