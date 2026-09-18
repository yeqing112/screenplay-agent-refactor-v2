import copy

import pytest

from core.prompt_ir_authority import (
    COMPILER_POLICY,
    MEDIA_PENDING,
    PromptIRAuthorityError,
    compile_prompt_ir_from_handoff,
    prompt_ir_authority_contract,
    serialize_prompt_ir_to_adapter,
    prompt_ir_payload_hash,
)


def _handoff():
    return {
        "schema_version": "storyboard_prompt_handoff_v1",
        "materialization_set_id": 10,
        "storyboard_shot_id": 20,
        "plan_shot_id": "S01",
        "beat_id": "B01",
        "scene_id": "E01_SC01",
        "shot_plan_id": 30,
        "shot_plan_revision": 1,
        "shot_plan_authority_fingerprint": "shot-authority",
        "storyboard_projection_fingerprint": "projection",
        "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow"},
        "duration": 4,
        "action_beats": [{"start_seconds": 0, "end_seconds": 2, "description": "抬头"}],
        "entry_state": {"position": "门口"},
        "exit_state": {"position": "门内"},
        "continuity_contract": {"screen_direction": "left_to_right"},
        "shot_purpose": "reveal",
        "transition": "cut",
        "asset_identity_bindings": {"canonical_asset_identity": {"scene": "SCENE_1", "characters": ["C1"], "props": ["P1"]}, "media_asset_pending": ["C1", "P1"]},
    }


def test_contract_separates_storyboard_assets_policy_and_adapter():
    contract = prompt_ir_authority_contract()
    classes = {item["authority_class"] for item in contract["fields"]}
    assert "STORYBOARD_CONSTRAINT" in classes
    assert "VISUAL_ASSET_CONSTRAINT" in classes
    assert COMPILER_POLICY in classes
    assert contract["model_generation_ready_is_distinct"] is True


def test_compile_consumes_handoff_without_inventing_visual_facts():
    ir = compile_prompt_ir_from_handoff(_handoff())
    assert ir["qualification_state"] == "PROMPT_IR_QUALIFIED"
    assert ir["asset_reference_state"] == "ASSET_REFERENCE_PENDING"
    assert ir["model_generation_ready"] is False
    assert ir["assets"]["pending_requirements"]
    assert not ir["assets"]["bindings"][0]["visual_facts"]
    assert ir["authority_classes"]["pending"] == MEDIA_PENDING
    assert ir["serialization"]["status"] == "NOT_SERIALIZED"


def test_missing_authoritative_duration_or_camera_is_blocked_without_defaults():
    handoff = _handoff()
    handoff.pop("duration")
    with pytest.raises(PromptIRAuthorityError) as exc:
        compile_prompt_ir_from_handoff(handoff)
    assert exc.value.code == "STORYBOARD_HANDOFF_INCOMPLETE"

    handoff = _handoff()
    handoff["camera"] = {"shot_size": "MS", "movement": "static"}
    with pytest.raises(PromptIRAuthorityError) as exc:
        compile_prompt_ir_from_handoff(handoff)
    assert exc.value.code == "STORYBOARD_CAMERA_REQUIRED"


def test_policy_defaults_are_explicit_and_retention_is_not_story_fact():
    handoff = _handoff()
    handoff.pop("transition")
    ir = compile_prompt_ir_from_handoff(handoff)
    assert ir["compiler_policy"]["defaults"][0]["code"] == "COMPILER_POLICY_DEFAULT"
    assert ir["retention_policy"]["origin"] == "compiler_policy"
    assert ir["retention_policy"]["version"]


def test_locked_authoritative_reference_enables_model_readiness_and_dynamic_reference_text():
    authority = {"authority_fingerprint": "assets-v1", "bindings": [{"asset_type": "scene", "asset_id": "SCENE_1", "asset_name": "门厅", "authority_status": "PRODUCTION_AUTHORITATIVE", "locked_reference": True, "reference_token": "@门厅", "visual_facts": [{"fact_key": "lighting", "value": "冷光"}]}]}
    ir = compile_prompt_ir_from_handoff(_handoff(), asset_authority=authority)
    assert ir["model_generation_ready"] is False  # character/prop remain pending
    authority["bindings"] += [{"asset_type": "character", "asset_id": "C1", "asset_name": "林晚", "authority_status": "PRODUCTION_AUTHORITATIVE", "locked_reference": True, "reference_token": "@林晚"}, {"asset_type": "prop", "asset_id": "P1", "asset_name": "照片", "authority_status": "PRODUCTION_AUTHORITATIVE", "locked_reference": True, "reference_token": "@照片"}]
    ir = compile_prompt_ir_from_handoff(_handoff(), asset_authority=authority)
    assert ir["model_generation_ready"] is True
    output = serialize_prompt_ir_to_adapter(ir, "kling")
    assert output["status"] == "ready"
    assert "@林晚" in output["static_prompt"]


def test_advisory_raw_prompt_does_not_override_structured_authority():
    authority = {"bindings": [{"asset_type": "character", "asset_id": "C1", "authority_status": "IDENTITY_BOUND", "authority_prompt_raw": "男性黑长发红披风", "locked_reference": False}]}
    ir = compile_prompt_ir_from_handoff(_handoff(), asset_authority=authority)
    output = serialize_prompt_ir_to_adapter(ir, "veo")
    assert "黑长发" not in output.get("static_prompt", "")
    assert "红披风" not in output.get("static_prompt", "")
    assert "参考图" not in output.get("static_prompt", "")


@pytest.mark.parametrize("adapter", ["kling", "seedance", "veo", "flux", "sd"])
def test_adapters_are_deterministic_and_cannot_mutate_authority(adapter):
    authority = {"bindings": [{"asset_type": role, "asset_id": asset, "authority_status": "PRODUCTION_AUTHORITATIVE", "locked_reference": True, "reference_token": f"@{asset}"} for role, asset in (("scene", "SCENE_1"), ("character", "C1"), ("prop", "P1"))]}
    ir = compile_prompt_ir_from_handoff(_handoff(), asset_authority=authority)
    first = serialize_prompt_ir_to_adapter(ir, adapter)
    second = serialize_prompt_ir_to_adapter(ir, adapter)
    assert first == second
    assert first["authority_projection"]["camera"] == _handoff()["camera"]
    assert first["authority_projection"]["duration"] == 4
    assert first["authority_projection"]["action_beats"] == _handoff()["action_beats"]


def test_adapter_missing_required_input_is_diagnostic_only():
    ir = compile_prompt_ir_from_handoff(_handoff())
    broken = copy.deepcopy(ir)
    broken["storyboard"].pop("duration")
    output = serialize_prompt_ir_to_adapter(broken, "kling")
    assert output["status"] == "blocked"
    assert output["diagnostics"][0]["code"] == "ADAPTER_REQUIRED_INPUT_MISSING"
    assert output["provider_calls"] == 0


def test_derived_serialization_change_does_not_change_prompt_ir_authority_hash():
    ir = compile_prompt_ir_from_handoff(_handoff())
    original = ir["payload_hash"]
    changed = copy.deepcopy(ir)
    changed["serialization"]["static_prompt"] = "不同的序列化文本"
    assert prompt_ir_payload_hash(changed) == original
