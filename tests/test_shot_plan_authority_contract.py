import copy

import pytest

from core.shot_plan import build_shot_plan
from core.shot_plan_authority import (
    SHOT_AUTHORING_DECISION,
    validate_shot_continuity,
    validate_shot_plan_candidate_authority,
    shot_plan_payload_hash,
)


def _baseline():
    plan = build_shot_plan(
        treatment={
            "scene_name": "门厅",
            "scene_id": "scene-1",
            "beat_map": [
                {"beat_id": "B01", "event": "开门", "duration_seconds": 3},
                {"beat_id": "B02", "event": "停步", "duration_seconds": 4},
            ],
        },
        blocking={
            "scene_name": "门厅",
            "scene_id": "scene-1",
            "participants": [{"character_id": "C1", "start_position": "门口", "facing": "right"}],
            "props": [{"prop_id": "P1", "entry_state": "closed", "location": "door"}],
            "screen_direction": "left_to_right",
        },
    )
    plan["scene_id"] = "scene-1"
    plan["schema_version"] = "shot_plan_v2"
    return plan


def test_candidate_preserves_cardinality_and_returns_executability_and_continuity():
    plan = _baseline()
    source = {field: plan[field] for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}
    candidate, continuity, executability = validate_shot_plan_candidate_authority(source, plan, scene_entry={})
    assert [item["plan_shot_id"] for item in candidate["shots"]] == ["S01", "S02"]
    assert continuity["status"] == "pass"
    assert executability["status"] != "blocked"
    assert candidate["unknowns"] == []


@pytest.mark.parametrize("mutation", ["append", "delete", "reorder"])
def test_candidate_rejects_shot_cardinality_or_order_mutation(mutation):
    plan = _baseline()
    candidate = {field: copy.deepcopy(plan[field]) for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}
    if mutation == "append":
        candidate["shots"].append(copy.deepcopy(candidate["shots"][-1]))
        candidate["shots"][-1]["plan_shot_id"] = "S03"
    elif mutation == "delete":
        candidate["shots"] = candidate["shots"][:1]
    else:
        candidate["shots"] = list(reversed(candidate["shots"]))
    with pytest.raises(ValueError, match="plan_shot_id"):
        validate_shot_plan_candidate_authority(candidate, plan, scene_entry={})


def test_candidate_rejects_unknown_closure_and_non_provenanced_camera():
    plan = _baseline()
    plan = {field: copy.deepcopy(plan[field]) for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}
    plan["unknowns"] = ["missing prop identity"]
    with pytest.raises(ValueError, match="unknowns"):
        validate_shot_plan_candidate_authority(plan, plan, scene_entry={})
    candidate_source = _baseline()
    candidate = {field: copy.deepcopy(candidate_source[field]) for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}
    del candidate["shots"][0]["camera_provenance"]
    with pytest.raises(ValueError, match="camera provenance"):
        validate_shot_plan_candidate_authority(candidate, _baseline(), scene_entry={})


def test_continuity_blocks_prop_drop_and_undeclared_screen_direction_break():
    plan = _baseline()
    plan["shots"][1]["entry_state"]["props"] = []
    plan["shots"][1]["continuity_contract"]["screen_direction"] = "right_to_left"
    report = validate_shot_continuity(shots=plan["shots"], scene_entry={})
    codes = {item["code"] for item in report["errors"]}
    assert "PROP_CONTINUITY_BREAK" in codes
    assert "SCREEN_DIRECTION_BREAK" in codes


def test_continuity_allows_declared_character_transition_and_payload_hash_is_stable():
    plan = _baseline()
    plan["shots"][1]["entry_state"]["characters"]["C1"]["position"] = "台阶"
    plan["shots"][1]["action_beats"] = [{"action_id": "B02_A01", "action": "走到台阶", "start_seconds": 0, "end_seconds": 2}]
    report = validate_shot_continuity(shots=plan["shots"], scene_entry={})
    assert report["status"] == "pass"
    assert shot_plan_payload_hash(plan) == shot_plan_payload_hash(copy.deepcopy(plan))


def test_camera_default_has_explicit_authority_provenance():
    plan = _baseline()
    assert plan["shots"][0]["camera_provenance"]["authority_class"] == SHOT_AUTHORING_DECISION
    assert plan["shots"][0]["camera_provenance"]["source"] == "deterministic_default"


def test_prop_continuity_projection_contains_identity_state_and_provenance():
    plan = _baseline()
    prop = plan["shots"][0]["entry_state"]["props"][0]
    assert {"prop_id", "scene_id", "shot_id", "entry_state", "exit_state", "location", "holder", "owner", "visibility", "state_variant", "source", "provenance", "unresolved"}.issubset(prop)
    assert plan["shots"][0]["asset_bindings"]["canonical_asset_identity"]["props"] == ["P1"]


def test_action_timing_overlap_requires_explicit_concurrency():
    plan = _baseline()
    plan["shots"][0]["action_beats"] = [
        {"action_id": "A1", "action": "开门", "start_seconds": 0, "end_seconds": 2},
        {"action_id": "A2", "action": "停步", "start_seconds": 1, "end_seconds": 2.5},
    ]
    with pytest.raises(ValueError, match="overlap"):
        validate_shot_plan_candidate_authority({field: plan[field] for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}, _baseline(), scene_entry={})
