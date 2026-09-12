from core.qualification_loop import qualify_candidate


def test_qualification_loop_repairs_and_revalidates_within_bound():
    def validator(candidate):
        return [{"code": "action_overloaded", "severity": "blocked", "target_layer": "SHOT_PLAN", "patch": [{"op": "replace", "path": "/duration", "value": 6}]}] if candidate["duration"] < 6 else []
    result = qualify_candidate({"duration": 4}, [validator], max_attempts=2)
    assert result["status"] == "qualified"
    assert result["candidate"]["duration"] == 6
    assert len(result["attempts"]) == 1


def test_unresolved_blocker_becomes_needs_review_when_no_explicit_repair_exists():
    result = qualify_candidate({"duration": 4}, [lambda _candidate: [{"code": "missing_core_action", "severity": "blocked"}]], max_attempts=2)
    assert result["status"] == "needs_review"
    # A diagnostic without an explicit patch is not executable.  The loop
    # stops after one recorded attempt instead of fabricating a second pass.
    assert len(result["attempts"]) == 1
    assert result["repair_unavailable"] is True
