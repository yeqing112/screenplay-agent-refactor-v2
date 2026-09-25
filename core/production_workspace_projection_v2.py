"""Read-only Production Workspace V2 projection.

V2 is a presentation of the existing Production Authority rows. It never
creates or updates authority, candidate, validation, prompt, or media rows.
Currentness is resolved through the typed asset, PromptIR, and OfficialMedia
contracts consumed by production execution.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from .production_workspace_projection import build_production_workspace_projection


# The repository has provider-free persistence helpers for controlled tests
# and backfills, but no public entity-first ingestion HTTP contract yet.  The
# projection must expose that boundary instead of presenting legacy upload
# controls as a production path.
PRODUCTION_ASSET_INGESTION_API_AVAILABLE = False


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


def _preview_url(identity: Any) -> str | None:
    """Return a browser display URL separately from formal storage identity."""
    value = _text(identity)
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} else None


def _prompt_lane(session: Any, *, shot: dict[str, Any], target_media: str) -> dict[str, Any]:
    from models import PromptIRAuthority, PromptIRPointer, PromptIRVersion

    book_id = int(shot.get("book_id") or 0)
    episode = int(shot.get("episode") or 0)
    shot_id = int(shot.get("storyboard_shot_id") or 0)
    pointer = session.query(PromptIRPointer).filter_by(
        book_id=book_id, episode=episode, storyboard_shot_id=shot_id, target_media=target_media,
    ).first()
    version = session.query(PromptIRVersion).filter_by(
        id=getattr(pointer, "prompt_ir_version_id", 0), book_id=book_id,
        episode=episode, storyboard_shot_id=shot_id,
    ).first() if pointer else None
    authority = session.query(PromptIRAuthority).filter_by(
        prompt_ir_version_id=getattr(pointer, "prompt_ir_version_id", 0), book_id=book_id,
        episode=episode, storyboard_shot_id=shot_id,
    ).first() if pointer else None
    payload = _json(getattr(version, "payload_json", "{}"), {}) if version else {}
    policy = payload.get("generation_policy") if isinstance(payload, dict) and isinstance(payload.get("generation_policy"), dict) else {}
    current = False
    state = "not_started"
    reason_codes: list[str] = []
    if pointer is None or version is None or authority is None:
        reason_codes.append("PROMPT_IR_POINTER_MISSING")
    else:
        try:
            from core.prompt_ir_phase_e import validate_prompt_ir_current_scope

            resolved = validate_prompt_ir_current_scope(
                session, book_id=book_id, episode=episode,
                storyboard_shot_id=shot_id, target_media=target_media,
            )
            current = bool(
                resolved.get("integrity_valid")
                and resolved.get("current_lineage_valid")
                and str(getattr(pointer, "payload_hash", "")) == str(getattr(version, "payload_hash", ""))
            )
            if not current:
                reason_codes.extend(
                    str(item.get("code") or "PROMPT_IR_NOT_CURRENT")
                    for item in (resolved.get("diagnostics") or [])
                    if isinstance(item, dict)
                )
        except Exception as exc:  # read-only projection must fail closed
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                reason_codes.append(_text(detail.get("code")) or "PROMPT_IR_CURRENTNESS_INVALID")
            else:
                reason_codes.append("PROMPT_IR_CURRENTNESS_INVALID")
        if _text(getattr(version, "stale_status", "")).upper() != "FRESH" or _text(getattr(authority, "stale_status", "")).upper() != "FRESH":
            reason_codes.append("PROMPT_IR_STALE")
        if not current and not reason_codes:
            reason_codes.append("PROMPT_IR_NOT_CURRENT")
    if current:
        state = "complete"
    elif "PROMPT_IR_STALE" in reason_codes or any("STALE" in code for code in reason_codes):
        state = "stale"
    elif pointer is not None:
        state = "blocked"
    return {
        "current": current,
        "version": getattr(version, "id", None),
        "stale": state == "stale",
        "state": state,
        "payload_hash": _text(getattr(version, "payload_hash", "")) or None,
        "generation_policy": dict(policy) if isinstance(policy, dict) else {},
        "reason_codes": sorted(set(reason_codes)),
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


def _validation_for_candidate(validations: list[Any], candidate_id: str) -> Any | None:
    """Choose validation by lifecycle meaning, then stable timestamps/ID."""
    rows = [row for row in validations if _text(getattr(row, "candidate_id", "")) == candidate_id]
    rank = {"TECHNICALLY_VALID": 4, "REVIEW_REQUIRED": 3, "VALIDATION_PENDING": 2, "STALE": 1}
    rows.sort(key=lambda row: (
        rank.get(_text(getattr(row, "status", "")).upper(), 0),
        _iso(getattr(row, "updated_at", None) or getattr(row, "created_at", None)) or "",
        _text(getattr(row, "validation_id", "")),
    ), reverse=True)
    return rows[0] if rows else None


def _candidate_projection(candidate: Any, validation: Any | None) -> dict[str, Any]:
    technical = _json(getattr(validation, "technical_validation_payload_json", "{}"), {}) if validation else {}
    storage = _text(getattr(candidate, "storage_identity", "")) or None
    return {
        "id": _text(getattr(candidate, "candidate_id", "")),
        "state": _text(getattr(candidate, "status", "")) or "MEDIA_CANDIDATE",
        "preview": _preview_url(storage),
        "preview_url": _preview_url(storage),
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
        "storage_identity": storage,
    }


def _official_projection(session: Any, *, shot: dict[str, Any], target_media: str) -> dict[str, Any]:
    from models import OfficialMediaAuthority, OfficialMediaPointer, OfficialMediaVersion

    book_id = int(shot.get("book_id") or 0)
    episode = int(shot.get("episode") or 0)
    shot_id = int(shot.get("storyboard_shot_id") or 0)
    role = "SHOT_PRIMARY_IMAGE" if target_media == "IMAGE" else "SHOT_PRIMARY_VIDEO"
    pointer = session.query(OfficialMediaPointer).filter_by(
        book_id=book_id, episode=episode, storyboard_shot_id=shot_id, media_role=role,
    ).first()
    if pointer is None:
        return {"current": False, "currentness": "missing", "version": None, "authority": None, "pointer": None, "preview": None, "preview_url": None}
    version = session.query(OfficialMediaVersion).filter_by(official_media_version_id=getattr(pointer, "official_media_version_id", "")).first()
    authority = session.query(OfficialMediaAuthority).filter_by(authority_id=getattr(pointer, "authority_id", "")).first()
    pointer_projection = {"id": getattr(pointer, "id", None), "authority_id": _text(getattr(pointer, "authority_id", "")) or None, "fingerprint": _text(getattr(pointer, "fingerprint", "")) or None}
    if version is None or authority is None:
        return {"current": False, "currentness": "invalid", "version": None, "authority": None, "pointer": pointer_projection, "preview": None, "preview_url": None}

    current = False
    failure = ""
    try:
        from core.media_authority import resolve_current_official_media_for_shot

        resolve_current_official_media_for_shot(
            session, book_id=book_id, episode=episode,
            storyboard_shot_id=shot_id, media_role=role,
        )
        current = True
    except Exception as exc:  # resolver is intentionally fail-closed
        failure = _text(getattr(exc, "code", "")) or _text(getattr(exc, "detail", ""))
    if not current:
        prompt_lane = _prompt_lane(session, shot=shot, target_media=target_media)
        prompt_moved = bool(
            not prompt_lane["current"]
            or int(prompt_lane.get("version") or 0) != int(getattr(version, "prompt_ir_version_id", 0) or 0)
            or _text(prompt_lane.get("payload_hash")) != _text(getattr(version, "prompt_ir_payload_hash", ""))
        )
        asset_moved = False
        try:
            from core.media_authority import _production_asset_binding_snapshot

            envelope = _json(getattr(authority, "authority_envelope_json", "{}"), {})
            declared = envelope.get("production_asset_binding") if isinstance(envelope, dict) else None
            live_binding = _production_asset_binding_snapshot(session, storyboard_shot_id=shot_id)
            asset_moved = bool(isinstance(declared, dict) and declared.get("fingerprint") != live_binding.get("fingerprint"))
        except Exception:
            asset_moved = False
        if (prompt_moved or asset_moved) and _text(getattr(version, "status", "")).upper() == "CURRENT":
            currentness = "obsolete"
        elif _text(getattr(version, "status", "")).upper() != "CURRENT" or _text(getattr(authority, "status", "")).upper() != "CURRENT":
            currentness = "historical"
        else:
            currentness = "invalid"
    else:
        currentness = "current"
    storage = _text(getattr(version, "storage_identity", "")) or None
    version_projection = {
        "id": _text(getattr(version, "official_media_version_id", "")),
        "revision": getattr(version, "revision", None),
        "media_type": _text(getattr(version, "media_type", "")),
        "storage_identity": storage,
        "checksum": _text(getattr(version, "checksum_sha256", "")) or None,
        "mime": _text(getattr(version, "mime_type", "")) or None,
        "width": getattr(version, "width", None),
        "height": getattr(version, "height", None),
        "duration_ms": getattr(version, "duration_ms", None),
        "candidate_id": _text(getattr(version, "candidate_id", "")) or None,
        "validation_id": _text(getattr(version, "validation_id", "")) or None,
    }
    return {
        "current": current,
        "currentness": currentness,
        "version": version_projection,
        "authority": {"id": _text(getattr(authority, "authority_id", "")) or None, "status": _text(getattr(authority, "status", "")) or None, "payload_hash": _text(getattr(authority, "payload_hash", "")) or None, "lineage_hash": _text(getattr(authority, "lineage_hash", "")) or None, "resolver_error": failure or None},
        "pointer": pointer_projection,
        "preview": _preview_url(storage),
        "preview_url": _preview_url(storage),
    }


def _required_asset_contract(session: Any, *, shot_id: int) -> list[tuple[str, str]]:
    """Read an explicit persisted requirement contract, never prompt prose."""
    from models import StoryboardShot

    shot = session.query(StoryboardShot).filter_by(id=shot_id).first()
    if shot is None:
        return []
    links = _json(getattr(shot, "asset_links", "{}"), {})
    meta = _json(getattr(shot, "meta_info", "{}"), {})
    candidates: list[Any] = []
    if isinstance(links, dict):
        candidates.extend([
            links.get("production_asset_requirements"),
            links.get("canonical_asset_identity"),
            links.get("asset_identity_bindings"),
        ])
    if isinstance(meta, dict):
        candidates.extend([
            meta.get("production_asset_requirements"),
            meta.get("asset_bindings"),
            meta.get("asset_identity_bindings"),
        ])
    result: list[tuple[str, str]] = []

    def add(kind: str, value: Any) -> None:
        kind = kind.upper()
        if kind not in {"CHARACTER", "SCENE", "PROP"}:
            return
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict):
                item = item.get("entity_id") or item.get("canonical_asset_id") or item.get("asset_id") or item.get("identity_ref")
                if isinstance(item, str) and ":" in item:
                    item = item.split(":", 1)[1]
            identity = _text(item)
            if ":" in identity:
                prefix, suffix = identity.split(":", 1)
                if prefix.strip().upper() in {"CHARACTER", "SCENE", "PROP"}:
                    identity = _text(suffix)
            if identity and (kind, identity) not in result:
                result.append((kind, identity))

    for candidate in candidates:
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict):
                    add(_text(item.get("asset_type") or item.get("type")), item)
                elif isinstance(item, str) and ":" in item:
                    prefix, identity = item.split(":", 1)
                    add(prefix, identity)
            continue
        if not isinstance(candidate, dict):
            continue
        canonical = candidate.get("canonical_asset_identity") if isinstance(candidate.get("canonical_asset_identity"), dict) else candidate
        add("SCENE", canonical.get("scene") or canonical.get("scene_id") or candidate.get("scene"))
        add("CHARACTER", canonical.get("characters") or canonical.get("character_asset_ids") or candidate.get("characters"))
        add("PROP", canonical.get("props") or canonical.get("prop_asset_ids") or candidate.get("props"))
        for item in candidate.get("bound_assets", []) if isinstance(candidate.get("bound_assets"), list) else []:
            if isinstance(item, dict):
                add(_text(item.get("asset_type") or item.get("type")), item)
    return result


def _asset_readiness(session: Any, *, shot_id: int, book_id: int) -> dict[str, Any]:
    from models import ShotAssetBinding
    from core.production_asset_authority import resolve_current_production_asset_binding

    bindings = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=shot_id).order_by(ShotAssetBinding.id.asc()).all()
    required: dict[str, list[dict[str, Any]]] = {"CHARACTER": [], "SCENE": [], "PROP": []}
    missing: list[str] = []
    stale: list[str] = []
    formal_requirements = _required_asset_contract(session, shot_id=shot_id)
    if not bindings and not formal_requirements:
        missing.append("FORMAL_ASSET_BINDINGS")
    resolved_rows: list[tuple[Any, dict[str, Any]]] = []
    for binding in bindings:
        resolved_rows.append((binding, resolve_current_production_asset_binding(session, binding)))
    if formal_requirements:
        for kind, entity_id in formal_requirements:
            matching = [(binding, resolved) for binding, resolved in resolved_rows if _text(getattr(binding, "asset_type", "")).upper() == kind and _text(resolved.get("entity_id")) == entity_id]
            if not matching:
                required.setdefault(kind, []).append({"entity_id": entity_id, "authority_id": None, "version_id": None, "status": "MISSING", "current": False, "media": {}, "failed_checks": ["binding_missing"], "fingerprint": None})
                missing.append(f"{kind}:{entity_id}")
                continue
            # A version rollover can leave a historical STALE row beside the
            # current binding. Prefer a row that resolves through the live
            # Authority/Pointer/Version chain, then keep the oldest row as a
            # deterministic fail-closed fallback when none resolves.
            bindings_for_requirement = sorted(
                matching,
                key=lambda pair: (
                    bool(pair[1].get("current")),
                    -int(getattr(pair[0], "id", 0) or 0),
                ),
                reverse=True,
            )[:1]
            for binding, resolved in bindings_for_requirement:
                _append_resolved_requirement(required, missing, stale, kind, entity_id, binding, resolved)
        # A formal requirement contract is authoritative; a binding row that
        # is not named by it is historical/extra and cannot satisfy coverage.
    else:
        for binding, resolved in resolved_rows:
            kind = _text(getattr(binding, "asset_type", "")).upper() or "UNKNOWN"
            entity_id = _text(resolved.get("entity_id")) or f"{kind}:{_text(getattr(binding, 'authority_id', ''))}"
            _append_resolved_requirement(required, missing, stale, kind, entity_id, binding, resolved)

    required_items = [item for values in required.values() for item in values]
    current = bool(formal_requirements or bindings) and not missing and not stale and bool(required_items) and all(item.get("current") for item in required_items)
    missing = sorted(set(missing))
    stale = sorted(set(stale))
    unique_required_items = {
        (str(item.get("asset_type", "")), str(item.get("entity_id", "")))
        for item in required_items
        if item.get("asset_type") and item.get("entity_id")
    }
    return {
        "state": "ready" if current else ("stale" if stale and not missing else "blocked"),
        "required": required,
        "required_entities": [
            f"{kind}:{entity_id}"
            for kind, entity_id in (formal_requirements or [(item.get("asset_type", ""), item.get("entity_id", "")) for item in required_items])
        ],
        "missing": missing,
        "stale": stale,
        "current": current,
        "required_entity_count": len(formal_requirements) or len(unique_required_items),
        "requirement_source": "production_asset_requirement_contract" if formal_requirements else "current_shot_asset_bindings",
    }


def _append_resolved_requirement(required: dict[str, list[dict[str, Any]]], missing: list[str], stale: list[str], kind: str, entity_id: str, binding: Any, resolved: dict[str, Any]) -> None:
    kind = _text(getattr(binding, "asset_type", "")).upper() or "UNKNOWN"
    failed_checks = list(resolved.get("failed_checks", []))
    media = dict(resolved.get("media")) if isinstance(resolved.get("media"), dict) else {}
    version = resolved.get("version")
    if version is not None:
        media.update({
            "storage_identity": _text(getattr(version, "storage_identity", "")) or None,
            "checksum": _text(getattr(version, "checksum", "")) or None,
            "metadata_hash": _text(getattr(version, "metadata_hash", "")) or None,
            "visual_asset_version_id": getattr(version, "visual_asset_version_id", None),
            "revision": getattr(version, "revision", None),
            "status": _text(getattr(version, "status", "")) or None,
        })
    row = {
        "entity_id": entity_id,
        "asset_type": kind,
        "authority_id": _text(getattr(binding, "authority_id", "")) or None,
        "version_id": _text(getattr(binding, "version_id", "")) or None,
        "status": _text(getattr(binding, "status", "ACTIVE")) or "ACTIVE",
        "current": bool(resolved.get("current")),
        "media": media,
        "failed_checks": failed_checks,
        "fingerprint": _text(getattr(binding, "binding_fingerprint", "")) or None,
    }
    required.setdefault(kind, []).append(row)
    key = f"{kind}:{entity_id}"
    if not resolved.get("current"):
        media_failure = (
            not bool(media.get("present"))
            or any(str(code).lower().startswith("media_") for code in failed_checks)
            or "media_present" in {str(code).lower() for code in failed_checks}
        )
        if row["status"].upper() == "STALE" or (not media_failure and failed_checks):
            stale.append(key)
        else:
            missing.append(key)


def _generation_readiness(*, target_media: str, asset: dict[str, Any], lane: dict[str, Any], selected_profile_id: str | None) -> dict[str, Any]:
    reasons: list[str] = []
    blockers: list[dict[str, Any]] = []
    if not asset.get("current"):
        reasons.append("ASSET_MEDIA_NOT_READY")
        blockers.append({"code": "ASSET_MEDIA_NOT_READY", "message": "先补齐当前镜头所需的真实 Production Asset 媒体。"})
    if not lane["prompt_ir"].get("current"):
        reasons.append("PROMPT_IR_NOT_CURRENT")
        blockers.append({"code": "PROMPT_IR_NOT_CURRENT", "message": "先建立当前正式 PromptIR。"})
    if lane["candidates"].get("count", 0) > 0:
        reasons.append("CANDIDATE_REVIEW_REQUIRED")
        blockers.append({"code": "CANDIDATE_REVIEW_REQUIRED", "message": "先验证或提升现有候选结果。"})
    if lane["official"].get("current"):
        reasons.append("OFFICIAL_MEDIA_ALREADY_CURRENT")
        blockers.append({"code": "OFFICIAL_MEDIA_ALREADY_CURRENT", "message": "当前已有正式版本。"})
    if target_media == "VIDEO":
        mode = lane.get("generation_mode")
        if mode not in {"TEXT_TO_VIDEO", "IMAGE_TO_VIDEO"}:
            reasons.append("VIDEO_GENERATION_MODE_INVALID")
            blockers.append({"code": "VIDEO_GENERATION_MODE_INVALID", "message": "当前 VIDEO PromptIR 没有受支持的生成模式。"})
        elif mode == "IMAGE_TO_VIDEO" and not (lane.get("source_official_image") or {}).get("current"):
            reasons.append("OFFICIAL_IMAGE_REQUIRED")
            blockers.append({"code": "OFFICIAL_IMAGE_REQUIRED", "message": "IMAGE_TO_VIDEO 需要先建立当前正式图片。"})
    if not selected_profile_id:
        reasons.append("MODEL_PROFILE_REQUIRED")
        blockers.append({"code": "MODEL_PROFILE_REQUIRED", "message": "请显式选择本次生成使用的模型。"})
    return {"ready": not reasons, "reason_codes": reasons, "primary_blocker": blockers[0] if blockers else None, "blockers": blockers}


def _lane(session: Any, *, shot: dict[str, Any], target_media: str, selected_profile_id: str | None = None) -> dict[str, Any]:
    from models import GenerationExecutionRecord, MediaCandidateRecord, MediaValidationRecord

    book_id = int(shot.get("book_id") or 0)
    episode = int(shot.get("episode") or 0)
    shot_id = int(shot.get("storyboard_shot_id") or 0)
    executions = session.query(GenerationExecutionRecord).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=shot_id, target_media=target_media).order_by(GenerationExecutionRecord.created_at.desc(), GenerationExecutionRecord.id.desc()).all()
    candidates = session.query(MediaCandidateRecord).join(GenerationExecutionRecord, MediaCandidateRecord.execution_id == GenerationExecutionRecord.execution_id).filter(GenerationExecutionRecord.book_id == book_id, GenerationExecutionRecord.episode == episode, GenerationExecutionRecord.storyboard_shot_id == shot_id, GenerationExecutionRecord.target_media == target_media).order_by(MediaCandidateRecord.created_at.desc(), MediaCandidateRecord.id.desc()).all()
    validation_ids = [item.candidate_id for item in candidates]
    validations = session.query(MediaValidationRecord).filter(MediaValidationRecord.candidate_id.in_(validation_ids)).all() if validation_ids else []
    prompt = _prompt_lane(session, shot=shot, target_media=target_media)
    official = _official_projection(session, shot=shot, target_media=target_media)
    latest_execution = _execution_projection(executions[0] if executions else None)
    candidate_items = [_candidate_projection(item, _validation_for_candidate(validations, _text(item.candidate_id))) for item in candidates[:8]]
    return {"prompt_ir": prompt, "generation_mode": None, "source_official_image": None, "model": {"selected_profile_id": selected_profile_id, "provider": None, "model_name": None, "last_execution_profile_id": latest_execution.get("model_profile_id") if latest_execution else None, "last_execution_model": latest_execution.get("model") if latest_execution else None}, "latest_execution": latest_execution, "candidates": {"count": len(candidates), "latest": candidate_items[0] if candidate_items else None, "items": candidate_items}, "official": official}


def _asset_projection(session: Any, *, base_assets: list[dict[str, Any]], book_id: int) -> list[dict[str, Any]]:
    from models import CharacterAssetAuthority, CharacterAssetVersion, CharacterAssetPointer, SceneAssetAuthority, SceneAssetVersion, SceneAssetPointer, PropAssetAuthority, PropAssetVersion, PropAssetPointer, ShotAssetBinding, StoryboardShot

    type_config = {"CHARACTER": (CharacterAssetAuthority, CharacterAssetVersion, CharacterAssetPointer, "character_id"), "SCENE": (SceneAssetAuthority, SceneAssetVersion, SceneAssetPointer, "scene_id"), "PROP": (PropAssetAuthority, PropAssetVersion, PropAssetPointer, "prop_id")}
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in base_assets:
        item = dict(raw)
        kind = _text(item.get("asset_type")).upper()
        entity = _text(item.get("asset_key")).split(":")[-1]
        by_key[(kind, entity)] = item
    shots = session.query(StoryboardShot).filter_by(book_id=book_id).all()
    shot_ids = [int(row.id) for row in shots]
    bindings = session.query(ShotAssetBinding).filter(ShotAssetBinding.storyboard_shot_id.in_(shot_ids)).all() if shot_ids else []
    binding_by_authority: dict[str, list[Any]] = defaultdict(list)
    for binding in bindings:
        binding_by_authority[_text(binding.authority_id)].append(binding)
    binding_authorities = {(str(binding.asset_type).upper(), _text(binding.authority_id)) for binding in bindings}
    for kind, (authority_model, version_model, pointer_model, entity_field) in type_config.items():
        entity_names = {entity for (asset_kind, entity) in by_key if asset_kind == kind}
        authorities = session.query(authority_model).filter(getattr(authority_model, entity_field).in_(entity_names)).all() if entity_names else []
        authorities_by_id = {_text(row.authority_id): row for row in authorities}
        for binding_kind, authority_id in binding_authorities:
            if binding_kind == kind and authority_id not in authorities_by_id:
                row = session.query(authority_model).filter_by(authority_id=authority_id).first()
                if row is not None:
                    authorities_by_id[authority_id] = row
        for authority_id, authority in authorities_by_id.items():
            entity_id = _text(getattr(authority, entity_field, ""))
            version = session.query(version_model).filter_by(authority_id=authority_id, version_id=getattr(authority, "current_version_id", "")).first() if getattr(authority, "current_version_id", None) else None
            pointer = session.query(pointer_model).filter_by(**{entity_field: entity_id, "authority_id": authority_id}).first()
            media = {"present": False, "storage_identity": None, "checksum": None, "metadata_hash": None, "visual_asset_version_id": None, "mime": None, "width": None, "height": None, "preview_url": None}
            if version is not None:
                from core.production_asset_authority import _pointer_fingerprint, production_asset_media_readiness

                ready = production_asset_media_readiness(
                    storage_identity=version.storage_identity,
                    checksum=version.checksum,
                    metadata_hash=version.metadata_hash,
                )
                pointer_exact = bool(
                    pointer is not None
                    and _text(getattr(pointer, "authority_id", "")) == authority_id
                    and _text(getattr(pointer, "version_id", "")) == _text(getattr(version, "version_id", ""))
                    and _text(getattr(pointer, "fingerprint", "")) == _pointer_fingerprint(
                        entity_id=entity_id,
                        authority_id=authority_id,
                        version_id=str(getattr(version, "version_id", "")),
                    )
                )
                media = {"present": bool(ready.present and _text(getattr(authority, "status", "")).upper() == "ACTIVE" and _text(getattr(version, "status", "")).upper() == "CURRENT" and _text(getattr(authority, "current_version_id", "")) == _text(getattr(version, "version_id", "")) and pointer_exact), "storage_identity": _text(getattr(version, "storage_identity", "")) or None, "checksum": _text(getattr(version, "checksum", "")) or None, "metadata_hash": _text(getattr(version, "metadata_hash", "")) or None, "visual_asset_version_id": getattr(version, "visual_asset_version_id", None), "mime": None, "width": None, "height": None, "preview_url": _preview_url(getattr(version, "storage_identity", "")), "readiness": ready.to_dict() | {"pointer_exact": pointer_exact, "authority_status": _text(getattr(authority, "status", "")) or None, "version_status": _text(getattr(version, "status", "")) or None}}
            item = by_key.setdefault((kind, entity_id), {"asset_key": f"book:{book_id}:{kind.lower()}:{entity_id}", "asset_type": kind.lower()})
            row_bindings = binding_by_authority.get(authority_id, [])
            resolved_bindings = [(row, resolve_current_production_asset_binding(session, row)) for row in row_bindings]
            current_count = sum(1 for _row, resolved in resolved_bindings if resolved.get("current"))
            stale_count = sum(1 for _row, resolved in resolved_bindings if not resolved.get("current"))
            item.update({"entity_id": entity_id, "asset_type": kind, "current_version_id": _text(getattr(version, "version_id", "")) or None, "revision": getattr(version, "revision", None) if version else None, "authority_status": _text(getattr(authority, "status", "")) or None, "stale_status": "FRESH" if media["present"] else "STALE", "reference_state": item.get("reference_state", "needs_action"), "reference_count": int(item.get("reference_count", 0) or 0), "locked_reference": bool(item.get("locked_reference", False)), "media": media, "current_version": {"version_id": _text(getattr(version, "version_id", "")) or None, "revision": getattr(version, "revision", None), "status": _text(getattr(version, "status", "")) or None, "storage_identity": _text(getattr(version, "storage_identity", "")) or None, "checksum": _text(getattr(version, "checksum", "")) or None, "metadata_hash": _text(getattr(version, "metadata_hash", "")) or None, "visual_asset_version_id": getattr(version, "visual_asset_version_id", None)} if version is not None else None, "bindings": [{"storyboard_shot_id": int(row.storyboard_shot_id), "authority_id": _text(row.authority_id), "version_id": _text(row.version_id), "status": _text(row.status) or "ACTIVE", "current": bool(resolved.get("current"))} for row, resolved in sorted(resolved_bindings, key=lambda pair: int(pair[0].storyboard_shot_id))], "binding_counts": {"current": current_count, "stale": stale_count}, "stale_binding_count": stale_count, "current_binding_count": current_count, "history": item.get("history", [])})
    for item in by_key.values():
        item.setdefault("entity_id", _text(item.get("asset_key")).split(":")[-1])
        item.setdefault("media", {"present": False, "storage_identity": None, "checksum": None, "metadata_hash": None, "visual_asset_version_id": None, "mime": None, "width": None, "height": None, "preview_url": None})
        item.setdefault("current_version", None)
        item.setdefault("bindings", [])
        item.setdefault("history", [])
        item.setdefault("binding_counts", {"current": 0, "stale": 0})
        item.setdefault("stale_binding_count", 0)
        item.setdefault("current_binding_count", 0)
    return sorted(by_key.values(), key=lambda item: (str(item.get("asset_type", "")), str(item.get("entity_id", ""))))


def build_production_workspace_projection_v2(session: Any, *, book_id: int, generation_profile_selection: dict[str, str | None] | None = None) -> dict[str, Any]:
    """Return the deterministic, read-only V2 production projection."""
    base = build_production_workspace_projection(session, book_id=book_id)
    selection = generation_profile_selection if isinstance(generation_profile_selection, dict) else {}
    image_profile = _text(selection.get("IMAGE") or selection.get("imageModelProfileId")) or None
    video_profile = _text(selection.get("VIDEO") or selection.get("videoModelProfileId")) or None
    shots: list[dict[str, Any]] = []
    for raw_base in base.get("shots", []):
        raw = dict(raw_base)
        raw["book_id"] = book_id
        readiness = _asset_readiness(session, shot_id=int(raw.get("storyboard_shot_id") or 0), book_id=book_id)
        image = _lane(session, shot=raw, target_media="IMAGE", selected_profile_id=image_profile)
        video = _lane(session, shot=raw, target_media="VIDEO", selected_profile_id=video_profile)
        image["generation_mode"] = "TEXT_TO_IMAGE"
        video_policy = video["prompt_ir"].get("generation_policy") or {}
        video_mode = _text(video_policy.get("mode")).upper()
        video["generation_mode"] = video_mode if video_mode in {"TEXT_TO_VIDEO", "IMAGE_TO_VIDEO"} else None
        video["generation_mode_source"] = "PromptIR.generation_policy.mode"
        video["source_official_image"] = image["official"] if video["generation_mode"] == "IMAGE_TO_VIDEO" and image["official"].get("current") else None
        image["generation_readiness"] = _generation_readiness(target_media="IMAGE", asset=readiness, lane=image, selected_profile_id=image_profile)
        video["generation_readiness"] = _generation_readiness(target_media="VIDEO", asset=readiness, lane=video, selected_profile_id=video_profile)
        blockers = []
        if readiness["state"] == "blocked":
            ingestion_blocked = bool(readiness["missing"] and not PRODUCTION_ASSET_INGESTION_API_AVAILABLE)
            blockers.append({"code": "UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API" if ingestion_blocked else "ASSET_MEDIA_MISSING", "message": "当前未提供正式的实体 Production Asset 摄取 API，暂不能在生产链路中上传或建立绑定。" if ingestion_blocked else "先补齐当前镜头所需的真实角色、场景或道具 Production Asset 媒体。", "entities": readiness["missing"]})
        elif readiness["state"] == "stale":
            blockers.append({"code": "ASSET_BINDING_STALE", "message": "资产已更新或绑定已漂移，请更新当前镜头绑定。", "entities": readiness["stale"]})
        for lane_name, lane in (("IMAGE", image), ("VIDEO", video)):
            primary = lane.get("generation_readiness", {}).get("primary_blocker")
            if isinstance(primary, dict) and primary.get("code") and not any(item.get("code") == primary.get("code") for item in blockers):
                blockers.append({"code": primary.get("code"), "message": primary.get("message", "当前生产状态暂不能继续。"), "lane": lane_name})
        next_action = "BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API" if (readiness["missing"] and not PRODUCTION_ASSET_INGESTION_API_AVAILABLE) else "UPDATE_BINDING" if readiness["stale"] else "UPLOAD_ASSET" if not readiness["current"] else ("REVIEW_IMAGE_CANDIDATE" if image["candidates"]["count"] else "GENERATE_IMAGE" if image["generation_readiness"]["ready"] else "SELECT_IMAGE_MODEL" if "MODEL_PROFILE_REQUIRED" in image["generation_readiness"]["reason_codes"] else "UPDATE_IMAGE_PROMPT" if "PROMPT_IR_NOT_CURRENT" in image["generation_readiness"]["reason_codes"] else "REVIEW_VIDEO_CANDIDATE" if video["candidates"]["count"] else "GENERATE_VIDEO" if video["generation_readiness"]["ready"] else "SELECT_VIDEO_MODEL" if "MODEL_PROFILE_REQUIRED" in video["generation_readiness"]["reason_codes"] else "PREPARE_VIDEO")
        labels = {"UPLOAD_ASSET": "补齐真实资产", "BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API": "等待正式资产摄取 API", "UPDATE_BINDING": "更新镜头绑定", "REVIEW_IMAGE_CANDIDATE": "审核候选图片", "GENERATE_IMAGE": "生成图片", "SELECT_IMAGE_MODEL": "选择图片模型", "UPDATE_IMAGE_PROMPT": "更新图片 PromptIR", "REVIEW_VIDEO_CANDIDATE": "审核候选视频", "GENERATE_VIDEO": "生成视频", "SELECT_VIDEO_MODEL": "选择视频模型", "PREPARE_VIDEO": "准备视频生成"}
        shots.append({"identity": {"episode": raw.get("episode"), "shot_id": raw.get("shot_id"), "storyboard_shot_id": raw.get("storyboard_shot_id"), "plan_shot_id": raw.get("plan_shot_id")}, "scene": {"id": raw.get("scene_id"), "name": raw.get("scene_id")}, "duration": raw.get("duration", 0), "camera": raw.get("camera", {}), "action": raw.get("action", ""), "asset_readiness": readiness, "IMAGE": image, "VIDEO": video, "next_action": {"key": next_action, "label": labels.get(next_action, next_action)}, "blockers": blockers, "legacy": {"prompt_ir_state": raw.get("prompt_ir_state"), "reference_state": raw.get("reference_state"), "media_state": raw.get("media_state")}})
    assets = _asset_projection(session, base_assets=[dict(item) for item in base.get("assets", [])], book_id=book_id)
    project = dict(base.get("project", {}))
    projection_blockers = [{"code": blocker.get("code"), "title": "生产状态阻塞", "description": blocker.get("message", ""), "severity": "blocked", "stage": "PRODUCTION_WORKSPACE_V2", "scope": "shot", "book_id": int(book_id), "episode": shot["identity"].get("episode"), "shot_id": shot["identity"].get("shot_id"), "recommended_action": shot["next_action"]["label"], "target_section": "assets" if blocker.get("code") == "UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API" else "storyboard", "target_params": {"section": "assets" if blocker.get("code") == "UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API" else "storyboard", "episode": shot["identity"].get("episode"), "shot_id": shot["identity"].get("shot_id"), "asset_key": (blocker.get("entities") or [None])[0], "blocker_code": blocker.get("code")}} for shot in shots for blocker in shot.get("blockers", [])]
    if projection_blockers:
        project["overall_state"] = "blocked"
        project["current_blockers"] = list(project.get("current_blockers") or []) + projection_blockers
        project["next_actions"] = [projection_blockers[0]]
    return {"schema_version": "production_workspace_projection_v2", "book_id": int(book_id), "workflow_profile": "production", "read_only": True, "authority_source": "current_authority_pointers_only", "project": project, "stages": base.get("stages", {}), "episodes": base.get("episodes", []), "shots": shots, "assets": assets, "asset_ingestion_api_available": PRODUCTION_ASSET_INGESTION_API_AVAILABLE, "view_contract": {"standard": "state,next_action,blockers,official_media", "professional": "authority,pointer,prompt_ir,model,adapter,transport,execution,candidate,validation,official,history"}, "legacy_adopted_is_display_only": True, "provider_calls": 0}


__all__ = ["build_production_workspace_projection_v2"]
