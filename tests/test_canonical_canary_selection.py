from __future__ import annotations

from types import SimpleNamespace

from core.canonical_canary_selection import _asset_gate, _authority_ok, rank_canary_candidates, select_canary_target


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
