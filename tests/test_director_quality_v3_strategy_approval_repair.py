import copy
from scripts.run_director_quality_v3_strategy_approval_repair import (
    _base_rows, _editable, provider_free_preflight, scope_diff,
    semantic_identity_audit,
)


def test_scope_validator_accepts_only_scene_one_editable_paths():
    row = _base_rows()[0]
    revised = copy.deepcopy(row["base"])
    revised["scene_phases"][1]["information"]["audience_suspicions"][0]["support_refs"] = ["beat:6"]
    result = scope_diff(row["base"], revised, _editable(row["scene_id"]))
    assert result["scope_status"] == "PASS"
    revised["scene_question"] = "非法改动"
    assert scope_diff(row["base"], revised, _editable(row["scene_id"]))["scope_status"] == "FAIL"


def test_semantic_identity_audit_flags_cross_character_text():
    row = _base_rows()[1]
    strategy = copy.deepcopy(row["base"])
    row["inputs"]["character_canonical"]["records"][0]["name"] = "Alice"
    row["inputs"]["character_canonical"]["records"][1]["name"] = "Bob"
    strategy["scene_phases"][0]["performance"][0]["objective"] = "Bob applies pressure"
    result = semantic_identity_audit(strategy, row["inputs"])
    assert result["status"] == "FAIL"
    assert result["findings"][0]["code"] == "CHARACTER_SEMANTIC_IDENTITY_MISMATCH"


def test_provider_free_preflight_has_zero_calls_and_no_downstream_effects():
    rows = _base_rows()
    result = provider_free_preflight(rows, {"model_name": "mimo-v2.5", "id": "test"})
    assert result["all_checks_pass"] is True
    assert result["real_mimo_calls"] == 0
    assert result["shotplan"] == result["storyboard"] == result["media"] == 0
