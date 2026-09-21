from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.generation_canary_api as canary
from core.provider_execution_profile import (
    build_provider_execution_profile,
    fingerprint_provider_execution_profile,
)
from models import GenerationExecutionRecord, MediaCandidateRecord


def test_provider_execution_profile_is_allowlisted_and_secret_free():
    raw = {
        "id": "image-a",
        "capability": "image",
        "provider": "openai-compatible",
        "base_url": "https://example.test/v1?key=ignored",
        "model_name": "image-v1",
        "source": "env-prod",
        "key_configured": True,
        "api_key": "PHASE_F_TEST_SECRET_DO_NOT_PERSIST",
        "default_params": {
            "size": "1024x1024",
            "timeout_seconds": 37,
            "nested": {"token": "PHASE_F_TEST_SECRET_DO_NOT_PERSIST"},
            "authorization": "Bearer PHASE_F_TEST_SECRET_DO_NOT_PERSIST",
        },
    }
    profile = build_provider_execution_profile(raw, adapter_id="image_generic", adapter_version="v1")
    rendered = str(profile)
    assert profile["schema_version"] == "provider_execution_profile_v1"
    assert profile["generation_params"] == {"size": "1024x1024"}
    assert profile["transport_config"] == {"timeout_seconds": 37}
    assert profile["credential"] == {"configured": True, "source_identity": "env-prod"}
    assert "PHASE_F_TEST_SECRET_DO_NOT_PERSIST" not in rendered

    rotated = dict(raw, api_key="ROTATED")
    assert fingerprint_provider_execution_profile(profile) == fingerprint_provider_execution_profile(
        build_provider_execution_profile(rotated, adapter_id="image_generic", adapter_version="v1")
    )
    changed = dict(raw, default_params={"size": "2048x2048", "timeout_seconds": 37})
    assert fingerprint_provider_execution_profile(profile) != fingerprint_provider_execution_profile(
        build_provider_execution_profile(changed, adapter_id="image_generic", adapter_version="v1")
    )


def test_successful_replay_validates_confirmation_before_reuse(monkeypatch):
    class Session:
        def __init__(self):
            self.rows = []
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def query(self, model):
            rows = [r for r in self.rows if isinstance(r, model)]
            class Q:
                def __init__(self, rows): self.rows, self.filters = rows, {}
                def filter_by(self, **kw): self.filters.update(kw); return self
                def first(self): return next((r for r in self.rows if all(getattr(r, k, None) == v for k, v in self.filters.items())), None)
                def update(self, values, synchronize_session=False):
                    del synchronize_session
                    count = 0
                    for r in self.rows:
                        if all(getattr(r, k, None) == v for k, v in self.filters.items()):
                            for k, v in values.items(): setattr(r, k, v)
                            count += 1
                    return count
            return Q(rows)
        def add(self, row): self.rows.append(row)
        def commit(self): pass
        def rollback(self): pass

    session = Session()
    context = {
        "row": SimpleNamespace(id=7),
        "resolved": {"version": SimpleNamespace(id=11, payload_hash="ir"), "authority": SimpleNamespace(id=13)},
        "payload": {"generation_payload_fingerprint": "payload", "generation_policy": {"fingerprint": "policy"}, "prompt_ir_ref": {"plan_shot_id": "p"}, "request": {"prompt": "x"}},
        "policy": {"fingerprint": "policy"}, "profile": {"provider": "prototype-task-adapter", "model_name": "mock"},
        "profile_fingerprint": "profile", "adapter": {"adapter_id": "image_generic", "adapter_version": "v1"},
        "reference_bindings_fingerprint": "refs", "request_snapshot": {"prompt": "x"},
        "provider_request_fingerprint": "request", "reference_images": [],
    }
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_execution_inputs", lambda *a, **k: context)
    preview = canary.preview_generation_canary(1, 1, 101, canary.CanaryPreviewRequest(adapter_id="image_generic", model_profile_id="mock"))
    execution = next(r for r in session.rows if isinstance(r, GenerationExecutionRecord))
    execution.status = "SUCCEEDED"
    execution.provider_response_hash = "response"
    execution.candidate_id = "candidate"
    candidate = MediaCandidateRecord(candidate_id="candidate", execution_id=execution.execution_id, status="MEDIA_CANDIDATE", media_type="IMAGE", storage_identity="local://x", checksum_sha256="x", mime_type="image/png", byte_size=1, width=1, height=1, prompt_ir_version_id=11, prompt_ir_payload_hash="ir", generation_payload_fingerprint="payload", model_profile_id="mock", model_profile_fingerprint="profile", provider_request_fingerprint="request", provider_response_hash="response")
    session.add(candidate)
    bad = canary.CanaryExecuteRequest(execute=True, confirmation_token="wrong", preview_execution_id=execution.execution_id)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_generation_canary(1, 1, 101, bad))
    assert exc.value.detail["code"] == "GENERATION_CANARY_CONFIRMATION_MISMATCH"
