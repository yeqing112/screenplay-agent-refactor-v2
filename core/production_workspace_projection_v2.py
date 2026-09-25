"""Read-only Production Workspace V2 projection.

V2 is a denser presentation model over the existing authority tables.  It
does not introduce a second source of truth, write rows, or infer production
state from browser caches.  The projection deliberately keeps candidate and
official media separate so the UI can present the promotion boundary clearly.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .production_workspace_projection import build_production_workspace_projection


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _prompt_lane(shot: dict[str, Any], target_media: str) -> dict[str, Any]:
    prompt = shot.get("prompt_ir", {}).get(target_media) if isinstance(shot.get("prompt_ir"), dict) else None
    prompt = prompt if isinstance(prompt, dict) else {}
    return {
        "current": prompt.get("state") == "complete",
        "version": prompt.get("prompt_ir_version_id"),
        "stale": prompt.get("state") == "stale",
        "state": prompt.get("state") or "not_started",
        "payload_hash": prompt.get("payload_hash"),
    }


def _execution_projection(execution: Any | None) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "id": _text(getattr(execution, "execution_id", "")),
        "state": _text(getattr(execution, "status", "")) or "unknown",
        "target_media": _text(getattr(execution, "target_media", "")).upper(),
        "model_profile_id": _text(getattr(execution, "model_profile_id", "")),
        "provider": _text(getattr(execution, "provider", "")),
        "model": _text(getattr(execution, "model", "")),
        "adapter": _text(getattr(execution, "provider_adapter_id", "")),
        "adapter_version": _text(getattr(execution, "provider_adapter_version", "")),
        "transport_retry_count": int(getattr(execution, "transport_retry_count", 0) or 0),
        "provider_task_id": _text(getattr(execution, "provider_task_id", "")),
        "provider_request_id": _text(getattr(execution, "provider_request_id", "")),
        "request_fingerprint": _text(getattr(execution, "provider_request_fingerprint", "")),
        "candidate_id": _text(getattr(execution, "candidate_id", "")) or None,
        "failure_code": _text(getattr(execution, "failure_code", "")) or None,
        "created_at": _iso(getattr(execution, "created_at", None)),
        "completed_at": _iso(getattr(execution, "completed_at", None)),
    }


def _candidate_projection(candidate: Any, validation: Any | None) -> dict[str, Any]:
    technical = _json(getattr(validation, "technical_validation_payload_json", "{}"), {}) if validation else {}
    return {
        "id": _text(getattr(candidate, "candidate_id", "")),
        "state": _text(getattr(candidate, "status", "")) or "MEDIA_CANDIDATE",
        "preview": _text(getattr(candidate, "storage_identity", "")) or None,
        "created_at": _iso(getattr(candidate, "created_at", None)),
        "model_profile_id": _text(getattr(candidate, "model_profile_id", "")),
        "technical_validation": {
            "status": _text(getattr(validation, "status", "")) or "NOT_RUN",
            "validation_id": _text(getattr(validation, "validation_id", "")) or None,
            "mime": _text(getattr(candidate, "mime_type", "")) or None,
            "width": getattr(candidate, "width", None),
            "height": getattr(candidate, "height", None),
            "duration_ms": getattr(candidate, "duration_ms", None),
            "details": technical if isinstance(technical, dict) else {},
        },
        "checksum": _text(getattr(candidate, "checksum_sha256", "")) or None,
        "storage_identity": _text(getattr(candidate, "storage_identity", "")) or None,
    }


def _official_projection(pointer: Any | None, version: Any | None, authority: Any | None) -> dict[str, Any]:
    if not pointer or not version:
        return {
            "current": False,
            "currentness": "missing",
            "version": None,
            "authority": None,
            "preview": None,
        }
    return {
        "current": _text(getattr(version, "status", "")).upper() == "CURRENT",
        "currentness": "current" if _text(getattr(version, "status", "")).upper() == "CURRENT" else "historical",
        "version": {
            "id": _text(getattr(version, "official_media_version_id", "")),
            "revision": getattr(version, "revision", None),
            "media_type": _text(getattr(version, "media_type", "")),
            "storage_identity": _text(getattr(version, "storage_identity", "")) or None,
            "checksum": _text(getattr(version, "checksum_sha256", "")) or None,
            "mime": _text(getattr(version, "mime_type", "")) or None,
            "width": getattr(version, "width", None),
            "height": getattr(version, "height", None),
            "duration_ms": getattr(version, "duration_ms", None),
            "candidate_id": _text(getattr(version, "candidate_id", "")) or None,
            "validation_id": _text(getattr(version, "validation_id", "")) or None,
        },
        "authority": {
            "id": _text(getattr(authority, "authority_id", "")) or None,
            "status": _text(getattr(authority, "status", "")) or None,
            "payload_hash": _text(getattr(authority, "payload_hash", "")) or None,
            "lineage_hash": _text(getattr(authority, "lineage_hash", "")) or None,
        } if authority else None,
        "pointer": {
            "id": getattr(pointer, "id", None),
            "authority_id": _text(getattr(pointer, "authority_id", "")) or None,
            "fingerprint": _text(getattr(pointer, "fingerprint", "")) or None,
        },
        "preview": _text(getattr(version, "storage_identity", "")) or None,
    }


def _asset_readiness(session: Any, *, shot_id: int, book_id: int) -> dict[str, Any]:
    from models import ShotAssetBinding

    bindings = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=shot_id).all()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in bindings:
        grouped[_text(getattr(binding, "asset_type", "")).upper()].append({
            "authority_id": _text(getattr(binding, "authority_id", "")),
            "version_id": _text(getattr(binding, "version_id", "")),
            "status": _text(getattr(binding, "status", "ACTIVE")) or "ACTIVE",
            "current": _text(getattr(binding, "status", "ACTIVE")).upper() == "ACTIVE",
            "fingerprint": _text(getattr(binding, "binding_fingerprint", "")),
        })
    required = {"CHARACTER": grouped.get("CHARACTER", []), "SCENE": grouped.get("SCENE", []), "PROP": grouped.get("PROP", [])}
    missing = [key for key, items in required.items() if not items]
    stale = [key for key, items in required.items() if any(not item["current"] for item in items)]
    return {
        "state": "blocked" if missing else ("stale" if stale else "ready"),
        "required": required,
        "missing": missing,
        "stale": stale,
        "current": not missing and not stale,
    }


def _lane(session: Any, *, shot: dict[str, Any], target_media: str) -> dict[str, Any]:
    from models import GenerationExecutionRecord, MediaCandidateRecord, MediaValidationRecord, OfficialMediaAuthority, OfficialMediaPointer, OfficialMediaVersion

    episode = int(shot.get("episode") or 0)
    storyboard_shot_id = int(shot.get("storyboard_shot_id") or 0)
    executions = session.query(GenerationExecutionRecord).filter_by(book_id=int(shot.get("book_id") or 0), episode=episode, storyboard_shot_id=storyboard_shot_id, target_media=target_media).order_by(GenerationExecutionRecord.created_at.desc()).all()
    candidates = session.query(MediaCandidateRecord).join(GenerationExecutionRecord, MediaCandidateRecord.execution_id == GenerationExecutionRecord.execution_id).filter(GenerationExecutionRecord.book_id == int(shot.get("book_id") or 0), GenerationExecutionRecord.episode == episode, GenerationExecutionRecord.storyboard_shot_id == storyboard_shot_id, GenerationExecutionRecord.target_media == target_media).order_by(MediaCandidateRecord.created_at.desc()).all()
    validation_ids = [item.candidate_id for item in candidates]
    validations = session.query(MediaValidationRecord).filter(MediaValidationRecord.candidate_id.in_(validation_ids)).all() if validation_ids else []
    validation_by_candidate = {_text(item.candidate_id): item for item in validations}
    role = "SHOT_PRIMARY_IMAGE" if target_media == "IMAGE" else "SHOT_PRIMARY_VIDEO"
    pointers = session.query(OfficialMediaPointer).filter_by(book_id=int(shot.get("book_id") or 0), episode=episode, storyboard_shot_id=storyboard_shot_id, media_role=role).all()
    pointer = pointers[0] if pointers else None
    version = session.query(OfficialMediaVersion).filter_by(official_media_version_id=getattr(pointer, "official_media_version_id", "")).first() if pointer else None
    authority = session.query(OfficialMediaAuthority).filter_by(official_media_version_id=getattr(pointer, "official_media_version_id", "")).first() if pointer else None
    latest_execution = _execution_projection(executions[0] if executions else None)
    latest_candidate = _candidate_projection(candidates[0], validation_by_candidate.get(_text(candidates[0].candidate_id))) if candidates else None
    return {
        "prompt_ir": _prompt_lane(shot, target_media),
        "generation_mode": None,
        "source_official_image": None,
        "model": {
            "selected_profile_id": latest_execution.get("model_profile_id") if latest_execution else None,
            "provider": latest_execution.get("provider") if latest_execution else None,
            "model_name": latest_execution.get("model") if latest_execution else None,
        },
        "latest_execution": latest_execution,
        "candidates": {"count": len(candidates), "latest": latest_candidate, "items": [_candidate_projection(item, validation_by_candidate.get(_text(item.candidate_id))) for item in candidates[:8]]},
        "official": _official_projection(pointer, version, authority),
    }


def build_production_workspace_projection_v2(session: Any, *, book_id: int) -> dict[str, Any]:
    """Return the V2 read model over the existing V1 authority projection."""
    from models import ProductionAssetVersionRegistry, ShotAssetBinding, StoryboardShot, VisualReferenceAuthority

    base = build_production_workspace_projection(session, book_id=book_id)
    shots = []
    for raw in base.get("shots", []):
        raw = dict(raw)
        raw["book_id"] = book_id
        readiness = _asset_readiness(session, shot_id=int(raw.get("storyboard_shot_id") or 0), book_id=book_id)
        image = _lane(session, shot=raw, target_media="IMAGE")
        video = _lane(session, shot=raw, target_media="VIDEO")
        image["generation_mode"] = "TEXT_TO_IMAGE"
        video["generation_mode"] = "IMAGE_TO_VIDEO" if image["official"].get("current") else "TEXT_TO_VIDEO"
        video["source_official_image"] = image["official"] if image["official"].get("current") else None
        blockers = []
        if readiness["state"] == "blocked": blockers.append({"code": "ASSET_MEDIA_MISSING", "message": "先补齐当前镜头所需的角色、场景或道具资产。"})
        if readiness["state"] == "stale": blockers.append({"code": "ASSET_BINDING_STALE", "message": "资产已更新，镜头绑定需要同步。"})
        next_action = "UPLOAD_ASSET" if readiness["state"] == "blocked" else ("UPDATE_BINDING" if readiness["state"] == "stale" else ("REVIEW_IMAGE_CANDIDATE" if image["candidates"]["count"] else ("GENERATE_IMAGE" if image["prompt_ir"]["current"] else "PREPARE_IMAGE")))
        shots.append({
            "identity": {"episode": raw.get("episode"), "shot_id": raw.get("shot_id"), "storyboard_shot_id": raw.get("storyboard_shot_id"), "plan_shot_id": raw.get("plan_shot_id")},
            "scene": {"id": raw.get("scene_id"), "name": raw.get("scene_id")},
            "duration": raw.get("duration", 0), "camera": raw.get("camera", {}), "action": raw.get("action", ""),
            "asset_readiness": readiness,
            "IMAGE": image, "VIDEO": video,
            "next_action": {"key": next_action, "label": {"UPLOAD_ASSET":"补齐资产", "UPDATE_BINDING":"更新镜头绑定", "REVIEW_IMAGE_CANDIDATE":"审核候选图片", "GENERATE_IMAGE":"生成图片", "PREPARE_IMAGE":"准备图片生成"}.get(next_action, next_action)},
            "blockers": blockers,
            "legacy": {"prompt_ir_state": raw.get("prompt_ir_state"), "reference_state": raw.get("reference_state"), "media_state": raw.get("media_state")},
        })

    references = session.query(VisualReferenceAuthority).filter(
        VisualReferenceAuthority.asset_key.in_([_text(item.get("asset_key")) for item in base.get("assets", [])])
    ).all() if base.get("assets") else []
    references_by_asset = defaultdict(list)
    for reference in references:
        references_by_asset[_text(getattr(reference, "asset_key", ""))].append(reference)
    bindings = session.query(ShotAssetBinding).join(StoryboardShot, ShotAssetBinding.storyboard_shot_id == StoryboardShot.id).filter(StoryboardShot.book_id == book_id).all()
    bindings_by_authority = defaultdict(list)
    for binding in bindings:
        bindings_by_authority[_text(getattr(binding, "authority_id", ""))].append(binding)
    production_versions = session.query(ProductionAssetVersionRegistry).all()
    production_version_by_visual_id = {
        int(getattr(version, "visual_asset_version_id")): version
        for version in production_versions
        if getattr(version, "visual_asset_version_id", None) is not None
    }

    assets = []
    for asset in base.get("assets", []):
        item = dict(asset)
        item["entity_id"] = _text(item.get("asset_key")).split(":")[-1]
        production_version = production_version_by_visual_id.get(int(item.get("current_version_id"))) if item.get("current_version_id") is not None else None
        authority_id = _text(getattr(production_version, "authority_id", ""))
        asset_refs = references_by_asset.get(_text(item.get("asset_key")), [])
        locked_ref = next((ref for ref in asset_refs if _text(getattr(ref, "status", "")).upper() == "LOCKED" and _text(getattr(ref, "stale_status", "")).upper() in {"", "FRESH", "CURRENT"}), None)
        item["media"] = {
            "present": bool(locked_ref and _text(getattr(locked_ref, "image_identity", "")) and _text(getattr(locked_ref, "checksum", ""))),
            "storage_identity": _text(getattr(locked_ref, "image_identity", "")) or None,
            "checksum": _text(getattr(locked_ref, "checksum", "")) or None,
            "mime": None,
            "width": None,
            "height": None,
        }
        item["bindings"] = [{
            "storyboard_shot_id": int(getattr(binding, "storyboard_shot_id", 0)),
            "authority_id": _text(getattr(binding, "authority_id", "")),
            "version_id": _text(getattr(binding, "version_id", "")),
            "status": _text(getattr(binding, "status", "ACTIVE")) or "ACTIVE",
        } for binding in bindings_by_authority.get(authority_id, [])]
        item["history"] = [{
            "reference_authority_id": getattr(ref, "id", None),
            "status": _text(getattr(ref, "status", "")),
            "stale_status": _text(getattr(ref, "stale_status", "")),
            "lock_revision": getattr(ref, "lock_revision", None),
        } for ref in asset_refs]
        assets.append(item)

    return {
        "schema_version": "production_workspace_projection_v2",
        "book_id": int(book_id),
        "workflow_profile": "production",
        "read_only": True,
        "authority_source": "current_authority_pointers_only",
        "project": base.get("project", {}),
        "stages": base.get("stages", {}),
        "episodes": base.get("episodes", []),
        "shots": shots,
        "assets": assets,
        "view_contract": {"standard": "state,next_action,blockers,official_media", "professional": "authority,pointer,prompt_ir,model,adapter,transport,execution,candidate,validation,official,history"},
        "legacy_adopted_is_display_only": True,
        "provider_calls": int(base.get("provider_calls", 0) or 0),
    }


__all__ = ["build_production_workspace_projection_v2"]
