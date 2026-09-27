"""MiniMax H3 video provider canary contracts (network-free)."""

import pytest

from core.video_provider_adapter import MinimaxH3VideoProvider, VideoProviderError


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
        return {
            "externalTaskId": "task-canary-1",
            "providerTaskId": "task-canary-1",
            "providerRequestId": "task-canary-1",
            "providerRequestPayload": {
                "model": profile["model_name"],
                "content": [{"type": "text", "text": kwargs["prompt"]}],
                "resolution": "768P",
            },
            "providerResponse": {"status": "succeeded", "duration": 5, "seed": 7},
            "previewUrl": "https://cdn.example.test/canary.mp4",
            "uri": "https://cdn.example.test/canary.mp4",
        }

    return run()


def test_minimax_h3_adapter_binds_registry_profile_and_records_response():
    result = MinimaxH3VideoProvider(PROFILE, transport=_transport).generate_video(
        prompt="A traveler faces the tunnel.",
        motion_profile={"camera_motion": "slow_push_in", "subject_motion": "head_turn"},
        duration=5,
        aspect_ratio="16:9",
        first_frame_asset={"keyframe_id": 1, "storage_identity": "https://cdn.example.test/frame.png"},
        last_frame_asset={},
        request_context={"canary_scope": "episode:1:shot:1"},
    )
    assert result.provider == "minimax-h3-async"
    assert result.model == "MiniMax-H3"
    assert result.provider_task_id == "task-canary-1"
    assert result.provider_response["video_url"].endswith("canary.mp4")
    assert result.provider_response["created_time"]
    assert result.provider_request["motion_profile"]["camera_motion"] == "slow_push_in"
    assert "api_key" not in str(result.as_dict())
    assert "secret-test-key" not in str(result.as_dict())


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
