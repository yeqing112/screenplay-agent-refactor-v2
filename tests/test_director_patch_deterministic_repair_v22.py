from core.director_patch_deterministic_repair import deterministic_repair_document, merge_duplicate_patches


def _doc(patches):
    return {
        "schema_version": "director_creative_patch_v1",
        "patches": patches,
        "auxiliary_shot_proposals": [],
    }


def test_identical_duplicate_patch_is_merged_deterministically():
    result = deterministic_repair_document(
        _doc([
            {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
            {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
        ])
    )
    assert result["status"] == "repaired"
    assert len(result["document"]["patches"]) == 1
    assert result["deterministic_repair_events"] == 1
    assert result["events"][-1]["kind"] == "DUPLICATE_IDENTICAL_PATCH"


def test_non_conflicting_duplicate_patch_is_merged_without_llm():
    result = deterministic_repair_document(
        _doc([
            {"plan_shot_id": "S02", "changes": {"camera.shot_size": "CU"}},
            {"plan_shot_id": "S02", "changes": {"camera.movement": "static"}},
        ])
    )
    patch = result["document"]["patches"][0]
    assert patch["changes"] == {"camera.shot_size": "CU", "camera.movement": "static"}
    assert result["events"][-1]["kind"] == "NON_CONFLICTING_DUPLICATE_PATCH"
    assert result["llm_required"] is False


def test_conflicting_duplicate_is_rejected_but_first_patch_is_retained():
    result = deterministic_repair_document(
        _doc([
            {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
            {"plan_shot_id": "S01", "changes": {"camera.shot_size": "MS"}},
            {"plan_shot_id": "S02", "changes": {"camera.angle": "eye_level"}},
        ])
    )
    assert result["status"] == "partial"
    assert len(result["document"]["patches"]) == 2
    assert result["rejected"][0]["code"] == "CROSS_PATCH_CONFLICT"


def test_patch_order_is_stable_by_target_and_contract_path_order():
    result = deterministic_repair_document(
        _doc([
            {"plan_shot_id": "S02", "changes": {"emotion.intensity": 5}},
            {"plan_shot_id": "S01", "changes": {"camera.movement": "static"}},
            {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
        ])
    )
    assert [item["plan_shot_id"] for item in result["document"]["patches"]] == ["S01", "S02"]
    assert list(result["document"]["patches"][0]["changes"]) == ["camera.movement", "camera.shot_size"]


def test_merge_helper_never_calls_or_needs_an_llm():
    result = merge_duplicate_patches([
        {"plan_shot_id": "S01", "changes": {"camera.shot_size": "CU"}},
        {"plan_shot_id": "S01", "changes": {"camera.angle": "eye_level"}},
    ])
    assert result["rejected"] == []
    assert result["events"][0]["kind"] == "NON_CONFLICTING_DUPLICATE_PATCH"
