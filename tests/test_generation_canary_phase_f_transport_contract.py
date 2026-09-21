from __future__ import annotations

import base64
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.generation_adapters import generate_image_asset
from core.provider_execution_profile import build_provider_execution_profile


def _client(response_payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = response_payload
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai-compatible", "shapi-openai-images", "shapi-gemini-image"])
async def test_phase_f_timeout_is_transport_only(provider):
    if provider == "shapi-gemini-image":
        response_payload = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b"generated").decode()} }]}}]}
    else:
        response_payload = {"data": [{"b64_json": base64.b64encode(b"generated").decode()}]}
    client = _client(response_payload)
    raw = {
        "id": "image-test",
        "capability": "image",
        "provider": provider,
        "base_url": "https://provider.example/v1",
        "model_name": "image-v1",
        "api_key": "key",
        "key_configured": True,
        "source": "test",
        "default_params": {"timeout_seconds": 37, "size": "1024x1024", "image_size": "2K"},
    }
    profile = dict(raw, provider_execution_profile=build_provider_execution_profile(raw, adapter_id="image_generic", adapter_version="v1"))
    with patch("api.generation_adapters.httpx.AsyncClient", return_value=client) as ctor:
        await generate_image_asset(profile, prompt="prompt", aspect_ratio="16:9")
    assert ctor.call_args.kwargs["timeout"] == 37
    payload = client.post.await_args.kwargs["json"]
    assert "timeout_seconds" not in str(payload)
    assert "timeout_seconds" not in payload
