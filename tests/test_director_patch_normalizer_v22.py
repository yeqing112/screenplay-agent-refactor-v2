import pytest

from core.director_creative_contract import build_director_creative_contract
from core.director_creative_planner import build_creative_patch_candidate
from core.scene_directing_strategy import build_scene_directing_strategy
from core.shot_plan import build_shot_plan
from core.director_patch_normalizer import (
    PatchNormalizationError,
    canonical_path,
    normalize_patch_document,
    normalize_patch_item,
)
from core.director_patch_schema import parse_creative_patch


def test_canonical_path_accepts_dotted_pointer_and_declared_wildcard_equivalents():
    assert canonical_path("camera.shotSize", plan_shot_id="S03") == "camera.shot_size"
    assert canonical_path("/shots/S03/camera/shot_size", plan_shot_id="S03") == "camera.shot_size"
    assert canonical_path("/shots/*/camera/shot_size", plan_shot_id="S03") == "camera.shot_size"


def test_canonical_path_rejects_cross_target_and_unbound_wildcard():
    with pytest.raises(PatchNormalizationError) as error:
        canonical_path("/shots/S02/camera/shot_size", plan_shot_id="S03")
    assert error.value.code == "DIRECTOR_PATCH_TARGET_MISMATCH"
    with pytest.raises(PatchNormalizationError) as error:
        canonical_path("/shots/*/camera/shot_size")
    assert error.value.code == "DIRECTOR_PATCH_TARGET_MISMATCH"


def test_nested_patch_and_alias_enum_numeric_values_are_normalized_without_creative_choice():
    patch = normalize_patch_item(
        {
            "plan_shot_id": "S01",
            "camera": {"shotSize": " close-up ", "cameraMovement": " static "},
            "emotion": {"intensity": "7"},
        }
    )
    assert patch["changes"] == {
        "camera.shot_size": "CU",
        "camera.movement": "static",
        "emotion.intensity": 7,
    }
    assert patch["_source_format"] == "nested_creative_fields"
    assert "enum_alias:shot_size" in patch["_normalization_reasons"]


def test_information_strategy_singular_provider_fields_are_protocol_aliases():
    patch = normalize_patch_item(
        {
            "plan_shot_id": "S01",
            "information_strategy": {"reveal": ["照片"], "withhold": ["来源"], "audienceFocus": "人物反应"},
        }
    )
    assert patch["changes"] == {
        "information_strategy.reveals": ["照片"],
        "information_strategy.withholds": ["来源"],
        "information_strategy.audience_focus": "人物反应",
    }


def test_strategy_refs_are_preserved_as_provenance_metadata():
    document = parse_creative_patch(
        {
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S01", "changes": {"emotion.intensity": 7}, "strategy_refs": ["emotion:B01:C1"]}],
            "auxiliary_shot_proposals": [],
        }
    )
    assert document["patches"][0]["strategy_refs"] == ["emotion:B01:C1"]


def test_json_patch_wildcard_and_numeric_selector_are_flattened():
    document = normalize_patch_document(
        {
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {
                    "plan_shot_id": "S03",
                    "patch": [
                        {"op": "replace", "path": "/shots/*/camera/shot_size", "value": "CU"},
                        {"op": "replace", "path": "camera.movement", "value": " static "},
                    ],
                }
            ],
            "auxiliary_shot_proposals": [],
        },
        known_plan_shot_ids=["S01", "S02", "S03"],
    )
    assert document["patches"][0]["changes"] == {"camera.shot_size": "CU", "camera.movement": "static"}
    assert document["normalization_metadata"]["normalization_applied"] is True
    assert document["normalization_metadata"]["before_fingerprint"]
    assert document["normalization_metadata"]["after_fingerprint"]


def test_normalizer_preserves_conflicting_duplicates_for_level_one():
    document = normalize_patch_document(
        {
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
                {"plan_shot_id": "S01", "changes": {"camera.shot_size": "MS"}},
            ],
            "auxiliary_shot_proposals": [],
        }
    )
    assert len(document["patches"]) == 2


def test_normalizer_does_not_drop_immutable_fields():
    with pytest.raises(PatchNormalizationError) as error:
        normalize_patch_item({"plan_shot_id": "S01", "event": "改写事实"})
    assert error.value.code == "DIRECTOR_PATCH_FIELD_FORBIDDEN"


def test_planner_uses_level0_before_schema_repair_for_equivalent_operation():
    treatment = {"scene_id": "E", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "event": "进入"}]}
    blocking = {"scene_id": "E", "scene_name": "门厅", "participants": [{"character_id": "C1", "name": "林晚"}]}
    structural = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=structural)
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    result = build_creative_patch_candidate(
        structural_shot_plan=structural,
        contract=contract,
        strategy=strategy,
        llm_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S01", "patch": [{"op": "replace", "path": "/shots/*/camera/shot_size", "value": "close-up"}]}],
            "auxiliary_shot_proposals": [],
        },
    )
    assert result["model_info"]["schema_pass"] is True
    assert result["model_info"]["v22_normalization"]["normalization_events"]
    assert result["patch_document"]["patches"][0]["changes"]["camera.shot_size"] == "CU"
