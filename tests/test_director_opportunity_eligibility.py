from core.director_opportunity_eligibility import (
    apply_opportunity_eligibility,
    evaluate_opportunity_eligibility,
)


def _opp(oid, kind="OPP_REACTION", *, refs=None, dims=None, beat="B01"):
    return {
        "opportunity_id": oid,
        "type": kind,
        "scene_id": "SCENE_01",
        "beat_id": beat,
        "subjects": ["C1"],
        "reason": "证据字段显示存在导演决策窗口",
        "evidence_refs": refs or ["treatment.beat_map[0].event"],
        "priority": "medium",
        "eligible": True,
        "recommended_directing_dimensions": dims or ["performance_direction", "edit_strategy"],
    }


def test_participant_delta_alone_does_not_make_entrance_or_exit_eligible():
    entrance = _opp("O_ENTER", "OPP_CHARACTER_ENTRANCE", refs=["treatment.beat_map[1].participants"])
    exit_ = _opp("O_EXIT", "OPP_CHARACTER_EXIT", refs=["treatment.beat_map[1].participants"])
    rows = evaluate_opportunity_eligibility(
        [entrance, exit_],
        treatment={"beat_map": [{"beat_id": "B01", "participants": ["C1"]}, {"beat_id": "B02", "participants": ["C1", "C2"]}]},
        blocking={"participants": ["C1", "C2"]},
    )
    assert rows[0]["status"] == "NOT_APPLICABLE"
    assert rows[1]["status"] == "NOT_APPLICABLE"


def test_explicit_entry_and_dialogue_pressure_evidence_are_required():
    rows = evaluate_opportunity_eligibility(
        [
            _opp("O_ENTER", "OPP_CHARACTER_ENTRANCE", refs=["treatment.beat_map[0].entry"]),
            _opp("O_PRESSURE", "OPP_DIALOGUE_PRESSURE", refs=["treatment.beat_map[0].dialogue"]),
        ],
        treatment={"beat_map": [{"beat_id": "B01", "entry": "C2 enters", "dialogue": "你为何回来？", "conflict": "confrontation"}]},
    )
    assert rows[0]["status"] == "ELIGIBLE"
    assert rows[1]["status"] == "ELIGIBLE"


def test_generic_evidence_is_weak_and_scene_button_requires_an_ending_signal():
    rows = evaluate_opportunity_eligibility(
        [
            _opp("O_WEAK", refs=["treatment.beat_map"]),
            _opp("O_BUTTON", "OPP_SCENE_BUTTON", refs=["treatment.beat_map[0].type"]),
        ],
        treatment={"beat_map": [{"beat_id": "B01", "type": "setup"}]},
    )
    assert rows[0]["status"] == "WEAK_EVIDENCE"
    assert rows[1]["status"] == "NOT_APPLICABLE"


def test_duplicate_and_already_covered_statuses_are_explicit():
    first = _opp("O1")
    duplicate = _opp("O2")
    covered = _opp("O3", beat="B02")
    result = apply_opportunity_eligibility(
        [first, duplicate, covered],
        treatment={"beat_map": [{"beat_id": "B01", "event": "reaction"}, {"beat_id": "B02", "event": "reaction"}]},
        structural_shot_plan={
            "shots": [
                {"plan_shot_id": "S01", "beat_id": "B01"},
                {"plan_shot_id": "S02", "beat_id": "B02", "performance_direction": {"objective": "hold"}, "edit": {"cut_reason": "reaction"}},
            ]
        },
    )
    assert result["decisions"][0]["status"] == "ELIGIBLE"
    assert result["decisions"][1]["status"] == "REDUNDANT"
    assert result["decisions"][2]["status"] == "ALREADY_COVERED"
    metrics = result["metrics"]
    assert metrics["detected_opportunity_count"] == 3
    assert metrics["redundant_opportunity_count"] == 1
    assert metrics["already_covered_count"] == 1
