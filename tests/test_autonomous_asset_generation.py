from __future__ import annotations

import pytest

from core.autonomous_asset_generation import (
    AssetGenerationBudgetPolicy,
    AssetRepairContext,
    AutonomousAssetGeneration,
    AutonomousAssetState,
    SceneDerivedViewPlan,
    SceneGeometryIR,
    geometry_constrained_prompt,
)


def _geometry() -> SceneGeometryIR:
    return SceneGeometryIR(
        scene_id="E01_SC002",
        walls=["LEFT", "BACK", "RIGHT", "FRONT"],
        zones=["WINDOW_LEFT", "CENTER_FOREGROUND", "KITCHEN_DOOR_RIGHT"],
        doors=[{"id": "kitchen_door", "wall": "RIGHT"}],
        windows=[{"id": "left_window", "wall": "LEFT"}],
        fixed_furniture=[{"id": "sink", "relation": "below_left_window"}],
        fixed_props=[{"id": "dish_rack", "relation": "near_sink"}],
        landmarks=["left_window", "sink_below_window", "rear_right_kitchen_door"],
        relative_positions=[{"subject": "sink", "relation": "below", "object": "left_window"}],
        adjacency=[{"a": "window_left", "b": "sink", "relation": "vertical_adjacent"}],
        lighting_sources=["cool daylight", "warm ceiling bulb"],
        lighting_directions=["LEFT toward CENTER", "CEILING downward"],
        materials=["old tile", "worn wood"],
        time="early evening",
        weather="overcast after rain",
    )


def _plan() -> SceneDerivedViewPlan:
    return SceneDerivedViewPlan(
        view_id="REVERSE",
        view_type="REVERSE",
        camera_position="near rear work zone",
        camera_direction="toward dining table",
        visible_landmarks=["rear_right_kitchen_door", "left_window_edge"],
        occluded_landmarks=["back_cabinet_partial"],
        required_landmarks=["rear_right_kitchen_door"],
        forbidden_changes=["moving the door", "moving the sink", "adding people or text"],
    )


def test_geometry_fingerprint_and_prompt_keep_topology_authoritative():
    geometry = _geometry()
    assert geometry.fingerprint == _geometry().fingerprint

    prompt = geometry_constrained_prompt(geometry, _plan())
    assert "SceneGeometryIR" in prompt
    assert "禁止改变墙体、门、窗" in prompt
    assert "rear_right_kitchen_door" in prompt


def test_budget_and_repair_attempts_are_enforced():
    runtime = AutonomousAssetGeneration(
        asset_type="SCENE",
        asset_id="E01_SC002",
        budget=AssetGenerationBudgetPolicy(normal_calls_max=2, max_attempts_per_view=2),
    )
    runtime.plan_scene(_geometry(), [_plan()])
    assert runtime.state == AutonomousAssetState.PRIMARY_GENERATING
    assert runtime.claim_image_call() == 1
    assert runtime.claim_image_call() == 2
    with pytest.raises(RuntimeError, match="ASSET_GENERATION_BUDGET_EXCEEDED"):
        runtime.claim_image_call()

    runtime.prepare_repair(
        AssetRepairContext(
            view_id="REVERSE",
            previous_prompt="previous",
            failed_output={},
            violations=["door mismatch"],
            required_corrections=["keep door on RIGHT wall"],
            attempt_number=2,
        )
    )
    assert runtime.state == AutonomousAssetState.REPAIRING
    with pytest.raises(RuntimeError, match="ASSET_CONSISTENCY_GENERATION_FAILED"):
        runtime.prepare_repair(
            AssetRepairContext(
                view_id="REVERSE",
                previous_prompt="previous",
                failed_output={},
                violations=["still inconsistent"],
                required_corrections=["preserve topology"],
                attempt_number=3,
            )
        )
    assert runtime.state == AutonomousAssetState.FAILED
