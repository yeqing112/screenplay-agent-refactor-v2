"""Provider-neutral video adapter boundary with a deterministic Mock provider."""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
from typing import Any, Mapping, Protocol


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


class VideoProviderRegistry:
    """Explicit provider plugin registry; only Mock is enabled this phase."""

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


__all__ = ["VideoProviderError", "VideoProviderResult", "VideoProviderAdapter", "MockVideoProvider", "VideoProviderRegistry", "DEFAULT_VIDEO_PROVIDER_REGISTRY"]
