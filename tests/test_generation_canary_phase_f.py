from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.generation_canary_api as canary
from models import GenerationExecutionRecord, MediaCandidateRecord


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def first(self):
        for row in self.rows:
            if all(getattr(row, key, None) == value for key, value in self.filters.items()):
                return row
        return None

    def update(self, values, synchronize_session=False):
        del synchronize_session
        count = 0
        for row in self.rows:
            if all(getattr(row, key, None) == value for key, value in self.filters.items()):
                for key, value in values.items():
                    setattr(row, key, value)
                count += 1
        return count


class _Session:
    def __init__(self):
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, model):
        return _Query([row for row in self.rows if isinstance(row, model)])

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        return None

    def rollback(self):
        return None


def _context(*, payload_fp="payload-fp"):
    return {
        "row": SimpleNamespace(id=7, shot_id=101),
        "payload": {
            "generation_payload_fingerprint": payload_fp,
            "prompt_ir_ref": {"plan_shot_id": "plan-101"},
            "generation_policy": {"fingerprint": "policy-fp"},
            "request": {"prompt": "A locked prompt", "negative_prompt": ""},
        },
        "policy": {"fingerprint": "policy-fp"},
        "resolved": {
            "version": SimpleNamespace(id=11, payload_hash="ir-hash"),
            "authority": SimpleNamespace(id=13),
        },
        "profile": {
            "id": "builtin-mock-image",
            "provider": "prototype-task-adapter",
            "model_name": "mock-image-v1",
        },
        "phase_profile": {"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic"},
        "profile_fingerprint": "profile-fp",
        "adapter": {"adapter_id": "image_generic", "adapter_version": "v1", "model_family": "GENERIC_IMAGE"},
        "reference_images": [],
        "reference_bindings_fingerprint": "refs-fp",
        "request_snapshot": {"schema_version": "phase_f_provider_request_v1", "prompt": "A locked prompt"},
        "provider_request_fingerprint": "request-fp",
    }


def test_fake_provider_returns_real_png_and_is_deterministic():
    result = asyncio.run(canary._fake_provider_image(request_snapshot={"prompt": "x"}, provider_request_fingerprint="abc123"))
    encoded = result["uri"].split(",", 1)[1]
    import base64

    data = base64.b64decode(encoded)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert canary._png_dimensions(data) == (1, 1)
    assert result["providerRequestId"] == "fake-abc123"
    assert canary._response_hash({"api_key": "secret", "status": "ok"}) == canary._response_hash({"api_key": "different", "status": "ok"})


def test_request_audit_snapshot_excludes_credentials_and_reference_tokens():
    snapshot = canary._request_snapshot(
        profile={"provider": "openai-compatible", "model_name": "image", "api_key": "SECRET-API-KEY"},
        adapter={"adapter_id": "image_generic", "adapter_version": "v1"},
        payload={"request": {"prompt": "locked", "reference_bindings": [{"reference_authority_fingerprint": "ref-fp", "reference_token": "SIGNED-SECRET"}]}},
        reference_bindings=[{"reference_authority_fingerprint": "ref-fp", "reference_token": "SIGNED-SECRET"}],
    )
    rendered = str(snapshot)
    assert "SECRET-API-KEY" not in rendered
    assert "SIGNED-SECRET" not in rendered
    assert snapshot["reference_bindings"] == [{"reference_authority_fingerprint": "ref-fp"}]


def test_preview_is_provider_free_and_reuses_fingerprint(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    req = canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image")

    first = canary.preview_generation_canary(1, 1, 101, req)
    second = canary.preview_generation_canary(1, 1, 101, req)

    assert first["provider_calls"] == 0
    assert first["reused"] is False
    assert second["provider_calls"] == 0
    assert second["reused"] is False
    assert first["execution"]["provider_request_fingerprint"] == second["execution"]["provider_request_fingerprint"]
    assert len([row for row in session.rows if isinstance(row, GenerationExecutionRecord)]) == 1


def test_execute_success_persists_one_candidate_and_replay_is_zero_call(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        return await canary._fake_provider_image(request_snapshot={"prompt": "x"}, provider_request_fingerprint="abc123")

    monkeypatch.setattr(canary, "_call_provider", provider)
    monkeypatch.setattr(canary, "_persist_candidate_media", lambda **_kwargs: {"storage_identity": "local://candidate-1", "storage_reference": {"image_url": "local://candidate-1"}, "checksum_sha256": "sha", "mime_type": "image/png", "byte_size": 68, "width": 1, "height": 1})
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])

    result = asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    replay = asyncio.run(canary.execute_generation_canary(1, 1, 101, req))

    assert result["provider_calls"] == 1
    assert result["candidate"]["status"] == "MEDIA_CANDIDATE"
    assert replay["provider_calls"] == 0
    assert replay["reused"] is True
    assert len(calls) == 1
    assert len([row for row in session.rows if isinstance(row, MediaCandidateRecord)]) == 1


def test_prompt_drift_fails_before_provider(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    context["payload"]["generation_payload_fingerprint"] = "drifted"
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        return {}

    monkeypatch.setattr(canary, "_call_provider", provider)
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "GENERATION_CANARY_STALE"
    assert exc.value.detail["provider_calls"] == 0
    assert calls == []
    assert not [row for row in session.rows if isinstance(row, MediaCandidateRecord)]


def test_provider_failure_has_no_candidate_or_retry(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        raise RuntimeError("provider down")

    monkeypatch.setattr(canary, "_call_provider", provider)
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.status_code == 502
    assert calls == [1]
    execution = next(row for row in session.rows if isinstance(row, GenerationExecutionRecord))
    assert execution.logical_provider_calls == 1
    assert execution.transport_retry_count == 0
    assert execution.submitted_at is not None
    assert not [row for row in session.rows if isinstance(row, MediaCandidateRecord)]


def test_invalid_media_fails_closed_without_candidate(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))

    async def provider(**_kwargs):
        return {"uri": "data:image/png;base64,AAAA", "providerResponse": {"status": "returned_media"}}

    monkeypatch.setattr(canary, "_call_provider", provider)
    monkeypatch.setattr(canary, "_persist_candidate_media", lambda **_kwargs: (_ for _ in ()).throw(canary._error(422, "GENERATION_MEDIA_INVALID", "invalid")))
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.status_code == 422
    assert not [row for row in session.rows if isinstance(row, MediaCandidateRecord)]
    execution = next(row for row in session.rows if isinstance(row, GenerationExecutionRecord))
    assert execution.logical_provider_calls == 1
    assert execution.transport_retry_count == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reference_bindings_fingerprint", "refs-drifted"),
        ("profile_fingerprint", "profile-drifted"),
        ("provider_request_fingerprint", "request-drifted"),
    ],
)
def test_asset_reference_and_model_drift_fail_before_provider(monkeypatch, field, value):
    session = _Session()
    preview_context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: preview_context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    if field == "profile_fingerprint":
        preview_context[field] = value
    elif field == "reference_bindings_fingerprint":
        preview_context[field] = value
    else:
        preview_context[field] = value
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        return {}

    monkeypatch.setattr(canary, "_call_provider", provider)
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "GENERATION_CANARY_STALE"
    assert exc.value.detail["provider_calls"] == 0
    assert calls == []


def test_authority_resolver_integrity_failure_is_stale_and_provider_free(monkeypatch):
    session = _Session()
    preview_context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: preview_context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))

    def fail_integrity(*_args, **_kwargs):
        raise canary._error(409, "PROMPT_IR_CURRENT_AUTHORITY_INVALID", "tampered historical PromptIR")

    monkeypatch.setattr(canary, "_resolve_execution_inputs", fail_integrity)
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        return {}

    monkeypatch.setattr(canary, "_call_provider", provider)
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.detail["code"] == "GENERATION_CANARY_STALE"
    assert calls == []


def test_transport_semantic_loss_fails_before_provider(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    context["payload"]["unsupported"] = ["required_camera_lens"]
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        return {}

    monkeypatch.setattr(canary, "_call_provider", provider)
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.detail["code"] == "GENERATION_TRANSPORT_SEMANTIC_UNREPRESENTABLE"
    assert exc.value.detail["provider_calls"] == 0
    assert calls == []


def test_real_provider_requires_explicit_opt_in_before_transport(monkeypatch):
    session = _Session()
    context = _context()
    context["profile"] = {"id": "real-image", "provider": "openai-compatible", "model_name": "image-model"}
    monkeypatch.delenv("PHASE_F_PROVIDER_CANARY_REAL", raising=False)
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        return {}

    monkeypatch.setattr(canary, "_call_provider", provider)
    req = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, req))
    assert exc.value.detail["code"] == "GENERATION_REAL_PROVIDER_OPT_IN_REQUIRED"
    assert exc.value.detail["provider_calls"] == 0
    assert calls == []


def _successful_replay_fixture(monkeypatch):
    session = _Session()
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    execution = next(row for row in session.rows if isinstance(row, GenerationExecutionRecord))
    execution.status = "SUCCEEDED"
    execution.provider_response_hash = "response-fp"
    execution.candidate_id = "candidate-replay"
    candidate = MediaCandidateRecord(
        candidate_id="candidate-replay", execution_id=execution.execution_id, status="MEDIA_CANDIDATE", media_type="IMAGE",
        storage_identity="local://candidate-replay", storage_reference_json='{"image_url":"local://candidate-replay"}',
        checksum_sha256="checksum", mime_type="image/png", byte_size=68, width=1, height=1,
        prompt_ir_version_id=execution.prompt_ir_version_id, prompt_ir_payload_hash=execution.prompt_ir_payload_hash,
        generation_payload_fingerprint=execution.generation_payload_fingerprint, model_profile_id=execution.model_profile_id,
        model_profile_fingerprint=execution.model_profile_fingerprint, provider_request_fingerprint=execution.provider_request_fingerprint,
        provider_response_hash=execution.provider_response_hash, provider_task_id="task",
    )
    session.add(candidate)
    request = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=execution.execution_id)
    return session, context, execution, candidate, request


@pytest.mark.parametrize("drift", ["prompt", "asset", "reference", "profile", "request"])
def test_successful_replay_revalidates_current_authority_before_reuse(monkeypatch, drift):
    session, context, _execution, _candidate, request = _successful_replay_fixture(monkeypatch)
    if drift == "prompt":
        context["resolved"]["version"].payload_hash = "drifted-prompt-ir"
    elif drift == "asset":
        context["payload"]["generation_payload_fingerprint"] = "drifted-asset-payload"
    elif drift == "reference":
        context["reference_bindings_fingerprint"] = "drifted-reference"
    elif drift == "profile":
        context["profile_fingerprint"] = "drifted-profile"
    else:
        context["provider_request_fingerprint"] = "drifted-request"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert exc.value.detail["code"] == "GENERATION_CANARY_STALE"
    assert exc.value.detail["provider_calls"] == 0
    assert next(row for row in session.rows if isinstance(row, GenerationExecutionRecord)).status == "STALE"


@pytest.mark.parametrize("field", ["generation_payload_fingerprint", "model_profile_fingerprint", "provider_response_hash", "execution_id", "status"])
def test_successful_replay_rejects_candidate_lineage_tamper(monkeypatch, field):
    _session, _context_value, execution, candidate, request = _successful_replay_fixture(monkeypatch)
    if field == "execution_id":
        candidate.execution_id = "another-execution"
    elif field == "status":
        candidate.status = "OFFICIAL"
    elif field == "provider_response_hash":
        candidate.provider_response_hash = "tampered-response"
    else:
        setattr(candidate, field, "tampered-lineage")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert exc.value.detail["code"] == "GENERATION_CANDIDATE_LINEAGE_INVALID"
    assert exc.value.detail["provider_calls"] == 0


def test_successful_replay_rejects_missing_candidate_without_provider_call(monkeypatch):
    session, _context_value, execution, _candidate, request = _successful_replay_fixture(monkeypatch)
    session.rows = [row for row in session.rows if not isinstance(row, MediaCandidateRecord)]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert exc.value.detail["code"] == "GENERATION_EXECUTION_CANDIDATE_MISSING"
    assert exc.value.detail["provider_calls"] == 0
