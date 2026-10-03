from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from api.generation_adapters import (
    reconcile_75api_minimax_h3_generation,
    submit_75api_minimax_h3_generation,
)
from api.server import _persist_generated_video_locally
import api.generation_canary_api as canary
from core.provider_transport_registry import reconcile_provider_transport, submit_provider_transport
from models import GenerationExecutionRecord


_MP4 = (
    b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
    b"\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
)


@pytest.fixture(autouse=True)
def _disable_http_proxy_for_local_fixture(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


class _75ApiFixture:
    def __init__(self):
        self.posts = 0
        self.status_gets = 0
        self.content_gets = 0
        self.status_by_task: dict[str, int] = {}
        self.authorization_headers: list[str] = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _auth(self) -> bool:
                value = self.headers.get("Authorization", "")
                fixture.authorization_headers.append(value)
                return value == "Bearer test-secret"

            def do_POST(self):
                if self.path != "/v1/videos" or not self._auth():
                    self.send_response(401)
                    self.end_headers()
                    return
                fixture.posts += 1
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                task_id = f"task-{fixture.posts:03d}"
                self.wfile.write((f'{{"task_id":"{task_id}","request_id":"request-{fixture.posts:03d}"}}').encode())

            def do_GET(self):
                if not self._auth():
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.path.startswith("/v1/videos/task-") and not self.path.endswith("/content"):
                    task_id = self.path.rsplit("/", 1)[-1]
                    fixture.status_gets += 1
                    fixture.status_by_task[task_id] = fixture.status_by_task.get(task_id, 0) + 1
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    if fixture.status_by_task[task_id] == 1:
                        self.wfile.write((f'{{"id":"{task_id}","status":"processing"}}').encode())
                    else:
                        self.wfile.write((f'{{"id":"{task_id}","status":"completed"}}').encode())
                    return
                if self.path.startswith("/v1/videos/task-") and self.path.endswith("/content"):
                    fixture.content_gets += 1
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.end_headers()
                    self.wfile.write(_MP4)
                    return
                self.send_response(404)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def _profile(base_url: str) -> dict:
    return {
        "provider": "75api-minimax-h3",
        "base_url": base_url,
        "model_name": "minimax_h3_no_audios",
        "default_params": {"poll_interval_seconds": 1, "poll_timeout_seconds": 10},
    }


def test_75api_async_lifecycle_uses_runtime_credential_for_submit_poll_and_content(tmp_path, monkeypatch):
    with _75ApiFixture() as fixture:
        profile = _profile(fixture.base_url)
        submitted = asyncio.run(
            submit_75api_minimax_h3_generation(
                profile,
                payload={"model": "minimax_h3_no_audios", "prompt": "fixture", "seconds": "5"},
                runtime_credential_value="test-secret",
            )
        )
        assert submitted["providerTaskId"] == "task-001"
        assert "api_key" not in profile

        running = asyncio.run(
            reconcile_75api_minimax_h3_generation(
                profile,
                external_task_id="task-001",
                runtime_credential_value="test-secret",
            )
        )
        assert running["status"] == "running"
        done = asyncio.run(
            reconcile_75api_minimax_h3_generation(
                profile,
                external_task_id="task-001",
                runtime_credential_value="test-secret",
            )
        )
        assert done["status"] == "done"
        assert done["providerContentRequiresAuth"] is True

        monkeypatch.setattr("api.server.config.UPLOAD_DIR", Path(tmp_path))
        stored = _persist_generated_video_locally(
            done["uri"],
            book_id=991001,
            task_id="execution-001",
            label="fixture",
            download_headers={"Authorization": "Bearer test-secret"},
        )
        assert stored["ok"] is True
        assert stored["content_type"] == "video/mp4"
        assert fixture.posts == 1
        assert fixture.status_gets == 2
        assert fixture.content_gets == 1
        assert fixture.authorization_headers == ["Bearer test-secret"] * 4


def test_provider_transport_submit_reconcile_contract_does_not_resubmit():
    with _75ApiFixture() as fixture:
        context = {
            "profile": {
                "provider": "75api-minimax-h3",
                "model_name": "minimax_h3_no_audios",
                "base_url": fixture.base_url,
                "transport_binding_id": "75api-minimax-h3.video.v1",
                "default_params": {"poll_interval_seconds": 1, "poll_timeout_seconds": 10},
            },
            "runtime_credential_value": "test-secret",
            "target_media": "VIDEO",
            "source_storage_identity": "https://fixture.invalid/source.png",
            "payload": {"request": {"prompt": "fixture", "duration_seconds": 5, "aspect_ratio": "16:9"}},
        }
        submitted = asyncio.run(submit_provider_transport(context))
        assert submitted["providerTaskId"] == "task-001"
        first = asyncio.run(reconcile_provider_transport(context, external_task_id="task-001"))
        second = asyncio.run(reconcile_provider_transport(context, external_task_id="task-001"))
        assert first["status"] == "running"
        assert second["status"] == "done"
        assert fixture.posts == 1
        assert fixture.status_gets == 2


class _MemoryQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def first(self):
        return next((row for row in self.rows if all(getattr(row, key, None) == value for key, value in self.filters.items())), None)

    def update(self, values, synchronize_session=False):
        del synchronize_session
        matches = [row for row in self.rows if all(getattr(row, key, None) == value for key, value in self.filters.items())]
        for row in matches:
            for key, value in values.items():
                setattr(row, key, value)
        return len(matches)


class _MemorySession:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, model):
        return _MemoryQuery([row for row in self.rows if isinstance(row, model)])

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        return None

    def rollback(self):
        return None

    def flush(self):
        return None


def test_canonical_async_submit_persists_running_identity_and_reconcile_does_not_resubmit(monkeypatch):
    context = {
        "row": SimpleNamespace(id=1),
        "target_media": "VIDEO",
        "profile": {
            "id": "local-video-ex8l4t", "provider": "75api-minimax-h3", "model_name": "minimax_h3_no_audios",
            "phase_j3_canonical": True, "transport_binding_id": "75api-minimax-h3.video.v1",
        },
        "runtime_credential_value": "test-secret",
        "payload": {"generation_payload_fingerprint": "payload-fp", "generation_policy": {"fingerprint": "policy-fp", "mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 5}, "request": {"prompt": "fixture", "mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 5, "aspect_ratio": "16:9", "resolution": None, "reference_bindings": []}},
        "policy": {"fingerprint": "policy-fp", "mode": "TEXT_TO_VIDEO", "target_media": "VIDEO", "duration_seconds": 5},
        "resolved": {"version": type("Version", (), {"payload_hash": "prompt-fp", "id": 1})()},
        "profile_fingerprint": "profile-fp", "reference_bindings_fingerprint": "refs-fp", "asset_bindings_fingerprint": "assets-fp",
        "request_snapshot": {"target_media": "VIDEO", "generation_mode": "TEXT_TO_VIDEO", "duration_seconds": 5, "aspect_ratio": "16:9", "resolution": None, "prompt": "fixture", "reference_bindings": [], "asset_bindings_fingerprint": "assets-fp"},
        "provider_request_fingerprint": "request-fp", "source_storage_identity": "https://fixture.invalid/source.png", "reference_images": [],
    }
    row = GenerationExecutionRecord(
        execution_id="execution-a", book_id=990452, episode=1, storyboard_shot_id=1, plan_shot_id="plan-1", execution_mode="CANARY", status="PREVIEWED", target_media="VIDEO",
        prompt_ir_version_id=1, prompt_ir_authority_id=1, prompt_ir_payload_hash="prompt-fp", generation_payload_fingerprint="payload-fp", generation_policy_fingerprint="policy-fp",
        model_profile_id="local-video-ex8l4t", model_profile_fingerprint="profile-fp", provider_adapter_id="video_generic", provider_adapter_version="video_generic_adapter_v1",
        reference_bindings_fingerprint="refs-fp", provider_request_fingerprint="request-fp", request_snapshot_json=__import__("json").dumps(context["request_snapshot"]), confirmation_binding_hash="", provider="", model="", provider_request_id="", provider_task_id="", provider_response_hash="", logical_provider_calls=0,
    )
    session = _MemorySession([row])
    monkeypatch.setattr(canary, "Session", lambda: session)
    monkeypatch.setattr(canary, "_resolve_canonical_execution_inputs", lambda *args, **kwargs: context)
    monkeypatch.setattr(canary, "_validate_url_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(canary, "_validate_real_provider_opt_in", lambda *_args: None)
    submits = []

    async def submit(_context):
        submits.append(1)
        return {"providerTaskId": "task-a", "providerRequestId": "request-a", "providerResponse": {"task_id": "task-a"}}

    monkeypatch.setattr(canary, "submit_provider_transport", submit)
    token = canary._confirmation_token(execution_id=row.execution_id, prompt_ir_version_id=row.prompt_ir_version_id, payload_fp=row.generation_payload_fingerprint, model_profile_id=row.model_profile_id, provider_request_fp=row.provider_request_fingerprint)
    executed = asyncio.run(canary._execute_generation_canary_impl(990452, 1, 1, canary.CanaryExecuteRequest(execute=True, confirmation_token=token, preview_execution_id=row.execution_id), _canonical=True))
    assert executed["async_phase"] == "SUBMIT"
    assert executed["execution"]["status"] == "RUNNING"
    assert executed["execution"]["provider_task_id"] == "task-a"
    assert executed["candidate"] is None

    reconcile_calls = []

    async def reconcile(_context, *, external_task_id):
        reconcile_calls.append(external_task_id)
        if len(reconcile_calls) == 1:
            return {"status": "running", "externalStatus": "processing"}
        return {"status": "done", "uri": "data:video/mp4;base64,AAAA", "providerResponse": {"task_id": external_task_id}}

    monkeypatch.setattr(canary, "reconcile_provider_transport", reconcile)
    monkeypatch.setattr(canary, "_persist_candidate_media", lambda **kwargs: {"storage_identity": "local://video", "storage_reference": {"video_url": "local://video"}, "checksum_sha256": "checksum", "mime_type": "video/mp4", "byte_size": 4, "width": 1, "height": 1, "duration_ms": 1000})
    monkeypatch.setattr("core.media_authority.validate_media_candidate", lambda *_args, **_kwargs: {"status": "valid"})
    request = canary.CanonicalReconcileRequest(execution_id=row.execution_id, confirmation_token=token)
    first = asyncio.run(canary._reconcile_generation_canary_impl(990452, 1, 1, request))
    second = asyncio.run(canary._reconcile_generation_canary_impl(990452, 1, 1, request))
    assert first["execution"]["status"] == "RUNNING"
    assert second["execution"]["status"] == "SUCCEEDED"
    assert second["candidate"]["provider_task_id"] == "task-a"
    assert submits == [1]
    assert reconcile_calls == ["task-a", "task-a"]


def test_provider_free_regenerate_allocates_new_execution_and_preserves_review_snapshot(tmp_path):
    with _75ApiFixture() as fixture:
        profile = _profile(fixture.base_url)
        first = asyncio.run(submit_75api_minimax_h3_generation(profile, payload={"model": "minimax_h3_no_audios", "prompt": "v1"}, runtime_credential_value="test-secret"))
        second = asyncio.run(submit_75api_minimax_h3_generation(profile, payload={"model": "minimax_h3_no_audios", "prompt": "v2"}, runtime_credential_value="test-secret"))
        assert first["providerTaskId"] == "task-001"
        assert second["providerTaskId"] == "task-002"
        assert first["providerTaskId"] != second["providerTaskId"]
        initial_snapshot = {"execution_id": "execution-a", "attempt_id": "attempt-a", "provider_task_id": first["providerTaskId"], "official_v1_current": True, "candidate_v2_pending": False, "official_v2_current": False}
        regenerate_snapshot = {**initial_snapshot, "execution_id": "execution-b", "attempt_id": "attempt-b", "provider_task_id": second["providerTaskId"], "candidate_v2_pending": True}
        import json
        (tmp_path / "VIDEO_OFFICIAL_V1_STATE.json").write_text(json.dumps(initial_snapshot), encoding="utf-8")
        (tmp_path / "VIDEO_REGENERATE_PRE_APPROVAL_STATE.json").write_text(json.dumps(regenerate_snapshot), encoding="utf-8")
        assert regenerate_snapshot["official_v1_current"] is True
        assert regenerate_snapshot["official_v2_current"] is False
        approved_snapshot = {**regenerate_snapshot, "candidate_v2_pending": False, "official_v1_current": False, "official_v2_current": True}
        (tmp_path / "VIDEO_OFFICIAL_V2_STATE.json").write_text(json.dumps(approved_snapshot), encoding="utf-8")
        assert approved_snapshot["official_v1_current"] is False
        assert approved_snapshot["official_v2_current"] is True
        assert fixture.posts == 2
