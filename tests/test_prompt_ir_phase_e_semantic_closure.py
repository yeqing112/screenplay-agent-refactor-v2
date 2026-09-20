"""Phase E PromptIR semantic compilation and adapter closure tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.prompt_ir_phase_e import (
    PromptIRPhaseEError,
    adapt_prompt_ir_to_generation_payload,
    compare_prompt_ir_adapter_payload_semantics,
    compile_storyboard_snapshot_to_prompt_ir,
    validate_prompt_ir_against_snapshot,
)
from core.storyboard_handoff import project_shot_design_to_storyboard_handoff
from core.storyboard_materializer import build_storyboard_production_snapshot, materialize_storyboard_from_handoff, projection_payload


ART = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"


def _snapshots():
    plans = json.loads((ART / "episode_01_shot_plan_phase_c.json").read_text(encoding="utf-8"))["plans"]
    blocking = json.loads((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf-8"))["scenes"]
    output = []
    for number, (plan, block) in enumerate(zip(plans, blocking), start=1):
        source = copy.deepcopy(plan)
        source["scene_name"] = source["scene_id"]
        handoff = project_shot_design_to_storyboard_handoff(source, blocking=block, require_phase_c=True)
        projections = materialize_storyboard_from_handoff(handoff, production=True)

        class SetRow:
            id = number
            status = "MATERIALIZED"
            stale_status = "FRESH"
            set_payload_fingerprint = f"set-{number}"

            def __init__(self, scene_id):
                self.scene_id = scene_id

        class Row:
            def __init__(self, value):
                self.id = value["shot_id"]
                self.plan_shot_id = value["plan_shot_id"]
                self.projection_fingerprint = value["projection_fingerprint"]
                meta = dict(value.get("meta_info") or {})
                meta["projection_payload"] = projection_payload(value)
                self.meta_info = json.dumps(meta, ensure_ascii=False)

        output.append(
            build_storyboard_production_snapshot(
                materialization_set=SetRow(source["scene_id"]),
                rows=[Row(value) for value in projections],
                authority_envelope={"storyboard_handoff": {"handoff_fingerprint": handoff["handoff_fingerprint"]}},
            )
        )
    return output


def _compiled():
    snapshots = _snapshots()
    compiled = [ir for snapshot in snapshots for ir in compile_storyboard_snapshot_to_prompt_ir(snapshot)]
    return snapshots, compiled


def test_real_phase_e_pilot_compiles_15_shots_and_preserves_structured_semantics():
    snapshots, compiled = _compiled()
    assert [len(snapshot["ordered_shots"]) for snapshot in snapshots] == [8, 7]
    assert len(compiled) == 15
    assert len({item["plan_shot_id"] for item in compiled}) == 15
    for snapshot, irs in zip(snapshots, (compiled[:8], compiled[8:])):
        for ir in irs:
            source = next(row["visual_semantic_handoff"] for row in snapshot["ordered_shots"] if row["plan_shot_id"] == ir["plan_shot_id"])
            assert ir["semantic_refs"]["information_refs"] == source["information_refs"]
            assert ir["semantic_refs"]["reaction_contract_refs"] == source["reaction_contract_refs"]
            assert ir["semantic_refs"]["coverage_roles"] == source["coverage_roles"]
            assert ir["camera"]["movement_trigger"] == source["camera"]["movement_trigger"]
            assert ir["camera"]["movement_target"] == source["camera"]["movement_target"]
            assert ir["camera"]["movement_end_condition"] == source["camera"]["movement_end_condition"]
            assert ir["temporal"]["duration_mode"] == source["temporal_intent"]["duration_mode"]
            assert ir["information_visibility"] == source["information_visibility"]
            assert ir["continuity"]["axis_policy"] == source["continuity"]["axis_policy"]
            assert ir["spatial"]["blocking_state_refs"] == source["spatial"]["blocking_state_refs"]


@pytest.mark.parametrize(
    "path",
    [
        ("subjects",),
        ("props",),
        ("semantic_refs", "information_refs"),
        ("semantic_refs", "reaction_contract_refs"),
        ("camera", "movement"),
        ("camera", "movement_trigger"),
        ("information_visibility",),
        ("continuity", "axis_policy"),
    ],
)
def test_prompt_ir_semantic_tamper_fails_closed(path):
    snapshots, compiled = _compiled()
    target = copy.deepcopy(compiled[8])
    node = target
    for key in path[:-1]:
        node = node[key]
    key = path[-1]
    if isinstance(node[key], list):
        node[key] = list(node[key]) + ["UNAUTHORIZED"]
    elif isinstance(node[key], dict):
        node[key] = {**node[key], "UNAUTHORIZED": "UNAUTHORIZED"}
    else:
        node[key] = "UNAUTHORIZED"
    result = validate_prompt_ir_against_snapshot(snapshots[1], target)
    assert result["valid"] is False
    assert result["errors"]


def test_asset_identity_tamper_and_fingerprint_tamper_fail_closed():
    snapshots, compiled = _compiled()
    target = copy.deepcopy(compiled[0])
    target["asset_authority_bindings"]["identity_refs"].append("character:UNAUTHORIZED")
    assert not validate_prompt_ir_against_snapshot(snapshots[0], target)["valid"]
    target = copy.deepcopy(compiled[0])
    target["prompt_ir_payload_fingerprint"] = "tampered"
    assert any(item["code"] == "PROMPT_IR_FINGERPRINT_TAMPERED" for item in validate_prompt_ir_against_snapshot(snapshots[0], target)["errors"])


def test_compile_is_deterministic_and_adapter_has_no_semantic_loss_or_provider_call():
    snapshots, compiled = _compiled()
    again = compile_storyboard_snapshot_to_prompt_ir(snapshots[0])
    assert [item["payload_hash"] for item in compiled[:8]] == [item["payload_hash"] for item in again]
    payload = adapt_prompt_ir_to_generation_payload(compiled[0], model_profile={"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic"})
    assert payload["provider_calls"] == 0
    assert compare_prompt_ir_adapter_payload_semantics(compiled[0], payload)["empty"]
    legacy = copy.deepcopy(compiled[0])
    legacy["visual_prompt_final"] = "cinematic 8k unauthorized prose"
    assert adapt_prompt_ir_to_generation_payload(legacy, model_profile={"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic"})["prompt_ir_ref"] == payload["prompt_ir_ref"]


def test_adapter_hard_gates_unsupported_model_capability_and_required_asset():
    _snapshots_value, compiled = _compiled()
    with pytest.raises(PromptIRPhaseEError, match="MODEL_ADAPTER_NOT_REGISTERED"):
        adapt_prompt_ir_to_generation_payload(compiled[0], model_profile={"model_family": "UNKNOWN", "adapter_id": "unknown"})
    with pytest.raises(PromptIRPhaseEError, match="MODEL_ADAPTER_CAPABILITY_UNSUPPORTED"):
        adapt_prompt_ir_to_generation_payload(compiled[0], generation_policy={"required_asset_classes": ["CHARACTER"]}, model_profile={"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic", "capabilities": {"supports_reference_images": False}})
    with pytest.raises(PromptIRPhaseEError, match="PROMPT_IR_REQUIRED_ASSET_AUTHORITY_MISSING"):
        compile_storyboard_snapshot_to_prompt_ir(_snapshots()[0], generation_policy={"required_asset_classes": ["CHARACTER"]})


def test_stale_required_asset_authority_cannot_compile():
    snapshots, compiled = _compiled()
    identity = next(item for item in compiled[0]["asset_authority_bindings"]["identity_refs"] if item.startswith("character:"))
    with pytest.raises(PromptIRPhaseEError, match="PROMPT_IR_ASSET_AUTHORITY_STALE"):
        compile_storyboard_snapshot_to_prompt_ir(
            snapshots[0],
            asset_authority={"bindings": [{"asset_type": "character", "canonical_asset_id": identity.split(":", 1)[1], "stale_status": "STALE"}]},
        )
