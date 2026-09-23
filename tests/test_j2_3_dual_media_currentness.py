"""Provider-free dual-media PromptIR resolver regressions."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.media_authority import build_image_to_video_source_binding, validate_image_to_video_source_binding
from core.prompt_ir_phase_e import build_generation_policy, fingerprint, prompt_ir_semantic_projection, resolve_current_authoritative_prompt_ir
from models import Base, GenerationExecutionRecord, OfficialMediaAuthority, OfficialMediaPointer, OfficialMediaVersion, PromptIRAuthority, PromptIRPointer, PromptIRVersion
from tests.test_prompt_ir_phase_e_semantic_closure import _persist_v2_for_resolver, _snapshots


def _install_video_scope(db, image_version, image_authority):
    payload = json.loads(image_version.payload_json)
    payload["generation_policy"] = build_generation_policy({"mode": "IMAGE_TO_VIDEO", "target_media": "VIDEO"}, allow_default=False)
    payload.setdefault("source_authority", {})["generation_policy_fingerprint"] = payload["generation_policy"]["fingerprint"]
    payload["prompt_ir_semantic_fingerprint"] = fingerprint(prompt_ir_semantic_projection(payload))
    payload_hash = fingerprint({key: value for key, value in payload.items() if key not in {"prompt_ir_payload_fingerprint", "payload_hash"}})
    payload["prompt_ir_payload_fingerprint"] = payload_hash
    payload["payload_hash"] = payload_hash
    envelope = json.loads(image_authority.envelope_json)
    envelope["generation_policy"] = payload["generation_policy"]
    envelope["prompt_ir_payload_hash"] = payload_hash
    envelope.pop("envelope_fingerprint", None)
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    now = datetime.now()
    video = PromptIRVersion(book_id=image_version.book_id, episode=image_version.episode, scene_id=image_version.scene_id, storyboard_shot_id=image_version.storyboard_shot_id, materialization_set_id=image_version.materialization_set_id, plan_shot_id=image_version.plan_shot_id, schema_version=image_version.schema_version, payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True), payload_hash=payload_hash, compiler_version=image_version.compiler_version, compiler_policy_version=image_version.compiler_policy_version, retention_policy_version=image_version.retention_policy_version, authority_envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state=image_version.qualification_state, asset_reference_state=image_version.asset_reference_state, model_generation_ready=image_version.model_generation_ready, stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    db.add(video)
    db.flush()
    authority = PromptIRAuthority(prompt_ir_version_id=video.id, book_id=video.book_id, episode=video.episode, storyboard_shot_id=video.storyboard_shot_id, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state=video.qualification_state, stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    pointer = PromptIRPointer(book_id=video.book_id, episode=video.episode, storyboard_shot_id=video.storyboard_shot_id, target_media="VIDEO", prompt_ir_version_id=video.id, payload_hash=payload_hash, qualification_state="PROMPT_IR_QUALIFIED", created_at=now, updated_at=now)
    db.add_all([authority, pointer])
    db.commit()
    return video, authority, pointer


def _patched_lineage(monkeypatch, snapshot, shot):
    source_row = snapshot["ordered_shots"][0]
    current_row = SimpleNamespace(id=shot.id, plan_shot_id=shot.plan_shot_id, projection_fingerprint=source_row["projection_fingerprint"], meta_info=json.dumps({"visual_semantic_handoff": source_row["visual_semantic_handoff"], "projection_payload": source_row["projection_payload"], "prompt_compiler_handoff": source_row["prompt_compiler_handoff"]}, ensure_ascii=False))
    current_set = SimpleNamespace(id=1, scene_id=snapshot["scene_id"], set_payload_fingerprint="set-1", status="MATERIALIZED", stale_status="FRESH")
    monkeypatch.setattr("core.storyboard_materializer.resolve_current_authoritative_materialization", lambda *args, **kwargs: (current_set, [current_row], snapshot["authority_envelope"]))
    monkeypatch.setattr("core.storyboard_materializer.build_storyboard_production_snapshot", lambda **kwargs: snapshot)
    monkeypatch.setattr("core.prompt_ir_phase_e.validate_prompt_ir_historical_integrity", lambda *args, **kwargs: {"integrity_valid": True})


def test_dual_scope_resolves_exact_image_and_video_without_fallback(monkeypatch):
    snapshot = _snapshots()[0]
    image_ir = __import__("core.prompt_ir_phase_e", fromlist=["compile_storyboard_snapshot_to_prompt_ir"]).compile_storyboard_snapshot_to_prompt_ir(snapshot)[0]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    shot, image, image_authority, image_pointer = _persist_v2_for_resolver(db, snapshot, image_ir)
    video, _video_authority, video_pointer = _install_video_scope(db, image, image_authority)
    _patched_lineage(monkeypatch, snapshot, shot)
    resolved_image = resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="IMAGE")
    resolved_video = resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="VIDEO")
    assert resolved_image["version"].id == image.id
    assert resolved_video["version"].id == video.id
    assert resolved_image["pointer"].target_media == "IMAGE"
    assert resolved_video["pointer"].target_media == "VIDEO"
    assert resolved_image["version"].id != resolved_video["version"].id
    db.delete(video_pointer)
    db.commit()
    with pytest.raises(Exception) as exc_info:
        resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="VIDEO")
    assert getattr(exc_info.value, "detail", {}).get("code") == "PROMPT_IR_POINTER_MISSING"
    engine.dispose()


def test_historical_video_version_without_pointer_never_becomes_current(monkeypatch):
    snapshot = _snapshots()[0]
    image_ir = __import__("core.prompt_ir_phase_e", fromlist=["compile_storyboard_snapshot_to_prompt_ir"]).compile_storyboard_snapshot_to_prompt_ir(snapshot)[0]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    shot, image, image_authority, _pointer = _persist_v2_for_resolver(db, snapshot, image_ir)
    video, video_authority, video_pointer = _install_video_scope(db, image, image_authority)
    db.delete(video_pointer)
    db.commit()
    with pytest.raises(Exception) as exc_info:
        resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="VIDEO")
    assert getattr(exc_info.value, "detail", {}).get("code") == "PROMPT_IR_POINTER_MISSING"
    assert video.id and video_authority.id
    engine.dispose()


def test_pointer_payload_media_scope_mismatch_fails_closed(monkeypatch):
    snapshot = _snapshots()[0]
    image_ir = __import__("core.prompt_ir_phase_e", fromlist=["compile_storyboard_snapshot_to_prompt_ir"]).compile_storyboard_snapshot_to_prompt_ir(snapshot)[0]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    shot, image, authority, pointer = _persist_v2_for_resolver(db, snapshot, image_ir)
    _patched_lineage(monkeypatch, snapshot, shot)
    pointer.target_media = "VIDEO"
    db.commit()
    with pytest.raises(Exception) as exc_info:
        resolve_current_authoritative_prompt_ir(db, book_id=77, episode=1, storyboard_shot_id=shot.id, target_media="VIDEO")
    assert getattr(exc_info.value, "detail", {}).get("code") == "PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH"
    engine.dispose()


def test_image_to_video_binding_is_structured_and_current_authority_bound():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = datetime.now()
    prompt = PromptIRVersion(book_id=77, episode=1, scene_id="S1", storyboard_shot_id=7, materialization_set_id=1, plan_shot_id="P7", schema_version="prompt_ir_v2", payload_json="{}", payload_hash="prompt-hash", compiler_version="c", compiler_policy_version="p", retention_policy_version="r", authority_envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="READY", model_generation_ready="false", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    db.add(prompt)
    db.flush()
    version = OfficialMediaVersion(official_media_version_id="omv-image-1", book_id=77, episode=1, storyboard_shot_id=7, plan_shot_id="P7", media_role="SHOT_PRIMARY_IMAGE", media_type="IMAGE", candidate_id="candidate-image-1", candidate_fingerprint="candidate-fp", storage_identity="fixture://image", checksum_sha256="checksum-image", mime_type="image/png", byte_size=4, width=1, height=1, duration_ms=None, prompt_ir_version_id=prompt.id, prompt_ir_payload_hash=prompt.payload_hash, generation_payload_fingerprint="generation-fp", provider_request_fingerprint="request-fp", provider_response_hash="response-fp", validation_id="validation-1", validation_fingerprint="validation-fp", revision=1, status="CURRENT", payload_hash="official-payload", created_at=now)
    authority = OfficialMediaAuthority(authority_id="oma-image-1", official_media_version_id=version.official_media_version_id, authority_envelope_json="{}", payload_hash=version.payload_hash, lineage_hash="lineage-fp", validation_fingerprint="validation-fp", promotion_fingerprint="promotion-fp", status="CURRENT", created_at=now)
    db.add_all([version, authority])
    db.flush()
    pointer = OfficialMediaPointer(book_id=77, episode=1, storyboard_shot_id=7, media_role="SHOT_PRIMARY_IMAGE", official_media_version_id=version.official_media_version_id, authority_id=authority.authority_id, fingerprint="pointer-fp", created_at=now, updated_at=now)
    db.add(pointer)
    execution = SimpleNamespace(book_id=77, episode=1, storyboard_shot_id=7, target_media="VIDEO")
    binding = build_image_to_video_source_binding(official_media_authority=authority, official_media_version=version)
    assert binding["authority_class"] == "OFFICIAL_MEDIA"
    assert binding["media_role"] == "SHOT_PRIMARY_IMAGE"
    assert validate_image_to_video_source_binding(db, execution=execution, binding=binding)["valid"] is True
    tampered = dict(binding, checksum_sha256="tampered")
    with pytest.raises(Exception) as exc_info:
        validate_image_to_video_source_binding(db, execution=execution, binding=tampered)
    assert getattr(exc_info.value, "code", "") == "IMAGE_TO_VIDEO_SOURCE_BINDING_INVALID"
    engine.dispose()
