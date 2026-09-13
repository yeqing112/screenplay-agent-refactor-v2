import pytest

from core.director_patch_recovery_rules import (
    RecoveryRule,
    RecoveryRuleError,
    apply_recovery_rule,
    clear_recovery_rules,
    list_recovery_rules,
    register_recovery_rule,
)
from core.director_rejection_trace import (
    capture_raw_patch_trace,
    classify_rejection_trace,
    finalize_rejection_trace,
)
from core.director_creative_contract import build_director_creative_contract
from core.director_quality_v22 import process_patch_pipeline
from core.scene_directing_strategy import build_scene_directing_strategy
from core.shot_plan import build_shot_plan


ALLOWED = ["/shots/*/camera/shot_size", "/shots/*/camera/angle"]


def test_raw_patch_is_captured_before_normalization_and_keeps_fingerprint():
    raw = {"plan_shot_id": "S03", "path": "/shots/S03/camera/shot-size", "value": " close-up "}
    trace = capture_raw_patch_trace(raw, scene_id="E01_SC01", episode=1, provider_patch_index=3, allowed_patch_paths=ALLOWED)
    assert trace["raw_patch"] == raw
    assert trace["raw_path"] == "/shots/S03/camera/shot-size"
    assert trace["raw_plan_shot_id"] == "S03"
    assert trace["canonical_path"] == "camera.shot_size"
    assert trace["allowed_path_match"] is True
    assert trace["path_resolution_rule"] == "slash_shot_selector"
    assert trace["raw_patch_fingerprint"]


def test_numeric_selector_preserves_raw_selector_and_resolved_identity():
    trace = capture_raw_patch_trace(
        {"path": "shots.1.camera.angle", "value": "low_angle"},
        scene_id="E", episode=1, provider_patch_index=1,
        known_plan_shot_ids=["S01", "S02"], allowed_patch_paths=ALLOWED,
    )
    assert trace["raw_selector"] == "1"
    assert trace["parsed"] == {"plan_shot_id": "S02", "path": "camera.angle"}
    assert trace["canonical"]["plan_shot_id"] == "S02"
    assert trace["path_resolution_rule"] == "numeric_index"


def test_forbidden_path_keeps_parse_candidate_but_marks_allow_match_false():
    trace = capture_raw_patch_trace(
        {"plan_shot_id": "S01", "changes": {"camera.zoom": "slow"}},
        scene_id="E", episode=1, provider_patch_index=0,
        known_plan_shot_ids=["S01"], allowed_patch_paths=ALLOWED,
    )
    assert trace["raw_path"] == "camera.zoom"
    assert trace["canonical_path"] == "camera.zoom"
    assert trace["allowed_path_match"] is False
    assert trace["resolution_code"] == "DIRECTOR_PATCH_PATH_FORBIDDEN"


def test_classification_is_evidence_driven_and_fact_override_cannot_recover():
    trace = capture_raw_patch_trace(
        {"plan_shot_id": "S01", "changes": {"event": "rewrite"}},
        scene_id="E", episode=1, allowed_patch_paths=ALLOWED,
    )
    assert classify_rejection_trace(trace, issue_code="DIRECTOR_FACT_OVERRIDE", rejection_stage="CONTRACT_VALIDATION") == "FACT_OVERRIDE"
    completed = finalize_rejection_trace(
        trace, issue_code="DIRECTOR_FACT_OVERRIDE", rejection_stage="CONTRACT_VALIDATION",
        final_action="FALLBACK",
    )
    assert completed["fallback_classification"] == "FACT_OVERRIDE"
    assert completed["rejection_stage"] == "CONTRACT_VALIDATION"


def test_alias_and_envelope_classification():
    alias = capture_raw_patch_trace(
        {"plan_shot_id": "S01", "changes": {"camera.cameraAngle": "low_angle"}},
        scene_id="E", episode=1, allowed_patch_paths=ALLOWED,
    )
    assert alias["allowed_path_match"] is True
    assert alias["path_alias_hit"] is True
    assert classify_rejection_trace(alias, issue_code="DIRECTOR_PATCH_PATH_FORBIDDEN", rejection_stage="ALLOWED_PATH_CHECK") == "SAFE_ALIAS"
    envelope = capture_raw_patch_trace(
        {"plan_shot_id": "S01", "path": "/shots/S01/camera/shot_size", "value": "CU"},
        scene_id="E", episode=1, allowed_patch_paths=ALLOWED,
    )
    assert classify_rejection_trace(envelope, issue_code="DIRECTOR_PATCH_PATH_FORBIDDEN", rejection_stage="ALLOWED_PATH_CHECK") == "SAFE_ENVELOPE_VARIANT"


def test_rejection_stage_taxonomy_rejects_unknown_stage():
    trace = capture_raw_patch_trace({"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}})
    with pytest.raises(ValueError):
        finalize_rejection_trace(trace, issue_code="INVALID_PATCH_VALUE", rejection_stage="NOT_A_STAGE")


def test_recovery_registry_requires_evidence_and_explicit_handler():
    clear_recovery_rules()
    with pytest.raises(RecoveryRuleError):
        register_recovery_rule({"rule_id": "bad", "classification": "SAFE_ALIAS", "evidence_count": 0, "example_raw_path": "x", "canonical_output": "y", "why_safe": "z", "test_case": "t"})
    rule = RecoveryRule("RULE_TEST", "SAFE_ALIAS", 1, "cameraShotSize", "camera.shot_size", "explicit alias", "test_alias")
    register_recovery_rule(rule, handler=lambda trace: {"accepted": True})
    assert list_recovery_rules()[0]["rule_id"] == "RULE_TEST"
    result = apply_recovery_rule("RULE_TEST", {"trace_id": "t"})
    assert result["recovery_rule_id"] == "RULE_TEST"
    clear_recovery_rules()


def test_recovery_registry_does_not_allow_unregistered_or_duplicate_rules():
    clear_recovery_rules()


def test_pipeline_propagates_complete_trace_to_fallback_without_side_effects():
    treatment = {"scene_id": "E", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "event": "进入"}]}
    blocking = {"scene_id": "E", "scene_name": "门厅", "participants": [{"character_id": "C1", "name": "林晚"}]}
    plan = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    result = process_patch_pipeline(
        structural_shot_plan=plan,
        contract=contract,
        strategy=strategy,
        treatment=treatment,
        blocking=blocking,
        scene_id="E",
        episode=1,
        raw_output={
            "schema_version": "director_creative_patch_v1",
            "patches": [
                {"plan_shot_id": "S01", "changes": {"event": "改写事实"}},
                {"plan_shot_id": "S01", "changes": {"camera.zoom": "slow"}},
            ],
            "auxiliary_shot_proposals": [],
        },
    )
    traces = result["rejection_traces"]
    assert len(traces) == len(result["fallbacks"])
    assert all(item["trace_id"] for item in result["fallbacks"])
    assert all(item["scene_id"] == "E" for item in result["fallbacks"])
    assert all(item["raw_patch"] for item in traces)
    assert all(item["rejection_stage"] in {"PATH_RESOLUTION", "CONTRACT_VALIDATION", "FINAL_FALLBACK"} for item in traces)
    assert all(item["final_action"] == "FALLBACK" for item in traces)
    rule = RecoveryRule("RULE_TEST", "SAFE_ENVELOPE_VARIANT", 1, "x", "y", "z", "t")
    register_recovery_rule(rule, handler=lambda trace: trace)
    with pytest.raises(RecoveryRuleError):
        register_recovery_rule(rule, handler=lambda trace: trace)
    with pytest.raises(RecoveryRuleError):
        apply_recovery_rule("MISSING", {})
    clear_recovery_rules()
