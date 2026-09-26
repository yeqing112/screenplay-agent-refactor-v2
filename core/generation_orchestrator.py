"""Generation Execution → Model Adapter runtime orchestration.

This phase wires the existing durable execution record to the existing Model
Registry selection surface.  It intentionally stops before real provider
transport: the only executable adapter is the deterministic mock adapter.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
import uuid
from typing import Any, Callable, Mapping

from api.model_registry import get_profile
from core.model_adapter_runtime import (
    DEFAULT_MODEL_ADAPTER_REGISTRY,
    ModelAdapterError,
    ModelAdapterRegistry,
    ModelAdapterResult,
)
from core.provider_execution_profile import (
    CAPABILITY_PARAM_KEYS,
    GENERATION_PARAM_KEYS,
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
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return f"[REDACTED image data URI: {len(value)} chars]"
        if len(value) > 4000:
            return f"[REDACTED large value: {len(value)} chars]"
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


def _image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None, None


def _persist_image_candidate(row: GenerationExecutionRecord, result: ModelAdapterResult) -> Any:
    """Materialize Provider output as one immutable MediaCandidate row."""
    if str(row.target_media or "IMAGE").upper() != "IMAGE":
        raise GenerationOrchestratorError(
            "ImageGenerationProviderAdapter can only create IMAGE candidates",
            code="MODEL_ADAPTER_TARGET_MEDIA_MISMATCH",
        )
    source_url = str(result.asset_uri or "").strip()
    if not source_url:
        raise GenerationOrchestratorError("Provider response did not include an image URI", code="REAL_PROVIDER_MEDIA_MISSING")
    try:
        from api.server import _persist_generated_image_locally
        from core.public_asset_storage import _load_source_bytes, _normalize_provider_image_bytes

        persisted = _persist_generated_image_locally(
            source_url,
            book_id=int(row.book_id),
            task_id=str(row.execution_id),
            label="real-image-provider-canary",
        )
        if not persisted.get("ok"):
            raise RuntimeError(str(persisted.get("error") or "provider image persistence failed"))
        local_path = str(persisted.get("local_path") or "")
        data, content_type = _load_source_bytes(local_path)
        data, content_type = _normalize_provider_image_bytes(data, content_type)
        width, height = _image_dimensions(data)
        if not data or not width or not height:
            raise RuntimeError("stored provider image has no valid bytes or dimensions")
    except GenerationOrchestratorError:
        raise
    except Exception as exc:
        raise GenerationOrchestratorError(
            "Provider image could not be persisted as a MediaCandidate",
            code="MEDIA_CANDIDATE_PERSIST_FAILED",
        ) from exc

    from models import MediaCandidateRecord

    candidate = MediaCandidateRecord(
        candidate_id="candidate-" + uuid.uuid4().hex,
        execution_id=row.execution_id,
        status="MEDIA_CANDIDATE",
        media_type="IMAGE",
        storage_identity=str(persisted.get("image_url") or ""),
        storage_reference_json=json.dumps(
            {
                "image_url": str(persisted.get("image_url") or ""),
                "local_path": local_path,
                "source_kind": str(persisted.get("source_kind") or "provider_url"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        metadata_json=json.dumps(
            {
                "media_type": "IMAGE",
                "mime_type": str(content_type or persisted.get("content_type") or "image/png").split(";", 1)[0].lower(),
                "byte_size": len(data),
                "width": int(width),
                "height": int(height),
                "duration_ms": None,
                "provider": str(result.provider or row.provider or ""),
                "model": str(result.model or row.model or ""),
                "provider_response_hash": str(result.provider_response_hash or _sha256(result.provider_response)),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        checksum_sha256=str(persisted.get("sha256") or hashlib.sha256(data).hexdigest()),
        mime_type=str(content_type or persisted.get("content_type") or "image/png").split(";", 1)[0].lower(),
        byte_size=len(data),
        width=int(width),
        height=int(height),
        duration_ms=None,
        prompt_ir_version_id=int(row.prompt_ir_version_id),
        prompt_ir_payload_hash=str(row.prompt_ir_payload_hash or ""),
        generation_payload_fingerprint=str(row.generation_payload_fingerprint or ""),
        model_profile_id=str(row.model_profile_id or ""),
        model_profile_fingerprint=str(row.model_profile_fingerprint or ""),
        provider_request_fingerprint=str(row.provider_request_fingerprint or ""),
        provider_response_hash=str(result.provider_response_hash or _sha256(result.provider_response)),
        provider_task_id=str(result.provider_task_id or result.provider_request_id or ""),
        created_at=datetime.utcnow(),
    )
    return candidate


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
        asset_uri=str(value.get("asset_uri") or value.get("assetUrl") or value.get("uri") or value.get("previewUrl") or ""),
        asset_mime_type=str(value.get("asset_mime_type") or value.get("assetMimeType") or ""),
        asset_width=value.get("asset_width", value.get("assetWidth")),
        asset_height=value.get("asset_height", value.get("assetHeight")),
        asset_duration_ms=value.get("asset_duration_ms", value.get("assetDurationMs")),
        provider_request_timestamp=str(value.get("provider_request_timestamp") or value.get("providerRequestTimestamp") or ""),
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
            # Registry profiles may carry provider transport knobs (for
            # example PoYo polling fields) that are intentionally outside the
            # canonical creative parameter schema.  Keep them in the private
            # transport profile while fingerprinting only the allowlisted
            # execution projection.
            raw_params = profile.get("default_params") if isinstance(profile.get("default_params"), Mapping) else {}
            projected_params = {
                key: value
                for key, value in raw_params.items()
                if key in GENERATION_PARAM_KEYS or key in CAPABILITY_PARAM_KEYS or key == "timeout_seconds"
            }
            projection_profile = {**profile, "default_params": projected_params}
            credential_lifecycle = {
                "credential_ref": str(profile.get("credential_ref") or profile.get("credential_source_identity") or f"profile:{profile.get('id') or ''}"),
                "configured": bool(profile.get("credential_configured") or profile.get("key_configured") or profile.get("api_key")),
                "resolved": bool(profile.get("api_key") or profile.get("_runtime_credential_value")),
                "validated": bool(profile.get("api_key") or profile.get("_runtime_credential_value")),
            }
            canonical = build_provider_execution_profile(
                projection_profile,
                adapter_id=str(getattr(adapter, "adapter_id", "runtime")),
                adapter_version=str(getattr(adapter, "adapter_version", "v1")),
                credential_lifecycle=credential_lifecycle,
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
            is_real_provider = not bool(profile.get("uses_mock")) and str(profile.get("provider") or "") not in {"prototype-task-adapter", "mock"}
            if is_real_provider and os.getenv("PHASE_F_PROVIDER_CANARY_REAL", "").strip() != "1":
                raise GenerationOrchestratorError(
                    "Real Provider Canary requires PHASE_F_PROVIDER_CANARY_REAL=1",
                    code="GENERATION_REAL_PROVIDER_OPT_IN_REQUIRED",
                )
            runtime_profile = self._build_runtime_profile(profile, adapter)
            version = self.session.query(PromptIRVersion).filter_by(id=row.prompt_ir_version_id).one_or_none()
            if version is None:
                raise GenerationOrchestratorError(
                    "PromptIRVersion for execution does not exist",
                    code="GENERATION_PROMPT_VERSION_NOT_FOUND",
                )
            prompt = _prompt_projection(version, row)
            if is_real_provider:
                # Reuse the existing PromptIR -> GenerationPayload compiler;
                # the runtime adapter receives the compiled request while the
                # durable lineage remains anchored to the PromptIR version.
                try:
                    from core.prompt_ir_phase_e import adapt_prompt_ir_to_generation_payload, build_generation_policy, build_model_profile

                    raw_prompt_payload = prompt.get("payload") if isinstance(prompt.get("payload"), Mapping) else {}
                    raw_policy = raw_prompt_payload.get("generation_policy") if isinstance(raw_prompt_payload.get("generation_policy"), Mapping) else None
                    phase_profile = build_model_profile(
                        {
                            "model_family": "GENERIC_IMAGE",
                            "adapter_id": "image_generic",
                            "provider_config_ref": str(row.model_profile_id),
                            "capabilities": {"supports_reference_images": True, "supports_negative_prompt": True},
                        }
                    )
                    generation_payload = adapt_prompt_ir_to_generation_payload(
                        dict(raw_prompt_payload),
                        generation_policy=build_generation_policy(raw_policy or {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, allow_default=False),
                        model_profile=phase_profile,
                    )
                    request_prompt = generation_payload.get("request", {}).get("prompt") if isinstance(generation_payload.get("request"), Mapping) else ""
                    # Small Foundation fixtures may carry an explicit prompt
                    # field without semantic PromptIR sections. Preserve that
                    # authored value rather than inventing one.
                    if request_prompt or not str(raw_prompt_payload.get("prompt") or "").strip():
                        prompt["payload"] = generation_payload
                    else:
                        prompt["payload"] = {**dict(raw_prompt_payload), "request": {"prompt": str(raw_prompt_payload.get("prompt") or ""), "target_media": "IMAGE", "mode": "TEXT_TO_IMAGE"}}
                except Exception as exc:
                    if not isinstance(prompt.get("payload"), Mapping) or not str(prompt["payload"].get("prompt") or "").strip():
                        raise GenerationOrchestratorError(
                            f"PromptIR could not be compiled into an image GenerationPayload: {exc}",
                            code=getattr(exc, "code", "GENERATION_PROMPT_COMPILE_FAILED"),
                        ) from exc
            runtime_params = _runtime_params(row, params)

            prompt_payload = prompt.get("payload") if isinstance(prompt.get("payload"), Mapping) else {}
            generation_policy = prompt_payload.get("generation_policy") if isinstance(prompt_payload.get("generation_policy"), Mapping) else {}
            generation_payload_fp = str(prompt_payload.get("generation_payload_fingerprint") or "").strip()
            policy_fp = str(generation_policy.get("fingerprint") or "").strip()
            if generation_payload_fp:
                row.generation_payload_fingerprint = generation_payload_fp
            if policy_fp:
                row.generation_policy_fingerprint = policy_fp

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
                "media_role": "SHOT_PRIMARY_IMAGE",
                "generation_policy": _secret_free(generation_policy),
                "reference_bindings": _secret_free(prompt_payload.get("request", {}).get("reference_bindings", [])) if isinstance(prompt_payload.get("request"), Mapping) else [],
                "asset_bindings": _secret_free(prompt_payload.get("asset_authority_bindings", {})),
            }
            # The raw Registry profile and the resolved credential are private
            # transport inputs.  Neither is included in the canonical runtime
            # profile fingerprint or durable request snapshot.
            transport_profile = dict(profile)
            transport_profile["_runtime_credential_value"] = str(profile.get("api_key") or "")
            runtime_profile["_transport_profile"] = transport_profile
            runtime_profile["_runtime_credential_value"] = transport_profile.get("_runtime_credential_value")
            runtime_profile["model_name"] = profile.get("model_name") or runtime_profile.get("model")
            runtime_profile["base_url"] = profile.get("base_url") or runtime_profile.get("endpoint_identity")
            runtime_profile["default_params"] = profile.get("default_params") or {}
            runtime_profile["capability"] = profile.get("capability") or "image"
            row.provider = str(profile.get("provider") or "")
            row.model = str(profile.get("model_name") or profile.get("model") or "")
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
            if result.asset_uri:
                self.executions.transition(execution_id, "PROVIDER_CALLED", response_payload=_serialize_result(result))
                candidate = _persist_image_candidate(row, result)
                self.session.add(candidate)
                row.candidate_id = candidate.candidate_id
            # The deterministic MockAdapter intentionally has no media URI;
            # keep its provider-free contract and direct terminal transition.
            self.executions.transition(execution_id, "SUCCESS", response_payload=_serialize_result(result))
            self.session.flush()
            return row
        except ModelAdapterError as exc:
            if row.execution_status in {"RUNNING", "PROVIDER_CALLED"}:
                row.logical_provider_calls = max(int(row.logical_provider_calls or 0), int(exc.provider_calls or 0))
                if exc.provider_request_id:
                    row.provider_request_id = exc.provider_request_id
                if exc.provider_task_id:
                    row.provider_task_id = exc.provider_task_id
                if exc.provider_response:
                    row.provider_response_hash = _sha256(exc.provider_response)
                row.response_payload = {
                    "status": "FAILED",
                    "error_code": exc.code,
                    "provider_request": _secret_free(exc.provider_request),
                    "provider_response": _secret_free(exc.provider_response),
                }
                self.executions.transition(execution_id, "FAILED", error_message=exc.message, response_payload=row.response_payload)
                self.session.flush()
            raise GenerationOrchestratorError(exc.message, code=exc.code, provider_calls=exc.provider_calls) from exc
        except GenerationOrchestratorError as exc:
            if row.execution_status in {"RUNNING", "PROVIDER_CALLED"}:
                self.executions.transition(execution_id, "FAILED", error_message=exc.message, response_payload={"error_code": exc.code})
                self.session.flush()
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

    def run_and_promote(self, execution_id: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Run one image execution, validate its Candidate, and promote it."""
        row = self.run(execution_id, params=params)
        if not row.candidate_id:
            raise GenerationOrchestratorError("Successful image execution has no MediaCandidate", code="GENERATION_EXECUTION_CANDIDATE_MISSING")
        from core.media_authority import promote_media_candidate, validate_media_candidate

        validation = validate_media_candidate(self.session, str(row.candidate_id))
        promoted = promote_media_candidate(
            self.session,
            str(row.candidate_id),
            str(validation["validation_id"]),
            confirmation=True,
        )
        row.official_promotion_count = int(row.official_promotion_count or 0) + 1
        self.session.flush()
        candidate = self.session.query(__import__("models", fromlist=["MediaCandidateRecord"]).MediaCandidateRecord).filter_by(candidate_id=row.candidate_id).one()
        return {"execution": row, "candidate": candidate, "validation": validation, "promotion": promoted}


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
