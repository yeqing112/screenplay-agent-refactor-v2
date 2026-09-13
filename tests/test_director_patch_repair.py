import pytest

from core.director_creative_contract import build_director_creative_contract
from core.director_patch_repair import RepairReplacementError, normalize_repair_output, repair_failed_patch
from core.scene_directing_strategy import build_scene_directing_strategy
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
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    return plan, contract, strategy


def test_local_repair_sends_only_failed_patch_context_and_stops_after_success():
    plan, contract, strategy = _inputs()
    requests = []

    def repair(request):
        requests.append(request)
        return {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}}

    result = repair_failed_patch(
        structural_shot_plan=plan,
        failed_patch={"plan_shot_id": "S01", "changes": {"camera.angle": ""}},
        issue={"code": "INVALID_PATCH_VALUE", "path": "/shots/0/camera/angle"},
        contract=contract,
        strategy=strategy,
        repair_callable=repair,
    )
    assert result["status"] == "repaired"
    assert result["attempt_count"] == 1
    assert len(requests) == 1
    assert "structural_shot_plan" not in requests[0]
    assert requests[0]["failed_patch"]["plan_shot_id"] == "S01"


def test_local_repair_is_bounded_and_falls_back_after_two_failures():
    plan, contract, strategy = _inputs()
    calls = []

    def repair(_request):
        calls.append(True)
        return {"plan_shot_id": "S01", "changes": {"event": "改写事实"}}

    result = repair_failed_patch(
        structural_shot_plan=plan,
        failed_patch={"plan_shot_id": "S01", "changes": {"camera.angle": ""}},
        issue={"code": "INVALID_PATCH_VALUE"},
        contract=contract,
        strategy=strategy,
        repair_callable=repair,
        max_attempts=5,
    )
    assert result["status"] == "fallback"
    assert result["fallback_to_baseline"] is True
    assert result["attempt_count"] == 2
    assert len(calls) == 2


def test_local_repair_records_each_attempt_when_ledger_context_is_supplied(monkeypatch):
    plan, contract, strategy = _inputs()
    records = []

    def fake_record(**kwargs):
        records.append(kwargs)

    monkeypatch.setattr(repair_module, "record_repair_attempt", fake_record)
    result = repair_module.repair_failed_patch(
        structural_shot_plan=plan,
        failed_patch={"plan_shot_id": "S01", "changes": {"camera.angle": ""}},
        issue={"code": "INVALID_PATCH_VALUE"},
        contract=contract,
        strategy=strategy,
        repair_callable=lambda _request: {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
        session=object(),
        repair_context={"book_id": 1, "episode": 1, "scene_id": "E01_SC01"},
        model="mock-model",
        prompt_fingerprint="prompt-fp",
    )
    assert result["status"] == "repaired"
    assert len(records) == 1
    assert records[0]["context"]["attempt_number"] == 1
    assert records[0]["context"]["model"] == "mock-model"
    assert records[0]["issue"]["target_layer"] == "DIRECTOR_CREATIVE"


def test_repair_replacement_schema_locks_target_and_normalizes_value():
    result = normalize_repair_output(
        {
            "schema_version": "director_patch_repair_v1",
            "target": {"plan_shot_id": "S01", "path": "camera.shot-size"},
            "replacement_value": " close-up ",
            "reason": "需要更明确的反应",
        },
        expected_plan_shot_id="S01",
        expected_path="camera.shot_size",
        allowed_repair_paths=["camera.shot_size"],
    )
    assert result["target"] == {"plan_shot_id": "S01", "path": "camera.shot_size"}
    assert result["replacement_value"] == "CU"


def test_repair_cannot_change_target_or_path_and_rejects_complete_scene():
    with pytest.raises(RepairReplacementError) as error:
        normalize_repair_output(
            {"target": {"plan_shot_id": "S02", "path": "camera.angle"}, "replacement_value": "low_angle"},
            expected_plan_shot_id="S01",
            expected_path="camera.angle",
            allowed_repair_paths=["camera.angle"],
        )
    assert error.value.code == "REPAIR_TARGET_MISMATCH"
    with pytest.raises(RepairReplacementError) as error:
        normalize_repair_output(
            {"target": {"plan_shot_id": "S01", "path": "camera.movement"}, "replacement_value": "tracking"},
            expected_plan_shot_id="S01",
            expected_path="camera.angle",
            allowed_repair_paths=["camera.angle"],
        )
    assert error.value.code in {"REPAIR_TARGET_MISMATCH", "DIRECTOR_PATCH_PATH_FORBIDDEN"}
    with pytest.raises(RepairReplacementError) as error:
        normalize_repair_output({"patches": [], "shots": []}, expected_plan_shot_id="S01", expected_path="camera.angle")
    assert error.value.code == "REPAIR_FORBIDDEN_FIELD"


def test_multi_field_repair_requires_explicit_whitelist():
    with pytest.raises(RepairReplacementError) as error:
        normalize_repair_output(
            {"plan_shot_id": "S01", "changes": {"camera.movement": "tracking", "camera.speed": "slow"}},
            expected_plan_shot_id="S01",
            allowed_repair_paths=[],
        )
    assert error.value.code == "REPAIR_FORBIDDEN_FIELD"
