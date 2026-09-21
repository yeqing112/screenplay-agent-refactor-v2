from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.generation_canary_api as canary
from models import GenerationExecutionRecord, MediaCandidateRecord


class _Query:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}

    def filter_by(self, **values):
        self.filters.update(values)
        return self

    @property
    def rows(self):
        return [row for row in self.session.rows if isinstance(row, self.model) and all(getattr(row, key, None) == value for key, value in self.filters.items())]

    def first(self):
        return self.rows[0] if self.rows else None

    def update(self, values, synchronize_session=False):
        del values, synchronize_session
        if self.model is GenerationExecutionRecord:
            self.session.winner_row.status = self.session.winner_status
            return 0
        return 0


class _ClaimLostSession:
    def __init__(self, winner_status: str):
        self.rows = []
        self.winner_status = winner_status
        self.winner_row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, model):
        return _Query(self, model)

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        return None

    def rollback(self):
        return None


def _context():
    return {
        "row": SimpleNamespace(id=7),
        "payload": {
            "generation_payload_fingerprint": "payload-fp",
            "prompt_ir_ref": {"plan_shot_id": "plan-101"},
            "generation_policy": {"fingerprint": "policy-fp"},
            "request": {"prompt": "A locked prompt", "negative_prompt": ""},
        },
        "policy": {"fingerprint": "policy-fp"},
        "resolved": {"version": SimpleNamespace(id=11, payload_hash="ir-hash"), "authority": SimpleNamespace(id=13)},
        "profile": {"id": "builtin-mock-image", "provider": "prototype-task-adapter", "model_name": "mock-image-v1"},
        "phase_profile": {"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic"},
        "profile_fingerprint": "profile-fp",
        "adapter": {"adapter_id": "image_generic", "adapter_version": "v1", "model_family": "GENERIC_IMAGE"},
        "reference_images": [],
        "reference_bindings_fingerprint": "refs-fp",
        "request_snapshot": {"schema_version": "phase_f_provider_request_v2", "prompt": "A locked prompt", "reference_bindings": []},
        "provider_request_fingerprint": "request-fp",
    }


def _setup(monkeypatch, winner_status: str):
    session = _ClaimLostSession(winner_status)
    context = _context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *args, **kwargs: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="builtin-mock-image"))
    execution = next(row for row in session.rows if isinstance(row, GenerationExecutionRecord))
    execution.provider_response_hash = "response-fp"
    execution.candidate_id = "candidate-winner"
    session.winner_row = execution
    candidate = MediaCandidateRecord(
        candidate_id="candidate-winner", execution_id=execution.execution_id, status="MEDIA_CANDIDATE", media_type="IMAGE",
        storage_identity="local://candidate-winner", checksum_sha256="checksum", mime_type="image/png", byte_size=68,
        width=1, height=1, prompt_ir_version_id=execution.prompt_ir_version_id, prompt_ir_payload_hash=execution.prompt_ir_payload_hash,
        generation_payload_fingerprint=execution.generation_payload_fingerprint, model_profile_id=execution.model_profile_id,
        model_profile_fingerprint=execution.model_profile_fingerprint, provider_request_fingerprint=execution.provider_request_fingerprint,
        provider_response_hash=execution.provider_response_hash,
    )
    session.add(candidate)
    request = canary.CanaryExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=execution.execution_id)
    return session, execution, candidate, request


@pytest.mark.parametrize("winner_status", ["SUCCEEDED", "REUSED"])
def test_claim_lost_valid_winner_reuses_after_lineage_validation(monkeypatch, winner_status):
    session, _execution, candidate, request = _setup(monkeypatch, winner_status)
    calls = []

    async def provider(**_kwargs):
        calls.append(1)
        raise AssertionError("claim-lost fallback must never call the provider")

    monkeypatch.setattr(canary, "_call_provider", provider)
    result = asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert result["reused"] is True
    assert result["provider_calls"] == 0
    assert result["candidate"]["candidate_id"] == candidate.candidate_id
    assert calls == []


def test_claim_lost_tampered_winner_candidate_fails_closed(monkeypatch):
    session, _execution, candidate, request = _setup(monkeypatch, "SUCCEEDED")
    candidate.provider_request_fingerprint = "tampered"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "GENERATION_CANDIDATE_LINEAGE_INVALID"
    assert exc.value.detail["provider_calls"] == 0
    assert session.winner_row.status == "SUCCEEDED"


def test_claim_lost_winner_without_candidate_fails_closed(monkeypatch):
    session, _execution, _candidate, request = _setup(monkeypatch, "SUCCEEDED")
    session.rows = [row for row in session.rows if not isinstance(row, MediaCandidateRecord)]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "GENERATION_EXECUTION_CANDIDATE_MISSING"
    assert exc.value.detail["provider_calls"] == 0


def test_claim_lost_running_winner_is_in_progress_without_provider_call(monkeypatch):
    _session, _execution, _candidate, request = _setup(monkeypatch, "RUNNING")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, request))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "GENERATION_CANARY_IN_PROGRESS"
    assert exc.value.detail["provider_calls"] == 0
