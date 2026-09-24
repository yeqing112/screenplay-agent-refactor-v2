from __future__ import annotations

import asyncio
import hashlib
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


def test_canonical_selection_does_not_accept_caller_adapter():
    with pytest.raises(ValueError):
        canary.CanonicalPreviewRequest(model_profile_id="builtin-mock-video", target_media="VIDEO", adapter_id="image_generic")


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
