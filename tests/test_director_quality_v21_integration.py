import copy

from core.director_creative_contract import build_director_creative_contract
from core.director_creative_planner import build_creative_patch_candidate
from core.director_patch_compiler import compile_creative_patches
from core.director_patch_repair import repair_failed_patch
from core.director_patch_validator import validate_compiled_patch_result
from core.director_partial_acceptance import apply_partial_acceptance
from core.director_quality_metrics import build_director_quality_metrics
from core.scene_directing_strategy import build_scene_directing_strategy
from core.executability import preflight_shot_plan
from core.shot_plan import build_shot_plan
from core.storyboard_materializer import materialize_storyboard_from_shot_plan


def test_v21_pipeline_keeps_structural_plan_immutable_and_accepts_partial_creative_output():
    treatment = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "visual_strategy": "用门口阻挡呈现关系变化",
        "beat_map": [
            {"beat_id": "B01", "type": "setup", "event": "林晚推开铁门进入门厅"},
            {"beat_id": "B02", "type": "reveal", "event": "林晚发现照片"},
        ],
    }
    blocking = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "participants": [{"character_id": "C1", "name": "林晚"}],
    }
    structural = build_shot_plan(treatment=treatment, blocking=blocking)
    structural_before = copy.deepcopy(structural)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=structural)
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)

    planner = build_creative_patch_candidate(
        structural_shot_plan=structural,
        contract=contract,
        strategy=strategy,
        llm_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {"plan_shot_id": "S01", "changes": {"camera.shot_size": "LS"}},
                {"plan_shot_id": "S99", "changes": {"camera.shot_size": "CU"}},
            ],
            "auxiliary_shot_proposals": [],
        },
    )
    accepted = apply_partial_acceptance(structural, planner["patch_document"], contract, treatment=treatment, blocking=blocking)
    assert accepted["partial_acceptance"]["accepted_patch_count"] == 1
    assert accepted["partial_acceptance"]["rejected_patch_count"] == 1
    assert accepted["candidate"]["shots"][0]["camera"]["shot_size"] == "LS"
    assert structural == structural_before

    failed = accepted["rejected_patches"][0]
    repaired = repair_failed_patch(
        structural_shot_plan=structural,
        failed_patch={"plan_shot_id": "S99", "changes": {"camera.shot_size": "CU"}},
        issue=failed,
        contract=contract,
        strategy=strategy,
        repair_callable=lambda _request: {"plan_shot_id": "S01", "changes": {"camera.shot_size": "MS"}},
    )
    assert repaired["status"] == "fallback"  # repair cannot retarget another shot

    compilation = compile_creative_patches(structural, planner["patch_document"], contract, allow_partial=True)
    validation = validate_compiled_patch_result(compilation, structural, contract, treatment=treatment, blocking=blocking)
    assert validation["contract_pass"] is True
    assert preflight_shot_plan(compilation["candidate"]["shots"])["status"] in {"pass", "warning"}
    metrics = build_director_quality_metrics(
        baseline=structural,
        first_candidate=compilation["candidate"],
        final_candidate=compilation["candidate"],
        contract_reliability={"schema_pass": True, "patch_path_pass": True, "parse_success": True, "repair_success": False},
        partial_acceptance=accepted["partial_acceptance"],
    )
    assert set(metrics["dimensions"]["after_repair"]) == set(metrics["director_dimensions"])


def test_v21_validated_candidate_materializes_one_to_one_with_execution_contract_intact():
    treatment = {
        "scene_id": "E01_SC02",
        "scene_name": "旧公寓门厅",
        "visual_strategy": "先建立空间，再把注意力收束到门缝",
        "beat_map": [
            {"beat_id": "B01", "type": "setup", "event": "林晚停在铁门内侧"},
            {"beat_id": "B02", "type": "reveal", "event": "林晚看见门缝透出的冷光"},
        ],
    }
    blocking = {
        "scene_id": "E01_SC02",
        "scene_name": "旧公寓门厅",
        "participants": [{"character_id": "C1", "name": "林晚"}],
    }
    structural = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=structural)
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    patch_document = {
        "schema_version": "director_creative_patch_v1",
        "patches": [
            {"plan_shot_id": structural["shots"][0]["plan_shot_id"], "changes": {"camera.shot_size": "CU", "camera.camera_side": "screen_left"}},
        ],
        "auxiliary_shot_proposals": [],
    }
    accepted = apply_partial_acceptance(structural, patch_document, contract, treatment=treatment, blocking=blocking)
    validation = validate_compiled_patch_result(accepted["compilation"], structural, contract, treatment=treatment, blocking=blocking)
    assert validation["contract_pass"] is True

    candidate = accepted["candidate"]
    materialized = materialize_storyboard_from_shot_plan(
        candidate,
        treatment=treatment,
        blocking=blocking,
        asset_snapshot={"snapshot_id": "offline-snapshot"},
    )

    assert len(materialized) == len(structural["shots"])
    structural_by_id = {item["plan_shot_id"]: item for item in structural["shots"]}
    candidate_by_id = {item["plan_shot_id"]: item for item in candidate["shots"]}
    materialized_by_id = {item["plan_shot_id"]: item for item in materialized}
    assert set(materialized_by_id) == set(structural_by_id)
    for plan_shot_id, source in structural_by_id.items():
        creative = candidate_by_id[plan_shot_id]
        row = materialized_by_id[plan_shot_id]
        assert row["action_process"] == source["event"]
        assert row["action_beats"] == source.get("action_beats", [])
        assert row["start_state"] == source.get("entry_state", "")
        assert row["end_state"] == source.get("exit_state", "")
        assert row["asset_bindings"] == source.get("asset_bindings", {})
        assert row["continuity_contract"] == source.get("continuity_contract", {})
        assert row["meta_info"]["shot_plan_ref"]["plan_shot_id"] == plan_shot_id
        assert row["meta_info"]["camera"] == creative.get("camera", {})
