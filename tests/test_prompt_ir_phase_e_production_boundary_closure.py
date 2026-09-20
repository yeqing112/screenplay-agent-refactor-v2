"""Production boundary contracts for Phase E.

These tests intentionally exercise the provider-free compiler and adapter
contracts without creating media or calling a provider.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.prompt_ir_authority_api import PhaseECompileRequest, compile_prompt_ir
from core.prompt_ir_phase_e import (
    PromptIRPhaseEError,
    adapt_prompt_ir_to_generation_payload,
    build_generation_policy,
    build_model_profile,
    compile_storyboard_snapshot_to_prompt_ir,
)
from tests.test_prompt_ir_phase_e_semantic_closure import _snapshots


def _snapshot_and_prop_authority(*, reference=None):
    snapshot = _snapshots()[0]
    prop_ids = sorted({str(prop) for row in snapshot["ordered_shots"] for prop in row.get("visual_semantic_handoff", {}).get("props", [])})
    authority = {"bindings": []}
    for prop_id in prop_ids:
        authority["bindings"].append({
                "asset_type": "prop",
                "canonical_asset_id": prop_id,
                "asset_key": f"book:1:prop:{prop_id}",
                "asset_version_id": 7,
                "asset_version_fingerprint": "asset-fp",
                "payload_hash": "asset-fp",
                "authority_fingerprint": "asset-fp",
                "authority_status": "SPEC_APPROVED",
                "stale_status": "FRESH",
                **({"reference_authority": reference} if reference is not None else {}),
            })
    return snapshot, authority


def test_production_policy_is_explicit_and_has_no_implicit_text_to_image():
    with pytest.raises(PromptIRPhaseEError, match="GENERATION_POLICY_REQUIRED"):
        build_generation_policy({}, allow_default=False)
    policy = build_generation_policy({"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, allow_default=False)
    assert policy["source"] == "explicit_request"
    assert policy["mode"] == "TEXT_TO_IMAGE"


def test_phase_e_request_cannot_carry_production_asset_authority():
    fields = getattr(PhaseECompileRequest, "model_fields", getattr(PhaseECompileRequest, "__fields__", {}))
    assert "asset_authority" not in fields


def test_required_reference_needs_concrete_locked_fresh_authority():
    snapshot, authority = _snapshot_and_prop_authority()
    with pytest.raises(PromptIRPhaseEError, match="PROMPT_IR_REQUIRED_REFERENCE_AUTHORITY_MISSING"):
        compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["PROP_REFERENCE"]}, asset_authority=authority, allow_default_policy=False)


def test_reference_authority_is_bound_to_current_asset_version():
    snapshot, authority = _snapshot_and_prop_authority(reference={"status": "LOCKED", "stale_status": "FRESH", "authority_fingerprint": "ref-fp", "asset_version_fingerprint": "asset-fp", "reference_token": "ref:TICKET"})
    compiled = compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["PROP_REFERENCE"]}, asset_authority=authority, allow_default_policy=False)
    binding = next(item for item in compiled[0]["asset_authority_bindings"]["resolved"] if item["identity_ref"] == "prop:TICKET")
    assert binding["reference_authority_fingerprint"] == "ref-fp"
    assert binding["reference_asset_version_fingerprint"] == "asset-fp"


def test_stale_reference_authority_fails_closed():
    snapshot, authority = _snapshot_and_prop_authority(reference={"status": "LOCKED", "stale_status": "STALE", "authority_fingerprint": "ref-fp", "asset_version_fingerprint": "asset-fp"})
    with pytest.raises(PromptIRPhaseEError, match="VISUAL_REFERENCE_AUTHORITY_STALE"):
        compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["PROP_REFERENCE"]}, asset_authority=authority, allow_default_policy=False)


def test_asset_requirement_does_not_require_reference_capability():
    snapshot, authority = _snapshot_and_prop_authority()
    compiled = compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy={"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": ["PROP"]}, asset_authority=authority, allow_default_policy=False)[0]
    profile = build_model_profile({"adapter_id": "image_generic", "model_family": "GENERIC_IMAGE", "capabilities": {}})
    payload = adapt_prompt_ir_to_generation_payload(compiled, generation_policy=compiled["generation_policy"], model_profile=profile)
    assert "MODEL_ADAPTER_CAPABILITY_UNSUPPORTED" not in {item for item in payload["readiness"]["reasons"]}


def test_legacy_single_shot_compile_is_disabled_before_any_write():
    with pytest.raises(HTTPException) as error:
        compile_prompt_ir(1, 1, 1, object())
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PROMPT_IR_LEGACY_PRODUCTION_DISABLED"
