from __future__ import annotations

import pytest

import api.generation_canary_api as canary
from core.provider_execution_profile import (
    PROFILE_SCHEMA_VERSION,
    ProviderExecutionProfileError,
    build_provider_execution_profile,
    fingerprint_provider_execution_profile,
    provider_generation_params,
    provider_timeout_seconds,
)


def _raw(**params):
    return {
        "id": "typed-image",
        "capability": "image",
        "provider": "openai-compatible",
        "base_url": "https://example.test/v1",
        "model_name": "image-v1",
        "source": "env-prod",
        "key_configured": True,
        "api_key": "PHASE_F_TEST_SECRET_DO_NOT_PERSIST",
        "default_params": params,
    }


def test_typed_generation_params_and_capabilities_are_canonicalized():
    profile = build_provider_execution_profile(
        _raw(
            size="1024x1024", quality="hd", response_format="b64_json", steps=28, cfg=6.5,
            seed=123, sampling="euler", aspect_ratio="16:9", image_size="2K",
            max_reference_images=4, max_reference_image_bytes=1000000, n=1, watermark=False,
            guidance_scale=7.0, num_inference_steps=28, background="transparent", moderation=False,
            size_by_aspect_ratio={"16:9": "1536x864", "9:16": "864x1536"},
            supports_reference_images=True, supports_negative_prompt=True,
        ),
        adapter_id="image_generic", adapter_version="v2",
    )
    assert profile["schema_version"] == PROFILE_SCHEMA_VERSION
    assert profile["generation_params"]["steps"] == 28
    assert profile["generation_params"]["size_by_aspect_ratio"] == {"16:9": "1536x864", "9:16": "864x1536"}
    assert profile["capabilities"] == {"supports_negative_prompt": True, "supports_reference_images": True}
    assert "supports_reference_images" not in profile["generation_params"]
    assert "supports_negative_prompt" not in profile["generation_params"]
    assert "PHASE_F_TEST_SECRET_DO_NOT_PERSIST" not in str(profile)


@pytest.mark.parametrize(
    "field,value",
    [
        ("steps", "twenty"),
        ("seed", {"x": 1}),
        ("cfg", [6.5]),
        ("size", {"secret": "x"}),
        ("size_by_aspect_ratio", {"16:9": {"size": "x"}}),
        ("size_by_aspect_ratio", {"api_key": "PHASE_F_TEST_SECRET_DO_NOT_PERSIST"}),
    ],
)
def test_typed_generation_params_fail_closed(field, value):
    with pytest.raises(ProviderExecutionProfileError) as exc:
        build_provider_execution_profile(_raw(**{field: value}), adapter_id="image_generic", adapter_version="v2")
    assert exc.value.code == "GENERATION_PROVIDER_PARAM_INVALID"


@pytest.mark.parametrize("field", ["negative_prompt", "style"])
def test_profile_semantic_params_are_rejected_before_canonicalization(field):
    with pytest.raises(ProviderExecutionProfileError) as exc:
        build_provider_execution_profile(_raw(**{field: "hidden creative instruction"}), adapter_id="image_generic", adapter_version="v2")
    assert exc.value.code == "GENERATION_PROVIDER_SEMANTIC_PARAM_FORBIDDEN"


def test_negative_prompt_snapshot_can_only_come_from_generation_payload():
    profile = build_provider_execution_profile(_raw(size="1024x1024"), adapter_id="image_generic", adapter_version="v2")
    snapshot = canary._request_snapshot(
        profile={**_raw(size="1024x1024"), "provider_execution_profile": profile},
        adapter={"adapter_id": "image_generic", "adapter_version": "v2"},
        payload={"request": {"prompt": "visual truth", "negative_prompt": "payload constraint"}},
        reference_bindings=[],
    )
    assert snapshot["negative_prompt"] == "payload constraint"
    assert "negative_prompt" not in snapshot["generation_params"]
    assert "style" not in snapshot["generation_params"]


def test_strict_phase_f_transport_requires_canonical_profile():
    with pytest.raises(ProviderExecutionProfileError):
        provider_generation_params({"phase_f_strict": True, "default_params": {"size": "1024x1024"}})
    with pytest.raises(ProviderExecutionProfileError):
        provider_timeout_seconds({"phase_f_strict": True, "default_params": {"timeout_seconds": 37}})


def test_fingerprint_only_accepts_typed_canonical_profile():
    profile = build_provider_execution_profile(_raw(size="1024x1024"), adapter_id="image_generic", adapter_version="v2")
    assert fingerprint_provider_execution_profile(profile)
    with pytest.raises(ProviderExecutionProfileError):
        fingerprint_provider_execution_profile(_raw(size="1024x1024"))
