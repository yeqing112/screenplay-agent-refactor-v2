"""Single-shot video production orchestration over the existing runtimes.

This module is intentionally a boundary layer.  It reconciles the current
Storyboard/ShotDirection/Keyframe/Prompt authorities into the existing
``VideoGenerationIntent`` and delegates execution, validation, review, and
promotion to the already shipped runtime services.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from api.model_registry import get_default_profile, get_profile
from core.automatic_keyframe_authoring import get_keyframe_plan
from core.production_asset_authority import resolve_current_production_asset_binding
from core.shot_direction import validate_shot_direction
from core.video_generation_runtime import (
    VideoGenerationError,
    _current_video_prompt_ir,
    _validate_frame_asset,
    execute_video_generation,
    get_video_generation_status,
)
from models import (
    AutomaticKeyframePlan,
    GenerationExecutionRecord,
    Keyframe,
    KeyframeAssetBinding,
    KeyframeSequence,
    MediaCandidateRecord,
    MediaPromotionRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    ProductionGenerationIntent,
    ProductionPromptVersion,
    PromptIRPointer,
    PromptIRVersion,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardShot,
    TaskRun,
    VideoGenerationIntent,
)


SCHEMA_VERSION = "shot_video_production_orchestration_v1"
ACTIVE_EXECUTION_STATUSES = frozenset({"CREATED", "QUEUED", "RUNNING", "PROVIDER_PENDING", "PROVIDER_CALLED"})
REVIEW_REJECTED = frozenset({"REJECTED", "REQUEST_CHANGE"})


class ShotVideoProductionError(VideoGenerationError):
    """Stable error surface for shot-scoped production eligibility."""


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
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise ShotVideoProductionError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def _active_materialization(session: Any, shot: StoryboardShot) -> tuple[StoryboardMaterializationSet, StoryboardMaterializationPointer]:
    if _text(shot.materialization_status).upper() not in {"MATERIALIZED", "ACTIVE"}:
        raise ShotVideoProductionError("StoryboardShot is not active", code="VIDEO_SHOT_NOT_ACTIVE")
    if shot.materialization_set_id is None or not _text(shot.scene_id):
        raise ShotVideoProductionError("current StoryboardMaterializationPointer is required", code="VIDEO_MATERIALIZATION_REQUIRED")
    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), scene_id=str(shot.scene_id)).one_or_none()
    if pointer is None:
        raise ShotVideoProductionError("current StoryboardMaterializationPointer is required", code="VIDEO_MATERIALIZATION_POINTER_REQUIRED")
    materialization = session.query(StoryboardMaterializationSet).filter_by(id=int(pointer.materialization_set_id)).one_or_none()
    if materialization is None or int(materialization.id) != int(shot.materialization_set_id):
        raise ShotVideoProductionError("StoryboardShot materialization is not current", code="VIDEO_MATERIALIZATION_STALE")
    if _text(materialization.status).upper() != "MATERIALIZED" or _text(materialization.stale_status).upper() != "FRESH":
        raise ShotVideoProductionError("Storyboard materialization is stale", code="VIDEO_MATERIALIZATION_STALE")
    if _text(pointer.qualification_state).upper() not in {"MATERIALIZED", "QUALIFIED", "ACTIVE"}:
        raise ShotVideoProductionError("Storyboard materialization pointer is not current", code="VIDEO_MATERIALIZATION_POINTER_STALE")
    if _text(pointer.set_payload_fingerprint) != _text(materialization.set_payload_fingerprint):
        raise ShotVideoProductionError("Storyboard materialization fingerprint is stale", code="VIDEO_MATERIALIZATION_POINTER_STALE")
    return materialization, pointer


def _current_direction(session: Any, shot: StoryboardShot) -> dict[str, Any]:
    result = validate_shot_direction(session, shot_id=int(shot.id))
    if result.get("status") != "PASS" or not isinstance(result.get("direction"), Mapping):
        raise ShotVideoProductionError("current ShotDirection is required", code="VIDEO_SHOT_DIRECTION_REQUIRED", diagnostics=result.get("errors") or [])
    return dict(result["direction"])


def _current_keyframe_plan(session: Any, shot: StoryboardShot, sequence: KeyframeSequence) -> dict[str, Any]:
    try:
        plan = get_keyframe_plan(session, shot_id=int(shot.id))
    except Exception as exc:
        raise ShotVideoProductionError("current AutomaticKeyframePlan is required", code="VIDEO_KEYFRAME_PLAN_REQUIRED", diagnostics=[{"error": str(exc)}]) from exc
    status = _text(plan.get("status")).upper()
    if status == "STALE":
        raise ShotVideoProductionError("AutomaticKeyframePlan is stale", code="STALE_SOURCE", diagnostics=plan.get("stale_reasons") or [])
    if status != "COMPILED" or int(plan.get("compiled_sequence_id") or 0) != int(sequence.id):
        raise ShotVideoProductionError("compiled current AutomaticKeyframePlan is required", code="VIDEO_KEYFRAME_PLAN_NOT_COMPILED", diagnostics=[{"status": status, "sequence_id": sequence.id, "compiled_sequence_id": plan.get("compiled_sequence_id")}])
    return plan


def _current_production_intent(session: Any, shot: StoryboardShot) -> ProductionGenerationIntent:
    rows = session.query(ProductionGenerationIntent).filter_by(shot_id=int(shot.id)).order_by(ProductionGenerationIntent.id.desc()).all()
    intent = rows[0] if rows else None
    if intent is None:
        raise ShotVideoProductionError("production GenerationIntent is required", code="VIDEO_GENERATION_INTENT_REQUIRED")
    constraints = _obj(intent.constraint_snapshot)
    if constraints.get("production_eligible") is False:
        raise ShotVideoProductionError("GenerationIntent is not production eligible", code="VIDEO_GENERATION_INTENT_INELIGIBLE")
    if not _text(intent.shot_requirement_fingerprint):
        raise ShotVideoProductionError("GenerationIntent fingerprint is missing", code="VIDEO_GENERATION_INTENT_INVALID")
    return intent


def _profile(provider_id: str, model_profile_id: str | None) -> dict[str, Any]:
    if model_profile_id:
        profile = get_profile(model_profile_id)
    elif provider_id == "mock-video":
        # The execution runtime resolves the default mock provider to the
        # built-in mock profile.  Resolve the same identity while building
        # the source fingerprint so the strict stale guard compares one
        # stable Model Registry projection before and after execution.
        profile = get_profile("builtin-mock-video")
    elif provider_id and provider_id != "minimax-h3-async":
        profile = get_profile(provider_id)
    else:
        profile = get_default_profile("video")
    if profile is None and provider_id == "mock-video":
        profile = {"id": "builtin-mock-video", "provider": "prototype-task-adapter", "model_name": "mock-video-v1", "capability": "video", "enabled": True, "uses_mock": True, "transport_binding_id": "prototype-task-adapter.video.v1"}
    if profile is None:
        raise ShotVideoProductionError("video Model Registry profile does not exist", code="VIDEO_MODEL_PROFILE_NOT_FOUND")
    if not bool(profile.get("enabled", True)):
        raise ShotVideoProductionError("video Model Registry profile is disabled", code="VIDEO_MODEL_PROFILE_DISABLED")
    if _text(profile.get("capability")).lower() != "video":
        raise ShotVideoProductionError("selected Model Registry profile is not a video model", code="VIDEO_MODEL_CAPABILITY_INVALID")
    return dict(profile)


def _capabilities(profile: Mapping[str, Any]) -> dict[str, bool]:
    declared = profile.get("video_capabilities") or profile.get("capabilities") or {}
    if not isinstance(declared, Mapping):
        declared = {}
    provider = _text(profile.get("provider")).lower()
    # The existing adapter contract is the fallback for the shipped profiles;
    # an explicit registry flag always wins and can disable a capability.
    return {
        "image_to_video": bool(declared.get("image_to_video", profile.get("supports_image_to_video", True))),
        "first_frame": bool(declared.get("first_frame", profile.get("supports_first_frame", True))),
        "last_frame": bool(declared.get("last_frame", profile.get("supports_last_frame", provider in {"minimax-h3-async", "75api-minimax-h3", "poyo-async", "prototype-task-adapter"}))),
        "duration": bool(declared.get("duration", profile.get("supports_duration", True))),
        "aspect_ratio": bool(declared.get("aspect_ratio", profile.get("supports_aspect_ratio", True))),
    }


def _prompt_text(prompt_ir: PromptIRVersion) -> str:
    payload = _obj(prompt_ir.payload_json)
    candidates: list[Any] = [
        payload.get("prompt"), payload.get("prompt_text"), payload.get("visual_prompt_motion"),
        _obj(payload.get("request")).get("prompt"), _obj(payload.get("generation_payload")).get("prompt"),
        _obj(payload.get("verbalization")).get("prompt"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _production_prompt(session: Any, plan: Mapping[str, Any], shot: StoryboardShot) -> ProductionPromptVersion:
    prompt_id = _text(plan.get("production_prompt_version_id"))
    row = session.query(ProductionPromptVersion).filter_by(prompt_version_id=prompt_id).one_or_none() if prompt_id else None
    if row is not None:
        latest = session.query(ProductionPromptVersion).filter_by(prompt_id=row.prompt_id).order_by(ProductionPromptVersion.version_number.desc()).first()
        return latest or row
    # Legacy fixtures can carry only a shot lineage.  This fallback remains a
    # lineage lookup; it does not make ProductionPromptVersion the executable
    # authority, which is always the VIDEO PromptIR pointer below.
    for candidate in session.query(ProductionPromptVersion).order_by(ProductionPromptVersion.id.desc()).all():
        structure = _obj(candidate.prompt_structure)
        lineage = _obj(candidate.storyboard_lineage)
        if str(structure.get("storyboard_shot_id")) == str(shot.id) or str(lineage.get("storyboard_shot_id")) == str(shot.id):
            return candidate
    raise ShotVideoProductionError("ProductionPromptVersion lineage is required", code="VIDEO_PROMPT_LINEAGE_REQUIRED")


def _official_asset(session: Any, *, shot: StoryboardShot, frame: Keyframe, asset: Mapping[str, Any]) -> dict[str, Any]:
    """Require a current OfficialMedia image behind a KeyframeAssetBinding."""
    binding = session.query(KeyframeAssetBinding).filter_by(id=int(asset.get("binding_id") or 0), status="ACTIVE").one_or_none()
    if binding is None:
        raise ShotVideoProductionError("current KeyframeAssetBinding is required", code="VIDEO_KEYFRAME_ASSET_BINDING_REQUIRED")
    resolved = resolve_current_production_asset_binding(session, binding)
    # KeyframeAssetBinding has an intentional frame-scoped fingerprint schema
    # (it includes keyframe_id), while the shared H2 resolver exposes the
    # shot-scoped binding check as ``binding_fingerprint``.  The keyframe
    # runtime already treats that one field as its own authority boundary.
    failed_checks = [item for item in (resolved.get("failed_checks") or []) if item != "binding_fingerprint"]
    if failed_checks:
        raise ShotVideoProductionError("KeyframeAssetBinding is stale", code="VIDEO_KEYFRAME_ASSET_STALE", diagnostics=failed_checks or resolved.get("diagnostics") or [])
    version = resolved.get("version")
    storage_identity = _text(getattr(version, "storage_identity", ""))
    candidates = session.query(OfficialMediaVersion).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), media_type="IMAGE").all()
    official = next((row for row in candidates if _text(row.storage_identity) == storage_identity and _text(row.status).upper() == "CURRENT"), None)
    if official is None:
        # Keyframe image approval bridges the OfficialMedia version into the
        # typed Production Asset Authority.  The bridge intentionally keeps
        # the asset storage identity independent; recover the exact official
        # version from the immutable bridge URL/authority projection.
        authority_row = resolved.get("authority")
        token = storage_identity.rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        official_id = token if token.startswith("omv-") else ""
        official = next((row for row in candidates if _text(row.official_media_version_id) == official_id and _text(row.status).upper() == "CURRENT"), None)
    if official is None:
        raise ShotVideoProductionError("Keyframe asset is not a current OfficialMedia image", code="VIDEO_OFFICIAL_KEYFRAME_REQUIRED", diagnostics=[{"keyframe_id": frame.id, "storage_identity": storage_identity}])
    authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=official.official_media_version_id, status="CURRENT").one_or_none()
    if authority is None:
        raise ShotVideoProductionError("Official keyframe authority is missing or stale", code="VIDEO_OFFICIAL_KEYFRAME_REQUIRED")
    pointer = session.query(OfficialMediaPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), media_role=str(official.media_role)).one_or_none()
    if pointer is None:
        raise ShotVideoProductionError("Official keyframe pointer is missing", code="VIDEO_OFFICIAL_KEYFRAME_POINTER_REQUIRED")
    return {"keyframe_id": int(frame.id), "binding_id": int(binding.id), "binding_fingerprint": binding.binding_fingerprint, "asset_authority_id": binding.authority_id, "asset_version_id": binding.version_id, "asset_authority_current": True, "storage_identity": storage_identity, "official_media_version_id": official.official_media_version_id, "official_media_authority_id": authority.authority_id, "official_media_role": official.media_role, "official_pointer_fingerprint": pointer.fingerprint, "checksum_sha256": official.checksum_sha256, "source_prompt_ir_version_id": int(official.prompt_ir_version_id), "source_prompt_ir_payload_hash": official.prompt_ir_payload_hash}


def _frames(session: Any, shot: StoryboardShot, sequence: KeyframeSequence, *, require_end: bool) -> tuple[Keyframe, Keyframe, dict[str, Any], dict[str, Any]]:
    frames = session.query(Keyframe).filter_by(keyframe_sequence_id=int(sequence.id), status="ACTIVE").order_by(Keyframe.time_seconds.asc(), Keyframe.order_index.asc()).all()
    start = next((row for row in frames if _text(row.frame_type).lower() == "start"), None)
    end = next((row for row in frames if _text(row.frame_type).lower() == "end"), None)
    if start is None or abs(float(start.time_seconds or 0)) > 1e-6:
        raise ShotVideoProductionError("active START keyframe is required", code="VIDEO_START_KEYFRAME_REQUIRED")
    if end is None and require_end:
        raise ShotVideoProductionError("current video capability requires an END keyframe", code="VIDEO_END_KEYFRAME_REQUIRED")
    if end is not None and abs(float(end.time_seconds or 0) - float(sequence.duration or 0)) > 1e-6:
        raise ShotVideoProductionError("END keyframe does not match sequence duration", code="VIDEO_END_KEYFRAME_INVALID")
    first = _validate_frame_asset(session, shot=shot, asset={"keyframe_id": start.id}, first=True)
    start_official = _official_asset(session, shot=shot, frame=start, asset=first)
    end_official: dict[str, Any] = {}
    if end is not None:
        last = _validate_frame_asset(session, shot=shot, asset={"keyframe_id": end.id}, first=False)
        end_official = _official_asset(session, shot=shot, frame=end, asset=last)
    return start, end, {**first, **start_official}, {**end_official, "keyframe_id": int(end.id)} if end is not None else {}


def _source_context(session: Any, shot_id: int, *, provider_id: str = "mock-video", model_profile_id: str | None = None) -> dict[str, Any]:
    shot = _resolve_shot(session, int(shot_id))
    materialization, materialization_pointer = _active_materialization(session, shot)
    direction = _current_direction(session, shot)
    sequence = session.query(KeyframeSequence).filter_by(storyboard_shot_id=int(shot.id), status="ACTIVE").order_by(KeyframeSequence.revision.desc()).first()
    if sequence is None:
        raise ShotVideoProductionError("active KeyframeSequence is required", code="VIDEO_KEYFRAME_SEQUENCE_REQUIRED")
    plan = _current_keyframe_plan(session, shot, sequence)
    generation_intent = _current_production_intent(session, shot)
    profile = _profile(provider_id, model_profile_id)
    capabilities = _capabilities(profile)
    start, end, start_asset, end_asset = _frames(session, shot, sequence, require_end=capabilities["last_frame"])
    pointer, prompt_ir, prompt_authority = _current_video_prompt_ir(session, shot=shot)
    if prompt_authority is None or _text(prompt_authority.stale_status).upper() != "FRESH" or _text(prompt_ir.stale_status).upper() != "FRESH":
        raise ShotVideoProductionError("current VIDEO PromptIR authority is stale", code="VIDEO_PROMPT_IR_STALE")
    if _text(prompt_ir.qualification_state).upper() not in {"PROMPT_IR_QUALIFIED", "QUALIFIED"}:
        raise ShotVideoProductionError("current VIDEO PromptIR is not qualified", code="VIDEO_PROMPT_IR_INELIGIBLE")
    prompt = _production_prompt(session, plan, shot)
    prompt_text = _prompt_text(prompt_ir)
    if not prompt_text:
        prompt_text = _text(prompt.prompt_text)
    if not prompt_text:
        raise ShotVideoProductionError("current VIDEO PromptIR has no executable prompt projection", code="VIDEO_PROMPT_IR_EMPTY")
    motion = {
        "camera_motion": _text(_obj(direction.get("movement_profile")).get("camera_motion") or _obj(direction.get("camera_profile")).get("movement") or end.character_motion if end else start.camera_motion),
        "subject_motion": _text(end.character_motion if end else start.character_motion),
        "environment_motion": _text(end.environment_motion if end else start.environment_motion),
        "emotion_transition": _text(end.emotion_transition if end else start.emotion_transition),
    }
    for key, value in motion.items():
        if not value:
            raise ShotVideoProductionError("Shot video motion profile is incomplete", code="VIDEO_MOTION_PROFILE_INCOMPLETE", diagnostics=[{"missing": key}])
    aspect_ratio = _text(_obj(shot.meta_info).get("aspect_ratio") or "16:9")
    if not capabilities["aspect_ratio"] and aspect_ratio:
        raise ShotVideoProductionError("selected video model does not support aspect ratio", code="VIDEO_CAPABILITY_UNSUPPORTED")
    basis = {
        "schema_version": SCHEMA_VERSION,
        "storyboard_materialization": {"set_id": int(materialization.id), "set_fingerprint": materialization.set_payload_fingerprint, "pointer_id": int(materialization_pointer.id), "pointer_fingerprint": materialization_pointer.set_payload_fingerprint},
        "storyboard_shot": {"id": int(shot.id), "projection_fingerprint": _text(shot.projection_fingerprint), "shot_fingerprint": _fingerprint({"id": shot.id, "shot_id": shot.shot_id, "plan_shot_id": shot.plan_shot_id, "scene_id": shot.scene_id})},
        "shot_direction": {"id": int(direction.get("id") or 0), "revision": int(direction.get("revision") or 0), "fingerprint": _text(direction.get("direction_fingerprint"))},
        "keyframe_sequence": {"id": int(sequence.id), "revision": int(sequence.revision), "fingerprint": _text(sequence.sequence_fingerprint)},
        "start_keyframe": {"id": int(start.id), "fingerprint": _text(start.frame_fingerprint), "asset": start_asset},
        "end_keyframe": {"id": int(end.id), "fingerprint": _text(end.frame_fingerprint), "asset": end_asset} if end is not None else {"asset": {}},
        "production_generation_intent": {"id": _text(generation_intent.generation_intent_id), "fingerprint": _text(generation_intent.shot_requirement_fingerprint)},
        "prompt_authority": {"pointer_id": int(pointer.id), "version_id": int(prompt_ir.id), "payload_hash": _text(prompt_ir.payload_hash), "authority_id": int(prompt_authority.id) if prompt_authority else None},
        "model_profile": {key: profile.get(key) for key in ("id", "provider", "model_name", "transport_binding_id", "capability")},
        "duration": float(sequence.duration),
        "aspect_ratio": aspect_ratio,
        "motion_profile": motion,
        "prompt_version": _text(prompt.prompt_version_id),
    }
    source_fingerprint = _fingerprint(basis)
    return {"shot": shot, "materialization": materialization, "materialization_pointer": materialization_pointer, "direction": direction, "sequence": sequence, "plan": plan, "generation_intent": generation_intent, "profile": profile, "capabilities": capabilities, "start": start, "end": end, "start_asset": start_asset, "end_asset": end_asset, "prompt_pointer": pointer, "prompt_ir": prompt_ir, "prompt_authority": prompt_authority, "prompt": prompt, "prompt_text": prompt_text, "duration": float(sequence.duration), "aspect_ratio": aspect_ratio, "motion_profile": motion, "source_fingerprint": source_fingerprint, "basis": basis}


def _intent_lineage(intent: VideoGenerationIntent) -> dict[str, Any]:
    return _obj(intent.motion_profile).get("orchestration_lineage") or {}


def _review_for_intent(session: Any, intent: VideoGenerationIntent) -> str:
    if not intent.generation_execution_id:
        return ""
    candidate = session.query(MediaCandidateRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none()
    review = session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).one_or_none() if candidate else None
    return _text(review.review_status).upper() if review else ""


def _public_source(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe source projection for orchestration responses."""
    basis = context.get("basis") if isinstance(context.get("basis"), Mapping) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "shot_id": int(getattr(context.get("shot"), "id", 0) or 0),
        "source_fingerprint": _text(context.get("source_fingerprint")),
        "basis": dict(basis),
        "duration": float(context.get("duration") or 0),
        "aspect_ratio": _text(context.get("aspect_ratio")),
        "motion_profile": dict(context.get("motion_profile") or {}),
        "prompt_text": _text(context.get("prompt_text")),
        "capabilities": dict(context.get("capabilities") or {}),
        "model_profile": dict(basis.get("model_profile") or {}) if isinstance(basis, Mapping) else {},
    }


def reconcile_video_intent(session: Any, *, shot_id: int, provider_id: str = "mock-video", model_profile_id: str | None = None) -> dict[str, Any]:
    context = _source_context(session, shot_id, provider_id=provider_id, model_profile_id=model_profile_id)
    existing_rows = []
    for row in session.query(VideoGenerationIntent).filter_by(storyboard_shot_id=int(context["shot"].id)).order_by(VideoGenerationIntent.id.desc()).all():
        if _text(_intent_lineage(row).get("base_source_fingerprint")) == context["source_fingerprint"]:
            existing_rows.append(row)
    latest = existing_rows[0] if existing_rows else None
    revision = 1
    if latest is not None:
        review = _review_for_intent(session, latest)
        if review not in REVIEW_REJECTED:
            return {"intent": _intent_payload(latest), "source": _public_source(context), "idempotent": True, "revision": int(_intent_lineage(latest).get("revision") or 1)}
        revision = int(_intent_lineage(latest).get("revision") or 1) + 1
    intent_basis = {"base_source_fingerprint": context["source_fingerprint"], "revision": revision, "provider": context["profile"].get("provider"), "model_profile_id": context["profile"].get("id")}
    intent_fingerprint = _fingerprint({"schema": "video_generation_intent_v2", **intent_basis})
    existing = session.query(VideoGenerationIntent).filter_by(intent_fingerprint=intent_fingerprint).one_or_none()
    if existing is not None:
        return {"intent": _intent_payload(existing), "source": _public_source(context), "idempotent": True, "revision": revision}
    lineage = {"schema_version": SCHEMA_VERSION, "base_source_fingerprint": context["source_fingerprint"], "source_basis": context["basis"], "revision": revision, "shot_direction_fingerprint": context["basis"]["shot_direction"]["fingerprint"], "keyframe_sequence_revision": context["sequence"].revision, "model_profile": context["basis"]["model_profile"], "prompt_authority": context["basis"]["prompt_authority"], "end_frame_required": bool(context["capabilities"]["last_frame"]), "last_frame_ignored_by_capability": not bool(context["capabilities"]["last_frame"]), "human_review_required": True}
    motion = {**context["motion_profile"], "orchestration_lineage": lineage}
    first = {**context["start_asset"], "frame_role": "START", "source_fingerprint": context["source_fingerprint"]}
    last = {**context["end_asset"], "frame_role": "END", "source_fingerprint": context["source_fingerprint"]} if context["end_asset"] else {}
    row = VideoGenerationIntent(storyboard_shot_id=int(context["shot"].id), duration=float(context["duration"]), aspect_ratio=context["aspect_ratio"], motion_profile=_canonical(motion), first_frame_asset=_canonical(first), last_frame_asset=_canonical(last), prompt_version=str(context["prompt"].prompt_version_id), intent_fingerprint=intent_fingerprint, status="READY")
    session.add(row)
    session.flush()
    return {"intent": _intent_payload(row), "source": _public_source(context), "idempotent": False, "revision": revision}


def _intent_payload(row: VideoGenerationIntent) -> dict[str, Any]:
    return {"id": int(row.id), "shot_id": int(row.storyboard_shot_id), "generation_type": "VIDEO", "duration": float(row.duration), "aspect_ratio": row.aspect_ratio, "motion_profile": _obj(row.motion_profile), "first_frame_asset": _obj(row.first_frame_asset), "last_frame_asset": _obj(row.last_frame_asset), "prompt_version": row.prompt_version, "intent_fingerprint": row.intent_fingerprint, "status": row.status, "generation_execution_id": row.generation_execution_id, "task_id": row.task_id, "source_fingerprint": _intent_lineage(row).get("base_source_fingerprint"), "source_lineage": _intent_lineage(row)}


def current_source_for_execution(session: Any, execution: GenerationExecutionRecord) -> dict[str, Any]:
    intent = session.query(VideoGenerationIntent).filter_by(generation_execution_id=execution.execution_id).one_or_none()
    if intent is None or not _intent_lineage(intent):
        return {"current": True, "reasons": [], "strict": False}
    try:
        context = _source_context(session, int(execution.storyboard_shot_id), provider_id=str(execution.provider or "mock-video"), model_profile_id=str(execution.model_profile_id or "") or None)
    except ShotVideoProductionError as exc:
        return {"current": False, "reasons": [exc.code], "strict": True, "error": exc.message}
    expected = _text(_intent_lineage(intent).get("base_source_fingerprint"))
    reasons = [] if expected == context["source_fingerprint"] else ["SOURCE_FINGERPRINT_CHANGED"]
    return {"current": not reasons, "reasons": reasons, "strict": True, "expected": expected, "actual": context["source_fingerprint"], "context": _public_source(context)}


def execute_shot_video_production(session: Any, *, shot_id: int, provider_id: str = "mock-video", model_profile_id: str | None = None, provider_registry: Any = None) -> dict[str, Any]:
    reconciled = reconcile_video_intent(session, shot_id=shot_id, provider_id=provider_id, model_profile_id=model_profile_id)
    intent = reconciled["intent"]
    result = execute_video_generation(session, intent_id=int(intent["id"]), provider_id=provider_id, model_profile_id=model_profile_id, provider_registry=provider_registry)
    result["orchestration"] = {"schema_version": SCHEMA_VERSION, "source_fingerprint": intent.get("source_fingerprint"), "idempotent_intent": reconciled["idempotent"], "human_review_required": True}
    return result


def get_shot_video_production(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    intent = session.query(VideoGenerationIntent).filter_by(storyboard_shot_id=int(shot.id)).order_by(VideoGenerationIntent.id.desc()).first()
    if intent is None:
        return {"shot_id": int(shot.id), "status": "VIDEO_NOT_READY", "intent": None, "execution": None, "candidate": None, "validation": None, "review": None, "official_media": None}
    status = get_video_generation_status(session, intent_id=int(intent.id))
    execution = status.get("execution") or {}
    review = status.get("promotion") or {}
    if review.get("review_status") == "APPROVED" and status.get("official_media_ready"):
        readiness = "VIDEO_APPROVED"
    elif review.get("review_status") in {"REVIEW_REQUIRED", "REJECTED", "REQUEST_CHANGE"}:
        readiness = "VIDEO_REVIEW_REQUIRED" if review.get("review_status") == "REVIEW_REQUIRED" else "VIDEO_NOT_READY"
    elif execution.get("status") in ACTIVE_EXECUTION_STATUSES:
        readiness = "VIDEO_GENERATING"
    elif execution.get("status") == "STALE" or _intent_lineage(intent).get("stale"):
        readiness = "VIDEO_STALE"
    elif intent.status == "READY":
        readiness = "VIDEO_READY_FOR_GENERATION"
    else:
        readiness = "VIDEO_NOT_READY"
    return {"shot_id": int(shot.id), "status": readiness, **status, "source_fingerprint": _intent_lineage(intent).get("base_source_fingerprint")}


__all__ = ["SCHEMA_VERSION", "ShotVideoProductionError", "reconcile_video_intent", "execute_shot_video_production", "get_shot_video_production", "current_source_for_execution"]
