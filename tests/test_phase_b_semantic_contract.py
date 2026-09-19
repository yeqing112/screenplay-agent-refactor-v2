from core.director_semantics import build_suggested_director_decisions, validate_director_contract
from core.blocking_state_compiler import compile_blocking_states


def _scene():
    return {"scene_id": "S1", "beats": [{"beat_id": "B1", "type": "ACTION"}, {"beat_id": "B2", "type": "REVEAL", "importance": "critical", "requires_reaction": True, "characters": ["A"]}]}


def test_director_decision_requires_structured_reaction_and_source_ref():
    scene = _scene()
    decisions = build_suggested_director_decisions(scene)
    assert validate_director_contract({"director_beat_decisions": decisions}, scene=scene, production=False)["status"] == "qualified"
    bad = [item for item in decisions if item["beat_ref"] == "B2"][0].copy()
    bad["reaction_contracts"] = []
    report = validate_director_contract({"director_beat_decisions": [decisions[0], bad]}, scene=scene, production=False)
    assert any(x["code"] == "DIRECTOR_REACTION_CONTRACT_MISSING" for x in report["errors"])


def test_generated_director_decision_cannot_enter_production():
    report = validate_director_contract({"director_beat_decisions": build_suggested_director_decisions(_scene())}, scene=_scene(), production=True)
    assert report["status"] == "blocked"
    assert any(x["code"] == "DIRECTOR_DECISION_NOT_ACCEPTED" for x in report["errors"])


def _initial():
    return {"characters": {"A": {"zone": "Z1", "facing": "B"}}, "props": {"P": {"zone": "Z1", "state": "PRESENT"}}, "exit_access": {"Z1": {"state": "AVAILABLE"}}}


def test_blocking_compiler_inherits_and_applies_transition_deterministically():
    beats = [{"beat_id": "B1"}, {"beat_id": "B2"}]
    transitions = [{"transition_id": "T1", "beat_ref": "B2", "subject_type": "CHARACTER", "subject_ref": "A", "changes": [{"property": "ZONE", "from": "Z1", "to": "Z2"}]}]
    one = compile_blocking_states(_initial(), beats, transitions, valid_zones={"Z1", "Z2"})
    two = compile_blocking_states(_initial(), beats, transitions, valid_zones={"Z1", "Z2"})
    assert one["status"] == "qualified"
    assert one["states"][0]["characters"]["A"]["zone"] == "Z1"
    assert one["states"][1]["characters"]["A"]["zone"] == "Z2"
    assert one["compiled_states_hash"] == two["compiled_states_hash"]


def test_blocking_compiler_rejects_source_mismatch_invalid_zone_and_conflict():
    beats = [{"beat_id": "B1"}]
    mismatch = [{"transition_id": "T1", "beat_ref": "B1", "subject_type": "CHARACTER", "subject_ref": "A", "changes": [{"property": "ZONE", "from": "Z2", "to": "Z1"}]}]
    assert any(x["code"] == "BLOCKING_TRANSITION_SOURCE_STATE_MISMATCH" for x in compile_blocking_states(_initial(), beats, mismatch, valid_zones={"Z1", "Z2"})["errors"])
    invalid = [{"transition_id": "T1", "beat_ref": "B1", "subject_type": "CHARACTER", "subject_ref": "A", "changes": [{"property": "ZONE", "from": "Z1", "to": "UNKNOWN"}]}]
    assert any(x["code"] == "BLOCKING_ZONE_REF_INVALID" for x in compile_blocking_states(_initial(), beats, invalid, valid_zones={"Z1", "Z2"})["errors"])
    conflict = [{"transition_id": "T1", "beat_ref": "B1", "subject_type": "CHARACTER", "subject_ref": "A", "changes": [{"property": "ZONE", "from": "Z1", "to": "Z2"}]}, {"transition_id": "T2", "beat_ref": "B1", "subject_type": "CHARACTER", "subject_ref": "A", "changes": [{"property": "ZONE", "from": "Z1", "to": "Z3"}]}]
    assert any(x["code"] == "BLOCKING_TRANSITION_CONFLICT" for x in compile_blocking_states(_initial(), beats, conflict, valid_zones={"Z1", "Z2", "Z3"})["errors"])
