import pytest

from core.director_patch_schema import (
    CreativePatchSchemaError,
    parse_creative_patch,
    parse_creative_patch_partial,
    validate_creative_patch_document,
)


def _valid_document():
    return {
        "schema_version": "director_creative_patch_v1",
        "patches": [
            {
                "plan_shot_id": "S03",
                "changes": {
                    "camera.shot_size": "CU",
                    "camera.movement": "slow_push_in",
                    "emotion.intensity": 7,
                },
                "rationale": "延迟切入反应以完成信息揭示",
                "confidence": 0.9,
            }
        ],
        "auxiliary_shot_proposals": [
            {
                "proposal_id": "AUX_001",
                "proposal_type": "reaction",
                "source_beat_id": "B04",
                "insert_after_plan_shot_id": "S05",
                "purpose": "show_reaction",
                "why_needed": "原结构镜头没有承载关键反应",
                "participants": ["CHAR_002"],
                "camera": {"shot_size": "CU", "angle": "eye_level"},
                "estimated_duration_seconds": 2,
            }
        ],
    }


def test_valid_patch_document_is_normalized_and_fingerprinted():
    document = parse_creative_patch(_valid_document())
    assert document["schema_version"] == "director_creative_patch_v1"
    assert document["patches"][0]["plan_shot_id"] == "S03"
    assert document["patches"][0]["changes"]["camera.shot_size"] == "CU"
    assert document["auxiliary_shot_proposals"][0]["source_beat_id"] == "B04"
    assert document["patch_fingerprint"]


def test_complete_shot_or_authoritative_top_level_is_rejected_before_compilation():
    payload = {"schema_version": "director_creative_patch_v1", "shots": []}
    with pytest.raises(CreativePatchSchemaError) as error:
        parse_creative_patch(payload)
    assert error.value.code == "DIRECTOR_PATCH_FIELD_FORBIDDEN"

    payload = _valid_document()
    payload["patches"][0]["changes"]["scene_name"] = "被篡改场景"
    with pytest.raises(CreativePatchSchemaError) as error:
        parse_creative_patch(payload)
    assert error.value.code == "DIRECTOR_FACT_OVERRIDE"


def test_non_conflicting_duplicate_targets_are_merged_and_conflicts_rejected():
    payload = _valid_document()
    payload["patches"].append({"plan_shot_id": "S03", "changes": {"camera.angle": "low_angle"}})
    merged = parse_creative_patch(payload)
    assert len(merged["patches"]) == 1
    assert merged["patches"][0]["changes"]["camera.angle"] == "low_angle"
    assert merged["patches"][0]["_source_format"] == "merged_equivalent"

    payload["patches"].append({"plan_shot_id": "S03", "changes": {"camera.angle": "dutch"}})
    with pytest.raises(CreativePatchSchemaError) as error:
        parse_creative_patch(payload)
    assert error.value.code == "DIRECTOR_PATCH_DUPLICATE_TARGET"

    payload = _valid_document()
    payload["auxiliary_shot_proposals"][0]["proposal_type"] = "new_plot"
    report = validate_creative_patch_document(payload)
    assert report["status"] == "invalid"
    assert report["errors"][0]["code"] == "INVALID_AUXILIARY_TYPE"


def test_invalid_schema_version_is_fail_closed():
    payload = _valid_document()
    payload["schema_version"] = "shot_plan_v2"
    report = validate_creative_patch_document(payload)
    assert report["status"] == "invalid"
    assert report["errors"][0]["code"] == "DIRECTOR_PATCH_SCHEMA_VERSION_INVALID"


def test_parser_accepts_its_normalized_fingerprint_and_rejects_tampering():
    normalized = parse_creative_patch(_valid_document())
    reparsed = parse_creative_patch(normalized)
    assert reparsed["patch_fingerprint"] == normalized["patch_fingerprint"]

    tampered = dict(normalized)
    tampered["patch_fingerprint"] = "0" * 64
    with pytest.raises(CreativePatchSchemaError) as error:
        parse_creative_patch(tampered)
    assert error.value.code == "DIRECTOR_PATCH_FINGERPRINT_MISMATCH"


def test_partial_parser_keeps_valid_patch_when_one_item_has_forbidden_field():
    result = parse_creative_patch_partial({
        "schema_version": "director_creative_patch_v1",
        "patches": [
            {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
            {"plan_shot_id": "S02", "changes": {"scene_name": "改写事实"}},
        ],
        "auxiliary_shot_proposals": [],
    })
    assert result["status"] == "partial"
    assert result["fatal"] is False
    assert [item["plan_shot_id"] for item in result["document"]["patches"]] == ["S01"]
    assert result["errors"][0]["code"] == "DIRECTOR_FACT_OVERRIDE"


def test_partial_parser_reports_fatal_fingerprint_mismatch():
    result = parse_creative_patch_partial({
        "schema_version": "director_creative_patch_v1",
        "patches": [{"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}}],
        "auxiliary_shot_proposals": [],
        "patch_fingerprint": "not-the-document-fingerprint",
    })
    assert result["fatal"] is True
    assert result["document"]["patches"][0]["plan_shot_id"] == "S01"
    assert any(item["code"] == "DIRECTOR_PATCH_FINGERPRINT_MISMATCH" for item in result["errors"])


def test_parser_normalizes_nested_creative_fields_without_guessing():
    document = parse_creative_patch({
        "schema_version": "director_creative_patch_v1",
        "patches": [{
            "plan_shot_id": "S01",
            "camera": {"shot_size": "CU", "movement": "static"},
            "emotion": {"intensity": 6},
            "why_this_shot": "完成反应",
        }],
        "auxiliary_shot_proposals": [],
    })
    patch = document["patches"][0]
    assert patch["changes"] == {
        "camera.shot_size": "CU",
        "camera.movement": "static",
        "emotion.intensity": 6,
        "why_this_shot": "完成反应",
    }
    assert document["normalization_metadata"] == {
        "normalization_applied": True,
        "source_formats": ["nested_creative_fields"],
    }


def test_parser_normalizes_json_patch_operation_and_wrapper():
    operation = parse_creative_patch({
        "schema_version": "director_creative_patch_v1",
        "patches": [{"plan_shot_id": "S01", "path": "/shots/0/camera/angle", "value": "eye_level"}],
        "auxiliary_shot_proposals": [],
    })
    wrapper = parse_creative_patch({
        "schema_version": "director_creative_patch_v1",
        "patches": [{"plan_shot_id": "S02", "patch": [{"op": "replace", "path": "camera.movement", "value": "tracking"}]}],
        "auxiliary_shot_proposals": [],
    })
    assert operation["patches"][0]["changes"] == {"camera.angle": "eye_level"}
    assert wrapper["patches"][0]["changes"] == {"camera.movement": "tracking"}
    assert operation["normalization_metadata"]["source_formats"] == ["json_patch_operation"]
    assert wrapper["normalization_metadata"]["source_formats"] == ["json_patch_wrapper"]


def test_parser_keeps_immutable_nested_fields_fail_closed():
    with pytest.raises(CreativePatchSchemaError) as error:
        parse_creative_patch({
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": "S01", "event": "改写事实"}],
            "auxiliary_shot_proposals": [],
        })
    assert error.value.code == "DIRECTOR_PATCH_FIELD_FORBIDDEN"
