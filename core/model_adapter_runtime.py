"""Provider-free runtime model adapter boundary.

The project already has :mod:`core.model_adapter`, which turns ShotIR into
model-facing prompt text.  This module is the *runtime* boundary described by
the production architecture: it accepts a resolved Model Registry profile and
an immutable prompt projection, then returns a normalized provider result.

The deterministic mock remains available for provider-free tests.  Real image
providers are enabled only through their explicit Registry provider bindings
and the phase opt-in enforced by the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import hashlib
import json
import threading
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


class ModelAdapterError(RuntimeError):
    """Stable error raised at the model adapter boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "MODEL_ADAPTER_FAILED",
        provider_calls: int = 0,
        provider_request: Mapping[str, Any] | None = None,
        provider_response: Mapping[str, Any] | None = None,
        provider_request_id: str = "",
        provider_task_id: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.provider_calls = int(provider_calls or 0)
        self.provider_request = dict(provider_request or {})
        self.provider_response = dict(provider_response or {})
        self.provider_request_id = str(provider_request_id or "")
        self.provider_task_id = str(provider_task_id or "")


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
    asset_uri: str = ""
    asset_mime_type: str = ""
    asset_width: int | None = None
    asset_height: int | None = None
    asset_duration_ms: int | None = None
    provider_request_timestamp: str = ""

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
            "asset_uri": self.asset_uri,
            "asset_mime_type": self.asset_mime_type,
            "asset_width": self.asset_width,
            "asset_height": self.asset_height,
            "asset_duration_ms": self.asset_duration_ms,
            "provider_request_timestamp": self.provider_request_timestamp,
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


def _redact(value: Any, *, key: str = "") -> Any:
    """Return a bounded provider evidence projection without credentials/media bytes."""
    lowered = str(key or "").lower()
    if any(token in lowered for token in ("api_key", "apikey", "authorization", "bearer", "password", "secret", "token", "credential")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key=key) for item in value[:100]]
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return f"[REDACTED image data URI: {len(value)} chars]"
        if len(value) > 4000:
            return f"[REDACTED large value: {len(value)} chars]"
    return value


def _await_sync(awaitable: Any) -> Any:
    """Resolve a coroutine from both ordinary workers and running event loops."""
    if not hasattr(awaitable, "__await__"):
        return awaitable
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    # ``GenerationOrchestrator.run`` is synchronous, but a caller may invoke
    # it from an async API handler.  A private thread gives the transport its
    # own event loop without nesting ``asyncio.run`` in the caller's loop.
    result: list[Any] = []
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(awaitable))
        except BaseException as exc:  # pragma: no cover - defensive boundary
            errors.append(exc)

    thread = threading.Thread(target=runner, name="image-provider-adapter", daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result[0] if result else None


def _prompt_request(prompt: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    projection = dict(prompt) if isinstance(prompt, Mapping) else {"prompt": str(prompt or "")}
    payload = projection.get("payload") if isinstance(projection.get("payload"), Mapping) else projection
    payload = dict(payload) if isinstance(payload, Mapping) else {}
    request = payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
    request = dict(request)
    text = str(request.get("prompt") or payload.get("prompt") or projection.get("prompt") or "").strip()
    if not text:
        raise ModelAdapterError("PromptIR projection has no image prompt", code="MODEL_ADAPTER_PROMPT_REQUIRED")
    return projection, {
        "prompt": text,
        "negative_prompt": str(request.get("negative_prompt") or payload.get("negative_prompt") or "").strip(),
        "aspect_ratio": request.get("aspect_ratio") or payload.get("aspect_ratio"),
        "reference_bindings": request.get("reference_bindings") if isinstance(request.get("reference_bindings"), list) else [],
        "target_media": str(request.get("target_media") or payload.get("target_media") or "IMAGE").upper(),
        "generation_mode": str(request.get("mode") or payload.get("generation_mode") or "TEXT_TO_IMAGE"),
    }


def _credential(profile: Mapping[str, Any]) -> str:
    value = str(profile.get("_runtime_credential_value") or profile.get("api_key") or "").strip()
    if value:
        return value
    # The formal resolver remains the fallback for environment or injected
    # bindings.  Its return value is used only for this transport call.
    from core.runtime_credentials import resolve_runtime_credential

    try:
        return resolve_runtime_credential(profile).value
    except Exception as exc:
        raise ModelAdapterError(str(exc), code=getattr(exc, "code", "RUNTIME_CREDENTIAL_NOT_RESOLVED")) from exc


class ImageGenerationProviderAdapter(UnavailableProviderAdapter):
    """Runtime image adapter backed by the existing exact transport registry.

    The adapter does not select providers or invent model configuration.  It
    receives one Registry profile, resolves one short lived credential, and
    dispatches the already registered IMAGE transport binding.
    """

    adapter_id = "image-generation-provider"
    adapter_version = "image-generation-provider-v1"
    available = True
    target_media = "IMAGE"

    def generate(
        self,
        model_profile: Mapping[str, Any],
        prompt: Any,
        params: Mapping[str, Any] | None = None,
    ) -> ModelAdapterResult:
        profile = dict(model_profile) if isinstance(model_profile, Mapping) else {}
        provider = str(profile.get("provider") or "").strip()
        model = str(profile.get("model_name") or profile.get("model") or "").strip()
        if not provider or not model:
            raise ModelAdapterError("Image Provider profile is missing provider or model", code="MODEL_PROFILE_INVALID")
        if str(profile.get("capability") or "image").lower() != "image":
            raise ModelAdapterError("ImageGenerationProviderAdapter requires an image profile", code="MODEL_PROFILE_CAPABILITY_MISMATCH")
        if provider in {"prototype-task-adapter", "mock"}:
            raise ModelAdapterError("Mock providers must use MockAdapter", code="MODEL_ADAPTER_PROVIDER_MISMATCH")
        if str(profile.get("phase_real_provider") or "1") == "0":
            raise ModelAdapterError("Real Provider execution is disabled", code="MODEL_ADAPTER_PROVIDER_NOT_ENABLED")

        projection, request_fields = _prompt_request(prompt)
        options = dict(params) if isinstance(params, Mapping) else {}
        options.pop("simulate_failure", None)
        reference_images = options.pop("reference_images", None)
        if not isinstance(reference_images, list):
            reference_images = []
        request_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        default_params = profile.get("default_params")
        effective_parameters = dict(default_params) if isinstance(default_params, Mapping) else {}
        effective_parameters.update(options)
        provider_request = {
            "provider": provider,
            "model": model,
            "prompt": request_fields["prompt"],
            "parameters": _redact(effective_parameters),
            "target_media": "IMAGE",
            "generation_mode": request_fields["generation_mode"],
            "timestamp": request_timestamp,
            "prompt_ir_version_id": projection.get("prompt_ir_version_id"),
            "prompt_ir_payload_hash": projection.get("payload_hash"),
        }
        transport_payload = {
            "request": {
                "prompt": request_fields["prompt"],
                "negative_prompt": request_fields["negative_prompt"],
                "aspect_ratio": request_fields["aspect_ratio"],
                "target_media": "IMAGE",
                "mode": request_fields["generation_mode"],
                "reference_bindings": request_fields["reference_bindings"],
            },
            "prompt_ir": {
                "version_id": projection.get("prompt_ir_version_id"),
                "payload_hash": projection.get("payload_hash"),
            },
        }
        transport_profile = dict(profile.get("_transport_profile") or profile)
        transport_profile.setdefault("provider", provider)
        transport_profile.setdefault("model_name", model)
        transport_profile.setdefault("transport_binding_id", profile.get("transport_binding_id") or "")
        transport_profile["api_key"] = _credential(profile)
        context = {
            "profile": transport_profile,
            "target_media": "IMAGE",
            "payload": transport_payload,
            "reference_images": reference_images,
            "runtime_credential_value": transport_profile.get("api_key"),
        }
        try:
            generated = _await_sync(__import__("core.provider_transport_registry", fromlist=["dispatch_provider_transport"]).dispatch_provider_transport(context))
        except Exception as exc:
            raw_response = getattr(exc, "provider_response", {})
            raw_request = getattr(exc, "provider_request_payload", {}) or provider_request
            task_id = str(getattr(exc, "external_task_id", "") or "")
            upstream_code = str(raw_response.get("code") or raw_response.get("type") or "").strip().lower() if isinstance(raw_response, Mapping) else ""
            if upstream_code == "insufficient_credits_error":
                error_code = "REAL_PROVIDER_CREDITS_INSUFFICIENT"
            elif upstream_code == "model_not_found":
                error_code = "REAL_PROVIDER_MODEL_UNAVAILABLE"
            else:
                error_code = getattr(exc, "code", "REAL_PROVIDER_CALL_FAILED")
            request_id = str((raw_response.get("request_id") if isinstance(raw_response, Mapping) else "") or "").strip()
            raise ModelAdapterError(
                str(exc),
                code=error_code,
                provider_calls=max(1, int(getattr(exc, "provider_calls", 1) or 1)),
                provider_request=_redact(raw_request),
                provider_response=_redact(raw_response),
                provider_request_id=request_id,
                provider_task_id=task_id,
            ) from exc
        if not isinstance(generated, Mapping):
            raise ModelAdapterError("Provider transport returned an invalid response", code="MODEL_ADAPTER_RESPONSE_INVALID", provider_calls=1, provider_request=provider_request)
        generated = dict(generated)
        asset_uri = str(generated.get("uri") or generated.get("previewUrl") or generated.get("asset_url") or "").strip()
        if not asset_uri:
            raise ModelAdapterError("Provider response did not include an image URI", code="REAL_PROVIDER_MEDIA_MISSING", provider_calls=1, provider_request=provider_request, provider_response=_redact(generated))
        provider_response = generated.get("providerResponse") if isinstance(generated.get("providerResponse"), Mapping) else {}
        provider_response = _redact(provider_response)
        provider_request_payload = generated.get("providerRequestPayload") if isinstance(generated.get("providerRequestPayload"), Mapping) else {}
        request_evidence = {**provider_request, "provider_payload": _redact(provider_request_payload)}
        request_id = str(generated.get("providerRequestId") or generated.get("request_id") or generated.get("externalTaskId") or "").strip()
        task_id = str(generated.get("providerTaskId") or generated.get("externalTaskId") or request_id).strip()
        provider_response = {**provider_response, "provider": provider, "model": model}
        response_hash = _sha256(provider_response)
        poll_attempts = int(generated.get("pollAttempts") or 1)
        return ModelAdapterResult(
            status="SUCCESS",
            provider_request=request_evidence,
            provider_response=provider_response,
            provider=provider,
            model=model,
            provider_request_id=request_id,
            provider_task_id=task_id,
            provider_response_hash=response_hash,
            logical_provider_calls=1,
            transport_retry_count=max(0, poll_attempts - 1),
            latency_ms=None,
            asset_uri=asset_uri,
            asset_mime_type="image/png",
            provider_request_timestamp=request_timestamp,
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
            "openai-compatible": ImageGenerationProviderAdapter(),
            "poyo-async": ImageGenerationProviderAdapter(),
            "minimax-h3-async": UnavailableProviderAdapter(),
            "75api-minimax-h3": UnavailableProviderAdapter(),
            "shapi-openai-images": ImageGenerationProviderAdapter(),
            "shapi-gemini-image": ImageGenerationProviderAdapter(),
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
    "ImageGenerationProviderAdapter",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelAdapterRegistry",
    "ModelAdapterResult",
    "MockAdapter",
    "UnavailableProviderAdapter",
    "build_default_adapter_registry",
]
