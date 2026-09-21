"""Phase F controlled generation-canary boundary.

The route resolves current PromptIR authority on every operation, rebuilds the
deterministic GenerationPayload, and persists an append-only execution record
before any provider call.  Successful output is stored only as a
``MEDIA_CANDIDATE``; no storyboard, PromptIR, asset pointer, or reference
authority is mutated here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.generation_adapters import (
    ModelProfileError,
    SHAPI_GEMINI_IMAGE_PROVIDER,
    SHAPI_OPENAI_IMAGES_PROVIDER,
    generate_image_asset,
)
from api.model_registry import get_profile
from core.prompt_ir_phase_e import (
    MODEL_ADAPTER_REGISTRY,
    PromptIRPhaseEError,
    adapt_prompt_ir_to_generation_payload,
    build_generation_policy,
    build_model_profile,
    canonical,
    fingerprint,
    resolve_current_authoritative_prompt_ir,
)
from core.provider_execution_profile import (
    PROFILE_SCHEMA_VERSION,
    build_provider_execution_profile,
    fingerprint_provider_execution_profile,
)
from core.public_asset_storage import _load_source_bytes, _normalize_provider_image_bytes
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    PromptIRPointer,
    Session,
    VisualAssetPointer,
    VisualReferenceAsset,
    VisualReferenceAuthority,
)


router = APIRouter(prefix="/api/books", tags=["generation-canary"])

_FAKE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_SYNC_IMAGE_PROVIDERS = {
    "openai-compatible",
    SHAPI_OPENAI_IMAGES_PROVIDER,
    SHAPI_GEMINI_IMAGE_PROVIDER,
}


class CanaryPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    adapter_id: str = Field(min_length=1, validation_alias="adapter_id")
    model_profile_id: str = Field(min_length=1, validation_alias="model_profile_id")


class CanaryExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    execute: bool = False
    confirmation_token: str = Field(default="", min_length=1)
    preview_execution_id: str = Field(min_length=1)


def _error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _redact(value: Any, *, key: str = "") -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("api_key", "authorization", "bearer", "password", "secret")):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key=key) for item in value]
    if isinstance(value, str) and len(value) > 2_000:
        return f"<redacted large value: {len(value)} chars>"
    return value


def _response_hash(value: Any) -> str:
    return hashlib.sha256(canonical(_redact(value)).encode("utf-8")).hexdigest()


def _profile_fingerprint(profile: dict[str, Any], *, adapter_id: str, adapter_version: str) -> str:
    return fingerprint_provider_execution_profile(
        build_provider_execution_profile(profile, adapter_id=adapter_id, adapter_version=adapter_version)
    )


def _confirmation_token(*, execution_id: str, prompt_ir_version_id: int, payload_fp: str, model_profile_id: str, provider_request_fp: str) -> str:
    return hashlib.sha256(
        canonical(
            {
                "schema_version": "phase_f_confirmation_v1",
                "execution_id": execution_id,
                "prompt_ir_version_id": prompt_ir_version_id,
                "generation_payload_fingerprint": payload_fp,
                "model_profile_id": model_profile_id,
                "provider_request_fingerprint": provider_request_fp,
            }
        ).encode("utf-8")
    ).hexdigest()


def _reference_images(session: Any, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve only exact current ReferenceAuthority bindings to media inputs."""
    output: list[dict[str, Any]] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        authority_fp = str(binding.get("reference_authority_fingerprint") or binding.get("reference_authority_ref") or "").strip()
        if not authority_fp:
            continue
        authority = session.query(VisualReferenceAuthority).filter_by(authority_fingerprint=authority_fp).first()
        if authority is None or str(authority.status or "").upper() not in {"LOCKED", "REFERENCE_LOCKED"} or str(authority.stale_status or "FRESH").upper() != "FRESH":
            raise _error(409, "GENERATION_REFERENCE_AUTHORITY_STALE", "Generation reference authority is not locked and fresh.", authority_fingerprint=authority_fp)
        pointer = session.query(VisualAssetPointer).filter_by(asset_key=authority.asset_key).first()
        if pointer is None or int(pointer.current_version_id or 0) != int(authority.asset_version_id or 0) or str(pointer.payload_hash or "") != str(authority.asset_version_fingerprint or ""):
            raise _error(409, "GENERATION_REFERENCE_AUTHORITY_STALE", "Generation reference authority is not bound to the current VisualAssetPointer.", authority_fingerprint=authority_fp)
        storage = _json(authority.storage_reference_json, {})
        reference = session.query(VisualReferenceAsset).filter_by(id=authority.visual_reference_asset_id).first()
        image_url = ""
        if isinstance(storage, dict):
            image_url = str(storage.get("image_url") or storage.get("imageUrl") or storage.get("public_url") or storage.get("url") or storage.get("storage_key") or "").strip()
        if not image_url and reference is not None:
            image_url = str(reference.image_url or reference.local_path or "").strip()
        if not image_url:
            raise _error(409, "GENERATION_REFERENCE_STORAGE_MISSING", "Current reference authority has no usable storage identity.", authority_fingerprint=authority_fp)
        output.append(
            {
                "image_url": image_url,
                "reference_authority_fingerprint": authority_fp,
                "reference_authority_ref": authority_fp,
            }
        )
    return output


def _request_snapshot(*, profile: dict[str, Any], adapter: dict[str, Any], payload: dict[str, Any], reference_bindings: list[dict[str, Any]]) -> dict[str, Any]:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    # motion_prompt is retained explicitly; the provider bridge combines it
    # with the static prompt without inventing new creative content.
    execution_profile = profile.get("provider_execution_profile") if isinstance(profile.get("provider_execution_profile"), dict) else build_provider_execution_profile(profile, adapter_id=str(adapter.get("adapter_id") or ""), adapter_version=str(adapter.get("adapter_version") or ""))
    return {
        "schema_version": "phase_f_provider_request_v2",
        "provider_execution_profile_schema": PROFILE_SCHEMA_VERSION,
        "provider": execution_profile.get("provider"),
        "model": execution_profile.get("model"),
        "adapter_id": adapter.get("adapter_id"),
        "adapter_version": adapter.get("adapter_version"),
        "generation_params": execution_profile.get("generation_params") or {},
        "transport_config": execution_profile.get("transport_config") or {},
        "credential": execution_profile.get("credential") or {},
        "target_media": "IMAGE",
        "prompt": str(request.get("prompt") or ""),
        "motion_prompt": str(request.get("motion_prompt") or ""),
        "negative_prompt": str(request.get("negative_prompt") or ""),
        "reference_bindings": [
            {
                "reference_authority_fingerprint": item.get("reference_authority_fingerprint") or item.get("reference_authority_ref"),
            }
            for item in reference_bindings
        ],
        "transport_retry_count": 0,
    }


def _resolve_profile(req: CanaryPreviewRequest, adapter: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    profile = get_profile(req.model_profile_id)
    if not profile:
        raise _error(409, "GENERATION_MODEL_PROFILE_NOT_FOUND", "The explicit image model profile does not exist.")
    if str(profile.get("capability") or "") != "image":
        raise _error(409, "GENERATION_MODEL_PROFILE_MODALITY_MISMATCH", "The explicit model profile is not an image profile.")
    if not profile.get("enabled", True):
        raise _error(409, "GENERATION_MODEL_PROFILE_DISABLED", "The explicit model profile is disabled.")
    provider = str(profile.get("provider") or "").strip()
    if provider != "prototype-task-adapter" and not bool(profile.get("key_configured") or profile.get("api_key")):
        raise _error(409, "GENERATION_PROVIDER_NOT_CONFIGURED", "The explicit image provider has no configured credential.")
    if provider != "prototype-task-adapter" and (not str(profile.get("base_url") or "").strip() or not str(profile.get("model_name") or "").strip()):
        raise _error(409, "GENERATION_PROVIDER_NOT_CONFIGURED", "The explicit image provider is missing base_url or model_name.")
    canonical_profile = build_provider_execution_profile(profile, adapter_id=req.adapter_id, adapter_version=str(adapter.get("adapter_version") or ""))
    if provider != "prototype-task-adapter":
        raw_params = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
        raw_transport = profile.get("transport_config") if isinstance(profile.get("transport_config"), dict) else {}
        timeout_seconds = raw_params.get("timeout_seconds", raw_transport.get("timeout_seconds"))
        try:
            timeout_seconds = float(timeout_seconds)
        except (TypeError, ValueError):
            timeout_seconds = 0
        if timeout_seconds <= 0:
            raise _error(409, "GENERATION_PROVIDER_TIMEOUT_NOT_CONFIGURED", "Phase F real provider profiles must declare a positive transport timeout.")
    if provider not in {"prototype-task-adapter", *_SYNC_IMAGE_PROVIDERS}:
        raise _error(409, "GENERATION_TRANSPORT_RETRY_UNSUPPORTED", "The selected image transport cannot prove zero retries for Phase F Canary.", provider=provider)
    phase_profile = build_model_profile(
        {
            "model_family": adapter.get("model_family") or req.adapter_id.upper(),
            "adapter_id": req.adapter_id,
            "provider_config_ref": req.model_profile_id,
            "capabilities": {
                "supports_reference_images": bool(adapter.get("supports_reference_images")),
                "supports_negative_prompt": bool(adapter.get("supports_negative_prompt")),
                "supports_image": True,
            },
        }
    )
    # Keep raw registry fields for credentialed transport adapters, while
    # exposing the canonical projection to every Phase F audit/request path.
    profile = dict(profile)
    profile["provider_execution_profile"] = canonical_profile
    return profile, phase_profile, fingerprint_provider_execution_profile(canonical_profile)


def _resolve_execution_inputs(session: Any, *, book_id: int, episode: int, shot_id: int, adapter_id: str, model_profile_id: str) -> dict[str, Any]:
    from api.prompt_ir_authority_api import _load_current, _production_asset_authority

    adapter = MODEL_ADAPTER_REGISTRY.get(adapter_id.lower())
    if not adapter or str(adapter.get("model_family") or "").upper() not in {"FLUX", "GENERIC_IMAGE"}:
        raise _error(409, "GENERATION_ADAPTER_NOT_REGISTERED", "The selected adapter is not a registered image adapter.")
    profile_request = CanaryPreviewRequest(adapter_id=adapter_id, model_profile_id=model_profile_id)
    profile, phase_profile, profile_fp = _resolve_profile(profile_request, adapter)
    _materialization_set, row, _set_envelope = _load_current(session, book_id=book_id, episode=episode, shot_id=shot_id)
    pointer = session.query(PromptIRPointer).filter_by(book_id=book_id, episode=episode, storyboard_shot_id=row.id).first()
    if pointer is None:
        raise _error(409, "PROMPT_IR_NOT_CURRENT", "No current PromptIR pointer exists for this shot.")
    meta = _json(getattr(row, "meta_info", "{}"), {})
    handoff = meta.get("prompt_compiler_handoff") if isinstance(meta, dict) else {}
    asset_authority = _production_asset_authority(session, book_id=book_id, handoff=handoff if isinstance(handoff, dict) else {})
    try:
        resolved = resolve_current_authoritative_prompt_ir(
            session,
            book_id=book_id,
            episode=episode,
            storyboard_shot_id=row.id,
            generation_policy=None,
            asset_authority=asset_authority,
            model_profile=phase_profile,
        )
        policy = build_generation_policy(resolved["payload"].get("generation_policy"), allow_default=False)
        if policy.get("target_media") != "IMAGE":
            raise _error(409, "GENERATION_CANARY_IMAGE_REQUIRED", "Phase F first Canary supports only an IMAGE GenerationPolicy.")
        payload = adapt_prompt_ir_to_generation_payload(resolved["payload"], generation_policy=policy, model_profile=phase_profile)
    except PromptIRPhaseEError as exc:
        raise _error(409, exc.code, exc.message, diagnostics=exc.diagnostics)
    if not payload.get("readiness", {}).get("ready"):
        raise _error(409, "GENERATION_PAYLOAD_NOT_READY", "Current PromptIR cannot produce a ready GenerationPayload.", diagnostics=payload.get("readiness", {}).get("reasons", []))
    reference_bindings = payload.get("request", {}).get("reference_bindings", []) if isinstance(payload.get("request"), dict) else []
    reference_images = _reference_images(session, reference_bindings)
    reference_fp = fingerprint(
        [
            {
                "authority_fingerprint": item.get("reference_authority_fingerprint") or item.get("reference_authority_ref"),
            }
            for item in reference_bindings
        ]
    )
    snapshot = _request_snapshot(profile=profile, adapter=adapter, payload=payload, reference_bindings=reference_bindings)
    payload_fp = str(payload.get("generation_payload_fingerprint") or "")
    policy_fp = str(payload.get("generation_policy", {}).get("fingerprint") or policy.get("fingerprint") or "")
    provider_request_fp = fingerprint(
        {
            "schema_version": "phase_f_provider_request_fingerprint_v1",
            "generation_payload_fingerprint": payload_fp,
            "prompt_ir_payload_hash": str(resolved["version"].payload_hash or ""),
            "model_profile_id": model_profile_id,
            "model_profile_fingerprint": profile_fp,
            "provider_adapter_id": adapter.get("adapter_id"),
            "provider_adapter_version": adapter.get("adapter_version"),
            "reference_bindings_fingerprint": reference_fp,
            "target_media": "IMAGE",
            "provider": profile.get("provider"),
            "model": profile.get("model_name"),
        }
    )
    return {
        "row": row,
        "pointer": pointer,
        "resolved": resolved,
        "profile": profile,
        "phase_profile": phase_profile,
        "profile_fingerprint": profile_fp,
        "adapter": adapter,
        "payload": payload,
        "policy": policy,
        "reference_images": reference_images,
        "reference_bindings_fingerprint": reference_fp,
        "request_snapshot": snapshot,
        "provider_request_fingerprint": provider_request_fp,
    }


async def _fake_provider_image(*, request_snapshot: dict[str, Any], provider_request_fingerprint: str) -> dict[str, Any]:
    response = {
        "provider": "phase-f-fake-image-provider",
        "model": "deterministic-image-v1",
        "request_id": f"fake-{provider_request_fingerprint[:24]}",
        "status": "returned_media",
        "media_type": "IMAGE",
    }
    data_uri = "data:image/png;base64," + base64.b64encode(_FAKE_PNG).decode("ascii")
    return {
        "previewUrl": data_uri,
        "uri": data_uri,
        "providerResponse": response,
        "providerRequestPayload": request_snapshot,
        "providerRequestId": response["request_id"],
        "providerTaskId": response["request_id"],
        "provider": response["provider"],
        "model": response["model"],
    }


def _provider_prompt(payload: dict[str, Any]) -> tuple[str, str]:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    prompt = str(request.get("prompt") or "")
    motion = str(request.get("motion_prompt") or "")
    if motion:
        prompt = f"{prompt}\nMOTION: {motion}"
    return prompt, str(request.get("negative_prompt") or "")


def _validate_transport_semantics(context: dict[str, Any]) -> None:
    """Fail closed when the deterministic payload contains unmapped fields."""
    payload = context["payload"]
    unsupported = payload.get("unsupported")
    if isinstance(unsupported, list) and unsupported:
        raise _error(
            409,
            "GENERATION_TRANSPORT_SEMANTIC_UNREPRESENTABLE",
            "GenerationPayload contains required semantics that the selected transport cannot represent.",
            unsupported=[str(item) for item in unsupported],
            provider_calls=0,
        )
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    snapshot = context.get("request_snapshot") if isinstance(context.get("request_snapshot"), dict) else {}
    if str(request.get("prompt") or "") != str(snapshot.get("prompt") or ""):
        raise _error(409, "GENERATION_TRANSPORT_SEMANTIC_UNREPRESENTABLE", "Transport prompt does not equal the deterministic GenerationPayload prompt.", provider_calls=0)
    expected_refs = request.get("reference_bindings") if isinstance(request.get("reference_bindings"), list) else []
    actual_refs = snapshot.get("reference_bindings") if isinstance(snapshot.get("reference_bindings"), list) else []
    expected_ref_ids = [str(item.get("reference_authority_fingerprint") or item.get("reference_authority_ref") or "") for item in expected_refs if isinstance(item, dict)]
    actual_ref_ids = [str(item.get("reference_authority_fingerprint") or item.get("reference_authority_ref") or "") for item in actual_refs if isinstance(item, dict)]
    if expected_ref_ids != actual_ref_ids:
        raise _error(409, "GENERATION_TRANSPORT_SEMANTIC_UNREPRESENTABLE", "Transport reference bindings do not equal the deterministic GenerationPayload.", provider_calls=0)


def _validate_real_provider_opt_in(context: dict[str, Any]) -> None:
    provider = str(context["profile"].get("provider") or "")
    if provider != "prototype-task-adapter" and os.getenv("PHASE_F_PROVIDER_CANARY_REAL", "").strip() != "1":
        raise _error(409, "GENERATION_REAL_PROVIDER_OPT_IN_REQUIRED", "Real Provider Canary requires PHASE_F_PROVIDER_CANARY_REAL=1.", provider_calls=0)


async def _call_provider(*, context: dict[str, Any]) -> dict[str, Any]:
    profile = context["profile"]
    if str(profile.get("provider") or "") == "prototype-task-adapter":
        return await _fake_provider_image(request_snapshot=context["request_snapshot"], provider_request_fingerprint=context["provider_request_fingerprint"])
    prompt, negative = _provider_prompt(context["payload"])
    try:
        generated = await generate_image_asset(
            profile,
            prompt=prompt,
            aspect_ratio=None,
            negative_prompt=negative,
            reference_images=context["reference_images"],
        )
    except ModelProfileError:
        raise
    generated.setdefault("provider", profile.get("provider"))
    generated.setdefault("model", profile.get("model_name"))
    generated.setdefault("providerRequestId", generated.get("externalTaskId") or "")
    generated.setdefault("providerTaskId", generated.get("externalTaskId") or "")
    return generated


def _png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    try:
        from PIL import Image

        import io

        with Image.open(io.BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None, None


def _persist_candidate_media(*, source_url: str, book_id: int, execution_id: str) -> dict[str, Any]:
    if not source_url:
        raise _error(422, "GENERATION_MEDIA_MISSING", "Provider response did not include media bytes or a media URL.")
    # Reuse the existing canonical generated-image storage bridge.  Importing
    # lazily avoids a module cycle while keeping the storage identity contract
    # identical to the existing creative pipeline.
    from api.server import _persist_generated_image_locally

    result = _persist_generated_image_locally(source_url, book_id=book_id, task_id=execution_id, label="phase-f-canary")
    if not result.get("ok"):
        raise _error(422, "GENERATION_MEDIA_INVALID", "Provider media failed canonical storage validation.", diagnostics=result)
    local_path = str(result.get("local_path") or "")
    try:
        data, content_type = _load_source_bytes(local_path)
        data, content_type = _normalize_provider_image_bytes(data, content_type)
    except Exception as exc:
        raise _error(422, "GENERATION_MEDIA_INVALID", "Stored candidate bytes could not be read.", diagnostics={"error": str(exc)})
    if not data:
        raise _error(422, "GENERATION_MEDIA_INVALID", "Stored candidate bytes are empty.")
    width, height = _png_dimensions(data)
    if not width or not height:
        raise _error(422, "GENERATION_MEDIA_INVALID", "Stored candidate image dimensions could not be parsed.")
    return {
        "storage_identity": str(result.get("image_url") or ""),
        "storage_reference": {
            "image_url": str(result.get("image_url") or ""),
            "local_path": local_path,
            "source_kind": result.get("source_kind") or "provider_url",
        },
        "checksum_sha256": str(result.get("sha256") or hashlib.sha256(data).hexdigest()),
        "mime_type": str(content_type or result.get("content_type") or "image/png").split(";", 1)[0].lower(),
        "byte_size": len(data),
        "width": width,
        "height": height,
    }


def _serialize_candidate(row: MediaCandidateRecord | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "candidate_id": row.candidate_id,
        "execution_id": row.execution_id,
        "status": row.status,
        "media_type": row.media_type,
        "storage_identity": row.storage_identity,
        "storage_reference": _json(row.storage_reference_json, {}),
        "checksum_sha256": row.checksum_sha256,
        "mime_type": row.mime_type,
        "byte_size": row.byte_size,
        "width": row.width,
        "height": row.height,
        "duration_ms": row.duration_ms,
        "prompt_ir_version_id": row.prompt_ir_version_id,
        "prompt_ir_payload_hash": row.prompt_ir_payload_hash,
        "generation_payload_fingerprint": row.generation_payload_fingerprint,
        "model_profile_id": row.model_profile_id,
        "model_profile_fingerprint": row.model_profile_fingerprint,
        "provider_request_fingerprint": row.provider_request_fingerprint,
        "provider_response_hash": row.provider_response_hash,
        "provider_task_id": row.provider_task_id,
    }


def _serialize_execution(row: GenerationExecutionRecord) -> dict[str, Any]:
    return {
        "execution_id": row.execution_id,
        "schema_version": row.schema_version,
        "book_id": row.book_id,
        "episode": row.episode,
        "storyboard_shot_id": row.storyboard_shot_id,
        "plan_shot_id": row.plan_shot_id,
        "execution_mode": row.execution_mode,
        "status": row.status,
        "target_media": row.target_media,
        "prompt_ir_version_id": row.prompt_ir_version_id,
        "prompt_ir_authority_id": row.prompt_ir_authority_id,
        "prompt_ir_payload_hash": row.prompt_ir_payload_hash,
        "generation_payload_fingerprint": row.generation_payload_fingerprint,
        "generation_policy_fingerprint": row.generation_policy_fingerprint,
        "model_profile_id": row.model_profile_id,
        "model_profile_fingerprint": row.model_profile_fingerprint,
        "provider_adapter_id": row.provider_adapter_id,
        "provider_adapter_version": row.provider_adapter_version,
        "reference_bindings_fingerprint": row.reference_bindings_fingerprint,
        "provider_request_fingerprint": row.provider_request_fingerprint,
        "provider": row.provider,
        "model": row.model,
        "provider_request_id": row.provider_request_id,
        "provider_task_id": row.provider_task_id,
        "provider_response_hash": row.provider_response_hash,
        "logical_provider_calls": row.logical_provider_calls,
        "transport_retry_count": row.transport_retry_count,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "latency_ms": row.latency_ms,
        "failure_code": row.failure_code,
        "failure_message": row.failure_message,
        "official_promotion_count": row.official_promotion_count,
        "candidate_id": row.candidate_id,
    }


def _validate_candidate_lineage(execution: GenerationExecutionRecord, candidate: MediaCandidateRecord | None) -> None:
    """Validate the durable candidate binding before any successful replay."""
    if candidate is None:
        raise _error(409, "GENERATION_EXECUTION_CANDIDATE_MISSING", "A successful execution has no persisted media candidate.", provider_calls=0)
    checks = {
        "execution_id": (candidate.execution_id, execution.execution_id),
        "provider_request_fingerprint": (candidate.provider_request_fingerprint, execution.provider_request_fingerprint),
        "generation_payload_fingerprint": (candidate.generation_payload_fingerprint, execution.generation_payload_fingerprint),
        "prompt_ir_version_id": (candidate.prompt_ir_version_id, execution.prompt_ir_version_id),
        "model_profile_id": (candidate.model_profile_id, execution.model_profile_id),
        "model_profile_fingerprint": (candidate.model_profile_fingerprint, execution.model_profile_fingerprint),
        "provider_response_hash": (candidate.provider_response_hash, execution.provider_response_hash),
        "status": (candidate.status, "MEDIA_CANDIDATE"),
    }
    invalid = [key for key, (actual, expected) in checks.items() if str(actual or "") != str(expected or "")]
    if invalid:
        raise _error(409, "GENERATION_CANDIDATE_LINEAGE_INVALID", "Persisted candidate lineage does not match the execution record.", invalid_fields=invalid, provider_calls=0)


def _validate_url_scope(session: Any, *, execution: GenerationExecutionRecord, shot_id: int) -> None:
    """Bind the public business shot URL before any replay capability check."""
    from models import StoryboardShot

    query = session.query(StoryboardShot)
    # The public route uses the durable business ``shot_id``.  Prefer that
    # binding; only fall back to the database row id for older/unit fixtures
    # that do not carry the business column.
    current = query.filter_by(book_id=execution.book_id, episode=execution.episode, shot_id=shot_id).first()
    if current is None:
        current = session.query(StoryboardShot).filter_by(book_id=execution.book_id, episode=execution.episode, id=shot_id).first()
    # Unit state-machine sessions do not persist StoryboardShot rows.  The
    # production resolver performs the definitive check below; a real row,
    # when present, must match the durable execution binding here.
    if current is not None and int(getattr(current, "id", 0)) != int(execution.storyboard_shot_id):
        raise _error(409, "GENERATION_CANARY_STALE", "The execution is bound to a different URL shot.", provider_calls=0)


@router.post("/{book_id}/episodes/{episode}/shots/{shot_id}/generation-canary/preview")
def preview_generation_canary(book_id: int, episode: int, shot_id: int, req: CanaryPreviewRequest):
    with Session() as session:
        context = _resolve_execution_inputs(session, book_id=book_id, episode=episode, shot_id=shot_id, adapter_id=req.adapter_id, model_profile_id=req.model_profile_id)
        existing = session.query(GenerationExecutionRecord).filter_by(provider_request_fingerprint=context["provider_request_fingerprint"]).first()
        if existing is not None:
            candidate = session.query(MediaCandidateRecord).filter_by(execution_id=existing.execution_id).first()
            if existing.status in {"SUCCEEDED", "REUSED"}:
                _validate_candidate_lineage(existing, candidate)
            token = _confirmation_token(execution_id=existing.execution_id, prompt_ir_version_id=existing.prompt_ir_version_id, payload_fp=existing.generation_payload_fingerprint, model_profile_id=existing.model_profile_id, provider_request_fp=existing.provider_request_fingerprint)
            return {
                "execution": _serialize_execution(existing),
                "candidate": _serialize_candidate(candidate),
                "generation_payload": context["payload"],
                "provider_request_snapshot": _redact(context["request_snapshot"]),
                "confirmation_token": token,
                "provider_calls": 0,
                "reused": existing.status in {"SUCCEEDED", "REUSED"},
                "media_generated": candidate is not None,
            }
        execution_id = uuid.uuid4().hex
        token = _confirmation_token(execution_id=execution_id, prompt_ir_version_id=int(context["resolved"]["version"].id), payload_fp=context["payload"]["generation_payload_fingerprint"], model_profile_id=req.model_profile_id, provider_request_fp=context["provider_request_fingerprint"])
        now = datetime.utcnow()
        row = GenerationExecutionRecord(
            execution_id=execution_id,
            schema_version="generation_execution_request_v1",
            book_id=book_id,
            episode=episode,
            storyboard_shot_id=int(context["row"].id),
            plan_shot_id=str(context["payload"].get("prompt_ir_ref", {}).get("plan_shot_id") or ""),
            execution_mode="PREVIEW",
            status="PREVIEWED",
            target_media="IMAGE",
            prompt_ir_version_id=int(context["resolved"]["version"].id),
            prompt_ir_authority_id=int(context["resolved"]["authority"].id),
            prompt_ir_payload_hash=str(context["resolved"]["version"].payload_hash or ""),
            generation_payload_fingerprint=str(context["payload"].get("generation_payload_fingerprint") or ""),
            generation_policy_fingerprint=str(context["policy"].get("fingerprint") or ""),
            model_profile_id=req.model_profile_id,
            model_profile_fingerprint=context["profile_fingerprint"],
            provider_adapter_id=str(context["adapter"].get("adapter_id") or req.adapter_id),
            provider_adapter_version=str(context["adapter"].get("adapter_version") or ""),
            reference_bindings_fingerprint=context["reference_bindings_fingerprint"],
            provider_request_fingerprint=context["provider_request_fingerprint"],
            request_snapshot_json=json.dumps(_redact(context["request_snapshot"]), ensure_ascii=False, sort_keys=True),
            confirmation_binding_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            provider=str(context["profile"].get("provider") or ""),
            model=str(context["profile"].get("model_name") or ""),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except Exception:
            session.rollback()
            existing = session.query(GenerationExecutionRecord).filter_by(provider_request_fingerprint=context["provider_request_fingerprint"]).first()
            if existing is None:
                raise
            candidate = session.query(MediaCandidateRecord).filter_by(execution_id=existing.execution_id).first()
            return {"execution": _serialize_execution(existing), "candidate": _serialize_candidate(candidate), "provider_calls": 0, "reused": True, "media_generated": candidate is not None}
        return {
            "execution": _serialize_execution(row),
            "generation_payload": context["payload"],
            "provider_request_snapshot": _redact(context["request_snapshot"]),
            "confirmation_token": token,
            "provider_calls": 0,
            "reused": False,
            "media_generated": False,
        }


@router.post("/{book_id}/episodes/{episode}/shots/{shot_id}/generation-canary/execute")
async def execute_generation_canary(book_id: int, episode: int, shot_id: int, req: CanaryExecuteRequest):
    if not req.execute:
        raise _error(409, "GENERATION_CANARY_EXECUTE_REQUIRED", "Canary execution requires execute=true.", provider_calls=0)
    with Session() as session:
        # The public route accepts the business ``StoryboardShot.shot_id``;
        # the durable record stores the database row id.  Resolve by the
        # opaque execution id first, then bind it to the current URL shot
        # after the authoritative re-resolution below.
        row = session.query(GenerationExecutionRecord).filter_by(
            execution_id=req.preview_execution_id,
            book_id=book_id,
            episode=episode,
        ).first()
        if row is None:
            raise _error(404, "GENERATION_CANARY_PREVIEW_NOT_FOUND", "The preview execution record does not exist.")
        _validate_url_scope(session, execution=row, shot_id=shot_id)
        candidate = session.query(MediaCandidateRecord).filter_by(execution_id=row.execution_id).first()
        # When the execution row carries a candidate id but the foreign
        # execution binding was tampered, load by the immutable candidate id
        # so the caller receives LINEAGE_INVALID rather than silently treating
        # it as an absent candidate.
        if candidate is None and row.candidate_id:
            candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=row.candidate_id).first()
        # Confirmation is checked before current resolution and before any
        # replay branch.  A successful record is never a bearer capability.
        expected_token = _confirmation_token(execution_id=row.execution_id, prompt_ir_version_id=row.prompt_ir_version_id, payload_fp=row.generation_payload_fingerprint, model_profile_id=row.model_profile_id, provider_request_fp=row.provider_request_fingerprint)
        if req.confirmation_token != expected_token:
            raise _error(409, "GENERATION_CANARY_CONFIRMATION_MISMATCH", "The confirmation token is not bound to this preview.", provider_calls=0)
        if row.status == "RUNNING":
            raise _error(409, "GENERATION_CANARY_IN_PROGRESS", "This execution is already claimed by another worker.", provider_calls=0)
        if row.status == "FAILED":
            raise _error(409, "GENERATION_CANARY_FAILED_REQUIRES_NEW_CONFIRMATION", "A failed execution cannot be retried with the same preview.", provider_calls=0)
        if row.status not in {"PREVIEWED", "AUTHORIZED", "SUCCEEDED", "REUSED"}:
            raise _error(409, "GENERATION_CANARY_STALE", "The preview is no longer executable.", provider_calls=0)
        try:
            context = _resolve_execution_inputs(session, book_id=book_id, episode=episode, shot_id=shot_id, adapter_id=row.provider_adapter_id, model_profile_id=row.model_profile_id)
        except HTTPException as exc:
            row.status = "STALE"
            row.failure_code = "GENERATION_CANARY_STALE"
            row.failure_message = "Current authority could not be resolved from the preview snapshot."
            row.updated_at = datetime.utcnow()
            session.commit()
            diagnostics = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
            raise _error(409, "GENERATION_CANARY_STALE", "Current authority could not be resolved from the preview snapshot.", diagnostics=diagnostics, provider_calls=0)
        drift_fields = {
            "prompt_ir_payload_hash": (row.prompt_ir_payload_hash, str(context["resolved"]["version"].payload_hash or "")),
            "generation_payload_fingerprint": (row.generation_payload_fingerprint, str(context["payload"].get("generation_payload_fingerprint") or "")),
            "generation_policy_fingerprint": (row.generation_policy_fingerprint, str(context["policy"].get("fingerprint") or "")),
            "model_profile_fingerprint": (row.model_profile_fingerprint, context["profile_fingerprint"]),
            "provider_request_fingerprint": (row.provider_request_fingerprint, context["provider_request_fingerprint"]),
            "reference_bindings_fingerprint": (row.reference_bindings_fingerprint, context["reference_bindings_fingerprint"]),
        }
        changed = [key for key, (before, after) in drift_fields.items() if str(before or "") != str(after or "")]
        if changed:
            row.status = "STALE"
            row.failure_code = "GENERATION_CANARY_STALE"
            row.failure_message = "Preview authority changed: " + ", ".join(changed)
            row.updated_at = datetime.utcnow()
            session.commit()
            raise _error(409, "GENERATION_CANARY_STALE", "Preview authority changed; create a new preview.", changed=changed, provider_calls=0)
        if int(row.storyboard_shot_id) != int(context["row"].id):
            row.status = "STALE"
            row.failure_code = "GENERATION_CANARY_SHOT_MISMATCH"
            row.failure_message = "Preview execution is bound to a different StoryboardShot."
            row.updated_at = datetime.utcnow()
            session.commit()
            raise _error(409, "GENERATION_CANARY_STALE", "Preview execution is bound to a different shot.", provider_calls=0)
        # Replay is permitted only after the same currentness checks as a new
        # execution, and only when the candidate lineage is self-consistent.
        if row.status in {"SUCCEEDED", "REUSED"}:
            try:
                _validate_candidate_lineage(row, candidate)
            except HTTPException:
                raise
            row.status = "REUSED"
            row.updated_at = datetime.utcnow()
            session.commit()
            return {"execution": _serialize_execution(row), "candidate": _serialize_candidate(candidate), "provider_calls": 0, "reused": True}
        _validate_transport_semantics(context)
        _validate_real_provider_opt_in(context)
        claim_time = datetime.utcnow()
        claimed = session.query(GenerationExecutionRecord).filter_by(
            execution_id=row.execution_id,
            status=row.status,
        ).update(
            {
                "status": "RUNNING",
                "execution_mode": "CANARY",
                "submitted_at": claim_time,
                "updated_at": claim_time,
            },
            synchronize_session=False,
        )
        if claimed != 1:
            session.rollback()
            current = session.query(GenerationExecutionRecord).filter_by(execution_id=row.execution_id).first() or row
            current_candidate = session.query(MediaCandidateRecord).filter_by(execution_id=row.execution_id).first()
            if current.status in {"SUCCEEDED", "REUSED"} and current_candidate is not None:
                return {"execution": _serialize_execution(current), "candidate": _serialize_candidate(current_candidate), "provider_calls": 0, "reused": True}
            raise _error(409, "GENERATION_CANARY_IN_PROGRESS", "This execution is already claimed by another worker.", provider_calls=0)
        row.status = "RUNNING"
        row.execution_mode = "CANARY"
        # ``submitted_at`` is the provider boundary audit timestamp.  It is
        # written and committed before the one logical provider call so a
        # failure cannot be mistaken for a pre-submit validation failure.
        row.submitted_at = claim_time
        row.updated_at = datetime.utcnow()
        session.commit()
        started = time.perf_counter()
        generated: dict[str, Any] = {}
        try:
            generated = await _call_provider(context=context)
            source_url = str(generated.get("uri") or generated.get("previewUrl") or "").strip()
            media = _persist_candidate_media(source_url=source_url, book_id=book_id, execution_id=row.execution_id)
            response_payload = generated.get("providerResponse") if isinstance(generated.get("providerResponse"), dict) else {}
            response_hash = _response_hash(response_payload)
            candidate_id = "candidate-" + uuid.uuid4().hex
            candidate = MediaCandidateRecord(
                candidate_id=candidate_id,
                execution_id=row.execution_id,
                status="MEDIA_CANDIDATE",
                media_type="IMAGE",
                storage_identity=media["storage_identity"],
                storage_reference_json=json.dumps(media["storage_reference"], ensure_ascii=False, sort_keys=True),
                checksum_sha256=media["checksum_sha256"],
                mime_type=media["mime_type"],
                byte_size=media["byte_size"],
                width=media["width"],
                height=media["height"],
                prompt_ir_version_id=row.prompt_ir_version_id,
                prompt_ir_payload_hash=row.prompt_ir_payload_hash,
                generation_payload_fingerprint=row.generation_payload_fingerprint,
                model_profile_id=row.model_profile_id,
                model_profile_fingerprint=row.model_profile_fingerprint,
                provider_request_fingerprint=row.provider_request_fingerprint,
                provider_response_hash=response_hash,
                provider_task_id=str(generated.get("providerTaskId") or generated.get("externalTaskId") or ""),
                created_at=datetime.utcnow(),
            )
            session.add(candidate)
            completed = datetime.utcnow()
            row.status = "SUCCEEDED"
            row.provider = str(generated.get("provider") or context["profile"].get("provider") or "")
            row.model = str(generated.get("model") or context["profile"].get("model_name") or "")
            row.provider_request_id = str(generated.get("providerRequestId") or "")
            row.provider_task_id = str(generated.get("providerTaskId") or generated.get("externalTaskId") or "")
            row.provider_response_hash = response_hash
            row.logical_provider_calls = 1
            row.transport_retry_count = 0
            row.completed_at = completed
            row.latency_ms = int((time.perf_counter() - started) * 1000)
            row.official_promotion_count = 0
            row.candidate_id = candidate_id
            row.failure_code = ""
            row.failure_message = ""
            row.updated_at = completed
            session.commit()
            return {"execution": _serialize_execution(row), "candidate": _serialize_candidate(candidate), "provider_calls": 1, "reused": False, "official_promotion_count": 0}
        except HTTPException as exc:
            session.rollback()
            row = session.query(GenerationExecutionRecord).filter_by(execution_id=req.preview_execution_id).first() or row
            row.status = "FAILED"
            row.logical_provider_calls = 1
            row.transport_retry_count = 0
            row.latency_ms = int((time.perf_counter() - started) * 1000)
            row.failure_code = str((exc.detail or {}).get("code") if isinstance(exc.detail, dict) else "GENERATION_MEDIA_INVALID")
            row.failure_message = str((exc.detail or {}).get("message") if isinstance(exc.detail, dict) else exc.detail)
            row.completed_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            session.commit()
            raise
        except Exception as exc:
            session.rollback()
            row = session.query(GenerationExecutionRecord).filter_by(execution_id=req.preview_execution_id).first() or row
            row.status = "FAILED"
            row.logical_provider_calls = 1
            row.transport_retry_count = 0
            row.latency_ms = int((time.perf_counter() - started) * 1000)
            row.failure_code = "GENERATION_EXECUTION_FAILED"
            row.failure_message = str(exc)[:500]
            row.completed_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            session.commit()
            raise _error(502, "GENERATION_EXECUTION_FAILED", str(exc)[:500], provider_calls=1, retry_calls=0)


__all__ = ["router", "CanaryPreviewRequest", "CanaryExecuteRequest"]
