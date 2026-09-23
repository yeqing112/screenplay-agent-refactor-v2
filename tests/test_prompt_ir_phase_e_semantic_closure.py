"""Phase E PromptIR semantic compilation and adapter closure tests."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.prompt_ir_phase_e import (
    PromptIRPhaseEError,
    adapt_prompt_ir_to_generation_payload,
    compare_prompt_ir_adapter_payload_semantics,
    compile_storyboard_snapshot_to_prompt_ir,
    validate_prompt_ir_against_snapshot,
    fingerprint,
    resolve_current_authoritative_prompt_ir,
)
from core.storyboard_handoff import project_shot_design_to_storyboard_handoff
from core.storyboard_materializer import build_storyboard_production_snapshot, materialize_storyboard_from_handoff, projection_payload
from models import Base, PromptIRAuthority, PromptIRPointer, PromptIRVersion, StoryboardShot
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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


def _persist_v2_for_resolver(db, snapshot, ir):
    now = datetime.now()
    shot = StoryboardShot(book_id=77, episode=1, scene_name=snapshot["scene_id"], scene_id=snapshot["scene_id"], plan_shot_id=ir["plan_shot_id"], materialization_set_id=1, source_shot_plan_id=1, source_shot_plan_revision=1, source_shot_plan_authority_fingerprint="", projection_fingerprint=ir["source_authority"]["storyboard_projection_fingerprint"], materialization_status="MATERIALIZED", shot_id=int(ir["storyboard_shot_id"]), created_at=now, updated_at=now)
    db.add(shot)
    db.flush()
    ir = copy.deepcopy(ir)
    ir["storyboard_shot_id"] = shot.id
    # Keep the current snapshot row identity aligned with the persisted shot.
    ir["source_authority"]["storyboard_materialization_set_id"] = 1
    payload_hash = fingerprint({key: value for key, value in ir.items() if key not in {"prompt_ir_payload_fingerprint", "payload_hash"}})
    ir["prompt_ir_payload_fingerprint"] = payload_hash
    ir["payload_hash"] = payload_hash
    envelope = {"schema_version": "prompt_ir_authority_envelope_v2", "source_authority": ir["source_authority"], "compiler_provenance": ir["compiler_provenance"], "generation_policy": ir["generation_policy"], "asset_authority_bindings": ir["asset_authority_bindings"], "prompt_ir_payload_hash": payload_hash, "qualification_state": "PROMPT_IR_QUALIFIED", "model_generation_ready": False, "stale_status": "FRESH"}
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    version = PromptIRVersion(book_id=77, episode=1, scene_id=snapshot["scene_id"], storyboard_shot_id=shot.id, materialization_set_id=1, plan_shot_id=ir["plan_shot_id"], schema_version="prompt_ir_v2", payload_json=json.dumps(ir, ensure_ascii=False, sort_keys=True), payload_hash=payload_hash, compiler_version=ir["compiler_provenance"]["compiler_version"], compiler_policy_version=ir["compiler_provenance"]["compiler_policy_version"], retention_policy_version="generation_policy_v1", authority_envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="ASSET_REFERENCE_PENDING", model_generation_ready="false", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    db.add(version)
    db.flush()
    authority = PromptIRAuthority(prompt_ir_version_id=version.id, book_id=77, episode=1, storyboard_shot_id=shot.id, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    pointer = PromptIRPointer(book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="IMAGE", prompt_ir_version_id=version.id, payload_hash=payload_hash, qualification_state="PROMPT_IR_QUALIFIED", created_at=now, updated_at=now)
    db.add_all([authority, pointer])
    db.commit()
    return shot, version, authority, pointer


def test_current_resolver_revalidates_pointer_and_authority_envelope(monkeypatch):
    snapshots = _snapshots()
    ir = compile_storyboard_snapshot_to_prompt_ir(snapshots[0])[0]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    shot, version, authority, pointer = _persist_v2_for_resolver(db, snapshots[0], ir)
    source_row = snapshots[0]["ordered_shots"][0]
    current_row = SimpleNamespace(id=shot.id, plan_shot_id=shot.plan_shot_id, projection_fingerprint=source_row["projection_fingerprint"], meta_info=json.dumps({"visual_semantic_handoff": source_row["visual_semantic_handoff"], "projection_payload": source_row["projection_payload"], "prompt_compiler_handoff": source_row["prompt_compiler_handoff"]}, ensure_ascii=False))
    current_set = SimpleNamespace(id=1, scene_id=snapshots[0]["scene_id"], set_payload_fingerprint="set-1", status="MATERIALIZED", stale_status="FRESH")
    monkeypatch.setattr("core.storyboard_materializer.resolve_current_authoritative_materialization", lambda *args, **kwargs: (current_set, [current_row], snapshots[0]["authority_envelope"]))
    monkeypatch.setattr("core.storyboard_materializer.build_storyboard_production_snapshot", lambda **kwargs: snapshots[0])
    # This unit fixture intentionally persists only the PromptIR pointer chain;
    # the dedicated historical-lineage closure suite exercises the full
    # MaterializationSet/StoryboardShot authority rows.
    monkeypatch.setattr("core.prompt_ir_phase_e.validate_prompt_ir_historical_integrity", lambda *args, **kwargs: {"integrity_valid": True})
    resolved = resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="IMAGE")
    assert resolved["payload"]["qualification_state"] == "PROMPT_IR_QUALIFIED"
    pointer.payload_hash = "tampered"
    db.commit()
    with pytest.raises(Exception) as exc_info:
        resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="IMAGE")
    assert getattr(exc_info.value, "detail", {}).get("code") == "PROMPT_IR_POINTER_TAMPERED"


def test_materialization_and_v2_asset_changes_stale_prompt_authority():
    from core.storyboard_materializer import mark_materialization_set_stale
    from core.visual_asset_authority import propagate_visual_asset_staleness

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    now = datetime.now()
    payload = {"schema_version": "prompt_ir_v2", "asset_authority_bindings": {"resolved": [{"asset_authority_ref": "book:character:LIN_WAN"}]}}
    version = PromptIRVersion(book_id=78, episode=1, scene_id="S", storyboard_shot_id=1, materialization_set_id=9, plan_shot_id="P", schema_version="prompt_ir_v2", payload_json=json.dumps(payload), payload_hash="h", compiler_version="c", compiler_policy_version="p", retention_policy_version="g", authority_envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="ASSET_REFERENCE_PENDING", model_generation_ready="false", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    db.add(version); db.flush()
    authority = PromptIRAuthority(prompt_ir_version_id=version.id, book_id=78, episode=1, storyboard_shot_id=1, envelope_fingerprint="e", envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    db.add(authority); db.commit()
    set_row = SimpleNamespace(id=9, status="MATERIALIZED", stale_status="FRESH", stale_reasons="[]", updated_at=now)
    mark_materialization_set_stale(db, set_row, ["STORYBOARD_POINTER_CHANGED"])
    db.commit()
    assert version.stale_status == "STALE" and authority.stale_status == "STALE"
    version.stale_status = authority.stale_status = "FRESH"
    db.commit()
    result = propagate_visual_asset_staleness(db, asset_key="book:character:LIN_WAN", reason="VISUAL_ASSET_VERSION_REPLACED")
    db.commit()
    assert result["prompt_ir_staled"] == 1
    assert version.stale_status == "STALE" and authority.stale_status == "STALE"
