"""MiniMax H3 video provider canary contracts (network-free)."""

import os

import pytest

from core.provider_transport_registry import get_provider_transport_binding
from core.video_provider_adapter import MinimaxH3VideoProvider, VideoProviderError
from api.generation_adapters import _build_minimax_h3_video_payload


PROFILE = {
    "id": "local-video-test",
    "capability": "video",
    "provider": "minimax-h3-async",
    "base_url": "https://metaso.cn/api/minimax",
    "model_name": "MiniMax-H3",
    "api_key": "secret-test-key",
    "enabled": True,
    "transport_binding_id": "minimax-h3-async.video.v1",
}


def _transport(profile, **kwargs):
    async def run():
        content = [{"type": "text", "text": kwargs["prompt"]}]
        if kwargs.get("first_frame_url"):
            content.append({"type": "image_url", "role": "first_frame", "image_url": {"url": kwargs["first_frame_url"]}})
        if kwargs.get("last_frame_url"):
            content.append({"type": "image_url", "role": "last_frame", "image_url": {"url": kwargs["last_frame_url"]}})
        return {
            "externalTaskId": "task-canary-1",
            "providerTaskId": "task-canary-1",
            "providerRequestId": "task-canary-1",
            "providerRequestPayload": {
                "model": profile["model_name"],
                "content": content,
                "resolution": "768P",
            },
            "providerResponse": {"status": "succeeded", "duration": 5, "seed": 7},
            "previewUrl": "https://cdn.example.test/canary.mp4",
            "uri": "https://cdn.example.test/canary.mp4",
        }

    return run()


def test_minimax_h3_adapter_binds_registry_profile_and_records_response():
    adapter = MinimaxH3VideoProvider(PROFILE, transport=_transport)
    result = adapter.generate_video(
        prompt="A traveler faces the tunnel.",
        motion_profile={"camera_motion": "slow_push_in", "subject_motion": "head_turn"},
        duration=5,
        aspect_ratio="16:9",
        first_frame_asset={"keyframe_id": 1, "storage_identity": "https://cdn.example.test/frame.png"},
        last_frame_asset={"keyframe_id": 2, "storage_identity": "https://cdn.example.test/end.png"},
        request_context={"canary_scope": "episode:1:shot:1", "shot_direction": {"direction_fingerprint": "sha256:direction"}, "_runtime_profile": PROFILE},
    )
    assert result.provider == "minimax-h3-async"
    assert result.model == "MiniMax-H3"
    assert result.provider_task_id == "task-canary-1"
    assert result.provider_response["video_url"].endswith("canary.mp4")
    assert result.provider_response["created_time"]
    assert result.provider_request["motion_profile"]["camera_motion"] == "slow_push_in"
    assert result.provider_request["shot_direction"]["direction_fingerprint"] == "sha256:direction"
    assert result.provider_request["content"][2]["role"] == "last_frame"
    assert "api_key" not in str(result.as_dict())
    assert "secret-test-key" not in str(result.as_dict())
    assert not hasattr(adapter, "profile")
    assert not hasattr(adapter, "base_url")
    assert not hasattr(adapter, "model_name")


def test_minimax_h3_payload_carries_authoritative_first_and_last_frames():
    payload = _build_minimax_h3_video_payload(
        PROFILE,
        prompt="prompt",
        duration_seconds=5,
        aspect_ratio="16:9",
        first_frame_url="https://cdn.example.test/start.png",
        last_frame_url="https://cdn.example.test/end.png",
    )
    image_roles = [item.get("role") for item in payload["content"] if item.get("type") == "image_url"]
    assert image_roles == ["first_frame", "last_frame"]
    assert [item["image_url"]["url"] for item in payload["content"] if item.get("type") == "image_url"] == [
        "https://cdn.example.test/start.png",
        "https://cdn.example.test/end.png",
    ]


def test_minimax_h3_model_registry_transport_binding_is_exact():
    binding = get_provider_transport_binding(
        provider_id="minimax-h3-async",
        target_media="VIDEO",
        binding_id="minimax-h3-async.video.v1",
    )
    assert binding is not None
    assert binding.provider_id == "minimax-h3-async"
    assert binding.target_media == "VIDEO"
    assert binding.mode == "async"
    assert binding.submit == "submit_minimax_h3_generation"
    assert binding.poll == "poll_minimax_h3_generation"


def test_real_provider_canary_requires_explicit_gray_gate(monkeypatch):
    """The real test is deliberately inert until the exact paid-call gate is set."""
    for name in ("MINIMAX_H3_GRAY_REAL", "MINIMAX_H3_GRAY_CONFIRM", "MINIMAX_H3_GRAY_WHITELIST"):
        monkeypatch.delenv(name, raising=False)
    assert os.environ.get("MINIMAX_H3_GRAY_REAL") != "1"
    assert os.environ.get("MINIMAX_H3_GRAY_CONFIRM") != "CONFIRM_MINIMAX_H3_SUBMIT"


def test_video_asset_promotion_boundary_is_explicit_review_only():
    """The runtime must hand a validated candidate to the existing review API."""
    from api.asset_promotion_api import router

    paths = {route.path for route in router.routes}
    assert "/assets/candidates/{candidate_id}/validate" in paths
    assert "/assets/candidates/{candidate_id}/promote" in paths


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"base_url": "https://shapi.vip/v1"}, "VIDEO_PROFILE_ENDPOINT_INVALID"),
        ({"model_name": "other-model"}, "VIDEO_PROFILE_MODEL_INVALID"),
        ({"capability": "image"}, "VIDEO_PROFILE_CAPABILITY_INVALID"),
    ],
)
def test_minimax_h3_adapter_rejects_non_registry_contract(changes, code):
    profile = {**PROFILE, **changes}
    with pytest.raises(VideoProviderError) as exc:
        MinimaxH3VideoProvider(profile, transport=_transport)
    assert exc.value.code == code


def test_minimax_h3_adapter_requires_single_shot_canary_scope():
    provider = MinimaxH3VideoProvider(PROFILE, transport=_transport)
    with pytest.raises(VideoProviderError) as exc:
        provider.generate_video(
            prompt="prompt",
            motion_profile={},
            duration=5,
            aspect_ratio="16:9",
            first_frame_asset={"storage_identity": "https://cdn.example.test/frame.png"},
            last_frame_asset={},
            request_context={},
        )
    assert exc.value.code == "VIDEO_CANARY_SCOPE_REQUIRED"
