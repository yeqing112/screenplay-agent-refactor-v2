import asyncio
import base64
import copy

import pytest

from api.generation_adapters import ModelProfileError, _generate_75api_image
from core.asset_provider_router import PostSubmissionState, ProviderFailureClassification, classify_provider_failure
from core.provider_response_contract import API75_IMAGE_RESPONSE_PATHS, API75ImageResponseInspector, extract_75api_image_result, response_fingerprint, safe_provider_response


def _profile():
    return {
        "id": "75-test",
        "provider": "75api-image",
        "model_name": "gpt-image-2-1k",
        "api_key": "secret",
        "base_url": "https://api.example.test",
        "default_params": {"n": 1, "quality": "high", "response_format": "url", "supports_reference_images": True},
    }


def test_documented_top_level_url_is_supported():
    result = extract_75api_image_result({"model": "gpt-image-2", "url": "http://154.9.235.100:3006/images/x.png"})
    assert result.source_path == "url"
    assert result.preview_url.startswith("http://")
    assert result.result_classification == "VALID_IMAGE_RESPONSE"


def test_openai_data_url_is_supported():
    result = extract_75api_image_result({"data": [{"url": "https://cdn.example.test/x.png?sig=secret"}]})
    assert result.source_path == "data[0].url"
    assert result.preview_url.startswith("https://")


def test_openai_data_base64_is_supported_and_not_in_shape():
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture-media").decode()
    result = extract_75api_image_result({"data": [{"b64_json": encoded}]})
    assert result.source_path == "data[0].b64_json"
    assert result.image_base64 == encoded
    shape = result.provider_response_shape
    assert encoded not in str(shape)
    assert shape["string_length_metadata"]["data[0].b64_json"]["type"] == "base64"


def test_documented_url_can_carry_base64():
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture-media").decode()
    result = extract_75api_image_result({"model": "gpt-image-2", "url": encoded})
    assert result.source_path == "url"
    assert result.image_base64 == encoded


def test_http_200_logical_error_is_distinct():
    with pytest.raises(ValueError, match="PROVIDER_LOGICAL_ERROR"):
        extract_75api_image_result({"code": "insufficient_balance", "message": "balance"})
    assert classify_provider_failure("75API_IMAGE_RESPONSE_LOGICAL_ERROR", post_submission_state=PostSubmissionState.TASK_CONFIRMED) == ProviderFailureClassification.PROVIDER_LOGICAL_ERROR


def test_valid_shape_without_media_is_contract_mismatch():
    with pytest.raises(ValueError, match="75API_IMAGE_RESPONSE_MEDIA_MISSING"):
        extract_75api_image_result({"model": "gpt-image-2", "data": []})
    assert classify_provider_failure("75API_IMAGE_RESPONSE_MEDIA_MISSING", post_submission_state=PostSubmissionState.TASK_CONFIRMED) == ProviderFailureClassification.PROVIDER_RESPONSE_CONTRACT_MISMATCH


def test_unknown_schema_fails_closed():
    with pytest.raises(ValueError, match="75API_IMAGE_RESPONSE_SCHEMA_UNKNOWN"):
        extract_75api_image_result({"model": "gpt-image-2", "result": {"asset": "opaque"}})


def test_signed_url_and_base64_are_redacted():
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture-media").decode()
    response = {"url": "https://cdn.example.test/x.png?token=secret", "b64_json": encoded, "api_key": "secret"}
    safe = safe_provider_response(response, http_status=200)
    serialized = str(safe)
    assert "token=secret" not in serialized
    assert encoded not in serialized
    assert "api_key" not in serialized
    assert safe["provider_response_shape"]["string_length_metadata"]["url"]["has_query"] is True


def test_response_fingerprint_is_stable_across_signed_url_query():
    first = {"url": "https://cdn.example.test/x.png?token=one"}
    second = {"url": "https://cdn.example.test/x.png?token=two"}
    assert response_fingerprint(first) == response_fingerprint(second)


def test_inspector_contains_only_safe_shape_metadata():
    encoded = base64.b64encode(b"\x89PNG\r\n\x1a\nfixture-media").decode()
    shape = API75ImageResponseInspector.inspect({"id": "x", "data": [{"b64_json": encoded}]}, http_status=200)
    assert shape["top_level_keys"] == ["data", "id"]
    assert "candidate_media_paths" in shape
    assert encoded not in str(shape)


def test_75api_adapter_propagates_documented_shape_and_safe_evidence(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"model": "gpt-image-2", "url": "http://154.9.235.100:3006/images/x.png"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("api.generation_adapters.httpx.AsyncClient", lambda **_kwargs: Client())
    result = asyncio.run(_generate_75api_image(_profile(), prompt="portrait", aspect_ratio="1:1", negative_prompt=None, reference_images=[]))
    assert result["providerResponseMediaPath"] == "url"
    assert result["providerHttpStatus"] == 200
    assert result["providerResponseFingerprint"]
    assert result["providerResponse"]["provider_response_shape"]["candidate_media_paths"] == ["url"]


def test_75api_adapter_unknown_response_propagates_contract_evidence(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"model": "gpt-image-2", "result": {"asset": "opaque"}}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("api.generation_adapters.httpx.AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(ModelProfileError) as caught:
        asyncio.run(_generate_75api_image(_profile(), prompt="portrait", aspect_ratio="1:1", negative_prompt=None, reference_images=[]))
    exc = caught.value
    assert exc.response_classification == "PROVIDER_RESPONSE_CONTRACT_MISMATCH"
    assert exc.provider_http_status == 200
    assert exc.provider_response_shape["top_level_keys"] == ["model", "result"]
    assert exc.provider_response_fingerprint


def test_response_paths_are_explicit_and_small():
    assert API75_IMAGE_RESPONSE_PATHS["documented"] == ("url",)
    assert API75_IMAGE_RESPONSE_PATHS["openai_compatible"] == ("data[].url", "data[].b64_json")
