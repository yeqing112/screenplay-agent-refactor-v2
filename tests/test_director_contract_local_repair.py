from core.director_contract_local_repair import repair_contract_failures
from core.director_creative_contract import build_director_creative_contract


def _inputs():
    plan = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "shots": [
            {
                "plan_shot_id": f"S{index:02d}",
                "beat_id": f"B{index:02d}",
                "beat_order": index,
                "event": f"节拍 {index}",
                "action_beats": [f"动作 {index}"],
                "entry_state": {},
                "exit_state": {},
                "participants": ["C1"],
                "asset_bindings": {},
                "continuity_contract": {},
            }
            for index in range(1, 21)
        ],
    }
    contract = build_director_creative_contract(structural_shot_plan=plan, treatment={"scene_id": "E01_SC01", "scene_name": "雨夜门厅"})
    return plan, contract


def _document_with_one_invalid_patch():
    patches = [
        {"plan_shot_id": f"S{index:02d}", "changes": {"camera.angle": "eye_level"}}
        for index in range(1, 20)
    ]
    patches.append({"plan_shot_id": "S20", "changes": {"camera.angle": ""}})
    return {"schema_version": "director_creative_patch_v1", "patches": patches, "auxiliary_shot_proposals": []}


def test_contract_local_repair_preserves_19_valid_and_repairs_only_invalid_field():
    plan, contract = _inputs()
    requests = []

    def repair(request):
        requests.append(request)
        target = request["failed_patch"]["plan_shot_id"]
        assert list(request["failed_patch"]["changes"]) == ["camera.angle"]
        assert request["allowed_repair_paths"] == ["camera.angle"]
        assert request["contract_subset"]["allowed_patch_paths"] == ["camera.angle"]
        assert "structural_shot_plan" not in request
        return {"target": {"plan_shot_id": target, "path": "camera.angle"}, "replacement_value": "low_angle"}

    result = repair_contract_failures(
        structural_shot_plan=plan,
        patch_document=_document_with_one_invalid_patch(),
        contract=contract,
        repair_callable=repair,
    )
    assert result["status"] == "valid"
    assert result["metrics"]["scene_contract_first_pass"] is False
    assert result["metrics"]["scene_contract_final_pass"] is True
    assert result["metrics"]["contract_repair_attempts"] == 1
    assert result["metrics"]["contract_repair_success_count"] == 1
    assert result["metrics"]["retained_valid_patch_count"] == 20
    assert len(requests) == 1
    assert result["candidate"]["shots"][19]["camera"]["angle"] == "low_angle"
    assert plan["shots"][19].get("camera") is None


def test_contract_local_repair_falls_back_to_baseline_after_two_failed_attempts():
    plan, contract = _inputs()
    calls = []

    def repair(request):
        calls.append(request)
        target = request["failed_patch"]["plan_shot_id"]
        return {"target": {"plan_shot_id": target, "path": "event"}, "replacement_value": "改写事实"}

    result = repair_contract_failures(
        structural_shot_plan=plan,
        patch_document=_document_with_one_invalid_patch(),
        contract=contract,
        repair_callable=repair,
        max_attempts=9,
    )
    assert result["status"] == "valid"
    assert len(calls) == 2
    assert result["metrics"]["contract_repair_attempts"] == 2
    assert result["metrics"]["contract_repair_success_count"] == 0
    assert result["metrics"]["fallback_patch_count"] == 1
    assert result["metrics"]["retained_valid_patch_count"] == 19
    assert result["candidate"]["shots"][19].get("camera") is None


def test_contract_boundary_failures_are_not_sent_to_llm():
    plan, contract = _inputs()
    calls = []
    document = _document_with_one_invalid_patch()
    document["patches"][-1] = {"plan_shot_id": "S20", "changes": {"event": "改写事实"}}
    result = repair_contract_failures(
        structural_shot_plan=plan,
        patch_document=document,
        contract=contract,
        repair_callable=lambda request: calls.append(request),
    )
    assert calls == []
    assert result["metrics"]["scene_contract_final_pass"] is True
    assert result["outcomes"][-1]["non_repairable_reason"] == "CONTRACT_BOUNDARY_REJECT"
