import copy

import pytest

from core.director_creative_contract import build_director_creative_contract
from core.director_patch_compiler import (
    DirectorPatchCompileError,
    compile_creative_patches,
    compile_single_patch,
)
from core.director_patch_schema import parse_creative_patch
from core.shot_plan import build_shot_plan


def _plan_and_contract():
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
    return plan, contract


def test_compiler_applies_only_allowed_creative_patch_and_preserves_baseline():
    plan, contract = _plan_and_contract()
    original = copy.deepcopy(plan)
    result = compile_single_patch(
        plan,
        {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU", "emotion.intensity": 7}},
        contract,
    )
    assert result["candidate"]["shots"][0]["camera"]["shot_size"] == "CU"
    assert result["candidate"]["shots"][0]["emotion"]["intensity"] == 7
    assert plan == original
    assert result["provenance"][0]["compiled_path"] == "/shots/0/camera/shot_size"
    assert result["before_fingerprint"] != result["after_fingerprint"]


def test_compiler_rejects_forbidden_path_and_immutable_fact():
    plan, contract = _plan_and_contract()
    with pytest.raises(DirectorPatchCompileError) as error:
        compile_single_patch(plan, {"plan_shot_id": "S01", "changes": {"asset_bindings.scene_asset_id": "new"}}, contract)
    assert error.value.code == "DIRECTOR_FACT_OVERRIDE"

    with pytest.raises(DirectorPatchCompileError) as error:
        compile_single_patch(plan, {"plan_shot_id": "S01", "changes": {"event": "改写事实"}}, contract)
    assert error.value.code == "DIRECTOR_FACT_OVERRIDE"


def test_compiler_rejects_unknown_shot_and_invalid_value():
    plan, contract = _plan_and_contract()
    with pytest.raises(DirectorPatchCompileError) as error:
        compile_single_patch(plan, {"plan_shot_id": "S99", "changes": {"camera.angle": "low_angle"}}, contract)
    assert error.value.code == "UNKNOWN_PLAN_SHOT_ID"

    with pytest.raises(DirectorPatchCompileError) as error:
        compile_single_patch(plan, {"plan_shot_id": "S01", "changes": {"emotion.intensity": 11}}, contract)
    assert error.value.code == "INVALID_PATCH_VALUE"


def test_compiler_default_is_atomic_and_partial_mode_keeps_valid_patches():
    plan, contract = _plan_and_contract()
    document = parse_creative_patch({
        "schema_version": "director_creative_patch_v1",
        "patches": [
            {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
            {"plan_shot_id": "S99", "changes": {"camera.angle": "high_angle"}},
        ],
        "auxiliary_shot_proposals": [],
    })
    with pytest.raises(DirectorPatchCompileError):
        compile_creative_patches(plan, document, contract)

    partial = compile_creative_patches(plan, document, contract, allow_partial=True)
    assert partial["status"] == "partial"
    assert partial["accepted_patch_count"] == 1
    assert partial["rejected_patch_count"] == 1
    assert partial["candidate"]["shots"][0]["camera"]["angle"] == "low_angle"
