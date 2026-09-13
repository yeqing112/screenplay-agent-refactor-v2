import pytest

from core.director_patch_normalizer import (
    PatchNormalizationError,
    canonical_path,
    normalize_patch_document,
    normalize_patch_item,
)


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
