from core.director_tail_repair_executor import execute_tail_repair
from core.director_creative_contract import build_director_creative_contract


def _inputs():
    candidate = {
        "scene_id": "SCENE_01",
        "scene_name": "门厅",
        "shots": [{"plan_shot_id": "S01", "beat_id": "B01", "event": "发现照片", "participants": ["C1"], "duration_hint_seconds": 4}],
    }
    contract = build_director_creative_contract(structural_shot_plan=candidate, treatment={"scene_id": "SCENE_01", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "event": "发现照片"}]})
    record = {"scene_id": "SCENE_01", "director_quality_score": 50, "eligible_coverage": {"edit_strategy": 0.2}}
    return candidate, contract, record


def test_tail_executor_runs_targeted_scope_and_accepts_only_target_improvement():
    candidate, contract, record = _inputs()
    requests = []

    def repair(request):
        requests.append(request)
        assert request["root_cause"] == "WEAK_EDIT_STRATEGY"
        assert "candidate" not in request
        return {"schema_version": "director_creative_patch_v1", "patches": [{"plan_shot_id": "S01", "changes": {"edit.cut_reason": "reaction_complete"}}], "auxiliary_shot_proposals": []}

    result = execute_tail_repair(candidate=candidate, record=record, contract=contract, repair_callable=repair)
    assert result["status"] == "accepted"
    assert result["execution_coverage"] == 1.0
    assert result["accepted"] == ["WEAK_EDIT_STRATEGY"]
    assert result["candidate"]["shots"][0]["edit"]["cut_reason"] == "reaction_complete"
    assert len(requests) == 1


def test_tail_executor_rolls_back_out_of_scope_repair_after_two_attempts():
    candidate, contract, record = _inputs()
    calls = []

    def repair(request):
        calls.append(request)
        return {"schema_version": "director_creative_patch_v1", "patches": [{"plan_shot_id": "S01", "changes": {"event": "改写事实"}}], "auxiliary_shot_proposals": []}

    result = execute_tail_repair(candidate=candidate, record=record, contract=contract, repair_callable=repair)
    assert result["status"] == "rolled_back"
    assert len(calls) == 2
    assert result["candidate"] == candidate
    assert result["attempts"][0]["rolled_back"] is True
    assert result["execution_coverage"] == 0.0


def test_non_tail_scene_does_not_call_repair_provider():
    candidate, contract, _ = _inputs()
    calls = []
    result = execute_tail_repair(candidate=candidate, record={"scene_id": "SCENE_01", "director_quality_score": 95, "eligible_coverage": {"edit_strategy": 1.0, "emotion_arc": 1.0, "information_strategy": 1.0}}, contract=contract, repair_callable=lambda request: calls.append(request))
    assert calls == []
    assert result["status"] == "not_triggered"


def test_tail_executor_writes_runtime_ledger_metadata(monkeypatch):
    candidate, contract, record = _inputs()
    ledger_rows = []
    monkeypatch.setattr("core.director_tail_repair_executor.record_repair_attempt", lambda **kwargs: ledger_rows.append(kwargs))
    result = execute_tail_repair(
        candidate=candidate,
        record=record,
        contract=contract,
        repair_callable=lambda request: {"schema_version": "director_creative_patch_v1", "patches": [{"plan_shot_id": "S01", "changes": {"edit.cut_reason": "reaction_complete"}}], "auxiliary_shot_proposals": []},
        session=object(),
        repair_context={"scene_id": "SCENE_01", "book_id": 990400, "episode": 1},
        model="mimo-v2.5",
    )
    assert result["status"] == "accepted"
    assert ledger_rows
    metadata = ledger_rows[0]["repair"]["ledger_metadata"]
    assert metadata["root_cause"] == "WEAK_EDIT_STRATEGY"
    assert metadata["compile_status"] == "compiled"
    assert metadata["contract_status"] == "pass"
