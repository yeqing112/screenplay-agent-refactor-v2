from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api.generation_canary_api as canary
import models
from models import GenerationExecutionRecord, MediaCandidateRecord


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def first(self):
        return next((row for row in self.rows if all(getattr(row, k, None) == v for k, v in self.filters.items())), None)

    def update(self, values, synchronize_session=False):
        del synchronize_session
        rows = [row for row in self.rows if all(getattr(row, k, None) == v for k, v in self.filters.items())]
        for row in rows:
            for key, value in values.items():
                setattr(row, key, value)
        return len(rows)


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


def _video_context():
    payload = {
        "generation_payload_fingerprint": "video-payload",
        "prompt_ir_ref": {"plan_shot_id": "plan-101"},
        "generation_policy": {"fingerprint": "video-policy", "mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 1},
        "request": {
            "prompt": "A locked video prompt",
            "motion_prompt": "A locked video prompt",
            "reference_bindings": [],
            "mode": "TEXT_TO_VIDEO",
            "target_media": "VIDEO",
            "duration_seconds": 1,
            "aspect_ratio": None,
            "resolution": None,
        },
    }
    return {
        "row": SimpleNamespace(id=7, shot_id=101),
        "payload": payload,
        "policy": payload["generation_policy"],
        "resolved": {"version": SimpleNamespace(id=11, payload_hash="video-ir-hash"), "authority": SimpleNamespace(id=13)},
        "profile": {"id": "builtin-mock-video", "provider": "prototype-task-adapter", "model_name": "mock-video-v1", "phase_j3_canonical": True},
        "phase_profile": {"model_family": "GENERIC_VIDEO", "adapter_id": "video_generic"},
        "profile_fingerprint": "video-profile-fp",
        "adapter": {"adapter_id": "video_generic", "adapter_version": "video_generic_adapter_v1", "target_media": "VIDEO"},
        "reference_images": [],
        "reference_bindings_fingerprint": "refs-fp",
        "request_snapshot": {"schema_version": "phase_f_provider_request_v2", "prompt": "A locked video prompt", "motion_prompt": "A locked video prompt", "target_media": "VIDEO", "generation_mode": "TEXT_TO_VIDEO", "duration_seconds": 1, "aspect_ratio": None, "resolution": None, "reference_bindings": []},
        "provider_request_fingerprint": "video-request-fp",
        "target_media": "VIDEO",
        "source_binding": None,
        "source_storage_identity": "",
    }


def _image_context():
    context = _video_context()
    context["payload"] = deepcopy(context["payload"])
    context["payload"]["generation_payload_fingerprint"] = "image-payload"
    context["payload"]["generation_policy"] = {"fingerprint": "image-policy", "mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}
    context["payload"]["request"] = {"prompt": "A locked image prompt", "reference_bindings": [], "mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "aspect_ratio": "16:9", "resolution": "1024x1024"}
    context["policy"] = context["payload"]["generation_policy"]
    context["profile"] = {"id": "builtin-mock-image", "provider": "prototype-task-adapter", "model_name": "mock-image-v1", "phase_j3_canonical": True}
    context["phase_profile"] = {"model_family": "GENERIC_IMAGE", "adapter_id": "image_generic"}
    context["adapter"] = {"adapter_id": "image_generic", "adapter_version": "image_generic_adapter_v1", "target_media": "IMAGE"}
    context["request_snapshot"] = {"schema_version": "phase_f_provider_request_v2", "prompt": "A locked image prompt", "target_media": "IMAGE", "generation_mode": "TEXT_TO_IMAGE", "aspect_ratio": "16:9", "resolution": "1024x1024", "reference_bindings": [], "asset_bindings_fingerprint": "assets-fp"}
    context["provider_request_fingerprint"] = "image-request-fp"
    context["target_media"] = "IMAGE"
    context["source_binding"] = None
    context["source_storage_identity"] = ""
    context["asset_bindings_fingerprint"] = "assets-fp"
    return context


def test_canonical_selection_does_not_accept_caller_adapter():
    with pytest.raises(ValueError):
        canary.CanonicalPreviewRequest(model_profile_id="builtin-mock-video", target_media="VIDEO", adapter_id="image_generic")


@pytest.mark.parametrize("target_media", ["image", "video", "AUTO", "DEFAULT", ""])
def test_canonical_media_scope_is_exact_and_fail_closed(target_media):
    with pytest.raises(HTTPException) as exc:
        canary.preview_canonical_generation(1, 1, 101, canary.CanonicalPreviewRequest(model_profile_id="builtin-mock-image", target_media=target_media))
    assert exc.value.detail["code"] == "GENERATION_MEDIA_SCOPE_MISMATCH"


def test_canonical_requires_explicit_model_selection_before_registry_lookup(monkeypatch):
    monkeypatch.setattr(canary, "get_profile", lambda _profile_id: (_ for _ in ()).throw(AssertionError("registry lookup must not run")))
    with pytest.raises(HTTPException) as exc:
        canary.preview_canonical_generation(1, 1, 101, canary.CanonicalPreviewRequest(model_profile_id="", target_media="IMAGE"))
    assert exc.value.detail["code"] == "PRODUCTION_MODEL_SELECTION_REQUIRED"


def test_canonical_image_mock_submit_and_candidate(monkeypatch):
    session = _Session()
    context = _image_context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    monkeypatch.setattr(canary, "_persist_candidate_media", lambda **kwargs: {
        "storage_identity": "local://image",
        "storage_reference": {"image_url": "local://image"},
        "checksum_sha256": hashlib.sha256(canary._FAKE_PNG).hexdigest(),
        "mime_type": "image/png",
        "byte_size": len(canary._FAKE_PNG),
        "width": 1,
        "height": 1,
        "duration_ms": None,
    })
    preview = canary.preview_canonical_generation(1, 1, 101, canary.CanonicalPreviewRequest(model_profile_id="builtin-mock-image", target_media="IMAGE", generation_mode="TEXT_TO_IMAGE"))
    assert preview["target_media"] == "IMAGE"
    assert preview["ready"] is False or isinstance(preview["blocking_reasons"], list)
    request = canary.CanonicalExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    result = asyncio.run(canary.execute_canonical_generation(1, 1, 101, request))
    assert result["candidate"]["media_type"] == "IMAGE"
    assert result["execution"]["logical_provider_calls"] == 1
    assert result["execution"]["official_promotion_count"] == 0


def test_canonical_execute_profile_drift_is_preview_stale_without_provider(monkeypatch):
    session = _Session()
    context = _image_context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    calls = []
    async def provider(**_kwargs):
        calls.append(1)
        return await canary._fake_provider_image(request_snapshot=context["request_snapshot"], provider_request_fingerprint="drift")
    monkeypatch.setattr(canary, "_call_provider", provider)
    monkeypatch.setattr(canary, "_persist_candidate_media", lambda **kwargs: {"storage_identity": "local://image", "storage_reference": {"image_url": "local://image"}, "checksum_sha256": "x", "mime_type": "image/png", "byte_size": 1, "width": 1, "height": 1, "duration_ms": None})
    preview = canary.preview_canonical_generation(1, 1, 101, canary.CanonicalPreviewRequest(model_profile_id="builtin-mock-image", target_media="IMAGE"))
    context["profile_fingerprint"] = "changed-profile"
    request = canary.CanonicalExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(canary.execute_canonical_generation(1, 1, 101, request))
    assert exc.value.detail["code"] == "GENERATION_PREVIEW_STALE"
    assert calls == []


def test_runtime_credential_lifecycle_separates_validation_and_never_uses_raw_key():
    from core.runtime_credentials import RuntimeCredentialError, resolve_runtime_credential

    profile = {"id": "real-image", "provider": "openai-compatible", "credential_ref": "env:IMAGE_KEY", "credential_configured": True, "api_key": "RAW_LEGACY_SECRET"}
    resolved = resolve_runtime_credential(profile, resolver=lambda ref: "runtime-secret" if ref == "env:IMAGE_KEY" else None, validator=lambda value: value == "runtime-secret")
    assert resolved.audit() == {"credential_ref": "env:IMAGE_KEY", "configured": True, "resolved": True, "validated": True}
    with pytest.raises(RuntimeCredentialError) as exc:
        resolve_runtime_credential(profile, resolver=lambda _ref: "runtime-secret", validator=lambda _value: False)
    assert exc.value.code == "RUNTIME_CREDENTIAL_NOT_VALIDATED"


def test_canonical_human_authorization_gate_is_provider_free(monkeypatch):
    monkeypatch.delenv("PHASE_J_PROVIDER_AUTHORIZED", raising=False)
    context = {"profile": {"phase_j3_canonical": True, "provider": "openai-compatible"}}
    with pytest.raises(HTTPException) as exc:
        canary._validate_real_provider_opt_in(context)
    assert exc.value.detail["code"] == "REAL_PROVIDER_EXECUTION_NOT_AUTHORIZED"


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is required by the declared VIDEO validator contract")
def test_video_validator_rejects_invalid_container_mime_size_and_missing_storage(tmp_path: Path):
    from core.media_authority import validate_media_candidate_technical

    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not-an-mp4")
    candidate = SimpleNamespace(storage_reference_json="{}", storage_identity=str(invalid), checksum_sha256=hashlib.sha256(invalid.read_bytes()).hexdigest(), mime_type="video/mp4", byte_size=len(invalid.read_bytes()), media_type="VIDEO", width=2, height=2, duration_ms=1000)
    with pytest.raises(Exception):
        validate_media_candidate_technical(candidate)

    valid_path = tmp_path / "candidate.mp4"
    valid_path.write_bytes(canary._FAKE_MP4)
    candidate.storage_identity = str(valid_path)
    candidate.checksum_sha256 = hashlib.sha256(canary._FAKE_MP4).hexdigest()
    candidate.byte_size = len(canary._FAKE_MP4)
    candidate.mime_type = "video/webm"
    report = validate_media_candidate_technical(candidate)
    assert report["mime_valid"] is False and report["valid"] is False
    candidate.mime_type = "video/mp4"
    candidate.storage_identity = ""
    with pytest.raises(Exception):
        validate_media_candidate_technical(candidate)


def test_canonical_video_mock_submit_poll_and_candidate(monkeypatch):
    session = _Session()
    context = _video_context()
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    monkeypatch.setattr(
        canary,
        "_persist_candidate_media",
        lambda **kwargs: {
            "storage_identity": "local://video",
            "storage_reference": {"video_url": "local://video"},
            "checksum_sha256": "video-sha",
            "mime_type": "video/mp4",
            "byte_size": len(canary._FAKE_MP4),
            "width": 2,
            "height": 2,
            "duration_ms": 1000,
        },
    )
    preview = canary.preview_canonical_generation(1, 1, 101, canary.CanonicalPreviewRequest(model_profile_id="builtin-mock-video", target_media="VIDEO", generation_mode="TEXT_TO_VIDEO"))
    request = canary.CanonicalExecuteRequest(execute=True, confirmation_token=preview["confirmation_token"], preview_execution_id=preview["execution"]["execution_id"])
    result = asyncio.run(canary.execute_canonical_generation(1, 1, 101, request))
    replay = asyncio.run(canary.execute_canonical_generation(1, 1, 101, request))
    assert result["provider_calls"] == 1
    assert result["candidate"]["media_type"] == "VIDEO"
    assert result["candidate"]["duration_ms"] == 1000
    assert result["execution"]["provider_task_id"].startswith("fake-video-")
    assert replay["provider_calls"] == 0 and replay["reused"] is True
    assert len([row for row in session.rows if isinstance(row, GenerationExecutionRecord)]) == 1
    assert len([row for row in session.rows if isinstance(row, MediaCandidateRecord)]) == 1


def test_fake_video_is_real_mp4_and_deterministic():
    first = asyncio.run(canary._fake_provider_video(request_snapshot={"duration_seconds": 1}, provider_request_fingerprint="abc"))
    second = asyncio.run(canary._fake_provider_video(request_snapshot={"duration_seconds": 1}, provider_request_fingerprint="abc"))
    assert first["uri"] == second["uri"]
    assert canary._FAKE_MP4[4:8] == b"ftyp"


def test_video_technical_validator_catches_checksum_and_duration(tmp_path: Path):
    from core.media_authority import validate_media_candidate_technical

    path = tmp_path / "candidate.mp4"
    path.write_bytes(canary._FAKE_MP4)
    candidate = SimpleNamespace(
        storage_reference_json="{}",
        storage_identity=str(path),
        checksum_sha256=hashlib.sha256(canary._FAKE_MP4).hexdigest(),
        mime_type="video/mp4",
        byte_size=len(canary._FAKE_MP4),
        media_type="VIDEO",
        width=2,
        height=2,
        duration_ms=1000,
    )
    assert validate_media_candidate_technical(candidate)["valid"] is True
    candidate.checksum_sha256 = "wrong"
    assert validate_media_candidate_technical(candidate)["checksum_valid"] is False
    candidate.checksum_sha256 = hashlib.sha256(canary._FAKE_MP4).hexdigest()
    candidate.duration_ms = 3000
    assert validate_media_candidate_technical(candidate)["duration_valid"] is False
