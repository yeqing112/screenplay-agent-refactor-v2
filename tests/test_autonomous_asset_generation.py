from __future__ import annotations

import pytest

from core.autonomous_asset_generation import (
    AssetGenerationBudgetPolicy,
    AssetRepairContext,
    AutonomousAssetGeneration,
    AutonomousAssetState,
    MediaEvidenceBinding,
    SceneConsistencyAudit,
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


def _evidence(view_id: str, attempt: int, *, master_sha: str = "master-sha", derived_sha: str = "derived-sha", response_sha: str = "judge-response") -> MediaEvidenceBinding:
    return MediaEvidenceBinding(
        view_id=view_id,
        attempt_number=attempt,
        master_sha256=master_sha,
        derived_sha256=derived_sha,
        master_generation_execution_id="exec-master",
        derived_generation_execution_id=f"exec-{view_id.lower()}-{attempt}",
        judge_profile_id="judge-profile",
        judge_model="vision-model",
        judge_request_fingerprint="judge-request",
        judge_response_fingerprint=response_sha,
        judge_raw_scores={"architecture_score": 90, "landmark_score": 90, "furniture_score": 90, "lighting_score": 90},
        judge_normalized_scores={"architecture_score": 90, "landmark_score": 90, "furniture_score": 90, "lighting_score": 90},
        generated_at="2026-10-04T00:00:00Z",
        judged_at="2026-10-04T00:01:00Z",
    )


def _passing_audit(view_id: str, attempt: int = 1, **kwargs) -> SceneConsistencyAudit:
    return SceneConsistencyAudit(
        view_id=view_id,
        status="PASS",
        same_physical_space=True,
        architecture_score=90,
        landmark_score=90,
        furniture_score=90,
        lighting_score=90,
        judge_status="VISION_JUDGE_EXECUTED",
        attempt_number=attempt,
        media_evidence=_evidence(view_id, attempt, **kwargs),
    )


def test_cannot_promote_failed_media_by_editing_audit_only():
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id="E01_SC002")
    runtime.plan_scene(_geometry(), [_plan()])
    runtime.media = {
        "MASTER": {"sha256": "master-sha", "generation_execution_id": "exec-master"},
        "REVERSE": {"sha256": "derived-sha", "generation_execution_id": "exec-reverse-1"},
        "SIDE": {"sha256": "derived-side", "generation_execution_id": "exec-side-1"},
        "DETAIL": {"sha256": "derived-detail", "generation_execution_id": "exec-detail-1"},
    }
    audits = [
        _passing_audit("REVERSE"),
        _passing_audit("SIDE", derived_sha="derived-side"),
        _passing_audit("DETAIL", derived_sha="derived-detail"),
    ]
    for audit in audits:
        runtime.record_audit(audit)
    audits[0].status = "FAIL"
    with pytest.raises(RuntimeError, match="AUDIT_STATUS_WITHOUT_MEDIA_EVIDENCE_CHANGE"):
        runtime.lock()


def test_stale_judge_evidence_is_rejected_after_new_derived_media():
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id="E01_SC002")
    runtime.plan_scene(_geometry(), [_plan()])
    runtime.media = {
        "MASTER": {"sha256": "master-sha", "generation_execution_id": "exec-master"},
        "REVERSE": {"sha256": "new-derived-sha", "generation_execution_id": "exec-reverse-2"},
        "SIDE": {"sha256": "derived-side", "generation_execution_id": "exec-side-1"},
        "DETAIL": {"sha256": "derived-detail", "generation_execution_id": "exec-detail-1"},
    }
    runtime.record_audit(_passing_audit("REVERSE", derived_sha="old-derived-sha"))
    with pytest.raises(RuntimeError, match="JUDGE_EVIDENCE_STALE"):
        runtime.lock()


def test_score_scale_must_be_explicitly_0_to_100():
    with pytest.raises(ValueError, match="VISION_JUDGE_INVALID_SCORE_SCALE"):
        SceneConsistencyAudit(
            view_id="REVERSE",
            status="REPAIR",
            same_physical_space=False,
            architecture_score=9,
            landmark_score=9,
            furniture_score=9,
            lighting_score=9,
            score_scale="0-10",
        )


def test_audit_without_media_evidence_cannot_be_recorded():
    runtime = AutonomousAssetGeneration(asset_type="SCENE", asset_id="E01_SC002")
    runtime.plan_scene(_geometry(), [_plan()])
    audit = SceneConsistencyAudit(
        view_id="REVERSE",
        status="REPAIR",
        same_physical_space=False,
        architecture_score=20,
        landmark_score=20,
        furniture_score=20,
        lighting_score=20,
    )
    with pytest.raises(RuntimeError, match="AUDIT_MEDIA_EVIDENCE_MISSING"):
        runtime.record_audit(audit)
