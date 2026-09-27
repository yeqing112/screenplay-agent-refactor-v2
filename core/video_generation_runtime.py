"""Video generation runtime over existing keyframes, execution, and media authority."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from core.generation_execution_service import GenerationExecutionService
from core.media_authority import MediaAuthorityError, validate_media_candidate
from core.video_provider_adapter import DEFAULT_VIDEO_PROVIDER_REGISTRY, VideoProviderError, VideoProviderRegistry
from models import (
    GenerationExecutionRecord,
    Keyframe,
    KeyframeAssetBinding,
    KeyframeSequence,
    MediaCandidateRecord,
    ProductionPromptVersion,
    PromptIRAuthority,
    PromptIRPointer,
    PromptIRVersion,
    StoryboardShot,
    TaskRun,
    VideoGenerationIntent,
)


MOTION_FIELDS = ("camera_motion", "subject_motion", "environment_motion", "emotion_transition")


class VideoGenerationError(ValueError):
    status_code = 409
    code = "VIDEO_GENERATION_INVALID"

    def __init__(self, message: str, *, code: str | None = None, diagnostics: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.diagnostics = diagnostics if diagnostics is not None else []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise VideoGenerationError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def _intent_dict(row: VideoGenerationIntent) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "shot_id": int(row.storyboard_shot_id),
        "storyboard_shot_id": int(row.storyboard_shot_id),
        "generation_type": "VIDEO",
        "duration": float(row.duration),
        "aspect_ratio": row.aspect_ratio,
        "motion_profile": _obj(row.motion_profile),
        "first_frame_asset": _obj(row.first_frame_asset),
        "last_frame_asset": _obj(row.last_frame_asset),
        "prompt_version": row.prompt_version,
        "intent_fingerprint": row.intent_fingerprint,
        "status": row.status,
        "generation_execution_id": row.generation_execution_id,
        "task_id": row.task_id,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _normalize_motion_profile(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(profile or {})
    aliases = {"subject_motion": ("subject_motion", "character_motion"), "environment_motion": ("environment_motion",), "emotion_transition": ("emotion_transition",), "camera_motion": ("camera_motion",)}
    result: dict[str, Any] = {}
    missing: list[str] = []
    for field in MOTION_FIELDS:
        value = ""
        for key in aliases[field]:
            if str(source.get(key) or "").strip():
                value = str(source[key]).strip()
                break
        if not value:
            missing.append(field)
        result[field] = value
    if missing:
        raise VideoGenerationError("motion_profile is incomplete", code="VIDEO_MOTION_PROFILE_INCOMPLETE", diagnostics=[{"missing": missing}])
    return result


def _validate_frame_asset(session: Any, *, shot: StoryboardShot, asset: Mapping[str, Any] | None, first: bool) -> dict[str, Any]:
    value = dict(asset or {})
    keyframe_id = value.get("keyframe_id")
    if keyframe_id in (None, ""):
        raise VideoGenerationError("first_frame_asset must identify a keyframe asset", code="VIDEO_FIRST_FRAME_INVALID" if first else "VIDEO_LAST_FRAME_INVALID")
    frame = session.query(Keyframe).filter_by(id=int(keyframe_id), status="ACTIVE").one_or_none()
    sequence = session.query(KeyframeSequence).filter_by(id=getattr(frame, "keyframe_sequence_id", 0), storyboard_shot_id=shot.id, status="ACTIVE").one_or_none() if frame else None
    if frame is None or sequence is None:
        raise VideoGenerationError("frame asset does not belong to the requested shot", code="VIDEO_FRAME_ASSET_INVALID")
    bindings = session.query(KeyframeAssetBinding).filter_by(keyframe_id=frame.id, status="ACTIVE").order_by(KeyframeAssetBinding.id.asc()).all()
    primary = next((item for item in bindings if item.is_primary), None)
    if primary is None:
        raise VideoGenerationError("frame asset has no active primary asset binding", code="VIDEO_FRAME_ASSET_NOT_CURRENT", diagnostics=[{"keyframe_id": frame.id}])
    value.update({"keyframe_id": int(frame.id), "sequence_id": int(sequence.id), "binding_id": int(primary.id), "binding_fingerprint": primary.binding_fingerprint, "asset_type": primary.asset_type, "authority_id": primary.authority_id, "version_id": primary.version_id})
    return value


def _current_video_prompt_ir(session: Any, *, shot: StoryboardShot) -> tuple[PromptIRPointer, PromptIRVersion, PromptIRAuthority | None]:
    pointer = session.query(PromptIRPointer).filter_by(book_id=shot.book_id, episode=shot.episode, storyboard_shot_id=shot.id, target_media="VIDEO").first()
    if pointer is None:
        raise VideoGenerationError("current VIDEO PromptIR pointer is required", code="VIDEO_PROMPT_IR_REQUIRED")
    version = session.query(PromptIRVersion).filter_by(id=pointer.prompt_ir_version_id).one_or_none()
    if version is None or str(version.payload_hash) != str(pointer.payload_hash):
        raise VideoGenerationError("current VIDEO PromptIR version is missing or stale", code="VIDEO_PROMPT_IR_STALE")
    authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one_or_none()
    if authority is None or str(authority.stale_status or "FRESH").upper() != "FRESH":
        raise VideoGenerationError("current VIDEO PromptIR authority is missing or stale", code="VIDEO_PROMPT_IR_STALE")
    return pointer, version, authority


def create_video_generation_intent(session: Any, *, shot_id: int, duration: float, aspect_ratio: str, motion_profile: Mapping[str, Any], first_frame_asset: Mapping[str, Any], last_frame_asset: Mapping[str, Any] | None, prompt_version: str) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    try:
        duration_value = float(duration)
    except (TypeError, ValueError):
        raise VideoGenerationError("duration must be numeric", code="VIDEO_DURATION_INVALID") from None
    if duration_value <= 0:
        raise VideoGenerationError("duration must be positive", code="VIDEO_DURATION_INVALID")
    ratio = str(aspect_ratio or "").strip()
    if not ratio:
        raise VideoGenerationError("aspect_ratio is required", code="VIDEO_ASPECT_RATIO_REQUIRED")
    motion = _normalize_motion_profile(motion_profile)
    sequence = session.query(KeyframeSequence).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").order_by(KeyframeSequence.revision.desc()).first()
    if sequence is None:
        raise VideoGenerationError("active keyframe sequence is required", code="VIDEO_KEYFRAME_SEQUENCE_REQUIRED")
    prompt_key = str(prompt_version or "").strip()
    prompt = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt_key).one_or_none()
    if prompt is None:
        raise VideoGenerationError("prompt_version does not identify a ProductionPromptVersion", code="VIDEO_PROMPT_LINEAGE_REQUIRED")
    first = _validate_frame_asset(session, shot=shot, asset=first_frame_asset, first=True)
    last = _validate_frame_asset(session, shot=shot, asset=last_frame_asset, first=False) if last_frame_asset else {}
    basis = {"shot_id": int(shot.id), "duration": duration_value, "aspect_ratio": ratio, "motion_profile": motion, "first_frame_asset": first, "last_frame_asset": last, "prompt_version": prompt_key}
    fingerprint = _fingerprint({"schema": "video_generation_intent_v1", **basis})
    existing = session.query(VideoGenerationIntent).filter_by(intent_fingerprint=fingerprint).one_or_none()
    if existing is not None:
        return _intent_dict(existing)
    row = VideoGenerationIntent(storyboard_shot_id=shot.id, duration=duration_value, aspect_ratio=ratio, motion_profile=_canonical(motion), first_frame_asset=_canonical(first), last_frame_asset=_canonical(last), prompt_version=prompt_key, intent_fingerprint=fingerprint, status="READY")
    session.add(row)
    session.flush()
    return _intent_dict(row)


def get_video_generation_intent(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    row = session.query(VideoGenerationIntent).filter_by(storyboard_shot_id=shot.id).order_by(VideoGenerationIntent.id.desc()).first()
    if row is None:
        raise VideoGenerationError("video generation intent does not exist", code="VIDEO_INTENT_NOT_FOUND")
    return _intent_dict(row)


def _persist_video_candidate(session: Any, execution: GenerationExecutionRecord, result: Any) -> MediaCandidateRecord:
    from api.generation_canary_api import _persist_candidate_media

    persisted = _persist_candidate_media(source_url=result.media_uri, book_id=int(execution.book_id), execution_id=str(execution.execution_id), target_media="VIDEO")
    candidate = MediaCandidateRecord(
        candidate_id="video-candidate-" + uuid.uuid4().hex,
        execution_id=execution.execution_id,
        status="MEDIA_CANDIDATE",
        media_type="VIDEO",
        storage_identity=str(persisted.get("storage_identity") or persisted.get("video_url") or ""),
        storage_reference_json=_canonical(persisted.get("storage_reference") or {}),
        metadata_json=_canonical({"media_type": "VIDEO", "mime_type": persisted.get("mime_type") or "video/mp4", "byte_size": int(persisted.get("byte_size") or 0), "width": persisted.get("width"), "height": persisted.get("height"), "duration_ms": persisted.get("duration_ms"), "provider": execution.provider, "model": execution.model}),
        checksum_sha256=str(persisted.get("checksum_sha256") or ""),
        mime_type=str(persisted.get("mime_type") or "video/mp4"),
        byte_size=int(persisted.get("byte_size") or 0),
        width=int(persisted.get("width") or result.width),
        height=int(persisted.get("height") or result.height),
        duration_ms=int(persisted.get("duration_ms") or result.duration_ms),
        prompt_ir_version_id=int(execution.prompt_ir_version_id),
        prompt_ir_payload_hash=str(execution.prompt_ir_payload_hash or ""),
        generation_payload_fingerprint=str(execution.generation_payload_fingerprint),
        model_profile_id=str(execution.model_profile_id),
        model_profile_fingerprint=str(execution.model_profile_fingerprint),
        provider_request_fingerprint=str(execution.provider_request_fingerprint),
        provider_response_hash=str(result.provider_response_hash),
        provider_task_id=str(result.provider_task_id),
        created_at=datetime.utcnow(),
    )
    session.add(candidate)
    session.flush()
    return candidate


def _execution_dict(row: GenerationExecutionRecord) -> dict[str, Any]:
    return {"execution_id": row.execution_id, "generation_type": row.generation_type, "status": row.execution_status, "target_media": row.target_media, "shot_id": row.storyboard_shot_id, "provider": row.provider, "model": row.model, "provider_task_id": row.provider_task_id, "candidate_id": row.candidate_id, "provider_calls": int(row.logical_provider_calls or 0), "request_payload": row.request_payload, "response_payload": row.response_payload}


def execute_video_generation(session: Any, *, intent_id: int, provider_id: str = "mock-video", provider_registry: VideoProviderRegistry | None = None) -> dict[str, Any]:
    intent = session.query(VideoGenerationIntent).filter_by(id=int(intent_id)).one_or_none()
    if intent is None:
        raise VideoGenerationError("video generation intent does not exist", code="VIDEO_INTENT_NOT_FOUND")
    if intent.generation_execution_id and intent.status == "SUCCEEDED":
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none()
        candidate = session.query(MediaCandidateRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none()
        return {"intent": _intent_dict(intent), "execution": _execution_dict(execution) if execution else None, "candidate": {"candidate_id": candidate.candidate_id, "media_type": candidate.media_type, "validation_status": candidate.validation_status} if candidate else None, "reused": True, "provider_calls": 0}
    shot = _resolve_shot(session, intent.storyboard_shot_id)
    first = _validate_frame_asset(session, shot=shot, asset=_obj(intent.first_frame_asset), first=True)
    last = _validate_frame_asset(session, shot=shot, asset=_obj(intent.last_frame_asset), first=False) if _obj(intent.last_frame_asset) else {}
    prompt = session.query(ProductionPromptVersion).filter_by(prompt_version_id=intent.prompt_version).one_or_none()
    if prompt is None:
        raise VideoGenerationError("prompt lineage is missing", code="VIDEO_PROMPT_LINEAGE_REQUIRED")
    pointer, prompt_ir, prompt_authority = _current_video_prompt_ir(session, shot=shot)
    payload = _obj(prompt_ir.payload_json)
    policy = payload.get("generation_policy") if isinstance(payload.get("generation_policy"), Mapping) else {"mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": float(intent.duration), "aspect_ratio": intent.aspect_ratio}
    generation_payload_fp = _fingerprint({"intent": intent.intent_fingerprint, "prompt_ir": prompt_ir.payload_hash})
    policy_fp = str(policy.get("fingerprint") or _fingerprint(policy))
    execution_id = "gex_video_" + uuid.uuid4().hex
    provider_fp = _fingerprint({"execution_id": execution_id, "intent": intent.intent_fingerprint, "provider": provider_id})
    now = datetime.utcnow()
    task_id = intent.task_id or f"video-generation-{intent.id}"
    task = session.query(TaskRun).filter_by(task_id=task_id).one_or_none()
    if task is None:
        task = TaskRun(task_id=task_id, task_kind="VIDEO_GENERATION", status="queued", progress=0, book_id=shot.book_id, episode=shot.episode, payload="{}", error="", created_at=now, updated_at=now)
        session.add(task)
    execution = GenerationExecutionRecord(execution_id=execution_id, schema_version="generation_execution_video_v1", book_id=shot.book_id, episode=shot.episode, storyboard_shot_id=shot.id, plan_shot_id=str(shot.plan_shot_id or ""), execution_mode="VIDEO_MOCK", status="CREATED", target_media="VIDEO", prompt_ir_version_id=int(prompt_ir.id), prompt_ir_authority_id=int(prompt_authority.id) if prompt_authority else 0, prompt_ir_payload_hash=str(prompt_ir.payload_hash), generation_payload_fingerprint=generation_payload_fp, generation_policy_fingerprint=policy_fp, model_profile_id="builtin-mock-video", model_profile_fingerprint=_fingerprint({"provider": provider_id, "model": "deterministic-video-v1"}), provider_adapter_id=str(provider_id), provider_adapter_version="mock-video-v1", reference_bindings_fingerprint="", provider_request_fingerprint=provider_fp, provider=provider_id, model="deterministic-video-v1", logical_provider_calls=0, transport_retry_count=0, created_at=now, updated_at=now)
    execution.request_payload = {"generation_type": "VIDEO", "video_intent_id": int(intent.id), "prompt_version": intent.prompt_version, "prompt_text": prompt.prompt_text, "motion_profile": _obj(intent.motion_profile), "first_frame_asset": first, "last_frame_asset": last, "generation_policy": policy, "media_role": "SHOT_PRIMARY_VIDEO"}
    session.add(execution)
    intent.generation_execution_id = execution_id
    intent.task_id = task_id
    intent.status = "EXECUTING"
    task.status = "running"
    task.progress = 10
    task.payload = _canonical({"intent_id": intent.id, "execution_id": execution_id, "generation_type": "VIDEO"})
    session.flush()
    service = GenerationExecutionService(session)
    try:
        service.transition(execution_id, "QUEUED")
        service.transition(execution_id, "RUNNING")
        provider = (provider_registry or DEFAULT_VIDEO_PROVIDER_REGISTRY).resolve(provider_id)
        result = provider.generate_video(prompt=prompt.prompt_text, motion_profile=_obj(intent.motion_profile), duration=float(intent.duration), aspect_ratio=intent.aspect_ratio, first_frame_asset=first, last_frame_asset=last, request_context={"intent_id": intent.id, "shot_id": shot.id})
        execution.provider = result.provider
        execution.model = result.model
        execution.provider_request_id = result.provider_request_id
        execution.provider_task_id = result.provider_task_id
        execution.provider_response_hash = result.provider_response_hash
        execution.logical_provider_calls = int(result.logical_provider_calls)
        execution.request_payload = {**execution.request_payload, "provider_request": dict(result.provider_request)}
        service.transition(execution_id, "PROVIDER_CALLED", response_payload={"provider_response": dict(result.provider_response), "media_type": "VIDEO"})
        candidate = _persist_video_candidate(session, execution, result)
        execution.candidate_id = candidate.candidate_id
        service.transition(execution_id, "SUCCESS", response_payload={"provider_response": dict(result.provider_response), "candidate_id": candidate.candidate_id, "media_type": "VIDEO"})
        validation = validate_media_candidate(session, candidate.candidate_id)
        intent.status = "SUCCEEDED"
        task.status = "completed"
        task.progress = 100
        task.finished_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        session.commit()
        return {"intent": _intent_dict(intent), "execution": _execution_dict(execution), "candidate": {"candidate_id": candidate.candidate_id, "media_type": candidate.media_type, "storage_identity": candidate.storage_identity, "duration_ms": candidate.duration_ms, "validation_status": candidate.validation_status}, "validation": {"validation_id": validation["validation_id"], "status": validation["validation"].status, "promotion_id": getattr(validation.get("promotion"), "promotion_id", None)}, "reused": False, "provider_calls": int(result.logical_provider_calls), "official_media_ready": False}
    except (VideoProviderError, MediaAuthorityError, Exception) as exc:
        intent.status = "FAILED"
        task.status = "failed"
        task.error = str(getattr(exc, "message", exc))
        task.updated_at = datetime.utcnow()
        if execution.execution_status in {"RUNNING", "PROVIDER_CALLED"}:
            try:
                service.transition(execution_id, "FAILED", error_message=str(getattr(exc, "message", exc)))
            except Exception:
                pass
        session.commit()
        if isinstance(exc, VideoGenerationError):
            raise
        raise VideoGenerationError("video generation failed", code=getattr(exc, "code", "VIDEO_GENERATION_FAILED"), diagnostics={"error": str(exc)}) from exc


__all__ = ["VideoGenerationError", "create_video_generation_intent", "get_video_generation_intent", "execute_video_generation"]
