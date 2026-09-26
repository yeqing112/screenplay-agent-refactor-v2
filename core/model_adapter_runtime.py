"""Provider-free runtime model adapter boundary.

The project already has :mod:`core.model_adapter`, which turns ShotIR into
model-facing prompt text.  This module is the *runtime* boundary described by
the production architecture: it accepts a resolved Model Registry profile and
an immutable prompt projection, then returns a normalized provider result.

Only the deterministic mock adapter is executable in this phase.  Real
provider names are registered as explicit unavailable adapters so a runtime
call can never accidentally reach a real model before the provider canary
phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, Protocol


class ModelAdapterError(RuntimeError):
    """Stable error raised at the model adapter boundary."""

    def __init__(self, message: str, *, code: str = "MODEL_ADAPTER_FAILED", provider_calls: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code
        self.provider_calls = int(provider_calls or 0)


@dataclass(frozen=True)
class ModelAdapterResult:
    """Normalized, secret-free result returned by a runtime adapter."""

    status: str
    provider_request: Mapping[str, Any] = field(default_factory=dict)
    provider_response: Mapping[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    provider_request_id: str = ""
    provider_task_id: str = ""
    provider_response_hash: str = ""
    logical_provider_calls: int = 0
    transport_retry_count: int = 0
    latency_ms: int | None = None
    error_code: str = ""
    error_message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_request": dict(self.provider_request),
            "provider_response": dict(self.provider_response),
            "provider": self.provider,
            "model": self.model,
            "provider_request_id": self.provider_request_id,
            "provider_task_id": self.provider_task_id,
            "provider_response_hash": self.provider_response_hash,
            "logical_provider_calls": self.logical_provider_calls,
            "transport_retry_count": self.transport_retry_count,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class ModelAdapter(Protocol):
    """Runtime adapter protocol used by :class:`ModelAdapterRegistry`."""

    adapter_id: str
    adapter_version: str

    def generate(
        self,
        model_profile: Mapping[str, Any],
        prompt: Any,
        params: Mapping[str, Any] | None = None,
    ) -> ModelAdapterResult:
        """Submit one normalized generation request."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_model_name(profile: Mapping[str, Any]) -> str:
    return str(profile.get("model_name") or profile.get("model") or "").strip()


class MockAdapter:
    """Deterministic adapter used to exercise the runtime without I/O.

    It returns metadata only.  It never writes a file, opens a network client,
    or creates a media candidate.  Tests can request a deterministic failure
    with ``params['simulate_failure']``.
    """

    adapter_id = "mock-runtime"
    adapter_version = "mock-runtime-v1"
    available = True

    def generate(
        self,
        model_profile: Mapping[str, Any],
        prompt: Any,
        params: Mapping[str, Any] | None = None,
    ) -> ModelAdapterResult:
        profile = _safe_mapping(model_profile)
        options = _safe_mapping(params)
        if bool(options.get("simulate_failure")):
            raise ModelAdapterError(
                "Mock provider failure requested by the execution test.",
                code="MOCK_PROVIDER_FAILURE",
                provider_calls=1,
            )

        provider = str(profile.get("provider") or "prototype-task-adapter")
        model = _safe_model_name(profile) or "mock-runtime-v1"
        request = {
            "provider": provider,
            "model": model,
            "prompt_fingerprint": _sha256(prompt),
            "params": {key: value for key, value in options.items() if key != "simulate_failure"},
            "media_generated": False,
        }
        response = {
            "mock": True,
            "message": "deterministic mock provider response",
            "prompt_fingerprint": request["prompt_fingerprint"],
            "media_generated": False,
        }
        request_id = "mockreq_" + _sha256(request)[7:23]
        return ModelAdapterResult(
            status="SUCCESS",
            provider_request=request,
            provider_response=response,
            provider=provider,
            model=model,
            provider_request_id=request_id,
            provider_task_id=request_id,
            provider_response_hash=_sha256(response),
            logical_provider_calls=1,
            transport_retry_count=0,
            latency_ms=0,
        )


class UnavailableProviderAdapter:
    """Explicit fail-closed adapter for providers reserved for later phases."""

    adapter_id = "provider-runtime-unavailable"
    adapter_version = "provider-runtime-unavailable-v1"
    available = False

    def generate(
        self,
        model_profile: Mapping[str, Any],
        prompt: Any,
        params: Mapping[str, Any] | None = None,
    ) -> ModelAdapterResult:
        provider = str(model_profile.get("provider") or "unknown") if isinstance(model_profile, Mapping) else "unknown"
        raise ModelAdapterError(
            f"Provider {provider!r} is reserved for PHASE_REAL_IMAGE_PROVIDER_CANARY.",
            code="MODEL_ADAPTER_PROVIDER_NOT_ENABLED",
            provider_calls=0,
        )


class FluxAdapter(UnavailableProviderAdapter):
    """Named placeholder for the future Flux provider adapter."""

    adapter_id = "flux-runtime"
    adapter_version = "flux-runtime-v0"


class ModelAdapterRegistry:
    """Exact provider-to-adapter registry; no provider guessing by model name."""

    def __init__(self, adapters: Mapping[str, ModelAdapter] | None = None):
        self._adapters: dict[str, ModelAdapter] = {}
        self._fallback = UnavailableProviderAdapter()
        for provider, adapter in (adapters or {}).items():
            self.register(provider, adapter)

    def register(self, provider: str, adapter: ModelAdapter) -> None:
        key = str(provider or "").strip().lower()
        if not key:
            raise ValueError("adapter registry provider cannot be empty")
        if not hasattr(adapter, "generate"):
            raise TypeError("adapter must implement generate(model_profile, prompt, params)")
        self._adapters[key] = adapter

    def resolve(self, provider: str) -> ModelAdapter:
        key = str(provider or "").strip().lower()
        if not key:
            raise ModelAdapterError("model profile provider is required", code="MODEL_ADAPTER_PROVIDER_REQUIRED")
        return self._adapters.get(key, self._fallback)

    def get_adapter(self, provider: str) -> ModelAdapter:
        """Alias for integrations that use the conventional method name."""
        return self.resolve(provider)

    def get(self, provider: str) -> ModelAdapter:
        return self.resolve(provider)

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


def build_default_adapter_registry() -> ModelAdapterRegistry:
    mock = MockAdapter()
    registry = ModelAdapterRegistry(
        {
            "mock": mock,
            "prototype-task-adapter": mock,
            "flux": FluxAdapter(),
            "openai-compatible": UnavailableProviderAdapter(),
            "poyo-async": UnavailableProviderAdapter(),
            "minimax-h3-async": UnavailableProviderAdapter(),
            "75api-minimax-h3": UnavailableProviderAdapter(),
            "shapi-openai-images": UnavailableProviderAdapter(),
            "shapi-gemini-image": UnavailableProviderAdapter(),
        }
    )
    return registry


DEFAULT_MODEL_ADAPTER_REGISTRY = build_default_adapter_registry()
MODEL_ADAPTER_REGISTRY = DEFAULT_MODEL_ADAPTER_REGISTRY
AdapterRegistry = ModelAdapterRegistry


__all__ = [
    "DEFAULT_MODEL_ADAPTER_REGISTRY",
    "MODEL_ADAPTER_REGISTRY",
    "AdapterRegistry",
    "FluxAdapter",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelAdapterRegistry",
    "ModelAdapterResult",
    "MockAdapter",
    "UnavailableProviderAdapter",
    "build_default_adapter_registry",
]
