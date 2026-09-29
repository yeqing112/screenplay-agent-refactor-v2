"""Safety-first runner for the controlled real Episode production pilot.

The default mode is read-only preflight.  ``--dry-run`` adds the existing
Episode production projection and still performs no production writes.  A
paid provider operation requires ``--execute`` plus the existing SHAPI and
MiniMax gates, an exact two-shot allowlist, and an explicit consent token.
The runner coordinates existing services; it does not implement a provider,
queue, review store, or asset store.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.model_registry import get_profile, list_profiles
from core.episode_production import (
    _active_plan,
    _active_sequence,
    _frames,
    _image_frame_state,
    _materialization_current,
    _video_state,
    get_episode_production_status,
    resolve_shot_production_state,
)
from core.episode_rendering import _items, get_episode_render_plan
from core.episode_production import run_episode_production
from core.keyframe_image_production import produce_keyframe_image
from core.shot_video_production import execute_shot_video_production
from models import (
    AutomaticKeyframePlan,
    GenerationExecutionRecord,
    PromptIRPointer,
    Session,
    ShotDirection,
    StoryboardShot,
)


SCHEMA_VERSION = "real_episode_production_pilot_v1"
CONSENT_TOKEN = "CONFIRM_REAL_EPISODE_PRODUCTION_PILOT"
MINIMAX_CONFIRMATION_TOKEN = "CONFIRM_MINIMAX_H3_SUBMIT"
MAX_SHOTS = 2
MAX_IMAGE_CALLS = 4
MAX_VIDEO_CALLS = 2
IMAGE_PROVIDER = "shapi-openai-images"
IMAGE_TRANSPORT = "shapi-openai-images.image.v1"
VIDEO_PROVIDER = "minimax-h3-async"
VIDEO_TRANSPORT = "minimax-h3-async.video.v1"
EXPECTED_BRANCH = "codex/visual-authoring-provider-canary-reconcile"
EXPECTED_MIGRATION_HEAD = "m4h5i6j7k8l9"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _short_exception(exc: BaseException) -> str:
    """Return a stable, secret-free blocker token for operator reports."""
    return type(exc).__name__


def _repository_snapshot(session: Any) -> dict[str, Any]:
    """Read repository and database state without changing either one."""
    def git(*args: str) -> str:
        try:
            result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    try:
        migration_head = str(session.execute(text("select version_num from alembic_version limit 1")).scalar() or "")
    except Exception:
        migration_head = ""
    branch = git("branch", "--show-current")
    commit = git("rev-parse", "HEAD")
    return {
        "branch": branch,
        "expected_branch": EXPECTED_BRANCH,
        "branch_matches": branch == EXPECTED_BRANCH,
        "head": commit,
        "working_tree_clean": git("status", "--porcelain") == "",
        "migration_head": migration_head,
        "expected_migration_head": EXPECTED_MIGRATION_HEAD,
        "migration_head_matches": migration_head == EXPECTED_MIGRATION_HEAD,
    }


def _safe_profile(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile, Mapping):
        return {"exists": False}
    return {
        "exists": True,
        "id": _text(profile.get("id")),
        "provider": _text(profile.get("provider")),
        "model_name": _text(profile.get("model_name")),
        "capability": _text(profile.get("capability")),
        "enabled": bool(profile.get("enabled", True)),
        "transport_binding_id": _text(profile.get("transport_binding_id")),
        "credential_present": bool(profile.get("credential_configured") or profile.get("key_configured") or profile.get("api_key")),
        "base_url": _text(profile.get("base_url")),
    }


def _profile_ready(profile: Mapping[str, Any] | None, *, provider: str, capability: str, transport: str) -> tuple[bool, str]:
    safe = _safe_profile(profile)
    if not safe.get("exists"):
        return False, "profile_missing"
    if not safe.get("enabled"):
        return False, "profile_disabled"
    if safe.get("provider") != provider:
        return False, "provider_mismatch"
    if safe.get("capability") != capability:
        return False, "capability_mismatch"
    if safe.get("transport_binding_id") != transport:
        return False, "transport_binding_mismatch"
    if not safe.get("credential_present"):
        return False, "credential_not_configured"
    return True, ""


def _target_key(shot: StoryboardShot) -> str:
    return f"{int(shot.book_id)}:{int(shot.episode)}:{int(shot.id)}"


def _gate_snapshot(shot_keys: list[str], *, episode_id: int = 0, allowed_episode_id: int | None = None) -> dict[str, Any]:
    whitelist = {item.strip() for item in _text(os.getenv("MINIMAX_H3_GRAY_WHITELIST")).split(",") if item.strip()}
    return {
        "image_canary_enabled": os.getenv("PHASE_F_PROVIDER_CANARY_REAL", "").strip() == "1",
        "video_gray_enabled": os.getenv("MINIMAX_H3_GRAY_REAL", "").strip() == "1",
        "video_confirmation_matches": os.getenv("MINIMAX_H3_GRAY_CONFIRM", "").strip() == MINIMAX_CONFIRMATION_TOKEN,
        "video_whitelist": sorted(whitelist),
        "exact_shots_whitelisted": bool(shot_keys) and set(shot_keys) == whitelist,
        "episode_allowlist_present": allowed_episode_id is not None,
        "episode_allowlist_matches": allowed_episode_id is not None and int(allowed_episode_id) == int(episode_id),
        "consent_token_required": CONSENT_TOKEN,
        "secrets_redacted": True,
    }


def _current_authority_check(session: Any, shot: StoryboardShot) -> dict[str, Any]:
    materialization_current, materialization_reason, materialization = _materialization_current(session, shot)
    direction = session.query(ShotDirection).filter_by(storyboard_shot_id=int(shot.id), status="ACTIVE").one_or_none()
    plan = _active_plan(session, shot)
    sequence = _active_sequence(session, shot, plan)
    frames = _frames(session, sequence)
    image_pointer = session.query(PromptIRPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), target_media="IMAGE").one_or_none()
    video_pointer = session.query(PromptIRPointer).filter_by(book_id=int(shot.book_id), episode=int(shot.episode), storyboard_shot_id=int(shot.id), target_media="VIDEO").one_or_none()
    plan_ok = bool(plan and _text(plan.status).upper() in {"APPROVED", "COMPILED"} and sequence is not None)
    frame_rows = [frames.get("start"), frames.get("end")]
    image_states = [_image_frame_state(session, shot, frame, sequence) for frame in frame_rows if frame is not None] if sequence else []
    return {
        "materialization_current": materialization_current,
        "materialization_reason": materialization_reason,
        "materialization_set_id": int(materialization.id) if materialization else None,
        "shot_direction_current": direction is not None,
        "automatic_keyframe_plan_approved": plan_ok,
        "automatic_keyframe_plan_id": int(plan.id) if plan else None,
        "keyframe_sequence_id": int(sequence.id) if sequence else None,
        "start_end_keyframes_present": all(frame is not None for frame in frame_rows),
        "image_prompt_authority_current": image_pointer is not None,
        "video_prompt_authority_current": video_pointer is not None,
        "image_states": image_states,
        "derived_state": resolve_shot_production_state(session, shot_id=int(shot.id)),
    }


def _blocked_authority(shot: StoryboardShot, exc: BaseException) -> dict[str, Any]:
    """Return a safe authority projection when the local schema is unavailable.

    Preflight must remain observable and fail closed when a stale or partially
    migrated database cannot answer an authority query.  Keep the exception
    detail type-only so SQL, paths, and credentials never enter the report.
    """
    reason = _short_exception(exc)
    return {
        "materialization_current": False,
        "materialization_reason": "authority_unavailable",
        "materialization_set_id": None,
        "shot_direction_current": False,
        "automatic_keyframe_plan_approved": False,
        "automatic_keyframe_plan_id": None,
        "keyframe_sequence_id": None,
        "start_end_keyframes_present": False,
        "image_prompt_authority_current": False,
        "video_prompt_authority_current": False,
        "image_states": [],
        "derived_state": {"state": "AUTHORITY_UNAVAILABLE"},
        "authority_error": reason,
        "shot_id": int(shot.id),
    }


def build_preflight(session: Any, *, episode_id: int, shot_ids: list[int], image_profile_id: str, video_profile_id: str, allowed_image_calls: int = MAX_IMAGE_CALLS, allowed_video_calls: int = MAX_VIDEO_CALLS, allowed_episode_id: int | None = None) -> dict[str, Any]:
    blockers: list[str] = []
    repository = _repository_snapshot(session)
    if not repository["branch_matches"]:
        blockers.append("branch_mismatch")
    if not repository["working_tree_clean"]:
        blockers.append("working_tree_not_clean")
    if not repository["migration_head_matches"]:
        blockers.append("migration_head_mismatch")
    plan = None
    try:
        plan = get_episode_render_plan(session, episode_id=int(episode_id))
        items = _items(session, plan)
    except Exception as exc:
        items = []
        blockers.append(f"episode_render_plan_unavailable:{_short_exception(exc)}")
    requested = [int(value) for value in shot_ids]
    if allowed_episode_id is None:
        blockers.append("exact_episode_allowlist_required")
    elif int(allowed_episode_id) != int(episode_id):
        blockers.append("exact_episode_allowlist_does_not_match_episode")
    if len(requested) != MAX_SHOTS or len(set(requested)) != MAX_SHOTS:
        blockers.append("pilot_requires_exactly_two_unique_shots")
    plan_shot_ids = [int(item.shot_id) for item in items]
    if len(plan_shot_ids) != MAX_SHOTS:
        blockers.append("episode_render_plan_must_contain_exactly_two_shots")
    if set(plan_shot_ids) != set(requested):
        blockers.append("exact_shot_allowlist_does_not_match_episode_render_plan")
    shot_query_error: str | None = None
    try:
        shots = session.query(StoryboardShot).filter(StoryboardShot.id.in_(requested)).order_by(StoryboardShot.id.asc()).all() if requested else []
    except Exception as exc:
        shots = []
        shot_query_error = _short_exception(exc)
        blockers.append(f"storyboard_shot_unavailable:{shot_query_error}")
        blockers.append(f"source_authority_schema_unavailable:{shot_query_error}")
        blockers.append(f"prompt_authority_schema_unavailable:{shot_query_error}")
    if len(shots) != len(requested):
        blockers.append("shot_allowlist_contains_missing_shot")
    image_profile = get_profile(image_profile_id)
    video_profile = get_profile(video_profile_id)
    image_ready, image_profile_blocker = _profile_ready(image_profile, provider=IMAGE_PROVIDER, capability="image", transport=IMAGE_TRANSPORT)
    video_ready, video_profile_blocker = _profile_ready(video_profile, provider=VIDEO_PROVIDER, capability="video", transport=VIDEO_TRANSPORT)
    if not image_ready:
        blockers.append(f"image_profile:{image_profile_blocker}")
    if not video_ready:
        blockers.append(f"video_profile:{video_profile_blocker}")
    keys = [_target_key(shot) for shot in shots]
    gates = _gate_snapshot(keys, episode_id=int(episode_id), allowed_episode_id=allowed_episode_id)
    if not gates["image_canary_enabled"]:
        blockers.append("PHASE_F_PROVIDER_CANARY_REAL_not_enabled")
    if not gates["video_gray_enabled"]:
        blockers.append("MINIMAX_H3_GRAY_REAL_not_enabled")
    if not gates["video_confirmation_matches"]:
        blockers.append("MINIMAX_H3_GRAY_CONFIRM_missing_or_invalid")
    if not gates["exact_shots_whitelisted"]:
        blockers.append("MINIMAX_H3_GRAY_WHITELIST_does_not_exactly_match_shots")

    authorities = []
    planned_image_calls = 0
    planned_video_calls = 0
    for shot in shots:
        try:
            authority = _current_authority_check(session, shot)
        except Exception as exc:
            reason = _short_exception(exc)
            blockers.append(f"source_authority_unavailable:{reason}")
            blockers.append(f"prompt_authority_unavailable:{reason}")
            authority = _blocked_authority(shot, exc)
        authorities.append({"shot_id": int(shot.id), **authority})
        required_keys = ("materialization_current", "shot_direction_current", "automatic_keyframe_plan_approved", "start_end_keyframes_present", "image_prompt_authority_current", "video_prompt_authority_current")
        if not all(bool(authority.get(key)) for key in required_keys):
            blockers.append(f"shot_{shot.id}_source_authority_not_current")
        if authority.get("authority_error"):
            # Unknown authority state cannot be converted into a paid
            # operation projection.  Keep planned call counts at zero.
            continue
        planned_image_calls += sum(1 for row in authority["image_states"] if row.get("state") not in {"APPROVED", "REVIEW_REQUIRED"})
        state = _text(authority["derived_state"].get("state")).upper()
        if state not in {"COMPLETE", "VIDEO_REVIEW_REQUIRED", "VIDEO_GENERATING"}:
            planned_video_calls += 1
    if planned_image_calls > int(allowed_image_calls):
        blockers.append("planned_image_calls_exceed_budget")
    if planned_video_calls > int(allowed_video_calls):
        blockers.append("planned_video_calls_exceed_budget")
    if planned_image_calls > MAX_IMAGE_CALLS:
        blockers.append("planned_image_calls_exceed_hard_limit")
    if planned_video_calls > MAX_VIDEO_CALLS:
        blockers.append("planned_video_calls_exceed_hard_limit")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "READY_FOR_REAL_PILOT" if not blockers else "BLOCKED",
        "created_at": datetime.now(UTC).isoformat(),
        "repository": repository,
        "episode_id": int(episode_id),
        "render_plan_id": int(plan.id) if plan is not None else None,
        "shot_ids": requested,
        "image_profile_id": image_profile_id,
        "video_profile_id": video_profile_id,
        "image_model_registry_profile": _safe_profile(image_profile),
        "video_model_registry_profile": _safe_profile(video_profile),
        "planned_real_image_calls": planned_image_calls,
        "planned_real_video_calls": planned_video_calls,
        "allowed_image_calls": int(allowed_image_calls),
        "allowed_video_calls": int(allowed_video_calls),
        "all_gates_ready": not any(key.startswith("PHASE_") or key.startswith("MINIMAX_") for key in blockers),
        "all_authorities_current": bool(authorities) and all(all(bool(row.get(key)) for key in ("materialization_current", "shot_direction_current", "automatic_keyframe_plan_approved", "start_end_keyframes_present", "image_prompt_authority_current", "video_prompt_authority_current")) for row in authorities),
        "exact_episode_allowlist": {"requested_episode_id": int(episode_id), "allowed_episode_id": int(allowed_episode_id) if allowed_episode_id is not None else None, "matches": allowed_episode_id is not None and int(allowed_episode_id) == int(episode_id)},
        "secrets_redacted": True,
        "gates": gates,
        "authorities": authorities,
        "blockers": blockers,
        "production_writes": 0,
        "real_shapi_calls": 0,
        "real_minimax_h3_submissions": 0,
    }


def _next_operation(session: Any, *, shot_ids: list[int], image_profile_id: str, video_profile_id: str) -> dict[str, Any] | None:
    for index, shot_id in enumerate(shot_ids):
        detail = resolve_shot_production_state(session, shot_id=int(shot_id))
        state = _text(detail.get("state")).upper()
        # Stage B cannot spend money while Stage A is awaiting review,
        # generating, failed, stale, or otherwise incomplete.
        if index > 0:
            previous = resolve_shot_production_state(session, shot_id=int(shot_ids[index - 1]))
            if _text(previous.get("state")).upper() != "COMPLETE":
                return None
        if state == "NEEDS_KEYFRAME_IMAGES":
            shot = session.query(StoryboardShot).filter_by(id=int(shot_id)).one()
            plan = _active_plan(session, shot)
            sequence = _active_sequence(session, shot, plan)
            frames = _frames(session, sequence)
            for frame_name in ("start", "end"):
                frame = frames.get(frame_name)
                if frame is not None and _image_frame_state(session, shot, frame, sequence).get("state") not in {"APPROVED", "REVIEW_REQUIRED"}:
                    return {"kind": "IMAGE", "shot_id": int(shot_id), "keyframe_id": int(frame.id), "profile_id": image_profile_id}
        if state == "READY_FOR_VIDEO":
            return {"kind": "VIDEO", "shot_id": int(shot_id), "profile_id": video_profile_id}
    return None


def execute_one(session: Any, *, shot_ids: list[int], image_profile_id: str, video_profile_id: str, allowed_image_calls: int, allowed_video_calls: int) -> dict[str, Any]:
    operation = _next_operation(session, shot_ids=shot_ids, image_profile_id=image_profile_id, video_profile_id=video_profile_id)
    if operation is None:
        return {"status": "NO_EXECUTABLE_OPERATION", "provider_calls": 0}
    image_calls = session.query(GenerationExecutionRecord).filter(GenerationExecutionRecord.target_media == "IMAGE", GenerationExecutionRecord.model_profile_id == image_profile_id).count()
    video_calls = session.query(GenerationExecutionRecord).filter(GenerationExecutionRecord.target_media == "VIDEO", GenerationExecutionRecord.model_profile_id == video_profile_id).count()
    if operation["kind"] == "IMAGE":
        if image_calls >= int(allowed_image_calls):
            return {"status": "BLOCKED_BUDGET", "blocker": "image_budget_exhausted", "provider_calls": 0}
        result = produce_keyframe_image(session, keyframe_id=operation["keyframe_id"], model_profile_id=image_profile_id, fixture=False, production_required=True)
        session.commit()
        return {"status": "IMAGE_SUBMITTED", "shot_id": operation["shot_id"], "keyframe_id": operation["keyframe_id"], "execution_id": result.get("execution", {}).get("execution_id"), "provider_calls": int(result.get("real_provider_calls") or result.get("provider_calls") or 0), "review_required": True}
    if video_calls >= int(allowed_video_calls):
        return {"status": "BLOCKED_BUDGET", "blocker": "video_budget_exhausted", "provider_calls": 0}
    result = execute_shot_video_production(session, shot_id=operation["shot_id"], provider_id=VIDEO_PROVIDER, model_profile_id=video_profile_id)
    session.commit()
    execution = result.get("execution") or {}
    return {"status": "VIDEO_SUBMITTED", "shot_id": operation["shot_id"], "execution_id": execution.get("execution_id"), "provider_task_id": execution.get("provider_task_id"), "provider_calls": int(result.get("provider_calls") or 0), "review_required": True}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-id", type=int, required=True)
    parser.add_argument("--allow-episode-id", type=int, default=None, help="Exact Episode allowlist entry required for pilot execution.")
    parser.add_argument("--shot-id", type=int, action="append", dest="shot_ids", required=True)
    parser.add_argument("--image-profile-id", default=os.getenv("REAL_EPISODE_IMAGE_PROFILE_ID", "local-image-mw4y52"))
    parser.add_argument("--video-profile-id", default=os.getenv("REAL_EPISODE_VIDEO_PROFILE_ID", "local-video-7deneh"))
    parser.add_argument("--allow-image-calls", type=int, default=MAX_IMAGE_CALLS)
    parser.add_argument("--allow-video-calls", type=int, default=MAX_VIDEO_CALLS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-real-pilot", default="")
    parser.add_argument("--report", type=Path, default=ROOT / "artifacts" / "e2e-production-pilot" / "REAL_EPISODE_PRODUCTION_PREFLIGHT.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    with Session() as session:
        preflight = build_preflight(session, episode_id=args.episode_id, shot_ids=args.shot_ids, image_profile_id=args.image_profile_id, video_profile_id=args.video_profile_id, allowed_image_calls=args.allow_image_calls, allowed_video_calls=args.allow_video_calls, allowed_episode_id=args.allow_episode_id)
        if args.dry_run:
            if preflight.get("render_plan_id") is None:
                preflight["dry_run"] = {"status": "BLOCKED", "planned_operations": [], "existing_assets": [], "new_executions_required": 0, "review_gates": [], "reason": "episode_render_plan_unavailable"}
            else:
                try:
                    projection = run_episode_production(session, episode_id=args.episode_id, dry_run=True)
                    preflight["dry_run"] = {"status": "PASS", "projection": projection, "planned_operations": projection.get("actions", []), "existing_assets": [item.get("official_media") for item in projection.get("shots", []) if item.get("official_media")], "new_executions_required": preflight.get("planned_real_image_calls", 0) + preflight.get("planned_real_video_calls", 0), "review_gates": [item.get("next_action") for item in projection.get("shots", []) if item.get("next_action")]}
                except Exception as exc:
                    preflight["dry_run"] = {"status": "BLOCKED", "planned_operations": [], "existing_assets": [], "new_executions_required": 0, "review_gates": [], "error": _short_exception(exc)}
            preflight["production_writes"] = 0
        if args.execute:
            if args.confirm_real_pilot != CONSENT_TOKEN:
                preflight["blockers"].append("explicit_real_pilot_consent_required")
                preflight["status"] = "BLOCKED"
            elif preflight["status"] == "READY_FOR_REAL_PILOT":
                preflight["execution"] = execute_one(session, shot_ids=args.shot_ids, image_profile_id=args.image_profile_id, video_profile_id=args.video_profile_id, allowed_image_calls=args.allow_image_calls, allowed_video_calls=args.allow_video_calls)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(preflight, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(preflight, ensure_ascii=False, indent=2, default=str))
        return 0 if preflight["status"] in {"READY_FOR_REAL_PILOT", "BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
