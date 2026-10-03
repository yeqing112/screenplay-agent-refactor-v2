"""Exact provider transport bindings for canonical IMAGE/VIDEO generation.

The registry is deliberately keyed by explicit provider transport identity and
target media.  Canonical orchestration freezes the request before dispatch;
handlers only submit/poll that frozen request and return the terminal provider
response.  Runtime credentials are copied into a short-lived profile at this
boundary and are never returned in the transport result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from api.generation_adapters import (
    MINIMAX_H3_75API_PROVIDER,
    MINIMAX_H3_ASYNC_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
    POYO_ASYNC_PROVIDER,
    SHAPI_GEMINI_IMAGE_PROVIDER,
    SHAPI_OPENAI_IMAGES_PROVIDER,
    generate_image_asset,
    generate_video_asset,
    reconcile_75api_minimax_h3_generation,
    submit_75api_minimax_h3_generation,
)


TransportHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ProviderTransportBinding:
    binding_id: str
    provider_id: str
    target_media: str
    mode: str
    submit: str
    poll: str
    handler: TransportHandler


_BINDINGS_BY_ID: dict[str, ProviderTransportBinding] = {}
_BINDINGS_BY_KEY: dict[tuple[str, str], ProviderTransportBinding] = {}


def register_provider_transport_binding(binding: ProviderTransportBinding) -> None:
    """Register an exact provider/media transport binding."""
    media = str(binding.target_media or "").upper()
    if media not in {"IMAGE", "VIDEO"}:
        raise ValueError("transport binding target_media must be IMAGE or VIDEO")
    if not binding.binding_id or not binding.provider_id:
        raise ValueError("transport binding requires binding_id and provider_id")
    normalized = ProviderTransportBinding(
        binding_id=str(binding.binding_id),
        provider_id=str(binding.provider_id),
        target_media=media,
        mode=str(binding.mode or "sync"),
        submit=str(binding.submit or ""),
        poll=str(binding.poll or ""),
        handler=binding.handler,
    )
    _BINDINGS_BY_ID[normalized.binding_id] = normalized
    _BINDINGS_BY_KEY[(normalized.provider_id, normalized.target_media)] = normalized


def get_provider_transport_binding(
    *, provider_id: str, target_media: str, binding_id: str | None = None
) -> ProviderTransportBinding | None:
    media = str(target_media or "").upper()
    provider = str(provider_id or "")
    if binding_id:
        binding = _BINDINGS_BY_ID.get(str(binding_id))
        if binding is None or binding.provider_id != provider or binding.target_media != media:
            return None
        return binding
    return _BINDINGS_BY_KEY.get((provider, media))


def list_provider_transport_bindings() -> list[ProviderTransportBinding]:
    return sorted(_BINDINGS_BY_ID.values(), key=lambda item: item.binding_id)


def _runtime_profile(context: dict[str, Any]) -> dict[str, Any]:
    profile = dict(context.get("profile") or {})
    runtime_credential = context.get("runtime_credential_value")
    if isinstance(runtime_credential, str) and runtime_credential:
        # This copy exists only for the transport call.  The canonical profile
        # and request snapshot remain secret-free.
        profile["api_key"] = runtime_credential
    return profile


async def _image_handler(context: dict[str, Any]) -> dict[str, Any]:
    payload = context.get("payload") if isinstance(context.get("payload"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    generated = await generate_image_asset(
        _runtime_profile(context),
        prompt=str(request.get("prompt") or ""),
        aspect_ratio=request.get("aspect_ratio"),
        negative_prompt=str(request.get("negative_prompt") or ""),
        reference_images=context.get("reference_images") or [],
        runtime_credential=None,
    )
    generated.setdefault("provider", context.get("profile", {}).get("provider"))
    generated.setdefault("model", context.get("profile", {}).get("model_name"))
    generated.setdefault("providerRequestId", generated.get("externalTaskId") or "")
    generated.setdefault("providerTaskId", generated.get("externalTaskId") or "")
    return generated


async def _video_handler(context: dict[str, Any]) -> dict[str, Any]:
    payload = context.get("payload") if isinstance(context.get("payload"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    source_url = str(context.get("source_storage_identity") or "").strip() or None
    last_frame_url = str(context.get("last_frame_storage_identity") or "").strip() or None
    generated = await generate_video_asset(
        _runtime_profile(context),
        prompt=str(request.get("prompt") or ""),
        duration_seconds=request.get("duration_seconds"),
        negative_prompt=str(request.get("negative_prompt") or ""),
        aspect_ratio=request.get("aspect_ratio"),
        first_frame_url=source_url,
        last_frame_url=last_frame_url,
        reference_images=context.get("reference_images") or [],
        runtime_credential_value=str(context.get("runtime_credential_value") or "").strip() or None,
    )
    generated.setdefault("provider", context.get("profile", {}).get("provider"))
    generated.setdefault("model", context.get("profile", {}).get("model_name"))
    generated.setdefault("providerRequestId", generated.get("externalTaskId") or "")
    generated.setdefault("providerTaskId", generated.get("externalTaskId") or "")
    return generated


async def submit_provider_transport(context: dict[str, Any]) -> dict[str, Any]:
    """Submit one async generation without polling it to terminal state."""
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    target_media = str(context.get("target_media") or "IMAGE").upper()
    binding = get_provider_transport_binding(
        provider_id=str(profile.get("provider") or ""),
        target_media=target_media,
        binding_id=str(profile.get("transport_binding_id") or "").strip() or None,
    )
    if binding is None:
        raise LookupError(f"No exact transport binding for provider={profile.get('provider')} target_media={target_media}")
    if binding.mode != "async" or target_media != "VIDEO":
        return await binding.handler(context)
    payload = context.get("payload") if isinstance(context.get("payload"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    runtime_credential_value = str(context.get("runtime_credential_value") or "").strip() or None
    transport_profile = _runtime_profile(context)
    provider = str(profile.get("provider") or "")
    if provider == MINIMAX_H3_75API_PROVIDER:
        provider_payload = {
            "model": transport_profile.get("model_name"),
            "prompt": str(request.get("prompt") or ""),
            "seconds": str(request.get("duration_seconds") or ""),
            "aspect_ratio": request.get("aspect_ratio"),
            "resolution": transport_profile.get("default_params", {}).get("resolution") if isinstance(transport_profile.get("default_params"), dict) else None,
            "images": [str(context.get("source_storage_identity") or "")] if str(context.get("source_storage_identity") or "").strip() else [],
        }
        provider_payload = {key: value for key, value in provider_payload.items() if value not in (None, "", [])}
        submitted = await submit_75api_minimax_h3_generation(
            transport_profile,
            payload=provider_payload,
            runtime_credential_value=runtime_credential_value,
        )
        response = submitted.get("providerResponse") if isinstance(submitted.get("providerResponse"), dict) else {}
        task_id = str(submitted.get("providerTaskId") or submitted.get("externalTaskId") or "").strip()
        return {
            "status": "submitted",
            "externalTaskId": task_id,
            "providerTaskId": task_id,
            "providerRequestId": str(response.get("request_id") or response.get("requestId") or task_id),
            "providerResponse": response,
            "providerRequestPayload": submitted.get("providerRequestPayload") or provider_payload,
        }
    raise LookupError(f"Async submit is not implemented for provider={provider}")


async def reconcile_provider_transport(context: dict[str, Any], *, external_task_id: str) -> dict[str, Any]:
    """Reconcile one persisted async task without issuing a new submission."""
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    target_media = str(context.get("target_media") or "IMAGE").upper()
    binding = get_provider_transport_binding(
        provider_id=str(profile.get("provider") or ""),
        target_media=target_media,
        binding_id=str(profile.get("transport_binding_id") or "").strip() or None,
    )
    if binding is None:
        raise LookupError(f"No exact transport binding for provider={profile.get('provider')} target_media={target_media}")
    if binding.mode != "async" or target_media != "VIDEO":
        return await binding.handler(context)
    runtime_credential_value = str(context.get("runtime_credential_value") or "").strip() or None
    transport_profile = _runtime_profile(context)
    if str(profile.get("provider") or "") == MINIMAX_H3_75API_PROVIDER:
        return await reconcile_75api_minimax_h3_generation(
            transport_profile,
            external_task_id=str(external_task_id),
            runtime_credential_value=runtime_credential_value,
        )
    raise LookupError(f"Async reconcile is not implemented for provider={profile.get('provider')}")


def dispatch_provider_transport(context: dict[str, Any]) -> Awaitable[dict[str, Any]]:
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    target_media = str(context.get("target_media") or "IMAGE").upper()
    binding = get_provider_transport_binding(
        provider_id=str(profile.get("provider") or ""),
        target_media=target_media,
        binding_id=str(profile.get("transport_binding_id") or "").strip() or None,
    )
    if binding is None:
        raise LookupError(
            f"No exact transport binding for provider={profile.get('provider')} target_media={target_media}"
        )
    return binding.handler(context)


def _register_builtin_real_bindings() -> None:
    for provider in (OPENAI_COMPATIBLE_PROVIDER, POYO_ASYNC_PROVIDER, SHAPI_OPENAI_IMAGES_PROVIDER, SHAPI_GEMINI_IMAGE_PROVIDER):
        if provider == OPENAI_COMPATIBLE_PROVIDER:
            binding_id = "openai-compatible.image.v1"
        elif provider == POYO_ASYNC_PROVIDER:
            binding_id = "poyo-async.image.v1"
        elif provider == SHAPI_OPENAI_IMAGES_PROVIDER:
            binding_id = "shapi-openai-images.image.v1"
        else:
            binding_id = "shapi-gemini-image.image.v1"
        register_provider_transport_binding(ProviderTransportBinding(binding_id, provider, "IMAGE", "sync" if provider != POYO_ASYNC_PROVIDER else "async", "generate_image_asset", "generate_image_asset", _image_handler))
    register_provider_transport_binding(ProviderTransportBinding("poyo-async.video.v1", POYO_ASYNC_PROVIDER, "VIDEO", "async", "submit_poyo_generation", "poll_poyo_generation", _video_handler))
    register_provider_transport_binding(ProviderTransportBinding("minimax-h3-async.video.v1", MINIMAX_H3_ASYNC_PROVIDER, "VIDEO", "async", "submit_minimax_h3_generation", "poll_minimax_h3_generation", _video_handler))
    register_provider_transport_binding(ProviderTransportBinding("75api-minimax-h3.video.v1", MINIMAX_H3_75API_PROVIDER, "VIDEO", "async", "submit_75api_minimax_h3_generation", "poll_75api_minimax_h3_generation", _video_handler))


_register_builtin_real_bindings()


__all__ = [
    "ProviderTransportBinding",
    "dispatch_provider_transport",
    "submit_provider_transport",
    "reconcile_provider_transport",
    "get_provider_transport_binding",
    "list_provider_transport_bindings",
    "register_provider_transport_binding",
]
