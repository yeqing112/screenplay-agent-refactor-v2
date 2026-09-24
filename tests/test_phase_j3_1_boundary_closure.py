from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import api.generation_adapters as adapters
import api.generation_canary_api as canary
import api.server as server
from core.provider_transport_registry import dispatch_provider_transport, list_provider_transport_bindings
from core.runtime_credentials import RuntimeCredentialError, resolve_runtime_credential


def test_runtime_credential_validator_is_required_and_fail_closed():
    profile = {
        "id": "real-video",
        "credential_ref": "env:J31_VIDEO_KEY",
        "credential_configured": True,
    }
    with pytest.raises(RuntimeCredentialError) as missing:
        resolve_runtime_credential(profile, resolver=lambda _ref: "runtime-secret")
    assert missing.value.code == "RUNTIME_CREDENTIAL_NOT_VALIDATED"

    with pytest.raises(RuntimeCredentialError) as rejected:
        resolve_runtime_credential(profile, resolver=lambda _ref: "runtime-secret", validator=lambda _value: False)
    assert rejected.value.code == "RUNTIME_CREDENTIAL_NOT_VALIDATED"

    validated = resolve_runtime_credential(
        profile,
        resolver=lambda _ref: "runtime-secret",
        validator=lambda value: value == "runtime-secret",
    )
    assert validated.audit() == {
        "credential_ref": "env:J31_VIDEO_KEY",
        "configured": True,
        "resolved": True,
        "validated": True,
    }
    assert "runtime-secret" not in str(validated.audit())


def test_transport_registry_exposes_exact_image_and_video_bindings():
    rows = list_provider_transport_bindings()
    keys = {(item.provider_id, item.target_media) for item in rows}
    assert ("poyo-async", "VIDEO") in keys
    assert ("minimax-h3-async", "VIDEO") in keys
    assert ("75api-minimax-h3", "VIDEO") in keys
    assert ("openai-compatible", "IMAGE") in keys
    assert all(item.submit and item.poll for item in rows)


def test_canonical_video_transport_submits_once_and_polls_without_resubmit(monkeypatch):
    calls = {"submit": 0, "poll": 0}

    async def submit(_profile, *, payload):
        calls["submit"] += 1
        assert payload["model"] == "MiniMax-H3"
        return {"externalTaskId": "task-j31", "providerResponse": {"status": "submitted"}}

    async def poll(_profile, *, external_task_id):
        calls["poll"] += 1
        assert external_task_id == "task-j31"
        return {
            "externalStatus": "succeeded",
            "pollAttempts": 2,
            "uri": "data:video/mp4;base64,AAAA",
            "previewUrl": "data:video/mp4;base64,AAAA",
            "providerResponse": {"status": "succeeded"},
        }

    monkeypatch.setattr(adapters, "_build_minimax_h3_video_payload", lambda *args, **kwargs: {"model": "MiniMax-H3", "content": []})
    monkeypatch.setattr(adapters, "submit_minimax_h3_generation", submit)
    monkeypatch.setattr(adapters, "poll_minimax_h3_generation", poll)
    context = {
        "profile": {
            "provider": "minimax-h3-async",
            "model_name": "MiniMax-H3",
            "base_url": "https://provider.invalid",
            "transport_binding_id": "minimax-h3-async.video.v1",
        },
        "runtime_credential_value": "runtime-secret",
        "target_media": "VIDEO",
        "payload": {
            "request": {
                "prompt": "locked prompt",
                "duration_seconds": 4,
                "aspect_ratio": "16:9",
                "negative_prompt": "",
            }
        },
        "reference_images": [],
        "source_storage_identity": "",
    }
    result = asyncio.run(dispatch_provider_transport(context))
    assert result["externalTaskId"] == "task-j31"
    assert calls == {"submit": 1, "poll": 1}


def test_storyboard_alias_without_profile_fails_closed_before_legacy_queue(monkeypatch):
    async def queue_must_not_run(*_args, **_kwargs):
        raise AssertionError("legacy queue must be unreachable")

    monkeypatch.setattr(server, "_queue_storyboard_generation_task", queue_must_not_run)
    request = server.StoryboardGenerationRequest()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server._delegate_storyboard_generation_to_canonical(
                1, 1, "101", request, target_media="IMAGE", bg=server.BackgroundTasks()
            )
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "PRODUCTION_MODEL_SELECTION_REQUIRED"
    assert exc.value.detail["provider_calls"] == 0
    assert exc.value.detail["creative_task_created"] is False


def test_real_video_profile_without_explicit_transport_binding_fails_closed(monkeypatch):
    profile = {
        "id": "video-without-transport",
        "provider": "minimax-h3-async",
        "model_name": "MiniMax-H3",
        "capability": "video",
        "generation_capability": "VIDEO_GENERATION",
        "adapter_id": "video_generic",
        "adapter_version": "video_generic_adapter_v1",
        "credential_ref": "env:J31_VIDEO_KEY",
        "credential_configured": True,
        "enabled": True,
        "base_url": "https://provider.invalid",
        "default_params": {"timeout_seconds": 30},
    }
    monkeypatch.setattr(canary, "list_profiles", lambda include_sensitive=False: [profile])
    with pytest.raises(HTTPException) as exc:
        canary._resolve_canonical_profile("video-without-transport", target_media="VIDEO")
    assert exc.value.detail["code"] == "PHASE_J3_REAL_VIDEO_TRANSPORT_BINDING_REQUIRED"
