"""Provider-neutral video adapters.

The real adapter deliberately accepts one already resolved Model Registry
profile.  It does not own provider configuration or credentials and only
returns a secret-free normalized result to the execution runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse


class VideoProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str = "VIDEO_PROVIDER_FAILED", provider_calls: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code
        self.provider_calls = int(provider_calls or 0)


@dataclass(frozen=True)
class VideoProviderResult:
    status: str
    provider: str
    model: str
    provider_request: Mapping[str, Any]
    provider_response: Mapping[str, Any]
    provider_request_id: str
    provider_task_id: str
    provider_response_hash: str
    media_uri: str
    media_mime_type: str
    duration_ms: int
    width: int
    height: int
    logical_provider_calls: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "provider_request": dict(self.provider_request),
            "provider_response": dict(self.provider_response),
            "provider_request_id": self.provider_request_id,
            "provider_task_id": self.provider_task_id,
            "provider_response_hash": self.provider_response_hash,
            "media_uri": self.media_uri,
            "media_mime_type": self.media_mime_type,
            "duration_ms": self.duration_ms,
            "width": self.width,
            "height": self.height,
            "logical_provider_calls": self.logical_provider_calls,
        }


class VideoProviderAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def generate_video(
        self,
        *,
        prompt: str,
        motion_profile: Mapping[str, Any],
        duration: float,
        aspect_ratio: str,
        first_frame_asset: Mapping[str, Any],
        last_frame_asset: Mapping[str, Any],
        request_context: Mapping[str, Any],
    ) -> VideoProviderResult:
        """Return one normalized video result without mutating authority rows."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class MockVideoProvider:
    """Deterministic provider-free adapter; it never calls a video API."""

    adapter_id = "mock-video"
    adapter_version = "mock-video-v1"
    available = True

    def generate_video(
        self,
        *,
        prompt: str,
        motion_profile: Mapping[str, Any],
        duration: float,
        aspect_ratio: str,
        first_frame_asset: Mapping[str, Any],
        last_frame_asset: Mapping[str, Any],
        request_context: Mapping[str, Any],
    ) -> VideoProviderResult:
        if not str(prompt or "").strip():
            raise VideoProviderError("video prompt is required", code="VIDEO_PROMPT_REQUIRED")
        if float(duration) <= 0:
            raise VideoProviderError("video duration must be positive", code="VIDEO_DURATION_INVALID")
        request = {
            "target_media": "VIDEO",
            "prompt_fingerprint": _hash(prompt),
            "motion_profile": dict(motion_profile),
            "duration": float(duration),
            "aspect_ratio": str(aspect_ratio),
            "first_frame_asset": dict(first_frame_asset),
            "last_frame_asset": dict(last_frame_asset),
            "request_context": dict(request_context),
        }
        request_id = "mock-video-" + _hash(request)[7:31]
        response = {"status": "succeeded", "mock": True, "media_type": "VIDEO", "request_id": request_id, "duration_ms": int(round(float(duration) * 1000))}
        # Keep the existing deterministic MP4 fixture as the provider-neutral
        # bytes source.  Import lazily so the adapter remains independent of
        # API module initialization and never performs network I/O.
        from api.generation_canary_api import _FAKE_MP4

        uri = "data:video/mp4;base64," + base64.b64encode(_FAKE_MP4).decode("ascii")
        return VideoProviderResult(
            status="SUCCESS",
            provider="mock-video",
            model="deterministic-video-v1",
            provider_request=request,
            provider_response=response,
            provider_request_id=request_id,
            provider_task_id=request_id,
            provider_response_hash=_hash(response),
            media_uri=uri,
            media_mime_type="video/mp4",
            duration_ms=int(round(float(duration) * 1000)),
            width=2,
            height=2,
            logical_provider_calls=1,
        )


class MinimaxH3VideoProvider:
    """MiniMax H3 async provider backed by the existing generation adapter."""

    adapter_id = "minimax-h3-video"
    adapter_version = "minimax-h3-video-v1"
    available = True

    def __init__(self, profile: Mapping[str, Any], *, transport: Any | None = None):
        raw_profile = dict(profile or {})
        self._validate_profile(raw_profile)
        # The adapter owns no provider configuration.  The profile is only
        # validated at construction; endpoint, model, and credential values
        # arrive as a short-lived runtime projection for each call.
        self.transport = transport

    @staticmethod
    def _validate_profile(profile: Mapping[str, Any]) -> None:
        provider = str(profile.get("provider") or "").strip()
        capability = str(profile.get("capability") or "").strip()
        model = str(profile.get("model_name") or "").strip().lower()
        base_url = str(profile.get("base_url") or "").strip()
        parsed = urlparse(base_url)
        if capability != "video":
            raise VideoProviderError("MiniMax H3 profile must declare video capability", code="VIDEO_PROFILE_CAPABILITY_INVALID")
        if provider != "minimax-h3-async":
            raise VideoProviderError("MiniMax H3 profile provider is invalid", code="VIDEO_PROFILE_PROVIDER_INVALID")
        if model not in {"minimax-h3", "minimax_h3"}:
            raise VideoProviderError("MiniMax H3 profile model_name is invalid", code="VIDEO_PROFILE_MODEL_INVALID")
        if parsed.scheme != "https" or parsed.hostname != "metaso.cn":
            raise VideoProviderError("MiniMax H3 profile base_url must use https://metaso.cn", code="VIDEO_PROFILE_ENDPOINT_INVALID")
        if not profile.get("enabled", True):
            raise VideoProviderError("MiniMax H3 profile is disabled", code="VIDEO_PROFILE_DISABLED")
        if not str(profile.get("api_key") or "").strip():
            raise VideoProviderError("MiniMax H3 profile is missing API key", code="VIDEO_PROFILE_CREDENTIAL_MISSING")

    @staticmethod
    def _run(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # Runtime endpoints are synchronous, but test harnesses may already
        # own an event loop.  Run the short adapter coroutine in a worker
        # thread rather than nesting asyncio.run into the active loop.
        import threading
        result: list[Any] = []
        error: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(coro))
            except BaseException as exc:  # pragma: no cover - defensive loop bridge
                error.append(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result[0] if result else None

    def generate_video(
        self,
        *,
        prompt: str,
        motion_profile: Mapping[str, Any],
        duration: float,
        aspect_ratio: str,
        first_frame_asset: Mapping[str, Any],
        last_frame_asset: Mapping[str, Any],
        request_context: Mapping[str, Any],
    ) -> VideoProviderResult:
        if not str(prompt or "").strip():
            raise VideoProviderError("video prompt is required", code="VIDEO_PROMPT_REQUIRED")
        first_frame_url = str(first_frame_asset.get("storage_identity") or "").strip()
        if not first_frame_url:
            raise VideoProviderError("MiniMax H3 requires a current keyframe asset URL", code="VIDEO_FIRST_FRAME_URL_REQUIRED")
        if not str(request_context.get("canary_scope") or "").strip():
            raise VideoProviderError("MiniMax H3 execution requires a single-shot canary scope", code="VIDEO_CANARY_SCOPE_REQUIRED")

        supplied_profile = request_context.get("_runtime_profile")
        if not isinstance(supplied_profile, Mapping):
            raise VideoProviderError("MiniMax H3 runtime Model Registry profile is missing", code="VIDEO_PROFILE_RUNTIME_REQUIRED")
        runtime_profile = dict(supplied_profile)
        self._validate_profile(runtime_profile)
        last_frame_url = str(last_frame_asset.get("storage_identity") or "").strip()
        try:
            if self.transport is not None:
                generated = self._run(self.transport(
                    runtime_profile,
                    prompt=prompt,
                    duration_seconds=int(round(float(duration))),
                    aspect_ratio=aspect_ratio,
                    first_frame_url=first_frame_url,
                    last_frame_url=last_frame_url or None,
                    reference_images=None,
                ))
            else:
                from core.provider_transport_registry import dispatch_provider_transport

                generated = self._run(dispatch_provider_transport({
                    "profile": runtime_profile,
                    "target_media": "VIDEO",
                    "payload": {"request": {"prompt": prompt, "duration_seconds": int(round(float(duration))), "aspect_ratio": aspect_ratio}},
                    "source_storage_identity": first_frame_url,
                    "last_frame_storage_identity": last_frame_url,
                }))
        except VideoProviderError:
            raise
        except Exception as exc:
            raise VideoProviderError(str(getattr(exc, "message", exc)), code=str(getattr(exc, "code", "VIDEO_PROVIDER_FAILED")), provider_calls=2) from exc
        if not isinstance(generated, Mapping):
            raise VideoProviderError("MiniMax H3 returned an invalid response", code="VIDEO_PROVIDER_RESPONSE_INVALID")
        response = dict(generated.get("providerResponse") or {})
        task_id = str(generated.get("providerTaskId") or generated.get("externalTaskId") or "").strip()
        media_uri = str(generated.get("uri") or generated.get("previewUrl") or "").strip()
        if not task_id or not media_uri:
            raise VideoProviderError("MiniMax H3 response is missing task id or video URL", code="VIDEO_PROVIDER_RESPONSE_INCOMPLETE")
        created_time = str(response.get("created_time") or response.get("createdTime") or datetime.now(timezone.utc).isoformat())
        provider_response = {
            "provider": "minimax-h3-async",
            "model": str(runtime_profile.get("model_name") or "MiniMax-H3"),
            "request_id": str(generated.get("providerRequestId") or task_id),
            "task_id": task_id,
            "video_url": media_uri,
            "metadata": response,
            "created_time": created_time,
        }
        provider_request = dict(generated.get("providerRequestPayload") or {})
        provider_request["motion_profile"] = dict(motion_profile)
        provider_request["canary_scope"] = str(request_context.get("canary_scope"))
        if isinstance(request_context.get("shot_direction"), Mapping):
            provider_request["shot_direction"] = dict(request_context["shot_direction"])
        return VideoProviderResult(
            status="SUCCESS",
            provider="minimax-h3-async",
            model=str(runtime_profile.get("model_name") or "MiniMax-H3"),
            provider_request=provider_request,
            provider_response=provider_response,
            provider_request_id=str(generated.get("providerRequestId") or task_id),
            provider_task_id=task_id,
            provider_response_hash=_hash(provider_response),
            media_uri=media_uri,
            media_mime_type="video/mp4",
            duration_ms=int(round(float(duration) * 1000)),
            width=int(generated.get("width") or 0),
            height=int(generated.get("height") or 0),
            logical_provider_calls=int(generated.get("logicalProviderCalls") or 2),
        )


class VideoProviderRegistry:
    """Explicit provider plugin registry."""

    def __init__(self, providers: Mapping[str, VideoProviderAdapter] | None = None):
        self._providers: dict[str, VideoProviderAdapter] = {}
        for name, provider in (providers or {"mock-video": MockVideoProvider()}).items():
            self.register(name, provider)

    def register(self, name: str, provider: VideoProviderAdapter) -> None:
        key = str(name or "").strip().lower()
        if not key or not hasattr(provider, "generate_video"):
            raise ValueError("video provider must expose generate_video")
        self._providers[key] = provider

    def resolve(self, name: str) -> VideoProviderAdapter:
        provider = self._providers.get(str(name or "").strip().lower())
        if provider is None:
            raise VideoProviderError(f"video provider {name!r} is not enabled", code="VIDEO_PROVIDER_NOT_ENABLED")
        return provider

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


DEFAULT_VIDEO_PROVIDER_REGISTRY = VideoProviderRegistry()


__all__ = ["VideoProviderError", "VideoProviderResult", "VideoProviderAdapter", "MockVideoProvider", "MinimaxH3VideoProvider", "VideoProviderRegistry", "DEFAULT_VIDEO_PROVIDER_REGISTRY"]
