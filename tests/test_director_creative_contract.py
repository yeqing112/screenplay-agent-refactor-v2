from core.director_creative_contract import (
    ALLOWED_PATCH_PATHS,
    AUXILIARY_SHOT_POLICY,
    build_director_creative_contract,
    is_allowed_patch_path,
)
from core.shot_plan import build_shot_plan


def _evidence():
    treatment = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "episode": 1,
        "beat_map": [
            {"beat_id": "B01", "type": "setup", "event": "林晚推门进入"},
            {"beat_id": "B02", "type": "reveal", "event": "她发现桌上的照片", "information_change": "照片出现"},
        ],
    }
    blocking = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "participants": [{"character_id": "CHAR_LIN", "name": "林晚"}],
        "source_spatial_facts": [
            {"fact_id": "F1", "subject_id": "CHAR_LIN", "predicate": "position", "value": "门口", "authority": "SOURCE_FACT"}
        ],
    }
    plan = build_shot_plan(treatment=treatment, blocking=blocking)
    return treatment, blocking, plan


def test_contract_exposes_only_explicit_creative_paths_and_immutable_projection():
    treatment, blocking, plan = _evidence()
    contract = build_director_creative_contract(
        fact_snapshot={"payload_hash": "facts-1", "records": [{"fact_id": "F1", "value": "门口"}]},
        script_scene={"scene_id": "E01_SC01", "name": "雨夜门厅", "episode": 1, "beats": treatment["beat_map"]},
        treatment=treatment,
        blocking=blocking,
        structural_shot_plan=plan,
    )

    assert contract["status"] == "ready"
    assert contract["contract_fingerprint"]
    assert contract["source_beat_map"]["B02"]["event"] == "她发现桌上的照片"
    assert contract["immutable_projection"]["shots"][0]["event"] == "林晚推门进入"
    assert "scene_name" in contract["immutable_fields"]
    assert "camera.shot_size" in contract["editable_fields"]
    assert "/shots/*/camera/shot_size" in contract["allowed_patch_paths"]


def test_contract_path_guard_accepts_relative_and_pointer_creative_paths_only():
    assert is_allowed_patch_path("camera.shot_size")
    assert is_allowed_patch_path("/shots/0/camera/movement")
    assert is_allowed_patch_path("shots/S03/information_strategy/audience_focus")
    assert not is_allowed_patch_path("event")
    assert not is_allowed_patch_path("/scene_name")
    assert not is_allowed_patch_path("/shots/0/asset_bindings/scene_asset_id")


def test_contract_fingerprint_changes_when_immutable_source_changes():
    treatment, blocking, plan = _evidence()
    first = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    changed = dict(treatment)
    changed["beat_map"] = [dict(item) for item in treatment["beat_map"]]
    changed["beat_map"][0]["event"] = "林晚撞开铁门"
    second = build_director_creative_contract(treatment=changed, blocking=blocking, structural_shot_plan=plan)
    assert first["contract_fingerprint"] != second["contract_fingerprint"]


def test_auxiliary_policy_is_explicit_and_bounded():
    assert set(AUXILIARY_SHOT_POLICY["allowed_types"]) == {"reaction", "insert", "establishing", "transition", "detail"}
    assert AUXILIARY_SHOT_POLICY["max_per_source_beat"] == 2
    assert "source_beat_id" in AUXILIARY_SHOT_POLICY["requires"]
    assert "/shots/*/event" not in ALLOWED_PATCH_PATHS
