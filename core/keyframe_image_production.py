"""Single-keyframe image production over the existing runtime authorities.

This module is deliberately a thin orchestration facade.  It does not own a
provider registry, prompt system, review system, or asset store.  It prepares
one executable PromptIR pointer from the immutable ProductionPromptVersion,
creates the existing GenerationExecutionRecord, and materialises a
deterministic fixture candidate when ``fixture=True`` (the default).
"""
from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
import uuid

import config
from api.model_registry import get_default_profile, get_profile
from core.automatic_keyframe_authoring import get_keyframe_plan
from core.generation_execution_service import GenerationExecutionService
from core.keyframe_authoring import bind_keyframe_asset
from core.media_authority import MediaAuthorityError, promote_media_candidate, validate_media_candidate
from core.production_asset_authority import ingest_production_asset
from core.production_prompt_lineage import create_production_prompt_lineage
from models import (
    AutomaticKeyframePlan,
    GenerationExecutionRecord,
    Keyframe,
    KeyframeSequence,
    MediaCandidateRecord,
    MediaPromotionRecord,
    MediaValidationRecord,
    ProductionGenerationIntent,
    ProductionPromptLineage,
    ProductionPromptVersion,
    PromptIRAuthority,
    PromptIRPointer,
    PromptIRVersion,
    Session,
    StoryboardShot,
)


PNG_FIXTURE = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
SCHEMA_VERSION = "keyframe_image_production_v1"
_ORDER = {"start": 0, "end": 1, "middle": 2}


class KeyframeImageProductionError(ValueError):
    status_code = 409

    def __init__(self, message: str, *, code: str = "KEYFRAME_IMAGE_PRODUCTION_INVALID", diagnostics: Any | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.diagnostics = diagnostics or []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fp(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _keyframe(row_id: int, session: Any) -> tuple[Keyframe, KeyframeSequence, StoryboardShot]:
    frame = session.query(Keyframe).filter_by(id=int(row_id), status="ACTIVE").one_or_none()
    if frame is None:
        raise KeyframeImageProductionError("keyframe does not exist or is stale", code="KEYFRAME_NOT_FOUND")
    sequence = session.query(KeyframeSequence).filter_by(id=frame.keyframe_sequence_id, status="ACTIVE").one_or_none()
    if sequence is None:
        raise KeyframeImageProductionError("keyframe sequence is not active", code="KEYFRAME_SEQUENCE_STALE")
    shot = session.query(StoryboardShot).filter_by(id=sequence.storyboard_shot_id).one_or_none()
    if shot is None:
        raise KeyframeImageProductionError("StoryboardShot does not exist", code="SHOT_NOT_FOUND")
    return frame, sequence, shot


def _prompt_for_keyframe(session: Any, frame: Keyframe, sequence: KeyframeSequence) -> ProductionPromptVersion:
    matches: list[ProductionPromptVersion] = []
    for row in session.query(ProductionPromptVersion).order_by(ProductionPromptVersion.id.desc()).all():
        structure = _json(row.prompt_structure, {})
        keyframe = structure.get("keyframe") if isinstance(structure, dict) else None
        if isinstance(keyframe, dict) and int(keyframe.get("keyframe_id", -1)) == int(frame.id) and int(keyframe.get("sequence_id", -1)) == int(sequence.id):
            matches.append(row)
    if not matches:
        raise KeyframeImageProductionError("current ProductionPromptVersion is required", code="PROMPT_LINEAGE_REQUIRED")
    row = matches[0]
    current = session.query(ProductionPromptVersion).filter_by(prompt_id=row.prompt_id).order_by(ProductionPromptVersion.version_number.desc()).first()
    if current is None or current.id != row.id:
        raise KeyframeImageProductionError("keyframe prompt is not current", code="PROMPT_LINEAGE_STALE")
    return row


def _source_guard(session: Any, frame: Keyframe, sequence: KeyframeSequence, shot: StoryboardShot) -> dict[str, Any]:
    plan = get_keyframe_plan(session, shot_id=int(shot.id), version=int(sequence.revision))
    if str(plan.get("status") or "").upper() == "STALE":
        raise KeyframeImageProductionError("keyframe source is stale", code="STALE_SOURCE", diagnostics=plan.get("stale_reasons") or [])
    if int(plan.get("compiled_sequence_id") or 0) != int(sequence.id):
        raise KeyframeImageProductionError("keyframe sequence is not the compiled current plan", code="KEYFRAME_SEQUENCE_STALE")
    if str(sequence.status).upper() != "ACTIVE" or str(frame.status).upper() != "ACTIVE":
        raise KeyframeImageProductionError("keyframe source is not active", code="STALE_SOURCE")
    intent_id = str(plan.get("generation_intent_id") or "").strip()
    intent = session.query(ProductionGenerationIntent).filter_by(generation_intent_id=intent_id, shot_id=int(shot.id)).one_or_none() if intent_id else None
    if intent is None:
        raise KeyframeImageProductionError("production GenerationIntent is missing for the keyframe plan", code="GENERATION_INTENT_REQUIRED")
    constraints = _json(intent.constraint_snapshot, {})
    if isinstance(constraints, dict) and constraints.get("production_eligible") is False:
        raise KeyframeImageProductionError("GenerationIntent is not production eligible", code="GENERATION_INTENT_INELIGIBLE")
    if not str(intent.shot_requirement_fingerprint or "").strip():
        raise KeyframeImageProductionError("GenerationIntent fingerprint is missing", code="GENERATION_INTENT_INVALID")
    return {"automatic_keyframe_plan_id": int(plan["id"]), "automatic_keyframe_plan_version": int(plan["version"]), "source_fingerprint": str(plan.get("source_fingerprint") or ""), "plan_fingerprint": str(plan.get("plan_fingerprint") or ""), "generation_intent_id": intent.generation_intent_id, "generation_intent_fingerprint": str(intent.shot_requirement_fingerprint or ""), "sequence_id": int(sequence.id), "sequence_revision": int(sequence.revision), "keyframe_id": int(frame.id), "frame_type": str(frame.frame_type).lower(), "storyboard_shot_id": int(shot.id)}


def _ensure_prompt_authority(session: Any, shot: StoryboardShot) -> tuple[PromptIRPointer, PromptIRVersion, PromptIRAuthority | None]:
    existing = session.query(PromptIRPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), target_media="IMAGE").first()
    if existing is not None:
        version = session.query(PromptIRVersion).filter_by(id=int(existing.prompt_ir_version_id)).one_or_none()
        authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=int(existing.prompt_ir_version_id)).one_or_none()
        if version is not None:
            return existing, version, authority
    # Use the canonical Storyboard snapshot/compiler when a prior image PromptIR
    # has not yet been activated for this shot.
    try:
        from core.storyboard_materializer import build_storyboard_production_snapshot, resolve_current_authoritative_materialization
        from core.prompt_ir_phase_e import build_generation_policy, compile_storyboard_snapshot_to_prompt_ir

        materialization, rows, envelope = resolve_current_authoritative_materialization(session, book_id=int(shot.book_id), episode=int(shot.episode), scene_id=str(shot.scene_id))
        snapshot = build_storyboard_production_snapshot(materialization_set=materialization, rows=rows, authority_envelope=envelope)
        policy = build_generation_policy({"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, allow_default=False)
        ir = next(item for item in compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy=policy, allow_default_policy=False) if int(item.get("storyboard_shot_id")) == int(shot.id))
    except Exception as exc:
        raise KeyframeImageProductionError("current Storyboard PromptIR cannot be activated", code="PROMPT_AUTHORITY_UNAVAILABLE", diagnostics=[{"error": str(exc)}]) from exc
    now = datetime.utcnow()
    envelope = {"schema_version": "prompt_ir_authority_envelope_v2", "source_authority": ir["source_authority"], "compiler_provenance": ir["compiler_provenance"], "generation_policy": ir["generation_policy"], "asset_authority_bindings": ir["asset_authority_bindings"], "prompt_ir_payload_hash": ir["payload_hash"], "qualification_state": "PROMPT_IR_QUALIFIED", "model_generation_ready": False, "stale_status": "FRESH"}
    # The phase-E fingerprint function is intentionally reused so the normal
    # PromptIR integrity validator remains the sole authority.
    from core.prompt_ir_phase_e import fingerprint
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    version = PromptIRVersion(book_id=int(shot.book_id), episode=int(shot.episode), scene_id=str(ir.get("scene_id") or shot.scene_id), storyboard_shot_id=int(shot.id), materialization_set_id=int(ir["source_authority"].get("storyboard_materialization_set_id") or shot.materialization_set_id or 0), plan_shot_id=str(ir.get("plan_shot_id") or shot.plan_shot_id or ""), schema_version=str(ir.get("schema_version") or "prompt_ir_v2"), payload_json=_canonical(ir), payload_hash=str(ir["payload_hash"]), compiler_version=str(ir["compiler_provenance"].get("compiler_version") or ""), compiler_policy_version=str(ir["compiler_provenance"].get("compiler_policy_version") or ""), retention_policy_version="generation_policy_v1", authority_envelope_json=_canonical(envelope), qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="ASSET_REFERENCE_PENDING", model_generation_ready="false", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    session.add(version)
    session.flush()
    authority = PromptIRAuthority(prompt_ir_version_id=int(version.id), book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=_canonical(envelope), qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now)
    session.add(authority)
    session.flush()
    pointer = existing or PromptIRPointer(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), target_media="IMAGE")
    pointer.prompt_ir_version_id = int(version.id)
    pointer.payload_hash = str(version.payload_hash)
    pointer.qualification_state = "PROMPT_IR_QUALIFIED"
    pointer.updated_at = now
    session.add(pointer)
    session.flush()
    return pointer, version, authority


def _profile(model_profile_id: str | None) -> dict[str, Any]:
    profile = get_profile(model_profile_id) if model_profile_id else get_default_profile("image")
    if not profile:
        raise KeyframeImageProductionError("image Model Registry profile does not exist", code="MODEL_PROFILE_NOT_FOUND")
    return profile


def _serialize(session: Any, frame: Keyframe, sequence: KeyframeSequence) -> dict[str, Any]:
    rows = session.query(GenerationExecutionRecord).filter_by(storyboard_shot_id=int(sequence.storyboard_shot_id)).all()
    matches = []
    for row in rows:
        meta = _json(row.request_payload, {})
        marker = meta.get("_keyframe_image_production") if isinstance(meta, dict) else None
        if isinstance(marker, dict) and int(marker.get("keyframe_id", -1)) == int(frame.id):
            matches.append(row)
    row = sorted(matches, key=lambda item: (item.created_at or datetime.min, item.id or 0), reverse=True)[0] if matches else None
    candidate = session.query(MediaCandidateRecord).filter_by(execution_id=row.execution_id).one_or_none() if row else None
    validation = session.query(MediaValidationRecord).filter_by(candidate_id=candidate.candidate_id).order_by(MediaValidationRecord.id.desc()).first() if candidate else None
    review = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).first() if candidate else None
    return {"schema_version": SCHEMA_VERSION, "keyframe_id": int(frame.id), "sequence_id": int(sequence.id), "frame_type": str(frame.frame_type), "execution": {"execution_id": row.execution_id, "status": row.execution_status, "provider": row.provider, "model": row.model, "provider_calls": int(row.logical_provider_calls or 0), "prompt_version_id": row.prompt_pointer_id, "request": row.request_payload} if row else None, "candidate": {"candidate_id": candidate.candidate_id, "status": candidate.status, "validation_status": candidate.validation_status, "storage_identity": candidate.storage_identity} if candidate else None, "validation": {"validation_id": validation.validation_id, "status": validation.status} if validation else None, "review": {"promotion_id": review.promotion_id, "review_status": review.review_status, "decision": review.decision, "official_media_version_id": review.official_media_version_id} if review else None}


def produce_keyframe_image(session: Any, *, keyframe_id: int, model_profile_id: str | None = None, fixture: bool = True, production_required: bool = True) -> dict[str, Any]:
    frame, sequence, shot = _keyframe(keyframe_id, session)
    source = _source_guard(session, frame, sequence, shot)
    if str(frame.frame_type).lower() == "middle" and not production_required:
        return {"schema_version": SCHEMA_VERSION, "keyframe_id": int(frame.id), "sequence_id": int(sequence.id), "frame_type": str(frame.frame_type), "production_required": False, "skipped": True, "reason": "MIDDLE_FRAME_OPTIONAL"}
    prompt = _prompt_for_keyframe(session, frame, sequence)
    profile = _profile(model_profile_id)
    marker = {**source, "prompt_version_id": str(prompt.prompt_version_id), "model_profile_id": str(profile.get("id") or model_profile_id or ""), "source_fingerprint": source.get("source_fingerprint") or _fp(source)}
    marker_fp = _fp(marker)
    prior_attempts = 0
    for existing in session.query(GenerationExecutionRecord).filter_by(storyboard_shot_id=int(shot.id)).all():
        payload = existing.request_payload
        existing_marker = payload.get("_keyframe_image_production") if isinstance(payload, dict) else None
        if isinstance(existing_marker, dict) and int(existing_marker.get("keyframe_id", -1)) == int(frame.id):
            prior_attempts = max(prior_attempts, int(existing_marker.get("attempt", 1) or 1))
            if existing_marker.get("request_key") == marker_fp:
                candidate = session.query(MediaCandidateRecord).filter_by(execution_id=existing.execution_id).one_or_none()
                review = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).first() if candidate else None
                if review is None or str(review.decision or "").upper() not in {"REJECT", "REQUEST_CHANGE"}:
                    return {**_serialize(session, frame, sequence), "idempotent": True}
    attempt = prior_attempts + 1
    marker["attempt"] = attempt
    marker["request_key"] = _fp({key: value for key, value in marker.items() if key not in {"attempt", "request_key", "idempotency_fingerprint"}})
    marker_fp = _fp(marker)
    pointer, ir_version, ir_authority = _ensure_prompt_authority(session, shot)
    execution = GenerationExecutionService(session).create_execution(shot_id=int(shot.id), prompt_pointer_id=int(pointer.id), prompt_version_id=int(ir_version.id), model_profile_id=str(profile.get("id") or model_profile_id or "builtin-mock-image"))
    role = f"KEYFRAME_{str(frame.frame_type).upper()}_IMAGE"
    from core.prompt_ir_phase_e import build_generation_policy
    policy = build_generation_policy({"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, allow_default=False)
    request = {"schema_version": SCHEMA_VERSION, "media_role": role, "prompt_version_id": str(prompt.prompt_version_id), "prompt_text": prompt.prompt_text, "keyframe": {"id": int(frame.id), "sequence_id": int(sequence.id), "frame_type": str(frame.frame_type), "time_seconds": float(frame.time_seconds), "description": frame.description, "camera_state": _json(frame.camera_state, {}), "character_state": _json(frame.character_state, {}), "scene_state": _json(frame.scene_state, {}), "emotion_state": _json(frame.emotion_state, {})}, "_keyframe_image_production": {**marker, "idempotency_fingerprint": marker_fp, "fixture": bool(fixture)}, "generation_policy": policy}
    execution.request_payload = request
    execution.execution_mode = "KEYFRAME_IMAGE_FIXTURE" if fixture else "KEYFRAME_IMAGE_PROVIDER"
    execution.provider = str(profile.get("provider") or "shapi-openai-images")
    execution.model = str(profile.get("model_name") or profile.get("model") or "fixture-image-v1")
    execution.model_profile_fingerprint = _fp({key: profile.get(key) for key in ("id", "provider", "base_url", "model_name", "transport_binding_id")})
    execution.generation_policy_fingerprint = str(request["generation_policy"]["fingerprint"])
    execution.provider_request_fingerprint = _fp({"idempotency": marker_fp, "profile": execution.model_profile_fingerprint})
    service = GenerationExecutionService(session)
    if not fixture:
        if os.getenv("PHASE_F_PROVIDER_CANARY_REAL", "").strip() != "1":
            raise KeyframeImageProductionError("real provider canary is disabled by gate", code="REAL_PROVIDER_CANARY_SKIPPED_BY_GATE")
        # Real provider calls stay on the canonical GenerationOrchestrator and
        # existing ModelAdapter registry.  The gate is checked before any
        # execution transition, so a skipped canary leaves no RUNNING row.
        from core.generation_orchestrator import GenerationOrchestrator, GenerationOrchestratorError
        try:
            service.transition(execution.execution_id, "QUEUED")
            row = GenerationOrchestrator(session).run(execution.execution_id)
        except GenerationOrchestratorError as exc:
            raise KeyframeImageProductionError(exc.message, code=exc.code, diagnostics=[{"provider_calls": exc.provider_calls}]) from exc
        if not row.candidate_id:
            raise KeyframeImageProductionError("real provider execution returned no MediaCandidate", code="GENERATION_EXECUTION_CANDIDATE_MISSING")
        try:
            current = _source_guard(session, frame, sequence, shot)
        except KeyframeImageProductionError as exc:
            row.response_payload = {**row.response_payload, "source_guard": {"status": "STALE_SOURCE", "code": exc.code}}
            session.commit()
            raise
        validation = validate_media_candidate(session, row.candidate_id)
        return {**_serialize(session, frame, sequence), "idempotent": False, "validation_id": validation["validation_id"], "provider_calls": int(row.logical_provider_calls or 0), "real_provider_calls": int(row.logical_provider_calls or 0), "source_guard": current}
    service.transition(execution.execution_id, "QUEUED")
    service.transition(execution.execution_id, "RUNNING")
    response = {"fixture": True, "provider": execution.provider, "model": execution.model, "request_id": "fixture-" + marker_fp[7:23], "keyframe_id": int(frame.id), "frame_type": str(frame.frame_type)}
    response_hash = _fp(response)
    root = Path(config.UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"keyframe-{frame.id}-{marker_fp[7:23]}.png"
    path.write_bytes(PNG_FIXTURE)
    execution.provider_request_id = response["request_id"]
    execution.provider_task_id = response["request_id"]
    execution.provider_response_hash = response_hash
    execution.logical_provider_calls = 1
    execution.request_payload = {**request, "provider_request": {"provider": execution.provider, "model": execution.model, "request_id": response["request_id"], "prompt_version_id": str(prompt.prompt_version_id)}}
    service.transition(execution.execution_id, "PROVIDER_CALLED", response_payload={"provider_response": response})
    candidate = MediaCandidateRecord(candidate_id="candidate-keyframe-" + uuid.uuid4().hex, execution_id=execution.execution_id, status="MEDIA_CANDIDATE", media_type="IMAGE", storage_identity=str(path), storage_reference_json=_canonical({"local_path": str(path), "source_kind": "deterministic_fixture"}), metadata_json=_canonical({"media_type": "IMAGE", "mime_type": "image/png", "byte_size": len(PNG_FIXTURE), "width": 1, "height": 1, "frame_type": str(frame.frame_type), "keyframe_id": int(frame.id), "keyframe_sequence_id": int(sequence.id), "source_fingerprint": marker["source_fingerprint"], "provider": execution.provider, "model": execution.model}), checksum_sha256=hashlib.sha256(PNG_FIXTURE).hexdigest(), mime_type="image/png", byte_size=len(PNG_FIXTURE), width=1, height=1, duration_ms=None, prompt_ir_version_id=int(ir_version.id), prompt_ir_payload_hash=str(ir_version.payload_hash), generation_payload_fingerprint=str(execution.generation_payload_fingerprint), model_profile_id=str(execution.model_profile_id), model_profile_fingerprint=str(execution.model_profile_fingerprint), provider_request_fingerprint=str(execution.provider_request_fingerprint), provider_response_hash=response_hash, provider_task_id=response["request_id"], created_at=datetime.utcnow())
    session.add(candidate)
    session.flush()
    execution.candidate_id = candidate.candidate_id
    service.transition(execution.execution_id, "SUCCESS", response_payload={"provider_response": response, "candidate_id": candidate.candidate_id, "keyframe_id": int(frame.id), "source_fingerprint": marker["source_fingerprint"]})
    session.commit()
    try:
        source_after_provider = _source_guard(session, frame, sequence, shot)
    except KeyframeImageProductionError as exc:
        execution.response_payload = {**execution.response_payload, "source_guard": {"status": "STALE_SOURCE", "code": exc.code}}
        session.commit()
        raise
    try:
        validation = validate_media_candidate(session, candidate.candidate_id)
    except MediaAuthorityError as exc:
        raise KeyframeImageProductionError(exc.message, code=exc.code, diagnostics=exc.diagnostics) from exc
    return {**_serialize(session, frame, sequence), "idempotent": False, "validation_id": validation["validation_id"], "provider_calls": 1, "real_provider_calls": 0, "source_guard": source_after_provider}


def promote_keyframe_image(session: Any, *, keyframe_id: int, validation_id: str, reviewer: str, decision: str = "APPROVE", review_notes: str = "") -> dict[str, Any]:
    frame, sequence, shot = _keyframe(keyframe_id, session)
    source = _source_guard(session, frame, sequence, shot)
    candidate = None
    for candidate_row in session.query(MediaCandidateRecord).join(GenerationExecutionRecord, GenerationExecutionRecord.execution_id == MediaCandidateRecord.execution_id).filter(GenerationExecutionRecord.storyboard_shot_id == int(shot.id)).order_by(MediaCandidateRecord.id.desc()).all():
        candidate_marker = _json(session.query(GenerationExecutionRecord).filter_by(execution_id=candidate_row.execution_id).one().request_payload, {}).get("_keyframe_image_production") or {}
        if int(candidate_marker.get("keyframe_id", -1)) == int(frame.id):
            candidate = candidate_row
            break
    if candidate is None:
        raise KeyframeImageProductionError("keyframe image candidate does not exist", code="CANDIDATE_NOT_FOUND")
    execution = session.query(GenerationExecutionRecord).filter_by(execution_id=candidate.execution_id).one()
    marker = _json(execution.request_payload, {}).get("_keyframe_image_production") or {}
    if int(marker.get("keyframe_id", -1)) != int(frame.id):
        raise KeyframeImageProductionError("candidate does not belong to the requested keyframe", code="CANDIDATE_KEYFRAME_MISMATCH")
    if marker.get("source_fingerprint") and marker.get("source_fingerprint") != source.get("source_fingerprint"):
        raise KeyframeImageProductionError("source changed after generation; promotion is blocked", code="STALE_SOURCE")
    def bridge(_rows: dict[str, Any]) -> None:
        version = _rows["version"]
        # The existing typed Production Asset Authority accepts durable object
        # identities.  Keep the MediaCandidate's local fixture path as the
        # canonical bytes source and expose a deterministic HTTPS identity for
        # the cross-runtime asset pointer.
        asset = ingest_production_asset(session, entity_type="PROP", entity_id=f"keyframe-image:{int(frame.id)}", book_id=int(shot.book_id), source={"storage_identity": f"https://fixture.invalid/keyframes/{int(frame.id)}/{str(version.official_media_version_id)}.png", "checksum": str(candidate.checksum_sha256), "metadata": {"role": str(version.media_role), "official_media_version_id": str(version.official_media_version_id), "keyframe_id": int(frame.id), "sequence_id": int(sequence.id)}})
        bind_keyframe_asset(session, keyframe_id=int(frame.id), asset_type="PROP", authority_id=asset["authority_id"], version_id=asset["version_id"], is_primary=str(frame.frame_type).lower() in {"start", "end"})
        create_production_prompt_lineage(session, asset_type="PROP", asset_id=f"keyframe-image:{int(frame.id)}", asset_version_id=asset["version_id"], shot_id=int(shot.id), prompt_version_id=str(marker.get("prompt_version_id") or ""), generation_intent_id=str(marker.get("generation_intent_id") or ""))
    try:
        result = promote_media_candidate(session, candidate.candidate_id, validation_id, confirmation=True, reviewer=reviewer, decision=decision, review_notes=review_notes, before_commit=bridge if str(decision).upper() == "APPROVE" else None)
    except MediaAuthorityError as exc:
        if str(decision).upper() in {"REJECT", "REQUEST_CHANGE"} and exc.code == "MEDIA_PROMOTION_REVIEW_REQUIRED":
            # The canonical review service records the decision before it
            # rejects publication.  Preserve that history and return the
            # review projection to the caller.
            session.commit()
            return _serialize(session, frame, sequence)
        session.rollback()
        raise KeyframeImageProductionError(exc.message, code=exc.code, diagnostics=exc.diagnostics) from exc
    except Exception:
        session.rollback()
        raise
    session.refresh(candidate)
    return {**_serialize(session, frame, sequence), "promotion": {"official_media_version_id": result["version"].official_media_version_id, "authority_id": result["authority"].authority_id}, "source_guard": source}


def get_keyframe_image_production(session: Any, *, keyframe_id: int) -> dict[str, Any]:
    frame, sequence, _shot = _keyframe(keyframe_id, session)
    return _serialize(session, frame, sequence)


__all__ = ["KeyframeImageProductionError", "produce_keyframe_image", "promote_keyframe_image", "get_keyframe_image_production"]
