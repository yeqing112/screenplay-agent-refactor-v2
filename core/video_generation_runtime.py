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
from core.video_provider_adapter import DEFAULT_VIDEO_PROVIDER_REGISTRY, MinimaxH3VideoProvider, MockVideoProvider, VideoProviderError, VideoProviderRegistry
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


def _text(value: Any) -> str:
    return str(value or "").strip()


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
    value.update({"keyframe_id": int(frame.id), "sequence_id": int(sequence.id), "binding_id": int(primary.id), "binding_fingerprint": primary.binding_fingerprint, "asset_type": primary.asset_type, "authority_id": primary.authority_id, "version_id": primary.version_id, "keyframe_motion_profile": {"camera_motion": str(frame.camera_motion or "").strip(), "subject_motion": str(frame.character_motion or "").strip(), "environment_motion": str(frame.environment_motion or "").strip(), "emotion_transition": str(frame.emotion_transition or "").strip()}})
    # Resolve the current typed Production Asset Version so a real provider
    # receives the authoritative keyframe bytes/URL rather than a UI supplied
    # path.  Keep the identity in the request projection; secrets never enter
    # this mapping.
    try:
        from core.production_asset_authority import resolve_current_production_asset_binding
        resolved = resolve_current_production_asset_binding(session, primary)
        version = resolved.get("version")
        value["storage_identity"] = str(getattr(version, "storage_identity", "") or "")
        value["asset_checksum"] = str(getattr(version, "checksum", "") or "")
        value["asset_metadata_hash"] = str(getattr(version, "metadata_hash", "") or "")
        value["asset_authority_current"] = bool(resolved.get("current"))
    except VideoGenerationError:
        raise
    except Exception as exc:
        raise VideoGenerationError("frame asset authority/version could not be resolved", code="VIDEO_FRAME_ASSET_NOT_CURRENT", diagnostics=[{"error": str(exc)}]) from exc
    if first and not value.get("storage_identity"):
        raise VideoGenerationError("first frame asset has no durable storage identity", code="VIDEO_FIRST_FRAME_URL_REQUIRED")
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


def _current_shot_direction(session: Any, *, shot: StoryboardShot) -> dict[str, Any]:
    """Resolve the active Shot Direction used by a real video canary."""
    from core.shot_direction import validate_shot_direction

    validation = validate_shot_direction(session, shot_id=shot.id)
    if validation.get("status") != "PASS" or not isinstance(validation.get("direction"), Mapping):
        raise VideoGenerationError(
            "a valid current Shot Direction is required for a real video canary",
            code="VIDEO_SHOT_DIRECTION_REQUIRED",
            diagnostics=validation.get("errors") or [],
        )
    direction = dict(validation["direction"])
    return {
        "id": int(direction.get("id") or 0),
        "shot_id": int(direction.get("shot_id") or shot.id),
        "revision": int(direction.get("revision") or 0),
        "direction_fingerprint": str(direction.get("direction_fingerprint") or ""),
        "shot_type": str(direction.get("shot_type") or ""),
        "camera_profile": dict(direction.get("camera_profile") or {}),
        "movement_profile": dict(direction.get("movement_profile") or {}),
        "composition_profile": dict(direction.get("composition_profile") or {}),
        "performance_profile": dict(direction.get("performance_profile") or {}),
        "emotion_profile": dict(direction.get("emotion_profile") or {}),
    }


def _shot_direction_motion_profile(direction: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
    """Project the authoritative Shot Direction into the provider motion contract."""
    camera = direction.get("camera_profile") if isinstance(direction.get("camera_profile"), Mapping) else {}
    movement = direction.get("movement_profile") if isinstance(direction.get("movement_profile"), Mapping) else {}
    performance = direction.get("performance_profile") if isinstance(direction.get("performance_profile"), Mapping) else {}
    emotion = direction.get("emotion_profile") if isinstance(direction.get("emotion_profile"), Mapping) else {}
    base = dict(fallback or {})
    projected = {
        "camera_motion": str(camera.get("movement") or movement.get("camera_motion") or base.get("camera_motion") or "").strip(),
        "subject_motion": str(performance.get("body_motion") or performance.get("gesture") or movement.get("subject_motion") or base.get("subject_motion") or "").strip(),
        "environment_motion": str(movement.get("environment_motion") or movement.get("trajectory") or movement.get("stabilization") or base.get("environment_motion") or "").strip(),
        "emotion_transition": str(emotion.get("transition") or emotion.get("arc") or base.get("emotion_transition") or "").strip(),
        "source": "SHOT_DIRECTION",
        "direction_fingerprint": str(direction.get("direction_fingerprint") or ""),
    }
    return projected


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
        metadata_json=_canonical({"media_type": "VIDEO", "mime_type": persisted.get("mime_type") or "video/mp4", "byte_size": int(persisted.get("byte_size") or 0), "width": persisted.get("width"), "height": persisted.get("height"), "duration_ms": persisted.get("duration_ms"), "provider": execution.provider, "model": execution.model, "shot_video_lineage": _obj(execution.request_payload).get("shot_video_lineage", {})}),
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


def get_video_generation_status(session: Any, *, intent_id: int) -> dict[str, Any]:
    """Read the intent/execution/candidate lineage without triggering work."""
    intent = session.query(VideoGenerationIntent).filter_by(id=int(intent_id)).one_or_none()
    if intent is None:
        raise VideoGenerationError("video generation intent does not exist", code="VIDEO_INTENT_NOT_FOUND")
    execution = session.query(GenerationExecutionRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none() if intent.generation_execution_id else None
    candidate = session.query(MediaCandidateRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none() if intent.generation_execution_id else None
    validation = None
    promotion = None
    if candidate is not None:
        from models import MediaValidationRecord, MediaPromotionRecord
        validation = session.query(MediaValidationRecord).filter_by(candidate_id=candidate.candidate_id).order_by(MediaValidationRecord.id.desc()).first()
        promotion = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).first()
    return {
        "intent": _intent_dict(intent),
        "execution": _execution_dict(execution) if execution else None,
        "candidate": {"candidate_id": candidate.candidate_id, "media_type": candidate.media_type, "validation_status": candidate.validation_status, "storage_identity": candidate.storage_identity} if candidate else None,
        "validation": {"validation_id": validation.validation_id, "status": validation.status} if validation else None,
        "promotion": {"promotion_id": promotion.promotion_id, "review_status": promotion.review_status, "official_media_version_id": promotion.official_media_version_id} if promotion else None,
        "official_media_ready": bool(promotion and promotion.official_media_version_id),
    }


def _resolve_video_provider(*, provider_id: str, model_profile_id: str | None, provider_registry: VideoProviderRegistry | None) -> tuple[Any, str, dict[str, Any]]:
    """Resolve a provider from the existing Model Registry, never a new config."""
    requested = str(provider_id or "mock-video").strip().lower() or "mock-video"
    registry = provider_registry or DEFAULT_VIDEO_PROVIDER_REGISTRY
    # An explicit profile id must be allowed to select the real provider even
    # when the backward-compatible provider_id default is still mock-video.
    if not (requested == "mock-video" and model_profile_id):
        try:
            provider = registry.resolve(requested)
            return provider, "builtin-mock-video" if requested == "mock-video" else str(model_profile_id or requested), {"provider": requested, "model_name": "deterministic-video-v1", "capability": "video", "id": str(model_profile_id or "builtin-mock-video"), "enabled": True}
        except VideoProviderError:
            pass
    from api.model_registry import get_default_profile, get_profile
    profile = get_profile(model_profile_id or (requested if requested not in {"mock-video", "minimax-h3-async"} else None))
    if profile is None:
        profile = get_default_profile("video")
    if profile is None:
        raise VideoGenerationError("video Model Registry profile does not exist", code="VIDEO_MODEL_PROFILE_NOT_FOUND")
    profile_provider = str(profile.get("provider") or "").strip().lower()
    if requested not in {"mock-video", profile_provider, str(profile.get("id") or "").strip().lower()}:
        raise VideoGenerationError("provider_id does not match the selected video Model Registry profile", code="VIDEO_PROVIDER_PROFILE_MISMATCH", diagnostics=[{"provider_id": requested, "profile_provider": profile_provider, "profile_id": profile.get("id")}])
    if profile_provider != "minimax-h3-async":
        raise VideoGenerationError("selected video provider is not enabled for this canary", code="VIDEO_PROVIDER_NOT_ENABLED")
    return MinimaxH3VideoProvider(profile), str(profile.get("id") or model_profile_id or ""), profile


def _strict_video_lineage(intent: VideoGenerationIntent) -> dict[str, Any]:
    value = _obj(intent.motion_profile).get("orchestration_lineage")
    return dict(value) if isinstance(value, Mapping) else {}


def _reused_execution_result(session: Any, intent: VideoGenerationIntent, execution: GenerationExecutionRecord, *, provider_calls: int = 0) -> dict[str, Any]:
    candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one_or_none()
    return {"intent": _intent_dict(intent), "execution": _execution_dict(execution), "candidate": {"candidate_id": candidate.candidate_id, "media_type": candidate.media_type, "validation_status": candidate.validation_status} if candidate else None, "reused": True, "provider_calls": int(provider_calls)}


def execute_video_generation(session: Any, *, intent_id: int, provider_id: str = "mock-video", model_profile_id: str | None = None, provider_registry: VideoProviderRegistry | None = None) -> dict[str, Any]:
    intent = session.query(VideoGenerationIntent).filter_by(id=int(intent_id)).one_or_none()
    if intent is None:
        raise VideoGenerationError("video generation intent does not exist", code="VIDEO_INTENT_NOT_FOUND")
    if intent.generation_execution_id and intent.status == "SUCCEEDED":
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none()
        if execution is not None:
            return _reused_execution_result(session, intent, execution)
    shot = _resolve_shot(session, intent.storyboard_shot_id)
    provider, resolved_profile_id, resolved_profile = _resolve_video_provider(provider_id=provider_id, model_profile_id=model_profile_id, provider_registry=provider_registry)
    first = _validate_frame_asset(session, shot=shot, asset=_obj(intent.first_frame_asset), first=True)
    last = _validate_frame_asset(session, shot=shot, asset=_obj(intent.last_frame_asset), first=False) if _obj(intent.last_frame_asset) else {}
    if not isinstance(provider, MockVideoProvider) and not first.get("asset_authority_current"):
        raise VideoGenerationError("first frame asset authority/version is stale", code="VIDEO_FRAME_ASSET_NOT_CURRENT", diagnostics=[{"keyframe_id": first.get("keyframe_id")}])
    is_mock = isinstance(provider, MockVideoProvider) or str(resolved_profile.get("provider") or provider_id) == "mock-video"
    intent_motion_profile = _obj(intent.motion_profile)
    shot_direction = {} if is_mock else _current_shot_direction(session, shot=shot)
    provider_motion_profile = intent_motion_profile if is_mock else _shot_direction_motion_profile(shot_direction, intent_motion_profile)
    prompt = session.query(ProductionPromptVersion).filter_by(prompt_version_id=intent.prompt_version).one_or_none()
    if prompt is None:
        raise VideoGenerationError("prompt lineage is missing", code="VIDEO_PROMPT_LINEAGE_REQUIRED")
    pointer, prompt_ir, prompt_authority = _current_video_prompt_ir(session, shot=shot)
    payload = _obj(prompt_ir.payload_json)
    policy = payload.get("generation_policy") if isinstance(payload.get("generation_policy"), Mapping) else {"mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": float(intent.duration), "aspect_ratio": intent.aspect_ratio}
    generation_payload_fp = _fingerprint({"intent": intent.intent_fingerprint, "prompt_ir": prompt_ir.payload_hash})
    policy_fp = str(policy.get("fingerprint") or _fingerprint(policy))
    strict_lineage = _strict_video_lineage(intent)
    if strict_lineage:
        # Reconcile is deterministic, but an API caller may hold an intent
        # while an upstream authority is revised.  Fail before creating or
        # submitting a paid execution in that case.
        try:
            from core.shot_video_production import _source_context
            current_context = _source_context(session, int(shot.id), provider_id=provider_id, model_profile_id=model_profile_id)
            if str(current_context.get("source_fingerprint") or "") != str(strict_lineage.get("base_source_fingerprint") or ""):
                raise VideoGenerationError("video source is stale before execution", code="STALE_SOURCE", diagnostics=[{"expected": strict_lineage.get("base_source_fingerprint"), "actual": current_context.get("source_fingerprint")}])
        except ImportError:
            pass
    provider_fp = str(strict_lineage.get("execution_fingerprint") or "")
    if not provider_fp:
        provider_fp = _fingerprint({"intent": intent.intent_fingerprint, "provider": resolved_profile.get("provider") or provider_id, "model_profile_id": resolved_profile_id, "transport_binding_id": resolved_profile.get("transport_binding_id") or ""})
    existing_execution = session.query(GenerationExecutionRecord).filter_by(provider_request_fingerprint=provider_fp).one_or_none()
    if existing_execution is not None and existing_execution.execution_status in ACTIVE_EXECUTION_STATUSES | {"SUCCESS", "STALE"}:
        return _reused_execution_result(session, intent, existing_execution)
    execution_id = "gex_video_" + uuid.uuid4().hex
    now = datetime.utcnow()
    task_id = intent.task_id or f"video-generation-{intent.id}"
    task = session.query(TaskRun).filter_by(task_id=task_id).one_or_none()
    if task is None:
        task = TaskRun(task_id=task_id, task_kind="VIDEO_GENERATION", status="queued", progress=0, book_id=shot.book_id, episode=shot.episode, payload="{}", error="", created_at=now, updated_at=now)
        session.add(task)
    execution = GenerationExecutionRecord(execution_id=execution_id, schema_version="generation_execution_video_v1", book_id=shot.book_id, episode=shot.episode, storyboard_shot_id=shot.id, plan_shot_id=str(shot.plan_shot_id or ""), execution_mode="VIDEO_MOCK" if is_mock else "VIDEO_PROVIDER_CANARY", status="CREATED", target_media="VIDEO", prompt_ir_version_id=int(prompt_ir.id), prompt_ir_authority_id=int(prompt_authority.id) if prompt_authority else 0, prompt_ir_payload_hash=str(prompt_ir.payload_hash), generation_payload_fingerprint=generation_payload_fp, generation_policy_fingerprint=policy_fp, model_profile_id=resolved_profile_id, model_profile_fingerprint=_fingerprint({key: resolved_profile.get(key) for key in ("id", "provider", "base_url", "model_name", "transport_binding_id")}), provider_adapter_id=str(getattr(provider, "adapter_id", provider_id)), provider_adapter_version=str(getattr(provider, "adapter_version", "")), reference_bindings_fingerprint="", provider_request_fingerprint=provider_fp, provider=str(resolved_profile.get("provider") or provider_id), model=str(resolved_profile.get("model_name") or "deterministic-video-v1"), logical_provider_calls=0, transport_retry_count=0, created_at=now, updated_at=now)
    prompt_text = _text(payload.get("prompt") or payload.get("prompt_text") or _obj(payload.get("request")).get("prompt") or prompt.prompt_text)
    execution.request_payload = {"generation_type": "VIDEO", "video_intent_id": int(intent.id), "prompt_version": intent.prompt_version, "prompt_text": prompt_text, "prompt_authority": {"pointer_id": int(pointer.id), "version_id": int(prompt_ir.id), "payload_hash": str(prompt_ir.payload_hash), "authority_id": int(prompt_authority.id) if prompt_authority else None}, "motion_profile": provider_motion_profile, "intent_motion_profile": intent_motion_profile, "motion_source": "SHOT_DIRECTION" if not is_mock else "VIDEO_GENERATION_INTENT", "shot_direction": shot_direction, "first_frame_asset": first, "last_frame_asset": last, "generation_policy": policy, "media_role": "SHOT_PRIMARY_VIDEO", "shot_video_lineage": strict_lineage}
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
        result = provider.generate_video(prompt=prompt_text, motion_profile=provider_motion_profile, duration=float(intent.duration), aspect_ratio=intent.aspect_ratio, first_frame_asset=first, last_frame_asset=last, request_context={"intent_id": intent.id, "shot_id": shot.id, "episode": shot.episode, "canary_scope": f"episode:{shot.episode}:shot:{shot.id}", "shot_direction": shot_direction, "_runtime_profile": resolved_profile})
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
        if strict_lineage:
            # The adapter owns submit/poll.  Re-read every authority after its
            # terminal response before technical validation; a changed
            # keyframe, direction, prompt, or materialization keeps the
            # candidate as history but makes the execution non-current.
            from core.shot_video_production import current_source_for_execution
            current = current_source_for_execution(session, execution)
            if not current.get("current"):
                execution.status = "STALE"
                execution.response_payload = {**execution.response_payload, "stale_guard": current}
                intent.status = "FAILED"
                task.status = "failed"
                task.error = "video source changed during generation"
                task.updated_at = datetime.utcnow()
                session.commit()
                raise VideoGenerationError("video source changed during generation; candidate retained and promotion blocked", code="STALE_SOURCE", diagnostics=current.get("reasons") or [])
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


__all__ = ["VideoGenerationError", "create_video_generation_intent", "get_video_generation_intent", "get_video_generation_status", "execute_video_generation"]
