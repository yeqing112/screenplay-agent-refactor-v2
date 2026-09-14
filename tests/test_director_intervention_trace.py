from core.director_intervention_trace import build_intervention_trace


def _opp(oid, beat="B01"):
    return {
        "opportunity_id": oid,
        "type": "OPP_EMOTION_TURN",
        "scene_id": "SCENE_01",
        "beat_id": beat,
        "subjects": ["C1"],
        "reason": "明确情绪变化字段",
        "evidence_refs": ["treatment.beat_map[0].emotion_change"],
        "priority": "high",
        "eligible": True,
        "recommended_directing_dimensions": ["emotion_arc", "performance_direction"],
    }


def test_trace_contains_every_required_intervention_stage():
    result = build_intervention_trace(
        opportunities=[_opp("O1")],
        planner_decisions=[{"opportunity_id": "O1", "decision": "ACT", "strategy_id": "emotion:B01:C1", "strategy": "先停顿再抬眼", "patch_ids": ["p1"]}],
        patch_document={"patches": [{"patch_id": "p1", "plan_shot_id": "S01", "strategy_refs": ["O1"]}], "auxiliary_shot_proposals": []},
        compilation={"compiled_patches": [{"patch_id": "p1", "plan_shot_id": "S01", "operations": []}], "rejected_patches": []},
        validation={"errors": []},
        applied_patch_ids=["p1"],
        dimension_deltas_before={"O1": {"emotion_arc": 2}},
        dimension_deltas_after={"O1": {"emotion_arc": 4}},
    )
    row = result["records"][0]
    assert result["trace_complete"] is True
    assert row["planner_decision"] == "ACT"
    assert row["strategy_id"] == "emotion:B01:C1"
    assert row["patch_ids"] == ["p1"]
    assert row["compile_results"]
    assert row["applied_patch_ids"] == ["p1"]
    assert row["affected_dimensions"] == ["emotion_arc", "performance_direction"]
    assert row["dimension_delta_after"] == {"emotion_arc": 4}
    assert row["final_status"] == "APPLIED_PENDING_MEASURE"


def test_trace_does_not_credit_unbound_patch_and_keeps_valid_skip_separate():
    result = build_intervention_trace(
        opportunities=[_opp("O_SKIP"), _opp("O_ACT", beat="B02")],
        planner_decisions=[
            {"opportunity_id": "O_SKIP", "decision": "SKIP_WITH_REASON", "reason": "已有覆盖"},
            {"opportunity_id": "O_ACT", "decision": "ACT"},
        ],
        patch_document={"patches": [{"patch_id": "unbound", "plan_shot_id": "S99"}], "auxiliary_shot_proposals": []},
    )
    by_id = {row["opportunity_id"]: row for row in result["records"]}
    assert by_id["O_SKIP"]["final_status"] == "SKIPPED_VALID_REASON"
    assert by_id["O_ACT"]["patch_ids"] == []
    assert by_id["O_ACT"]["final_status"] == "REJECTED_QUALITY"
