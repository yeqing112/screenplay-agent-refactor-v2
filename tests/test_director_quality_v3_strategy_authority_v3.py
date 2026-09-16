from __future__ import annotations

import json

import pytest

from core.director_authority import authority_completeness_gate, provider_readiness_gate
from core.director_strategy_provider_spec import (
    PRESERVE_INTENT_REQUIRED_FIELDS,
    PRESERVE_KINDS,
    STRATEGY_REQUIRED_FIELDS,
    VISIBILITY_REQUIREMENTS,
    build_strategy_provider_contract,
    canonicalize_strategy_v3,
    provider_validator_parity,
    strategy_provider_spec,
    validate_strategy_v3_shape,
)
from core.strategy_preserve_authority import compile_preserve_intents_to_authority


def _scene():
    return {
        "scene_id": "s1",
        "beats": [{"beat_id": "1"}, {"beat_id": "2"}],
        "participants": [{"character_id": "19"}],
        "props": [{"prop_id": "bag"}],
        "locations": [{"location_id": "room"}],
    }


def _contract():
    return build_strategy_provider_contract({
        "scene": _scene(),
        "strategy_contract": {
            "beat_ids": ["1", "2"],
            "character_ids": ["19"],
            "prop_ids": ["bag"],
            "location_ids": ["room"],
        },
    })


def _strategy(**intent):
    preserve = {
        "kind": "CHARACTER_ACTION",
        "description": "touches the bag",
        "anchor_refs": ["beat:1"],
        "subject_refs": ["character:19"],
        "object_refs": ["prop:bag"],
        "visibility_requirement": "EXPLICIT",
    }
    preserve.update(intent)
    return {
        "schema_version": "director_scene_strategy_ir_v3",
        "dramatic_objective": "pressure",
        "scene_question": "who moves",
        "strategy_summary": "object to witness",
        "visual_thesis": "the bag is evidence",
        "scene_phases": [{"phase_id": "P01", "beat_ids": ["1", "2"]}],
        "spatial_expression": "door to table",
        "prop_visual_strategy": "hold bag in frame",
        "creative_risks": [],
        "must_avoid": [],
        "preserve_intents": [preserve],
    }


def test_strategy_v3_requires_preserve_intents_and_rejects_legacy_only():
    contract = _contract()
    result = validate_strategy_v3_shape({"schema_version": "director_scene_strategy_ir_v3", "must_preserve": ["legacy"]}, contract=contract)
    assert result["status"] == "FAIL"
    assert any(error["path"] == "preserve_intents" for error in result["errors"])


def test_strategy_v3_legacy_projection_requires_explicit_human_marker():
    contract = _contract()
    value = _strategy()
    value["must_preserve"] = ["display only"]
    assert validate_strategy_v3_shape(value, contract=contract)["status"] == "FAIL"
    value["must_preserve_projection"] = "human_readable_projection_only"
    assert validate_strategy_v3_shape(value, contract=contract)["status"] == "PASS"


def test_strategy_spec_and_validator_share_required_fields_enums_and_fingerprint():
    spec = strategy_provider_spec()
    parity = provider_validator_parity()
    assert parity["status"] == "PASS"
    assert spec["required_fields"] == list(STRATEGY_REQUIRED_FIELDS)
    assert spec["preserve_intent_required_fields"] == list(PRESERVE_INTENT_REQUIRED_FIELDS)
    assert spec["preserve_kind_enum"] == list(PRESERVE_KINDS)
    assert spec["visibility_requirement_enum"] == list(VISIBILITY_REQUIREMENTS)
    assert parity["fingerprint_parity"] is True


def test_v3_prompt_uses_ssot_and_allowed_refs(monkeypatch):
    from scripts import run_director_quality_v3_fresh_integration_pilot as pilot

    row = {"scene_id": "s1", "book_id": 1, "scene": _scene(), "fact_snapshot": {}, "director_treatment": {}, "scene_blocking": {}, "source_evidence": {}}
    prompt = pilot._strategy_request(row, _contract(), {"model_name": "mimo-v2.5"})["request"]
    assert "preserve_intents" in prompt["system_prompt"]
    assert "allowed_source_refs" in prompt["user_prompt"]
    assert "must_preserve string[]" not in prompt["system_prompt"]

    def fail_v2(*args, **kwargs):
        raise AssertionError("Fresh path must not call V2 prompt builder")

    monkeypatch.setattr("core.director_strategy_prompt.build_scene_strategy_ir_v2_prompt", fail_v2)
    pilot._strategy_request(row, _contract(), {"model_name": "mimo-v2.5"})


def test_v3_prompt_exposes_provider_visible_semantic_event_refs():
    from scripts import run_director_quality_v3_fresh_integration_pilot as pilot

    scene = _scene()
    scene["beats"][0]["action"] = "touches the bag"
    row = {"scene_id": "s1", "book_id": 1, "scene": scene, "fact_snapshot": {}, "director_treatment": {}, "scene_blocking": {}, "source_evidence": {}}
    request = pilot._strategy_request(row, _contract(), {"model_name": "mimo-v2.5"})["request"]
    assert request["provider_contract"]["allowed_event_refs"]
    assert "allowed_event_refs" in request["user_prompt"]


def test_preserve_compiler_assigns_deterministic_ids_and_maps_multiple_anchors():
    result = compile_preserve_intents_to_authority(
        [{**_strategy()["preserve_intents"][0], "anchor_refs": ["beat:1", "beat:2"]}],
        allowed_source_refs=["beat:1", "beat:2"],
        allowed_character_refs=["character:19"],
        allowed_prop_refs=["prop:bag"],
        scene_id="s1",
    )
    assert result["status"] == "PASS"
    assert result["constraints"][0]["constraint_id"] == "MP01"
    assert result["constraints"][0]["beat_refs"] == ["beat:1", "beat:2"]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("anchor_refs", ["beat:UNKNOWN"], "PRESERVE_ANCHOR_INVALID"),
        ("anchor_refs", [], "PRESERVE_ANCHOR_MISSING"),
        ("subject_refs", ["character:999"], "PRESERVE_SUBJECT_INVALID"),
        ("object_refs", ["prop:missing"], "PRESERVE_OBJECT_INVALID"),
    ],
)
def test_preserve_compiler_rejects_invalid_refs(field, value, code):
    result = compile_preserve_intents_to_authority(
        [{**_strategy()["preserve_intents"][0], field: value}],
        allowed_source_refs=["beat:1"],
        allowed_character_refs=["character:19"],
        allowed_prop_refs=["prop:bag"],
        scene_id="s1",
    )
    assert result["status"] == "FAIL"
    assert code in {error["code"] for error in result["errors"]}


def test_description_never_substitutes_for_anchor():
    intent = {**_strategy()["preserve_intents"][0], "description": "beat:1 is obvious", "anchor_refs": []}
    result = compile_preserve_intents_to_authority(intent and [intent], allowed_source_refs=["beat:1"], scene_id="s1")
    assert result["status"] == "FAIL"
    assert any(error["code"] == "PRESERVE_ANCHOR_MISSING" for error in result["errors"])


def test_fresh_authority_passes_only_before_program_fingerprint_is_added():
    strategy = _strategy()
    authority = authority_completeness_gate(strategy=strategy, scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, fresh_path=True, provider_contract=_contract())
    assert authority["status"] == "PASS"
    canonical = canonicalize_strategy_v3(strategy)
    legacy = authority_completeness_gate(strategy=canonical, scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, fresh_path=True, provider_contract=_contract())
    assert legacy["status"] == "AUTHORITY_COMPLETENESS_FAILED"


def test_legacy_string_only_fresh_path_fails_closed_and_invalid_anchor_blocks_readiness():
    contract = _contract()
    legacy = authority_completeness_gate(strategy={"must_preserve": ["touches bag"]}, scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, fresh_path=True, provider_contract=contract)
    assert legacy["provider_callable"] is False
    invalid = authority_completeness_gate(strategy=_strategy(anchor_refs=["beat:UNKNOWN"]), scene=_scene(), identity_projection={"records": [{"character_id": "19"}]}, fresh_path=True, provider_contract=contract)
    assert invalid["provider_callable"] is False


def test_closure_artifacts_and_pointer_are_provider_free_and_retired():
    from scripts.run_director_quality_v3_fresh_integration_pilot import RETIRED_SCENES
    from scripts.run_director_quality_v3_authority_contract_ssot import main as closure_main

    assert len(RETIRED_SCENES) >= 6
    assert closure_main() == 0
    pointer = json.load(open("artifacts/director-quality-v3-current-stage-authority.json", encoding="utf-8"))
    ssot = pointer["strategy_authority_contract_ssot"]
    assert ssot["status"] == "CLOSED"
    assert ssot["legacy_fallback"] is False
    assert ssot["fresh_path"] == "V3_ONLY"
    assert pointer["fresh_integration_pilot"]["experiment_validity"] == "INVALID"
    assert pointer["fresh_integration_pilot"]["primary_root_cause"] == "STRATEGY_PROVIDER_AUTHORITY_CONTRACT_MISMATCH"
    assert pointer["shot_architecture"]["generation_architecture_redesign"]["spine_topology_canary"]["no_further_spine_topology_recanary"] is True
