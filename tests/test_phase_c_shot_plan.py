import copy

from core.phase_c_shot_plan import (
    build_phase_c_shot_plan,
    compile_shot_coverage,
    validate_shot_plan_contract,
)


def _inputs():
    treatment = {
        "scene_id": "E01_SC002",
        "beat_map": [
            {"beat_id": "SC02-B01", "type": "action", "event": "林晚试探", "characters": ["林晚"], "requires_reaction": False},
            {"beat_id": "SC02-B02", "type": "reveal", "event": "红纤维出现", "characters": ["林晚"], "requires_reaction": True},
        ],
    }
    blocking = {"scene_id": "E01_SC002", "participants": [{"character_id": "林晚", "start_position": "APT_CENTER"}]}
    return treatment, blocking


def test_phase_c_compilers_are_deterministic_and_ready():
    treatment, blocking = _inputs()
    first = build_phase_c_shot_plan(treatment=treatment, blocking=blocking)
    second = build_phase_c_shot_plan(treatment=treatment, blocking=blocking)
    assert first["payload_hash"] == second["payload_hash"]
    assert first["phase_c_semantic_ready"] is True
    assert all(item["complete"] for item in compile_shot_coverage(treatment=treatment, blocking=blocking, shots=first["shots"]))


def test_phase_c_rejects_hidden_cut_and_invented_spatial_state():
    treatment, blocking = _inputs()
    plan = build_phase_c_shot_plan(treatment=treatment, blocking=blocking)
    candidate = copy.deepcopy(plan)
    candidate["shots"][0]["camera_segments"] = [{}, {}]
    candidate["shots"][0]["spatial_binding"]["subject_zones"]["林晚"] = "WINDOW"
    result = validate_shot_plan_contract(plan=candidate, treatment=treatment, blocking=blocking)
    codes = {item["code"] for item in result["errors"]}
    assert {"SHOT_INTERNAL_CUT_INVALID", "SHOT_SPATIAL_BINDING_INVALID"} <= codes


def test_phase_c_contract_rejects_invalid_references_and_camera_state():
    treatment, blocking = _inputs()
    plan = build_phase_c_shot_plan(treatment=treatment, blocking=blocking)
    plan["shots"][0]["beat_refs"] = ["MISSING"]
    plan["shots"][0]["spatial_binding"]["blocking_state_ref"] = "MISSING"
    plan["shots"][0]["camera_state"] = {}
    result = validate_shot_plan_contract(plan=plan, treatment=treatment, blocking=blocking)
    codes = {item["code"] for item in result["errors"]}
    assert {"SHOT_BEAT_REF_INVALID", "SHOT_BLOCKING_STATE_REF_INVALID", "SHOT_CAMERA_STATE_INCOMPLETE"} <= codes


def test_phase_c_missing_reaction_is_a_hard_coverage_failure():
    treatment, blocking = _inputs()
    plan = build_phase_c_shot_plan(treatment=treatment, blocking=blocking)
    reaction_shot = next(shot for shot in plan["shots"] if "REACTION_COVERAGE" in shot["coverage_roles"])
    reaction_shot["coverage_roles"].remove("REACTION_COVERAGE")
    result = validate_shot_plan_contract(plan=plan, treatment=treatment, blocking=blocking)
    assert any(item["code"] == "SHOT_COVERAGE_INCOMPLETE" and item["beat_ref"] == "SC02-B02" for item in result["errors"])
