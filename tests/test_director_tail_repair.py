from core.director_tail_repair import TailRepairError, apply_tail_repair, build_tail_repair_plan


def test_tail_repair_triggers_only_for_low_tail_or_eligible_coverage():
    plan = build_tail_repair_plan({"director_quality_score": 60, "coverage": {"edit_strategy_coverage": 1.0}}, root_causes=["WEAK_EDIT_STRATEGY"])
    assert plan["triggered"] is True
    assert plan["max_attempts_per_root_cause"] == 2
    assert plan["scopes"]["WEAK_EDIT_STRATEGY"] == ["edit"]


def test_tail_repair_prefers_opportunity_level_coverage_when_present():
    plan = build_tail_repair_plan(
        {
            "director_quality_score": 90,
            "coverage": {"edit_strategy_coverage": 0.1},
            "eligible_coverage": {"edit_strategy": 1.0},
        },
        root_causes=["WEAK_EDIT_STRATEGY"],
    )
    assert plan["triggered"] is False


def test_tail_repair_changes_only_root_cause_scope():
    record = {"director_quality_score": 60, "coverage": {"edit_strategy_coverage": 0.2}}
    plan = build_tail_repair_plan(record, root_causes=["WEAK_EDIT_STRATEGY"])
    result = apply_tail_repair({"shots": [{"plan_shot_id": "S01", "edit": {"cut_reason": "old"}}]}, plan, root_cause="WEAK_EDIT_STRATEGY", attempt_number=1, patch={"shots.0.edit.cut_reason": "reaction_complete"})
    assert result["changed"] is True
    assert result["candidate"]["shots"][0]["edit"]["cut_reason"] == "reaction_complete"


def test_tail_repair_rejects_immutable_or_out_of_scope_patch_and_third_attempt():
    plan = build_tail_repair_plan({"director_quality_score": 60}, root_causes=["WEAK_EDIT_STRATEGY"])
    try:
        apply_tail_repair({"shots": [{"plan_shot_id": "S01"}]}, plan, root_cause="WEAK_EDIT_STRATEGY", attempt_number=1, patch={"event": "rewrite"})
    except TailRepairError:
        pass
    else:
        raise AssertionError("immutable fields must be rejected")
    try:
        apply_tail_repair({"shots": []}, plan, root_cause="WEAK_EDIT_STRATEGY", attempt_number=3, patch={"edit.cut_reason": "x"})
    except TailRepairError:
        pass
    else:
        raise AssertionError("third attempt must be rejected")
