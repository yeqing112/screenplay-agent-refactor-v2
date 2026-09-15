from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.director_scene_strategy import SCENE_STRATEGY_SCHEMA_VERSION
from core.director_strategy_prompt import PHASE1_PROMPT_PROTOCOL_VERSION, build_scene_strategy_prompt
from core.director_strategy_quality import compare_strategies, diagnose_scene_strategy
from scripts.run_director_quality_v3_phase1 import (
    CONFIRMATION_TOKEN,
    GOLDEN_PATH,
    REQUIRED_SCENES,
    _load_frozen_records,
    build_authoritative_inputs,
    provider_contract,
    provider_free_preflight,
    provenance_preflight,
    resolved_manifest,
    typed_fingerprint,
    validate_real_authorization,
)


def _profile():
    return {
        "id": "test-mimo",
        "provider": "openai-compatible",
        "capability": "llm",
        "model_name": "mimo-v2.5",
        "base_url": "https://example.invalid/v1",
        "api_key": "secret",
        "enabled": True,
        "default_params": {"thinking": {"type": "disabled"}},
    }


def test_typed_fingerprint_distinguishes_domain_objects():
    payload = {"scene_id": "s1", "status": "approved"}
    assert typed_fingerprint("DirectorTreatment", payload) != typed_fingerprint("SceneBlocking", payload)


def test_frozen_cohort_is_exact_and_independently_projected():
    records = _load_frozen_records()
    assert tuple(_load_frozen_records()[i]["metadata"]["scene_id"] for i in range(3)) == REQUIRED_SCENES
    inputs = build_authoritative_inputs(records[0])
    assert inputs["director_treatment"] is not inputs["scene_blocking"]
    assert inputs["scene"]["beats"] is not inputs["director_treatment"]["beat_map"]


def test_provenance_resolves_historical_collision_without_wiring_error():
    records = _load_frozen_records()
    result = provenance_preflight(records, profile=_profile())
    assert result["status"] == "PASS"
    assert result["diagnosis"] == "historical_manifest_projection_collision_only"
    assert result["wiring_error"] is False
    assert result["historical_manifest_collisions"] == 3
    assert result["typed_fingerprints_distinct"] is True


def test_resolved_manifest_contains_typed_authority_and_no_secret():
    records = _load_frozen_records()
    manifest = resolved_manifest(records, _profile())
    assert manifest["scene_count"] == 3
    for row in manifest["scenes"]:
        assert row["director_treatment_typed_fingerprint"] != row["scene_blocking_typed_fingerprint"]
        assert "api_key" not in json.dumps(row)


def test_prompt_is_stable_and_excludes_baseline_shot_decisions():
    records = _load_frozen_records()
    profile = _profile()
    prompts = [build_scene_strategy_prompt(evidence=build_authoritative_inputs(row), model_profile=profile) for row in records]
    assert {row["protocol_version"] for row in prompts} == {PHASE1_PROMPT_PROTOCOL_VERSION}
    assert len({row["stable_prefix_fingerprint"] for row in prompts}) == 1
    assert all('"shots":' not in row["user_prompt"] for row in prompts)
    assert all('"plan_shot_id":' not in row["user_prompt"] for row in prompts)
    assert all("DQ weights" not in row["user_prompt"] or "Do not use DQ weights" in row["system_prompt"] for row in prompts)


def test_provider_contract_enforces_attempt_and_parser_budgets():
    contract = provider_contract(_profile())
    assert contract["json_parser_retry_count"] == 0
    assert contract["semantic_attempt_budget_per_scene"] == 2
    assert contract["max_provider_http_requests"] == 6
    assert contract["attempt_types"] == ["CREATIVE_GENERATION", "FORMAT_REPAIR"]


def test_provider_free_preflight_passes_without_provider_call():
    records = _load_frozen_records()
    result = provider_free_preflight(records, _profile())
    assert result["status"] == "PASS"
    assert result["all_checks_pass"] is True
    assert result["real_mimo_calls"] == 0
    assert result["shotplan"] == 0


def test_real_authorization_is_fail_closed_and_mimo_only():
    profile = _profile()
    with pytest.raises(PermissionError):
        validate_real_authorization(execute_real=False, confirmation_token=CONFIRMATION_TOKEN, profile=profile)
    with pytest.raises(PermissionError):
        validate_real_authorization(execute_real=True, confirmation_token="wrong", profile=profile)
    assert validate_real_authorization(execute_real=True, confirmation_token=CONFIRMATION_TOKEN, profile=profile)["model_name"] == "mimo-v2.5"


def test_generic_strategy_diagnostic_requires_evidence_binding():
    strategy = {"dramatic_objective": "增强情绪", "camera_principles": ["使用不同景别"], "scene_id": "s1"}
    findings = diagnose_scene_strategy(strategy=strategy)["findings"]
    assert any(item["issue_code"] == "GENERIC_DIRECTOR_STRATEGY" for item in findings)


def test_cross_scene_exact_template_is_hard_failure():
    a = {"scene_id": "a", "strategy_fingerprint": "same", "dramatic_objective": "x", "scene_question": "x", "visual_grammar": "x", "camera_principles": ["x"], "edit_arc": {"x": 1}, "must_avoid": ["x"], "strategy_summary": "x"}
    b = {**a, "scene_id": "b"}
    assert compare_strategies([a, b])["hard_failure"] is True


def test_schema_authority_is_foundation_v1():
    assert SCENE_STRATEGY_SCHEMA_VERSION == "director_scene_strategy_v1"
    assert GOLDEN_PATH.exists()

