from core.director_creative_contract import build_director_creative_contract
from core.director_partial_acceptance import apply_partial_acceptance
from core.shot_plan import build_shot_plan


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
    return plan, contract


def test_one_failed_patch_does_not_discard_other_accepted_patches():
    plan, contract = _inputs()
    document = {
        "schema_version": "director_creative_patch_v1",
        "patches": [
            {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
            {"plan_shot_id": "S99", "changes": {"camera.angle": "high_angle"}},
        ],
        "auxiliary_shot_proposals": [],
    }
    result = apply_partial_acceptance(plan, document, contract)
    assert result["status"] == "partial"
    assert result["director_mode"] == "partial_creative_planner"
    assert result["candidate"]["shots"][0]["camera"]["angle"] == "low_angle"
    assert result["partial_acceptance"] == {
        "accepted_patch_count": 1,
        "rejected_patch_count": 1,
        "repaired_patch_count": 0,
        "fallback_patch_count": 1,
    }

