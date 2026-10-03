from __future__ import annotations

import asyncio
import json

import pytest

import api.model_registry as model_registry
import core.provider_transport_registry as transport_registry
import core.model_registry_credentials as registry_credentials
from core.runtime_credentials import RuntimeCredentialError, resolve_runtime_credential


def _profile() -> dict:
    return {
        "id": "local-video-ex8l4t",
        "name": "75api-minimax-h3",
        "capability": "video",
        "provider": "75api-minimax-h3",
        "base_url": "https://www.75api.com",
        "model_name": "minimax_h3_no_audios",
        "generation_capability": "VIDEO_GENERATION",
        "adapter_id": "video_generic",
        "adapter_version": "video_generic_adapter_v1",
        "transport_binding_id": "75api-minimax-h3.video.v1",
        "credential_ref": "profile:legacy-profile-key",
        "runtime_binding_id": "profile:legacy-profile-key",
        "api_key": "legacy-secret-must-not-be-canonical",
        "key_configured": True,
        "enabled": True,
        "default_params": {"seconds": 5, "resolution": "768p", "max_reference_images": 8},
    }


def test_75api_saved_model_management_key_maps_to_secret_free_profile_reference(monkeypatch):
    monkeypatch.delenv("API75_API_KEY", raising=False)
    monkeypatch.setattr(model_registry, "_all_profiles_raw", lambda: [_profile()])

    public = next(item for item in model_registry.list_profiles() if item["id"] == "local-video-ex8l4t")

    assert public["key_configured"] is True
    assert public["credential_configured"] is True
    assert public["credential_ref"] == "profile:local-video-ex8l4t"
    assert public["runtime_binding_id"] == "model-registry-profile-secret"
    assert "api_key" not in public


def test_75api_model_management_credential_resolves_server_side(monkeypatch):
    monkeypatch.delenv("API75_API_KEY", raising=False)
    monkeypatch.setattr(model_registry, "_all_profiles_raw", lambda: [_profile()])
    monkeypatch.setattr(registry_credentials, "get_kv", lambda _key, _default: json.dumps([_profile()]))

    public = next(item for item in model_registry.list_profiles() if item["id"] == "local-video-ex8l4t")
    assert public["credential_configured"] is True

    resolved = resolve_runtime_credential(public)
    assert resolved.audit() == {
        "credential_ref": "profile:local-video-ex8l4t",
        "configured": True,
        "resolved": True,
        "validated": True,
        "validation_method": "model-registry-secret-presence",
        "validation_version": "v1",
    }
    assert "legacy-secret-must-not-be-canonical" not in str(resolved.audit())


def test_75api_missing_model_management_credential_fails_closed(monkeypatch):
    monkeypatch.delenv("API75_API_KEY", raising=False)
    profile = _profile()
    profile["api_key"] = ""
    monkeypatch.setattr(model_registry, "_all_profiles_raw", lambda: [profile])
    monkeypatch.setattr(registry_credentials, "get_kv", lambda _key, _default: json.dumps([profile]))
    public = next(item for item in model_registry.list_profiles() if item["id"] == "local-video-ex8l4t")

    assert public["key_configured"] is False
    assert public["credential_configured"] is False
    with pytest.raises(RuntimeCredentialError) as exc:
        resolve_runtime_credential(public)
    assert exc.value.code == "RUNTIME_CREDENTIAL_NOT_RESOLVED"
    assert exc.value.credential_ref == "profile:local-video-ex8l4t"


def test_75api_transport_injects_ephemeral_credential_only(monkeypatch):
    captured: dict = {}

    async def fake_generate(profile, **kwargs):
        captured["profile"] = dict(profile)
        captured["kwargs"] = kwargs
        return {"externalTaskId": "zero-call-test", "provider": "75api-minimax-h3", "model": "minimax_h3_no_audios"}

    monkeypatch.setattr(transport_registry, "generate_video_asset", fake_generate)
    canonical_profile = {key: value for key, value in _profile().items() if key != "api_key"}
    canonical_profile["credential_ref"] = "profile:local-video-ex8l4t"
    canonical_profile["runtime_binding_id"] = "model-registry-profile-secret"
    context = {
        "profile": canonical_profile,
        "runtime_credential_value": "ephemeral-runtime-secret",
        "target_media": "VIDEO",
        "source_storage_identity": "https://cdn.example.com/source.png",
        "payload": {"request": {"prompt": "zero-call payload", "duration_seconds": 5, "aspect_ratio": "16:9"}},
        "reference_images": [],
    }

    result = asyncio.run(transport_registry.dispatch_provider_transport(context))

    assert result["externalTaskId"] == "zero-call-test"
    assert captured["profile"]["api_key"] == "ephemeral-runtime-secret"
    assert "api_key" not in canonical_profile
    assert "ephemeral-runtime-secret" not in str(result)
