"""Resumable episode production orchestration over the shipped runtimes.

The episode layer owns coordination only.  Shot state is derived from the
existing materialization, keyframe, candidate, review, execution and official
media authorities; no second execution or review system is introduced.
"""
from __future__ import annotations

from datetime import datetime
import json
from collections.abc import Mapping
from typing import Any

from core.automatic_keyframe_authoring import (
    AutomaticKeyframePlanError,
    compile_keyframe_plan,
    plan_keyframes,
)
from core.episode_rendering import EpisodeRenderingError, _items, get_episode_render_plan
from core.keyframe_image_production import KeyframeImageProductionError, _source_guard as _image_source_guard, produce_keyframe_image
from core.shot_video_production import (
    ShotVideoProductionError,
    _official_asset,
    _resolve_shot,
    execute_shot_video_production,
)
from models import (
    AutomaticKeyframePlan,
    EpisodeRenderItem,
    EpisodeRenderPlan,
    GenerationExecutionRecord,
    Keyframe,
    KeyframeAssetBinding,
    KeyframeSequence,
    MediaCandidateRecord,
    MediaPromotionRecord,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRPointer,
    ProductionGenerationIntent,
    ShotDirection,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardShot,
    VideoGenerationIntent,
)


EPISODE_PRODUCTION_SCHEMA_VERSION = "episode_automatic_production_v1"
ACTIVE_EXECUTION_STATUSES = frozenset({"CREATED", "QUEUED", "RUNNING", "PROVIDER_PENDING", "PROVIDER_CALLED"})
VIDEO_ROLE = "SHOT_PRIMARY_VIDEO"


class EpisodeProductionError(EpisodeRenderingError):
    """Stable error surface for episode production coordination."""


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


def _shot_id(shot: StoryboardShot) -> int:
    return int(shot.id)


def _active_plan(session: Any, shot: StoryboardShot) -> AutomaticKeyframePlan | None:
    return session.query(AutomaticKeyframePlan).filter_by(storyboard_shot_id=_shot_id(shot)).order_by(AutomaticKeyframePlan.version.desc(), AutomaticKeyframePlan.id.desc()).first()


def _active_sequence(session: Any, shot: StoryboardShot, plan: AutomaticKeyframePlan | None) -> KeyframeSequence | None:
    if plan is not None and plan.compiled_sequence_id:
        sequence = session.query(KeyframeSequence).filter_by(id=int(plan.compiled_sequence_id)).one_or_none()
        if sequence is not None and _text(sequence.status).upper() == "ACTIVE":
            return sequence
    return session.query(KeyframeSequence).filter_by(storyboard_shot_id=_shot_id(shot), status="ACTIVE").order_by(KeyframeSequence.revision.desc(), KeyframeSequence.id.desc()).first()


def _frames(session: Any, sequence: KeyframeSequence | None) -> dict[str, Keyframe]:
    if sequence is None:
        return {}
    rows = session.query(Keyframe).filter_by(keyframe_sequence_id=int(sequence.id), status="ACTIVE").order_by(Keyframe.order_index.asc()).all()
    return {str(row.frame_type).lower(): row for row in rows}


def _materialization_current(session: Any, shot: StoryboardShot) -> tuple[bool, str, StoryboardMaterializationSet | None]:
    if _text(shot.materialization_status).upper() not in {"MATERIALIZED", "ACTIVE"} or shot.materialization_set_id is None or not _text(shot.scene_id):
        return False, "current storyboard materialization is required", None
    pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), scene_id=str(shot.scene_id)).one_or_none()
    if pointer is None:
        return False, "current storyboard materialization pointer is missing", None
    materialization = session.query(StoryboardMaterializationSet).filter_by(id=int(pointer.materialization_set_id)).one_or_none()
    if materialization is None or int(materialization.id) != int(shot.materialization_set_id):
        return False, "storyboard materialization pointer is stale", materialization
    if _text(materialization.status).upper() != "MATERIALIZED" or _text(materialization.stale_status).upper() != "FRESH":
        return False, "storyboard materialization is stale", materialization
    if _text(pointer.set_payload_fingerprint) != _text(materialization.set_payload_fingerprint):
        return False, "storyboard materialization fingerprint is stale", materialization
    return True, "", materialization


def _review_for_candidate(session: Any, candidate: MediaCandidateRecord | None) -> MediaPromotionRecord | None:
    return session.query(MediaPromotionRecord).filter_by(candidate_id=candidate.candidate_id).one_or_none() if candidate is not None else None


def _image_frame_state(session: Any, shot: StoryboardShot, frame: Keyframe, sequence: KeyframeSequence | None = None) -> dict[str, Any]:
    """Resolve one START/END image from existing candidate and official facts."""
    executions = session.query(GenerationExecutionRecord).filter_by(storyboard_shot_id=_shot_id(shot)).order_by(GenerationExecutionRecord.id.desc()).all()
    matching: list[tuple[GenerationExecutionRecord, MediaCandidateRecord | None, MediaPromotionRecord | None]] = []
    for execution in executions:
        marker = _obj(execution.request_payload).get("_keyframe_image_production")
        if not isinstance(marker, Mapping) or int(marker.get("keyframe_id", -1)) != int(frame.id):
            continue
        candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one_or_none()
        matching.append((execution, candidate, _review_for_candidate(session, candidate)))
    execution, candidate, review = matching[0] if matching else (None, None, None)
    role_prefix = f"KEYFRAME_{str(frame.frame_type).upper()}_IMAGE"
    pointer = session.query(OfficialMediaPointer).filter(OfficialMediaPointer.book_id == int(shot.book_id), OfficialMediaPointer.episode == int(shot.episode), OfficialMediaPointer.storyboard_shot_id == _shot_id(shot), OfficialMediaPointer.media_role == role_prefix).one_or_none()
    official = session.query(OfficialMediaVersion).filter_by(official_media_version_id=pointer.official_media_version_id).one_or_none() if pointer is not None else None
    # A candidate may still be waiting for review when one of its source
    # authorities changes.  Resolve currentness before exposing the review
    # gate so the Episode projection fails closed and preserves the candidate
    # as history instead of inviting promotion of stale media.
    if execution is not None and sequence is not None:
        marker = _obj(execution.request_payload).get("_keyframe_image_production")
        if isinstance(marker, Mapping) and marker.get("source_fingerprint"):
            try:
                current_source = _image_source_guard(session, frame, sequence, shot)
                if marker.get("source_fingerprint") != current_source.get("source_fingerprint"):
                    return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "STALE", "next_action": "GENERATE_KEYFRAME_IMAGE", "blocking_reason": f"{str(frame.frame_type).upper()} image source is stale", "candidate_id": candidate.candidate_id if candidate else None}
            except Exception:
                return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "STALE", "next_action": "GENERATE_KEYFRAME_IMAGE", "blocking_reason": f"{str(frame.frame_type).upper()} image authority is stale", "candidate_id": candidate.candidate_id if candidate else None}
    if official is not None and _text(official.status).upper() == "CURRENT" and _text(official.media_type).upper() == "IMAGE":
        if sequence is not None:
            try:
                current_source = _image_source_guard(session, frame, sequence, shot)
                marker = _obj(execution.request_payload).get("_keyframe_image_production") if execution is not None else {}
                if marker.get("source_fingerprint") and marker.get("source_fingerprint") != current_source.get("source_fingerprint"):
                    return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "STALE", "next_action": "GENERATE_KEYFRAME_IMAGE", "blocking_reason": f"{str(frame.frame_type).upper()} image source is stale", "candidate_id": candidate.candidate_id if candidate else None}
            except Exception:
                return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "STALE", "next_action": "GENERATE_KEYFRAME_IMAGE", "blocking_reason": f"{str(frame.frame_type).upper()} image authority is stale", "candidate_id": candidate.candidate_id if candidate else None}
        return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "APPROVED", "next_action": "NONE", "review_status": _text(review.review_status).upper() if review else "APPROVED", "candidate_id": candidate.candidate_id if candidate else None, "official_media_version_id": official.official_media_version_id}
    if review is not None and _text(review.review_status).upper() in {"REVIEW_REQUIRED", "REQUEST_CHANGE"}:
        return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "REVIEW_REQUIRED", "next_action": "HUMAN_REVIEW", "blocking_reason": f"{str(frame.frame_type).upper()} candidate awaiting human review", "review_status": _text(review.review_status).upper(), "candidate_id": candidate.candidate_id if candidate else None}
    if review is not None and _text(review.review_status).upper() == "REJECTED":
        return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "NEEDS_PRODUCTION", "next_action": "GENERATE_KEYFRAME_IMAGE", "blocking_reason": f"{str(frame.frame_type).upper()} candidate was rejected", "review_status": "REJECTED", "candidate_id": candidate.candidate_id if candidate else None}
    return {"frame_type": str(frame.frame_type).upper(), "keyframe_id": int(frame.id), "state": "NEEDS_PRODUCTION", "next_action": "GENERATE_KEYFRAME_IMAGE", "blocking_reason": f"current Official {str(frame.frame_type).upper()} image is missing", "candidate_id": candidate.candidate_id if candidate else None}


def _video_state(session: Any, shot: StoryboardShot, *, expected_source: str = "") -> dict[str, Any]:
    intents = session.query(VideoGenerationIntent).filter_by(storyboard_shot_id=_shot_id(shot)).order_by(VideoGenerationIntent.id.desc()).all()
    intent = intents[0] if intents else None
    if intent is None:
        return {"state": "READY_FOR_VIDEO", "next_action": "GENERATE_VIDEO", "intent": None, "execution": None, "candidate": None, "official_media": None}
    lineage = _obj(intent.motion_profile).get("orchestration_lineage") or {}
    execution = session.query(GenerationExecutionRecord).filter_by(execution_id=intent.generation_execution_id).one_or_none() if intent.generation_execution_id else None
    candidate = session.query(MediaCandidateRecord).filter_by(execution_id=execution.execution_id).one_or_none() if execution else None
    review = _review_for_candidate(session, candidate)
    pointer = session.query(OfficialMediaPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=_shot_id(shot), media_role=VIDEO_ROLE).one_or_none()
    official = session.query(OfficialMediaVersion).filter_by(official_media_version_id=pointer.official_media_version_id).one_or_none() if pointer else None
    # Reconcile source currentness for every execution state, including a
    # candidate that is still awaiting review.  This is the durable stale
    # boundary; review status alone must never make an obsolete candidate
    # promotable.
    if execution is not None and lineage.get("base_source_fingerprint"):
        try:
            from core.shot_video_production import current_source_for_execution
            current = current_source_for_execution(session, execution)
            if not current.get("current"):
                return {"state": "STALE", "next_action": "RECONCILE_VIDEO", "blocking_reason": "video source is stale", "intent": intent, "execution": execution, "candidate": candidate, "official_media": official, "review": review, "source_fingerprint": lineage.get("base_source_fingerprint"), "stale": current}
        except Exception as exc:
            return {"state": "STALE", "next_action": "RECONCILE_VIDEO", "blocking_reason": str(exc), "intent": intent, "execution": execution, "candidate": candidate, "official_media": official, "review": review, "source_fingerprint": lineage.get("base_source_fingerprint")}
    if official is not None and _text(official.status).upper() == "CURRENT" and _text(official.media_type).upper() == "VIDEO":
        if execution is not None and lineage.get("base_source_fingerprint"):
            try:
                from core.shot_video_production import current_source_for_execution
                current = current_source_for_execution(session, execution)
                if not current.get("current"):
                    return {"state": "STALE", "next_action": "RECONCILE_VIDEO", "blocking_reason": "official video source is stale", "intent": intent, "execution": execution, "candidate": candidate, "official_media": official, "source_fingerprint": lineage.get("base_source_fingerprint"), "stale": current}
            except Exception as exc:
                return {"state": "STALE", "next_action": "RECONCILE_VIDEO", "blocking_reason": str(exc), "intent": intent, "execution": execution, "candidate": candidate, "official_media": official, "source_fingerprint": lineage.get("base_source_fingerprint")}
        return {"state": "COMPLETE", "next_action": "NONE", "intent": intent, "execution": execution, "candidate": candidate, "official_media": official, "source_fingerprint": lineage.get("base_source_fingerprint")}
    if review is not None and _text(review.review_status).upper() in {"REVIEW_REQUIRED", "REQUEST_CHANGE"}:
        return {"state": "VIDEO_REVIEW_REQUIRED", "next_action": "HUMAN_REVIEW", "blocking_reason": "video candidate awaiting human review", "intent": intent, "execution": execution, "candidate": candidate, "review": review, "source_fingerprint": lineage.get("base_source_fingerprint")}
    if review is not None and _text(review.review_status).upper() == "REJECTED":
        return {"state": "READY_FOR_VIDEO", "next_action": "REGENERATE_VIDEO", "blocking_reason": "video candidate was rejected", "intent": intent, "execution": execution, "candidate": candidate, "review": review, "source_fingerprint": lineage.get("base_source_fingerprint")}
    if execution is not None and _text(execution.execution_status).upper() in ACTIVE_EXECUTION_STATUSES:
        return {"state": "VIDEO_GENERATING", "next_action": "OBSERVE", "blocking_reason": "provider execution is in flight", "intent": intent, "execution": execution, "candidate": candidate, "source_fingerprint": lineage.get("base_source_fingerprint")}
    if execution is not None and _text(execution.execution_status).upper() in {"FAILED", "STALE"}:
        return {"state": "FAILED" if _text(execution.execution_status).upper() == "FAILED" else "STALE", "next_action": "RETRY_VIDEO" if _text(execution.execution_status).upper() == "FAILED" else "RECONCILE_VIDEO", "blocking_reason": _text(execution.error_message) or "video execution failed", "intent": intent, "execution": execution, "candidate": candidate, "source_fingerprint": lineage.get("base_source_fingerprint")}
    return {"state": "READY_FOR_VIDEO", "next_action": "GENERATE_VIDEO", "intent": intent, "execution": execution, "candidate": candidate, "source_fingerprint": lineage.get("base_source_fingerprint")}


def resolve_shot_production_state(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, int(shot_id))
    current, reason, materialization = _materialization_current(session, shot)
    base: dict[str, Any] = {"shot_id": _shot_id(shot), "order": int(shot.shot_id), "state": "NOT_READY", "blocking_reason": reason, "next_action": "WAIT_FOR_MATERIALIZATION", "dependency_ready": True, "source_fingerprint": None, "current_authorities": {"materialization_set_id": int(materialization.id) if materialization else None, "shot_direction_id": None, "keyframe_plan_id": None, "keyframe_sequence_id": None, "video_intent_id": None}}
    if not current:
        return base
    direction = session.query(ShotDirection).filter_by(storyboard_shot_id=_shot_id(shot), status="ACTIVE").one_or_none()
    if direction is None:
        base.update(state="NOT_READY", blocking_reason="current ShotDirection is required", next_action="CREATE_SHOT_DIRECTION")
        return base
    base["current_authorities"]["shot_direction_id"] = int(direction.id)
    plan = _active_plan(session, shot)
    if plan is None:
        base.update(state="NEEDS_KEYFRAME_PLAN", blocking_reason="AutomaticKeyframePlan is missing", next_action="GENERATE_KEYFRAME_PLAN")
        return base
    base["current_authorities"]["keyframe_plan_id"] = int(plan.id)
    if _text(plan.status).upper() == "STALE":
        base.update(state="STALE", blocking_reason="AutomaticKeyframePlan is stale", next_action="GENERATE_KEYFRAME_PLAN", source_fingerprint=plan.source_fingerprint)
        return base
    if int(plan.storyboard_materialization_set_id or 0) != int(materialization.id) or _text(plan.materialization_set_fingerprint) != _text(materialization.set_payload_fingerprint) or _text(plan.shot_direction_fingerprint) != _text(direction.direction_fingerprint) or int(plan.shot_direction_revision or 0) != int(direction.revision or 0):
        base.update(state="STALE", blocking_reason="AutomaticKeyframePlan source authorities changed", next_action="GENERATE_KEYFRAME_PLAN", source_fingerprint=plan.source_fingerprint)
        return base
    if _text(plan.status).upper() in {"REVIEW_REQUIRED", "REJECTED", "REVISE", "SUPERSEDED"}:
        base.update(state="KEYFRAME_PLAN_REVIEW_REQUIRED", blocking_reason="AutomaticKeyframePlan requires human review", next_action="HUMAN_REVIEW", source_fingerprint=plan.source_fingerprint)
        return base
    sequence = _active_sequence(session, shot, plan)
    if sequence is None or _text(plan.status).upper() != "COMPILED":
        base.update(state="NEEDS_KEYFRAME_COMPILE", blocking_reason="approved keyframe plan is not compiled", next_action="COMPILE_KEYFRAME_PLAN", source_fingerprint=plan.source_fingerprint)
        return base
    base["current_authorities"]["keyframe_sequence_id"] = int(sequence.id)
    frames = _frames(session, sequence)
    required = [frames.get("start"), frames.get("end")]
    if any(frame is None for frame in required):
        base.update(state="NOT_READY", blocking_reason="START and END keyframes are required", next_action="REVISE_KEYFRAME_PLAN", source_fingerprint=plan.source_fingerprint)
        return base
    images = [_image_frame_state(session, shot, frame, sequence) for frame in required if frame is not None]
    base["keyframe_images"] = images
    if any(item["state"] == "REVIEW_REQUIRED" for item in images):
        base.update(state="KEYFRAME_IMAGE_REVIEW_REQUIRED", blocking_reason=next(item.get("blocking_reason") for item in images if item["state"] == "REVIEW_REQUIRED"), next_action="HUMAN_REVIEW", source_fingerprint=plan.source_fingerprint)
        return base
    if any(item["state"] != "APPROVED" for item in images):
        base.update(state="NEEDS_KEYFRAME_IMAGES", blocking_reason=next(item.get("blocking_reason") for item in images if item["state"] != "APPROVED"), next_action="GENERATE_KEYFRAME_IMAGE", source_fingerprint=plan.source_fingerprint)
        return base
    # Video generation requires an explicit VIDEO-scoped PromptIR authority.
    # Keep this preparation boundary derived from the existing pointer rather
    # than allowing the video runtime to turn a missing authority into a
    # provider failure.
    video_prompt = session.query(PromptIRPointer).filter_by(
        book_id=int(shot.book_id),
        episode=int(shot.episode),
        storyboard_shot_id=_shot_id(shot),
        target_media="VIDEO",
    ).one_or_none()
    if video_prompt is None:
        base.update(state="NOT_READY", blocking_reason="current VIDEO PromptIR pointer is required", next_action="PREPARE_VIDEO_PROMPT", source_fingerprint=plan.source_fingerprint)
        return base
    video = _video_state(session, shot)
    base.update({key: value for key, value in video.items() if key not in {"intent", "execution", "candidate", "official_media"}})
    base["current_authorities"]["video_intent_id"] = int(video["intent"].id) if video.get("intent") is not None else None
    base["source_fingerprint"] = video.get("source_fingerprint") or plan.source_fingerprint
    base["latest_execution"] = {"execution_id": video["execution"].execution_id, "status": video["execution"].execution_status, "provider_task_id": video["execution"].provider_task_id} if video.get("execution") else None
    base["candidate"] = {"candidate_id": video["candidate"].candidate_id, "media_type": video["candidate"].media_type, "validation_status": video["candidate"].validation_status} if video.get("candidate") else None
    base["official_media"] = {"official_media_version_id": video["official_media"].official_media_version_id, "media_role": video["official_media"].media_role} if video.get("official_media") else None
    return base


def _public_detail(detail: dict[str, Any]) -> dict[str, Any]:
    result = dict(detail)
    for key in ("intent", "execution", "candidate", "official_media", "review"):
        value = result.pop(key, None)
        if value is not None and key not in result:
            result[key] = value
    if isinstance(result.get("execution"), GenerationExecutionRecord):
        execution = result["execution"]
        result["execution"] = {"execution_id": execution.execution_id, "status": execution.execution_status, "provider_task_id": execution.provider_task_id}
    if isinstance(result.get("candidate"), MediaCandidateRecord):
        candidate = result["candidate"]
        result["candidate"] = {"candidate_id": candidate.candidate_id, "media_type": candidate.media_type, "validation_status": candidate.validation_status}
    if isinstance(result.get("official_media"), OfficialMediaVersion):
        official = result["official_media"]
        result["official_media"] = {"official_media_version_id": official.official_media_version_id, "media_role": official.media_role}
    if isinstance(result.get("intent"), VideoGenerationIntent):
        intent = result["intent"]
        result["intent"] = {"id": int(intent.id), "status": intent.status, "generation_execution_id": intent.generation_execution_id}
    if isinstance(result.get("review"), MediaPromotionRecord):
        review = result["review"]
        result["review"] = {"promotion_id": review.promotion_id, "review_status": review.review_status, "decision": review.decision}
    return result


def _episode_summary(details: list[dict[str, Any]], *, episode_id: int, plan_id: int, dry_run: bool) -> dict[str, Any]:
    counts = {"shots_total": len(details), "shots_complete": 0, "shots_waiting_review": 0, "shots_generating": 0, "shots_blocked": 0, "shots_failed": 0, "shots_stale": 0}
    for detail in details:
        state = _text(detail.get("state")).upper()
        if state == "COMPLETE": counts["shots_complete"] += 1
        if state in {"KEYFRAME_PLAN_REVIEW_REQUIRED", "KEYFRAME_IMAGE_REVIEW_REQUIRED", "VIDEO_REVIEW_REQUIRED"}: counts["shots_waiting_review"] += 1
        if state == "VIDEO_GENERATING": counts["shots_generating"] += 1
        if state in {"NOT_READY", "NEEDS_KEYFRAME_PLAN", "NEEDS_KEYFRAME_COMPILE", "NEEDS_KEYFRAME_IMAGES", "READY_FOR_VIDEO", "BLOCKED_DEPENDENCY"}: counts["shots_blocked"] += 1
        if state == "FAILED": counts["shots_failed"] += 1
        if state == "STALE": counts["shots_stale"] += 1
    if counts["shots_total"] and counts["shots_complete"] == counts["shots_total"]:
        state = "PRODUCTION_COMPLETE"
    elif counts["shots_failed"]:
        state = "FAILED"
    elif counts["shots_waiting_review"] or counts["shots_generating"]:
        state = "WAITING_REVIEW" if counts["shots_waiting_review"] else "PRODUCING"
    elif counts["shots_blocked"] or counts["shots_stale"]:
        state = "BLOCKED"
    else:
        state = "PREPARING"
    return {"schema_version": EPISODE_PRODUCTION_SCHEMA_VERSION, "episode_id": int(episode_id), "render_plan_id": int(plan_id), "state": state, "dry_run": bool(dry_run), **counts, "shots": details}


def run_episode_production(session: Any, *, episode_id: int, plan_id: int | str | None = None, dry_run: bool = False, retry_failed: bool = False, provider_id: str = "mock-video", model_profile_id: str | None = None) -> dict[str, Any]:
    plan = get_episode_render_plan(session, episode_id=int(episode_id), plan_id=plan_id)
    items = _items(session, plan)
    details: list[dict[str, Any]] = []
    by_shot: dict[int, dict[str, Any]] = {}
    actions: list[dict[str, Any]] = []
    for item in items:
        detail = resolve_shot_production_state(session, shot_id=int(item.shot_id))
        dependencies = [int(value) for value in _list(item.dependency)]
        dependency_details = [by_shot.get(dep) or resolve_shot_production_state(session, shot_id=dep) for dep in dependencies]
        dependency_ready = all(_text(dep.get("state")).upper() == "COMPLETE" for dep in dependency_details)
        detail["dependency_ready"] = dependency_ready
        if not dependency_ready:
            detail["state"] = "BLOCKED_DEPENDENCY"
            detail["next_action"] = "WAIT_FOR_DEPENDENCY"
            detail["blocking_reason"] = f"dependency shot {next(dep.get('shot_id') for dep in dependency_details if dep.get('state') != 'COMPLETE')} is not COMPLETE"
        elif not dry_run:
            # A single run may cross deterministic boundaries (plan compile
            # then image dispatch), but it always stops at a human review,
            # provider-in-flight, stale, or failure boundary.
            for _stage in range(4):
                state = _text(detail.get("state")).upper()
                try:
                    if state == "NEEDS_KEYFRAME_PLAN":
                        generated = plan_keyframes(session, shot_id=int(item.shot_id))
                        actions.append({"shot_id": int(item.shot_id), "action": "GENERATE_KEYFRAME_PLAN", "result": generated.get("status"), "provider_calls": 0})
                    elif state == "NEEDS_KEYFRAME_COMPILE":
                        plan_row = _active_plan(session, _resolve_shot(session, int(item.shot_id)))
                        if plan_row is None:
                            raise EpisodeProductionError("keyframe plan disappeared during run", code="EPISODE_KEYFRAME_PLAN_MISSING")
                        compiled = compile_keyframe_plan(session, shot_id=int(item.shot_id), version=int(plan_row.version))
                        actions.append({"shot_id": int(item.shot_id), "action": "COMPILE_KEYFRAME_PLAN", "result": compiled.get("plan", {}).get("status"), "provider_calls": 0})
                    elif state == "NEEDS_KEYFRAME_IMAGES":
                        shot = _resolve_shot(session, int(item.shot_id))
                        sequence = _active_sequence(session, shot, _active_plan(session, shot))
                        frames = _frames(session, sequence)
                        produced_frame = None
                        for frame_name in ("start", "end"):
                            frame = frames.get(frame_name)
                            if frame is None:
                                continue
                            frame_state = _image_frame_state(session, shot, frame, sequence)
                            if frame_state.get("state") != "APPROVED":
                                produced = produce_keyframe_image(session, keyframe_id=int(frame.id), fixture=True, production_required=True)
                                produced_frame = frame_name.upper()
                                actions.append({"shot_id": int(item.shot_id), "action": "GENERATE_KEYFRAME_IMAGE", "frame_type": produced_frame, "idempotent": bool(produced.get("idempotent")), "provider_calls": int(produced.get("provider_calls") or 0)})
                                break
                        # Image candidates are review gates.  Re-resolve once
                        # and stop this shot even if an adapter reports a
                        # reused candidate.
                        if produced_frame:
                            break
                    elif state == "FAILED" and not retry_failed:
                        detail["next_action"] = "RETRY_VIDEO"
                        break
                    elif state == "READY_FOR_VIDEO" or (state == "FAILED" and retry_failed):
                        # Real provider polling remains behind its existing
                        # canary gate.  Also reject a real model profile when
                        # provider_id keeps the backward-compatible mock
                        # default, so the Episode boundary cannot accidentally
                        # open a paid provider.
                        mock_allowed = provider_id == "mock-video" and model_profile_id in {None, "", "builtin-mock-video"}
                        if not mock_allowed:
                            actions.append({"shot_id": int(item.shot_id), "action": "PROVIDER_CANARY_DISABLED", "provider": provider_id, "model_profile_id": model_profile_id, "provider_calls": 0})
                            detail["next_action"] = "PROVIDER_CANARY_DISABLED"
                            detail["blocking_reason"] = "real video provider canary is disabled for Episode orchestration"
                            break
                        result = execute_shot_video_production(session, shot_id=int(item.shot_id), provider_id=provider_id, model_profile_id=model_profile_id)
                        actions.append({"shot_id": int(item.shot_id), "action": "GENERATE_VIDEO", "execution_id": result.get("execution", {}).get("execution_id"), "provider_calls": int(result.get("provider_calls") or 0)})
                        break
                    else:
                        break
                    detail = resolve_shot_production_state(session, shot_id=int(item.shot_id))
                    detail["dependency_ready"] = dependency_ready
                    if _text(detail.get("state")).upper() in {"KEYFRAME_PLAN_REVIEW_REQUIRED", "KEYFRAME_IMAGE_REVIEW_REQUIRED", "VIDEO_REVIEW_REQUIRED", "VIDEO_GENERATING", "STALE", "FAILED", "COMPLETE", "BLOCKED_DEPENDENCY", "NOT_READY"}:
                        break
                except (AutomaticKeyframePlanError, KeyframeImageProductionError, ShotVideoProductionError, EpisodeProductionError) as exc:
                    detail["state"] = "FAILED" if _text(getattr(exc, "code", "")).upper() not in {"REVIEW_REQUIRED", "VIDEO_KEYFRAME_PLAN_NOT_COMPILED"} else detail.get("state")
                    detail["next_action"] = "RETRY" if detail["state"] == "FAILED" else detail.get("next_action")
                    detail["blocking_reason"] = str(getattr(exc, "message", exc))
                    break
                except Exception as exc:
                    # Unexpected errors are surfaced as a durable shot
                    # failure projection while the caller retains control of
                    # the outer transaction.
                    detail["state"] = "FAILED"
                    detail["next_action"] = "RETRY"
                    detail["blocking_reason"] = str(exc)
                    break
            # Re-resolve after every successful dispatch so the returned
            # projection exposes the newly created review or in-flight gate
            # instead of echoing the pre-dispatch READY_FOR_VIDEO state.
            detail = resolve_shot_production_state(session, shot_id=int(item.shot_id)) if _text(detail.get("state")).upper() != "FAILED" else detail
            detail["dependency_ready"] = dependency_ready
        by_shot[int(item.shot_id)] = detail
        if not dry_run:
            item.status = {"COMPLETE": "COMPLETED", "VIDEO_GENERATING": "RUNNING", "FAILED": "FAILED"}.get(_text(detail.get("state")).upper(), "PENDING")
            item.error = _text(detail.get("blocking_reason"))[:4000]
            item.updated_at = datetime.utcnow()
        details.append(_public_detail(detail))
    summary = _episode_summary(details, episode_id=int(episode_id), plan_id=int(plan.id), dry_run=dry_run)
    summary["run_id"] = f"episode-render-plan:{int(plan.id)}"
    summary["actions"] = actions
    summary["human_review_required"] = True
    summary["resumable"] = True
    summary["provider_calls"] = {"llm": 0, "image": sum(int(item.get("provider_calls") or 0) for item in actions if item.get("action") == "GENERATE_KEYFRAME_IMAGE"), "video": sum(int(item.get("provider_calls") or 0) for item in actions if item.get("action") == "GENERATE_VIDEO"), "real_llm": 0, "real_image": 0, "real_video": 0}
    if not dry_run:
        if summary["state"] == "PRODUCTION_COMPLETE":
            plan.status = "REVIEWING"
        elif summary["state"] == "FAILED":
            plan.status = "FAILED"
        else:
            plan.status = "GENERATING"
        plan.updated_at = datetime.utcnow()
        session.flush()
    return summary


def get_episode_production_status(session: Any, *, episode_id: int, plan_id: int | str | None = None) -> dict[str, Any]:
    plan = get_episode_render_plan(session, episode_id=int(episode_id), plan_id=plan_id)
    details = []
    by_shot = {}
    for item in _items(session, plan):
        detail = resolve_shot_production_state(session, shot_id=int(item.shot_id))
        dependencies = [int(value) for value in _list(item.dependency)]
        if any(_text(by_shot.get(dep, {}).get("state")).upper() != "COMPLETE" for dep in dependencies):
            detail["state"] = "BLOCKED_DEPENDENCY"
            detail["next_action"] = "WAIT_FOR_DEPENDENCY"
            detail["dependency_ready"] = False
        by_shot[int(item.shot_id)] = detail
        details.append(_public_detail(detail))
    result = _episode_summary(details, episode_id=int(episode_id), plan_id=int(plan.id), dry_run=False)
    result["run_id"] = f"episode-render-plan:{int(plan.id)}"
    result["human_review_required"] = True
    result["resumable"] = True
    return result


__all__ = ["EPISODE_PRODUCTION_SCHEMA_VERSION", "EpisodeProductionError", "resolve_shot_production_state", "run_episode_production", "get_episode_production_status"]
