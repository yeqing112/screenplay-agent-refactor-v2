"""Generation Execution → Model Adapter runtime orchestration.

This phase wires the existing durable execution record to the existing Model
Registry selection surface.  It intentionally stops before real provider
transport: the only executable adapter is the deterministic mock adapter.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Callable, Mapping

from api.model_registry import get_profile
from core.model_adapter_runtime import (
    DEFAULT_MODEL_ADAPTER_REGISTRY,
    ModelAdapterError,
    ModelAdapterRegistry,
    ModelAdapterResult,
)
from core.provider_execution_profile import (
    ProviderExecutionProfileError,
    build_provider_execution_profile,
    fingerprint_provider_execution_profile,
)
from core.generation_execution_service import (
    GenerationExecutionError,
    GenerationExecutionService,
)
from models import GenerationExecutionRecord, PromptIRVersion, Session


class GenerationOrchestratorError(ValueError):
    """Stable error for readiness, adapter, and execution failures."""

    status_code = 409

    def __init__(self, message: str, *, code: str = "GENERATION_ORCHESTRATOR_INVALID", provider_calls: int = 0):
        super().__init__(message)
        self.message = message
        self.code = code
        self.provider_calls = int(provider_calls or 0)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _secret_free(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower() in {"api_key", "apikey", "authorization", "access_token", "token", "credential", "credential_value"} else _secret_free(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_secret_free(item) for item in value]
    return value


def _prompt_projection(version: PromptIRVersion, row: GenerationExecutionRecord) -> dict[str, Any]:
    payload = _parse_json(version.payload_json)
    request = row.request_payload
    return {
        "prompt_ir_version_id": int(version.id),
        "payload_hash": str(version.payload_hash or row.prompt_ir_payload_hash or ""),
        "payload": payload,
        "request": _secret_free(request),
    }


def _runtime_params(row: GenerationExecutionRecord, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    request = row.request_payload
    params = request.get("params") if isinstance(request, Mapping) else {}
    result = dict(params) if isinstance(params, Mapping) else {}
    if overrides:
        result.update(dict(overrides))
    return result


def _serialize_result(result: ModelAdapterResult) -> dict[str, Any]:
    return _secret_free(result.as_dict())


def _coerce_result(value: Any, *, profile: Mapping[str, Any]) -> ModelAdapterResult:
    """Accept the documented mapping shape as well as the typed result."""
    if isinstance(value, ModelAdapterResult):
        return value
    if not isinstance(value, Mapping):
        raise ModelAdapterError("adapter returned an invalid result", code="MODEL_ADAPTER_RESULT_INVALID", provider_calls=1)
    response = value.get("provider_response", value.get("providerResponse", {}))
    request = value.get("provider_request", value.get("providerRequest", {}))
    return ModelAdapterResult(
        status=str(value.get("status") or "").upper(),
        provider_request=dict(request) if isinstance(request, Mapping) else {},
        provider_response=dict(response) if isinstance(response, Mapping) else {},
        provider=str(value.get("provider") or profile.get("provider") or ""),
        model=str(value.get("model") or profile.get("model") or profile.get("model_name") or ""),
        provider_request_id=str(value.get("provider_request_id") or value.get("providerRequestId") or ""),
        provider_task_id=str(value.get("provider_task_id") or value.get("providerTaskId") or ""),
        provider_response_hash=str(value.get("provider_response_hash") or value.get("providerResponseHash") or ""),
        logical_provider_calls=int(value.get("logical_provider_calls", value.get("provider_calls", 1)) or 0),
        transport_retry_count=int(value.get("transport_retry_count", value.get("transportRetryCount", 0)) or 0),
        latency_ms=value.get("latency_ms", value.get("latencyMs")),
        error_code=str(value.get("error_code") or value.get("errorCode") or ""),
        error_message=str(value.get("error_message") or value.get("errorMessage") or ""),
    )


class GenerationOrchestrator:
    """Coordinate one durable execution through a runtime ModelAdapter."""

    def __init__(
        self,
        session: Any,
        *,
        adapter_registry: ModelAdapterRegistry | None = None,
        profile_resolver: Callable[[str], dict[str, Any] | None] | None = None,
    ):
        self.session = session
        self.adapters = adapter_registry or DEFAULT_MODEL_ADAPTER_REGISTRY
        self.profile_resolver = profile_resolver or get_profile
        self.executions = GenerationExecutionService(session)

    def _resolve_profile(self, row: GenerationExecutionRecord) -> dict[str, Any]:
        profile = self.profile_resolver(str(row.model_profile_id or ""))
        if not isinstance(profile, Mapping):
            raise GenerationOrchestratorError(
                "model profile does not exist in Model Registry",
                code="MODEL_PROFILE_NOT_FOUND",
            )
        profile = dict(profile)
        if not bool(profile.get("enabled", True)):
            raise GenerationOrchestratorError("model profile is disabled", code="MODEL_PROFILE_DISABLED")
        if str(profile.get("id") or row.model_profile_id) != str(row.model_profile_id):
            raise GenerationOrchestratorError("model profile id does not match execution", code="MODEL_PROFILE_MISMATCH")
        capability = str(profile.get("capability") or "").lower()
        expected = str(row.target_media or "IMAGE").lower()
        if capability and capability != expected:
            raise GenerationOrchestratorError(
                f"model profile capability {capability!r} does not match target media {expected!r}",
                code="MODEL_PROFILE_CAPABILITY_MISMATCH",
            )
        return profile

    def _build_runtime_profile(self, profile: dict[str, Any], adapter: Any) -> dict[str, Any]:
        try:
            canonical = build_provider_execution_profile(
                profile,
                adapter_id=str(getattr(adapter, "adapter_id", "runtime")),
                adapter_version=str(getattr(adapter, "adapter_version", "v1")),
                transport_binding_id=str(profile.get("transport_binding_id") or ""),
            )
            canonical["profile_id"] = str(profile.get("id") or canonical.get("profile_id") or "")
            canonical["raw_provider"] = str(profile.get("provider") or "")
            return canonical
        except ProviderExecutionProfileError as exc:
            raise GenerationOrchestratorError(
                str(exc),
                code=getattr(exc, "code", "MODEL_PROFILE_INVALID"),
            ) from exc

    def run(self, execution_id: str, *, params: Mapping[str, Any] | None = None) -> GenerationExecutionRecord:
        row = self.executions.get_execution(execution_id)
        if row.execution_status not in {"CREATED", "QUEUED"}:
            raise GenerationOrchestratorError(
                f"execution {execution_id} cannot run from status {row.execution_status}",
                code="GENERATION_EXECUTION_NOT_RUNNABLE",
            )

        try:
            profile = self._resolve_profile(row)
            adapter = self.adapters.resolve(str(profile.get("provider") or ""))
            if getattr(adapter, "available", True) is False:
                raise GenerationOrchestratorError(
                    f"Provider {profile.get('provider')!r} is not enabled in this phase",
                    code="MODEL_ADAPTER_PROVIDER_NOT_ENABLED",
                )
            runtime_profile = self._build_runtime_profile(profile, adapter)
            version = self.session.query(PromptIRVersion).filter_by(id=row.prompt_ir_version_id).one_or_none()
            if version is None:
                raise GenerationOrchestratorError(
                    "PromptIRVersion for execution does not exist",
                    code="GENERATION_PROMPT_VERSION_NOT_FOUND",
                )
            prompt = _prompt_projection(version, row)
            runtime_params = _runtime_params(row, params)

            if row.execution_status == "CREATED":
                self.executions.transition(execution_id, "QUEUED")
            self.executions.transition(execution_id, "RUNNING")
            row.provider_adapter_id = str(getattr(adapter, "adapter_id", "runtime"))
            row.provider_adapter_version = str(getattr(adapter, "adapter_version", "v1"))
            row.model_profile_fingerprint = fingerprint_provider_execution_profile(runtime_profile)
            row.request_payload = {
                **row.request_payload,
                "runtime": {
                    "adapter_id": row.provider_adapter_id,
                    "adapter_version": row.provider_adapter_version,
                    "provider": runtime_profile.get("provider"),
                    "model": runtime_profile.get("model"),
                    "params": _secret_free(runtime_params),
                },
            }
            result = _coerce_result(adapter.generate(runtime_profile, prompt, runtime_params), profile=runtime_profile)
            if str(result.status).upper() != "SUCCESS":
                raise ModelAdapterError(
                    result.error_message or "adapter did not return SUCCESS",
                    code=result.error_code or "MODEL_ADAPTER_RESULT_FAILED",
                    provider_calls=result.logical_provider_calls,
                )
            row.provider = str(result.provider or runtime_profile.get("provider") or "")
            row.model = str(result.model or runtime_profile.get("model") or "")
            row.provider_request_id = str(result.provider_request_id or "")
            row.provider_task_id = str(result.provider_task_id or "")
            row.provider_response_hash = str(result.provider_response_hash or _sha256(result.provider_response))
            row.logical_provider_calls = int(result.logical_provider_calls or 0)
            row.transport_retry_count = int(result.transport_retry_count or 0)
            row.latency_ms = result.latency_ms
            self.executions.transition(execution_id, "SUCCESS", response_payload=_serialize_result(result))
            self.session.flush()
            return row
        except ModelAdapterError as exc:
            if row.execution_status == "RUNNING":
                row.logical_provider_calls = max(int(row.logical_provider_calls or 0), int(exc.provider_calls or 0))
                self.executions.transition(execution_id, "FAILED", error_message=exc.message, response_payload={"error_code": exc.code})
                self.session.flush()
            raise GenerationOrchestratorError(exc.message, code=exc.code, provider_calls=exc.provider_calls) from exc
        except GenerationOrchestratorError:
            raise
        except GenerationExecutionError as exc:
            raise GenerationOrchestratorError(exc.message, code=exc.code) from exc
        except Exception as exc:
            if row.execution_status == "RUNNING":
                self.executions.transition(execution_id, "FAILED", error_message=str(exc), response_payload={"error_code": "GENERATION_ORCHESTRATOR_FAILED"})
                self.session.flush()
            raise GenerationOrchestratorError(str(exc), code="GENERATION_ORCHESTRATOR_FAILED") from exc

    def execute(self, execution_id: str, *, params: Mapping[str, Any] | None = None) -> GenerationExecutionRecord:
        """Alias for integrations that call the operation ``execute``."""
        return self.run(execution_id, params=params)


def run_generation_execution(*, session: Any, execution_id: str, params: Mapping[str, Any] | None = None, adapter_registry: ModelAdapterRegistry | None = None, profile_resolver: Callable[[str], dict[str, Any] | None] | None = None) -> GenerationExecutionRecord:
    return GenerationOrchestrator(
        session,
        adapter_registry=adapter_registry,
        profile_resolver=profile_resolver,
    ).run(execution_id, params=params)


__all__ = [
    "GenerationOrchestrator",
    "GenerationOrchestratorError",
    "run_generation_execution",
]
