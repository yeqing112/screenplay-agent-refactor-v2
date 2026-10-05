from __future__ import annotations

from types import SimpleNamespace

from core.canonical_canary_selection import (
    _asset_gate,
    _authority_ok,
    _reference_requirements,
    detect_semantic_clone_groups,
    extract_canary_semantic_features,
    rank_canary_candidates,
    reference_readiness_blockers,
    select_canary_target,
    select_semantic_canary_target,
)
import json


def _candidate(plan_shot_id: str, *, score_shape: bool = True, hard_gate: str = "PASS") -> dict:
    return {
        "book_id": 990448,
        "episode": 1,
        "plan_shot_id": plan_shot_id,
        "storyboard_shot_id": int(plan_shot_id.rsplit("_", 1)[-1]),
        "hard_gate": hard_gate,
        "characters": 2 if score_shape else 0,
        "dialogue_present": bool(score_shape),
        "props": 0,
        "duration": 5,
        "prompt_ir": {"IMAGE": "PRESENT_CURRENT", "VIDEO": "PRESENT_CURRENT"},
        "blockers": [] if hard_gate == "PASS" else ["STORYBOARD_MATERIALIZATION_INVALID"],
    }


def test_benchmark_fixture_historical_keyframe_cannot_be_canonical():
    from core.canary_identity_boundary import classify_canary_identity

    result = classify_canary_identity("SH_E01_SC002_006")
    assert result["production_canonical_identity"] is False
    assert result["historical_media_authority"] is False
    assert "PRODUCTION_SHOT_AUTHORITY" in result["forbidden_usage"]


def test_exact_current_candidate_is_ranked_and_selected_when_unique():
    result = select_canary_target([_candidate("SH_E01_SC001_001", score_shape=True)])
    assert result["status"] == "CANONICAL_CANARY_TARGET_SELECTED"
    assert result["selected"]["plan_shot_id"] == "SH_E01_SC001_001"


def test_tied_candidates_fail_closed_as_ambiguous():
    result = select_canary_target([_candidate("SH_E01_SC001_001"), _candidate("SH_E01_SC001_002")])
    assert result["status"] == "CANONICAL_CANARY_TARGET_AMBIGUOUS"
    assert len(result["top_candidates"]) == 2


def test_no_hard_gate_candidate_returns_explicit_no_target():
    result = select_canary_target([_candidate("SH_E01_SC001_001", hard_gate="FAIL")])
    assert result["status"] == "NO_CANONICAL_CANARY_TARGET_READY"
    assert result["blocker_counts"]["STORYBOARD_MATERIALIZATION_INVALID"] == 1


def test_ranking_is_deterministic_and_excludes_blocked_rows():
    rows = [_candidate("SH_E01_SC001_002"), _candidate("SH_E01_SC001_001"), _candidate("SH_E01_SC001_003", hard_gate="FAIL")]
    ranked = rank_canary_candidates(rows)
    assert [item["plan_shot_id"] for item in ranked] == ["SH_E01_SC001_001", "SH_E01_SC001_002"]


def test_missing_pointer_treatment_blocking_materialization_and_stale_authority_fail():
    good_row = SimpleNamespace(id=1, qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH")
    good_authority = SimpleNamespace(qualification_state="AUTHORITY_BOUND", stale_status="FRESH", envelope_fingerprint="fp")
    good_pointer = SimpleNamespace(shot_plan_id=1, authority_envelope_fingerprint="fp", qualification_state="PRODUCTION_QUALIFIED")
    assert _authority_ok(good_row, good_authority, good_pointer)
    assert not _authority_ok(good_row, good_authority, None)
    assert not _authority_ok(good_row, SimpleNamespace(qualification_state="AUTHORITY_BOUND", stale_status="STALE", envelope_fingerprint="fp"), good_pointer)
    assert not _authority_ok(None, good_authority, good_pointer)


def test_asset_authority_missing_required_scene_and_character_is_blocked(monkeypatch):
    monkeypatch.setattr("core.canonical_canary_selection._production_asset_authority", lambda *args, **kwargs: {"bindings": [], "authority_fingerprint": None})
    handoff = {"asset_identity_bindings": {"canonical_asset_identity": {"scene": "E01_SC001", "characters": ["LIN_WAN"], "props": []}}}
    assets, blockers = _asset_gate(SimpleNamespace(), book_id=990448, handoff=handoff)
    assert assets["status"] == "FAIL"
    assert "ASSET_AUTHORITY_SCENE_MISSING" in blockers
    assert "ASSET_AUTHORITY_REQUIRED_CHARACTERS_MISSING" in blockers


def test_materialization_membership_and_prompt_readiness_are_hard_gate_inputs():
    row = _candidate("SH_E01_SC001_001", hard_gate="FAIL")
    row["blockers"] = ["MATERIALIZATION_POINTER_MISSING", "STORYBOARD_SHOT_NOT_IN_CURRENT_SET", "PROMPT_IR_VIDEO_NOT_CURRENT"]
    result = select_canary_target([row])
    assert result["status"] == "NO_CANONICAL_CANARY_TARGET_READY"
    assert set(result["blocker_counts"]) == set(row["blockers"])


def test_selection_is_provider_free():
    result = select_canary_target([_candidate("SH_E01_SC001_001")])
    assert result["status"] == "CANONICAL_CANARY_TARGET_SELECTED"
    assert "provider_calls" not in result


def _semantic(subjects=None, props=None, dialogue="", framing="MEDIUM", movement="NONE", support="STATIC", duration=5, useful=True):
    subjects = subjects or []
    props = props or []
    return {
        "subject_ids": subjects,
        "subject_count": len(subjects),
        "prop_ids": props,
        "prop_count": len(props),
        "dialogue_present": bool(dialogue),
        "dialogue_length": len(dialogue),
        "dialogue_fingerprint": "dialogue-fp",
        "camera": {"framing": framing, "movement": movement, "support": support},
        "camera_complexity": "LOW" if movement in {"", "NONE", "STATIC"} and support in {"", "STATIC"} else "MEDIUM",
        "reaction_or_performance_presence": useful,
        "temporal_intent_presence": useful,
        "entry_state_presence": useful,
        "exit_state_presence": useful,
        "continuity_data_presence": True,
        "visual_semantic_fingerprint": f"semantic-{len(subjects)}-{bool(dialogue)}-{framing}-{movement}",
    }


def test_subjects_are_read_from_visual_semantic_handoff_and_nested_asset_identity():
    row = SimpleNamespace(dialogue="", duration=5, meta_info=json.dumps({
        "visual_semantic_handoff": {
            "subjects": [{"character_id": "LIN_WAN"}, {"id": "LU_SHU"}],
            "props": [{"prop_id": "APPLE"}],
            "asset_identity_bindings": {"canonical_asset_identity": {"scene": "E01_SC001", "characters": ["LIN_WAN", "LU_SHU"], "props": ["APPLE"]}},
            "camera": {"framing_class": "MEDIUM", "movement": "NONE", "support": "STATIC"},
        }
    }))
    features = extract_canary_semantic_features(row)
    assert features["subject_ids"] == ["LIN_WAN", "LU_SHU"]
    assert features["subject_count"] == 2
    assert features["prop_ids"] == ["APPLE"]
    assert features["canonical_asset_identity"]["characters"] == ["LIN_WAN", "LU_SHU"]


def test_semantic_subject_asset_authority_mismatch_fails_closed(monkeypatch):
    monkeypatch.setattr("core.canonical_canary_selection._production_asset_authority", lambda *args, **kwargs: {"bindings": [{"asset_type": "scene", "canonical_asset_id": "E01_SC001"}, {"asset_type": "character", "canonical_asset_id": "LIN_WAN"}], "authority_fingerprint": "fp"})
    features = {"asset_identity_refs": {"scene": "E01_SC001", "characters": ["LIN_WAN", "LU_SHU"], "props": []}, "subject_ids": ["LIN_WAN", "LU_SHU"], "prop_ids": []}
    _, blockers = _asset_gate(SimpleNamespace(), book_id=990448, handoff={}, semantic_features=features)
    assert "ASSET_AUTHORITY_REQUIRED_CHARACTERS_MISSING" in blockers


def test_dialogue_truth_comes_from_storyboard_projection_and_is_hashed():
    row = SimpleNamespace(dialogue="对白内容", duration=5, meta_info=json.dumps({"projection_payload": {"dialogue": "对白内容"}, "visual_semantic_handoff": {"subjects": []}}))
    features = extract_canary_semantic_features(row)
    assert features["dialogue_present"] is True
    assert features["dialogue_length"] == 4
    assert features["dialogue_fingerprint"]
    assert features["dialogue_consistency"] == "PASS"


def test_missing_prompt_ir_is_readiness_only_and_keeps_identity_candidate():
    row = _candidate("SH_E01_SC001_001")
    row["canonical_eligibility"] = "PASS"
    row["prompt_ir_readiness"] = {"IMAGE": "PRESENT_CURRENT", "VIDEO": "MISSING_COMPILE_REQUIRED"}
    ranked = rank_canary_candidates([row])
    assert ranked and ranked[0]["prompt_ir_readiness"]["VIDEO"] == "MISSING_COMPILE_REQUIRED"


def test_missing_image_prompt_ir_is_readiness_only_and_keeps_identity_candidate():
    row = _candidate("SH_E01_SC001_001")
    row["canonical_eligibility"] = "PASS"
    row["prompt_ir_readiness"] = {"IMAGE": "MISSING_COMPILE_REQUIRED", "VIDEO": "PRESENT_CURRENT"}
    ranked = rank_canary_candidates([row])
    assert ranked and ranked[0]["prompt_ir_readiness"]["IMAGE"] == "MISSING_COMPILE_REQUIRED"


def test_invalid_prompt_ir_is_execution_integrity_blocker():
    row = _candidate("SH_E01_SC001_001")
    row["canonical_eligibility"] = "FAIL"
    row["blockers"] = ["PROMPT_IR_VIDEO_INVALID_CURRENT_AUTHORITY"]
    assert select_canary_target([row])["status"] == "NO_CANONICAL_CANARY_TARGET_READY"


def test_unknown_provenance_cannot_become_production_canary():
    row = _candidate("SH_E01_SC001_001")
    row["canonical_eligibility"] = "FAIL"
    row["book"] = {"provenance_class": "UNKNOWN_PROVENANCE", "eligible": False}
    result = select_semantic_canary_target([row])
    assert result["status"] in {"NO_PRODUCTION_CANARY_PROJECT_ELIGIBLE", "NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET"}


def test_clone_group_detection_is_deterministic_and_ignores_book_identity():
    rows = []
    for book_id in (990448, 990449):
        row = _candidate("SH_E01_SC001_001")
        row.update({"book_id": book_id, "semantic_features": _semantic(subjects=["LIN_WAN"], dialogue="x")})
        row["canonical_eligibility"] = "PASS"
        rows.append(row)
    first = detect_semantic_clone_groups(rows)
    second = detect_semantic_clone_groups(rows)
    assert first == second
    assert first[0]["member_book_ids"] == [990448, 990449]


def test_book_and_storyboard_ids_do_not_change_quality_score():
    a = _candidate("SH_E01_SC001_001"); a.update({"book_id": 1, "storyboard_shot_id": 1, "canonical_eligibility": "PASS", "semantic_features": _semantic(subjects=["LIN_WAN", "LU_SHU"], dialogue="x")})
    b = _candidate("SH_E01_SC001_002"); b.update({"book_id": 999999, "storyboard_shot_id": 999999, "canonical_eligibility": "PASS", "semantic_features": _semantic(subjects=["LIN_WAN", "LU_SHU"], dialogue="x")})
    ranked = rank_canary_candidates([a, b])
    assert ranked[0]["selection_score"] == ranked[1]["selection_score"]


def test_two_character_dialogue_beats_empty_static_scene():
    rich = _candidate("SH_E01_SC001_001"); rich.update({"canonical_eligibility": "PASS", "semantic_features": _semantic(subjects=["LIN_WAN", "LU_SHU"], dialogue="x")})
    empty = _candidate("SH_E01_SC001_002"); empty.update({"canonical_eligibility": "PASS", "semantic_features": _semantic(subjects=[], dialogue="", useful=False)})
    ranked = rank_canary_candidates([empty, rich])
    assert ranked[0]["plan_shot_id"] == "SH_E01_SC001_001"
    assert ranked[0]["selection_score"] > ranked[1]["selection_score"]


def test_camera_complexity_and_reference_policy_are_explicit():
    complex_features = _semantic(subjects=["LIN_WAN"], movement="ORBIT", support="HANDHELD")
    assert complex_features["camera_complexity"] == "MEDIUM"
    optional = _reference_requirements(complex_features, image_profile={"default_params": {"supports_reference_images": True}}, prompt_payload={"generation_policy": {"required_asset_classes": []}})
    required = _reference_requirements(complex_features, image_profile={"default_params": {"supports_reference_images": True}}, prompt_payload={"generation_policy": {"required_asset_classes": ["CHARACTER"]}})
    assert optional["character"] == "OPTIONAL"
    assert required["character"] == "REQUIRED"


def test_optional_reference_pending_does_not_block_but_required_reference_does():
    features = {"asset_identity_refs": {"scene": "E01_SC001", "characters": ["LIN_WAN"], "props": []}}
    assets = {"bindings": [{"asset_type": "character", "reference_status": "REFERENCE_PENDING"}]}
    assert reference_readiness_blockers(features, assets, {"scene": "OPTIONAL", "character": "OPTIONAL", "prop": "OPTIONAL"}) == []
    assert reference_readiness_blockers(features, assets, {"scene": "OPTIONAL", "character": "REQUIRED", "prop": "OPTIONAL"}) == ["REQUIRED_CHARACTER_REFERENCE_NOT_READY"]


def test_semantic_selection_rejects_all_zero_subject_inventory():
    rows = []
    for index in range(2):
        row = _candidate(f"SH_E01_SC001_00{index + 1}")
        row.update({"canonical_eligibility": "PASS", "book": {"provenance_class": "PRODUCTION_PROJECT", "eligible": True}, "semantic_features": _semantic(subjects=[], dialogue="", useful=False), "semantic_useful": False})
        rows.append(row)
    result = select_semantic_canary_target(rows)
    assert result["status"] == "NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET"


def test_unique_semantic_top_candidate_is_selectable():
    rich = _candidate("SH_E01_SC001_001"); rich.update({"canonical_eligibility": "PASS", "book": {"provenance_class": "PRODUCTION_PROJECT", "eligible": True}, "semantic_features": _semantic(subjects=["LIN_WAN", "LU_SHU"], dialogue="x"), "semantic_useful": True})
    fallback = _candidate("SH_E01_SC001_002"); fallback.update({"canonical_eligibility": "PASS", "book": {"provenance_class": "PRODUCTION_PROJECT", "eligible": True}, "semantic_features": _semantic(subjects=["LIN_WAN"], dialogue="", useful=False), "semantic_useful": False})
    result = select_semantic_canary_target([rich, fallback])
    assert result["status"] == "CANONICAL_CANARY_TARGET_SELECTED"
    assert result["selected"]["plan_shot_id"] == "SH_E01_SC001_001"


def test_true_semantic_tie_remains_ambiguous():
    rows = []
    for plan_shot_id in ("SH_E01_SC001_001", "SH_E01_SC001_002"):
        row = _candidate(plan_shot_id)
        row.update({"canonical_eligibility": "PASS", "book": {"provenance_class": "PRODUCTION_PROJECT", "eligible": True}, "semantic_features": _semantic(subjects=["LIN_WAN", "LU_SHU"], dialogue="x"), "semantic_useful": True})
        rows.append(row)
    result = select_semantic_canary_target(rows)
    assert result["status"] == "CANONICAL_CANARY_TARGET_AMBIGUOUS"
