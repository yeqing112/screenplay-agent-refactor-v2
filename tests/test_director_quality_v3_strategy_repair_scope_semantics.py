from core.director_strategy_scope_semantics import (
    FIELD_SEMANTICS_REGISTRY,
    compare_set_like,
    field_semantics,
    is_identity_semantic_sync_change,
    segment_match,
    semantic_diff,
)


def test_segment_matcher_is_selector_aware():
    assert segment_match("scene_phases[*].performance[*].character_id", "scene_phases[P01].performance[0].character_id")
    assert segment_match("scene_phases[*].performance[*].character_id", "scene_phases[2].performance[0].character_id")
    assert segment_match("scene_phases[P02].information.hint_refs", "scene_phases[P02].information.hint_refs[0]")
    assert not segment_match("scene_phases[P01].information.hint_refs", "scene_phases[P02].information.hint_refs")


def test_registry_does_not_treat_all_arrays_as_sets():
    assert field_semantics("scene_phases[P01].information.reveal_refs") == "SET_LIKE"
    assert field_semantics("scene_phases[P01].beat_ids") == "ORDERED"
    assert field_semantics("scene_phases[P01].performance") == "ORDERED"
    assert FIELD_SEMANTICS_REGISTRY["scene_phases[*].performance"] == "ORDERED"


def test_set_like_reorder_is_explicit_semantic_noop():
    result = compare_set_like(["beat:1", "character:19", "character:20"], ["beat:1", "character:20", "character:19"])
    assert result["added_refs"] == []
    assert result["removed_refs"] == []
    assert result["same_refs_reordered"] is True
    assert result["semantic_change"] is False
    diff = semantic_diff({"scene_phases": [{"phase_id": "P01", "information": {"reveal_refs": ["a", "b"]}}]}, {"scene_phases": [{"phase_id": "P01", "information": {"reveal_refs": ["b", "a"]}}]})
    assert diff[0]["classification"] == "NO_SEMANTIC_CHANGE"
    assert diff[0]["reordered_only"] is True


def test_set_like_add_remove_is_real_change_and_duplicates_visible():
    result = compare_set_like(["beat:1", "beat:2"], ["beat:1", "beat:3"])
    assert result["removed_refs"] == ["beat:2"]
    assert result["added_refs"] == ["beat:3"]
    assert result["semantic_change"] is True
    dup = compare_set_like(["character:19"], ["character:19", "character:19"])
    assert dup["revised_duplicates"] == ["character:19"]
    assert dup["semantic_change"] is True


def test_ordered_reorders_remain_changes():
    base = {"scene_phases": [{"phase_id": "P01", "beat_ids": ["1", "2"], "performance": [{"character_id": "19"}, {"character_id": "20"}]}]}
    revised = {"scene_phases": [{"phase_id": "P01", "beat_ids": ["2", "1"], "performance": [{"character_id": "20"}, {"character_id": "19"}]}]}
    diffs = semantic_diff(base, revised)
    assert {d["path"] for d in diffs} == {"scene_phases[P01].beat_ids", "scene_phases[P01].performance[0].character_id", "scene_phases[P01].performance[1].character_id"}
    assert all(d["semantic_change"] for d in diffs)


def test_identity_dependency_allows_only_authoritative_subject_restore():
    result = is_identity_semantic_sync_change("character:20", "character:19", {"19": "林晚", "20": "顾沉"}, semantic_subject="林晚")
    assert result["classification"] == "IDENTITY_DEPENDENCY_PASS"
    assert result["base_bound_name"] == "顾沉"
    assert result["revised_bound_name"] == "林晚"


def test_identity_dependency_rejects_unknown_or_changed_subject():
    assert is_identity_semantic_sync_change("character:20", "character:999", {"19": "林晚", "20": "顾沉"}, semantic_subject="林晚")["classification"] == "REJECT"
    assert is_identity_semantic_sync_change("character:20", "character:19", {"19": "林晚", "20": "顾沉"}, semantic_subject="顾沉")["classification"] == "REJECT"
    assert is_identity_semantic_sync_change("beat:1", "character:19", {"19": "林晚"}, semantic_subject="林晚")["classification"] == "REJECT"
