import base64
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from api.generation_adapters import (
    ModelProfileError,
    generate_image_asset,
    generate_video_asset,
    reconcile_75api_minimax_h3_generation,
    reconcile_minimax_h3_generation,
    reconcile_poyo_generation,
)


class GenerationAdaptersTests(unittest.IsolatedAsyncioTestCase):
    async def test_shapi_openai_images_uses_allowlisted_payload_and_maps_size(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"b64_json": "ZmFrZS1pbWFnZQ=="}]}
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_image_asset(
                {
                    "provider": "shapi-openai-images",
                    "base_url": "https://shapi.vip/v1",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                    "default_params": {
                        "size": "auto",
                        "quality": "high",
                        "response_format": "b64_json",
                        "size_by_aspect_ratio": {"16:9": "1536x1024"},
                        "supports_reference_images": False,
                    },
                },
                prompt="镜头提示词",
                aspect_ratio="16:9",
                negative_prompt="extra fingers",
            )

        payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(mock_client.post.await_args.args[0], "https://shapi.vip/v1/images/generations")
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["n"], 1)
        self.assertEqual(payload["size"], "1536x1024")
        self.assertNotIn("size_by_aspect_ratio", payload)
        self.assertNotIn("supports_reference_images", payload)
        self.assertIn("Negative constraints", payload["prompt"])
        self.assertTrue(result["previewUrl"].startswith("data:image/png;base64,"))

    async def test_shapi_openai_images_rejects_reference_images_instead_of_dropping_them(self):
        with self.assertRaises(ModelProfileError) as ctx:
            await generate_image_asset(
                {
                    "provider": "shapi-openai-images",
                    "base_url": "https://shapi.vip/v1",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                },
                prompt="镜头提示词",
                aspect_ratio="16:9",
                reference_images=[{"image_url": "https://cdn.example.com/ref.png"}],
            )
        self.assertIn("拒绝忽略参考图", str(ctx.exception))

    async def test_shapi_gemini_image_inlines_data_uri_references_and_redacts_audit_payload(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"inlineData": {"mimeType": "image/jpeg", "data": "Z2VuZXJhdGVk"}, "thoughtSignature": "transport-only-signature"}]
                    }
                }
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        source_bytes = b"reference-image"
        data_uri = f"data:image/png;base64,{base64.b64encode(source_bytes).decode('ascii')}"

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_image_asset(
                {
                    "provider": "shapi-gemini-image",
                    "base_url": "https://shapi.vip",
                    "model_name": "nano-banana-2",
                    "api_key": "secret-test-key",
                    "default_params": {"aspect_ratio": "16:9", "image_size": "2K", "max_reference_images": 14},
                },
                prompt="镜头提示词",
                aspect_ratio="9:16",
                reference_images=[
                    {
                        "image_url": data_uri,
                        "referenceName": "林晚",
                        "referencePurpose": "identity_costume_face_hair",
                        "role": "character",
                    }
                ],
            )

        payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(mock_client.post.await_args.args[0], "https://shapi.vip/v1beta/models/nano-banana-2:generateContent")
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["IMAGE"])
        self.assertEqual(payload["generationConfig"]["imageConfig"], {"aspectRatio": "9:16", "imageSize": "2K"})
        self.assertIn("林晚", payload["contents"][0]["parts"][1]["text"])
        self.assertIn("identity_costume_face_hair", payload["contents"][0]["parts"][1]["text"])
        self.assertIn("已确认的视觉事实", payload["contents"][0]["parts"][1]["text"])
        self.assertEqual(payload["contents"][0]["parts"][2]["inlineData"]["data"], base64.b64encode(source_bytes).decode("ascii"))
        self.assertIn("redacted base64", result["providerRequestPayload"]["contents"][0]["parts"][2]["inlineData"]["data"])
        self.assertIn("redacted base64", result["providerResponse"]["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        self.assertIn("redacted thought signature", result["providerResponse"]["candidates"][0]["content"]["parts"][0]["thoughtSignature"])
        self.assertTrue(result["previewUrl"].startswith("data:image/jpeg;base64,"))

    async def test_openai_compatible_image_success_returns_preview(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {
                    "b64_json": "ZmFrZS1pbWFnZQ==",
                    "revised_prompt": "镜头提示词 [provider]",
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_image_asset(
                {
                    "provider": "openai-compatible",
                    "base_url": "http://127.0.0.1:8891/v1",
                    "model_name": "fake-image-model",
                    "api_key": "secret-test-key",
                    "default_params": {"size": "1024x1024"},
                },
                prompt="镜头提示词",
                aspect_ratio="16:9",
            )

        self.assertTrue(result["previewUrl"].startswith("data:image/png;base64,"))
        self.assertEqual(result["revisedPrompt"], "镜头提示词 [provider]")

    async def test_openai_compatible_image_maps_auth_failure(self):
        request = httpx.Request("POST", "http://127.0.0.1:8891/v1/images/generations")
        response = httpx.Response(401, request=request)

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("auth", request=request, response=response)

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            with self.assertRaises(ModelProfileError) as ctx:
                await generate_image_asset(
                    {
                        "provider": "openai-compatible",
                        "base_url": "http://127.0.0.1:8891/v1",
                        "model_name": "fake-image-model",
                        "api_key": "bad-key",
                    },
                    prompt="镜头提示词",
                    aspect_ratio="16:9",
                )

        self.assertIn("认证未通过", str(ctx.exception))


    async def test_poyo_image_submit_and_poll_returns_file_url(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-poyo-1"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "finished",
            "files": [{"file_url": "https://cdn.example.com/poyo-image.png"}],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_image_asset(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                    "default_params": {
                        "task_modes": ["text_to_image", "image_to_image"],
                        "supports_reference_images": True,
                        "max_reference_images": 2,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="镜头提示词",
                aspect_ratio="16:9",
                reference_images=[{"image_url": "https://cdn.example.com/ref-a.png"}],
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(result["externalTaskId"], "task-poyo-1")
        self.assertEqual(result["previewUrl"], "https://cdn.example.com/poyo-image.png")
        self.assertEqual(result["externalStatus"], "finished")
        self.assertEqual(result["providerRequestPayload"], submit_payload)
        self.assertEqual(submit_payload["model"], "gpt-image-2")
        self.assertEqual(submit_payload["input"]["task_mode"], "image_to_image")
        self.assertNotIn("aspect_ratio", submit_payload["input"])
        self.assertEqual(submit_payload["input"]["size"], "16:9")
        self.assertEqual(submit_payload["input"]["resolution"], "2K")
        self.assertEqual(submit_payload["input"]["reference_image_urls"], ["https://cdn.example.com/ref-a.png"])

    async def test_poyo_image_poll_accepts_nested_image_url_shapes(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-poyo-2"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "finished",
            "data": {
                "images": [{"image_url": "https://cdn.example.com/poyo-image-nested.png"}]
            },
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_image_asset(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                    "default_params": {
                        "task_modes": ["text_to_image"],
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="nested poyo image prompt",
                aspect_ratio="1:1",
            )

        self.assertEqual(result["previewUrl"], "https://cdn.example.com/poyo-image-nested.png")

    async def test_poyo_image_submit_accepts_nested_id_response_shape(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"code": 200, "data": {"id": "task-poyo-nested-id"}}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "finished",
            "files": [{"file_url": "https://cdn.example.com/poyo-nested-id.png"}],
        }
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_image_asset(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                    "default_params": {"poll_interval_seconds": 1, "poll_timeout_seconds": 5},
                },
                prompt="镜头提示词",
                aspect_ratio="16:9",
            )

        self.assertEqual(result["externalTaskId"], "task-poyo-nested-id")

    async def test_poyo_image_submit_without_task_id_keeps_response_for_audit(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"code": 400, "data": {"error": "unsupported reference image mode"}}
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            with self.assertRaises(ModelProfileError) as ctx:
                await generate_image_asset(
                    {
                        "provider": "poyo-async",
                        "base_url": "https://api.poyo.ai",
                        "model_name": "gpt-image-2",
                        "api_key": "secret-test-key",
                    },
                    prompt="镜头提示词",
                    aspect_ratio="16:9",
                )

        self.assertIn("unsupported reference image mode", str(ctx.exception))
        self.assertEqual(ctx.exception.provider_response["code"], 400)
        self.assertEqual(ctx.exception.provider_request_payload["model"], "gpt-image-2")

    async def test_poyo_video_uses_first_frame_and_reference_images(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-poyo-video-1"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "finished",
            "files": [{"file_url": "https://cdn.example.com/poyo-video.mp4"}],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_video_asset(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "seedance-2",
                    "api_key": "secret-test-key",
                    "default_params": {
                        "task_modes": ["image_to_video", "text_to_video"],
                        "supports_reference_images": True,
                        "max_reference_images": 4,
                        "supports_first_frame": True,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="视频提示词",
                duration_seconds=5,
                aspect_ratio="16:9",
                first_frame_url="https://cdn.example.com/first-frame.png",
                reference_images=[
                    {"image_url": "https://cdn.example.com/ref-b.png"},
                    {"image_url": "https://cdn.example.com/ref-c.png"},
                ],
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(result["externalTaskId"], "task-poyo-video-1")
        self.assertEqual(result["uri"], "https://cdn.example.com/poyo-video.mp4")
        self.assertEqual(result["providerRequestPayload"], submit_payload)
        self.assertEqual(submit_payload["model"], "seedance-2")
        self.assertEqual(submit_payload["input"]["task_mode"], "image_to_video")
        self.assertEqual(submit_payload["input"]["duration"], 5)
        self.assertEqual(submit_payload["input"]["aspect_ratio"], "16:9")
        self.assertEqual(submit_payload["input"]["first_frame"], "https://cdn.example.com/first-frame.png")
        self.assertEqual(
            submit_payload["input"]["reference_image_urls"],
            [
                "https://cdn.example.com/ref-b.png",
                "https://cdn.example.com/ref-c.png",
            ],
        )

    async def test_minimax_h3_text_to_video_payload_uses_ratio(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-h3-text-1"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "task": {"content": {"url": "https://cdn.example.com/h3-text.mp4"}},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                    "default_params": {
                        "resolution": "2K",
                        "duration": 5,
                        "ratio": "16:9",
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="H3 视频提示词",
                duration_seconds=6,
                aspect_ratio="9:16",
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(result["externalTaskId"], "task-h3-text-1")
        self.assertEqual(result["previewUrl"], "https://cdn.example.com/h3-text.mp4")
        self.assertEqual(result["taskMode"], "text_to_video")
        self.assertEqual(result["providerRequestPayload"], submit_payload)
        self.assertEqual(submit_payload["model"], "MiniMax-H3")
        self.assertEqual(submit_payload["content"], [{"type": "text", "text": "H3 视频提示词"}])
        self.assertEqual(submit_payload["duration"], 6)
        self.assertEqual(submit_payload["resolution"], "2K")
        self.assertEqual(submit_payload["ratio"], "9:16")

    async def test_minimax_h3_defaults_to_768p_when_resolution_is_not_configured(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-h3-default-resolution"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "task": {"content": {"url": "https://cdn.example.com/h3-default-resolution.mp4"}},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                    "default_params": {
                        "duration": 5,
                        "ratio": "16:9",
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="H3 默认 768P 视频提示词",
                duration_seconds=5,
                aspect_ratio="16:9",
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        submit_url = mock_client.post.await_args.args[0]
        self.assertEqual(result["externalTaskId"], "task-h3-default-resolution")
        self.assertEqual(submit_url, "https://metaso.cn/api/minimax/v2/video_generation")
        self.assertEqual(submit_payload["resolution"], "768P")
        self.assertNotIn("aigc_watermark", submit_payload)

    async def test_minimax_h3_sends_aigc_watermark_only_when_enabled(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-h3-watermark"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "task": {"content": {"url": "https://cdn.example.com/h3-watermark.mp4"}},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                    "default_params": {
                        "resolution": "768P",
                        "duration": 5,
                        "ratio": "16:9",
                        "aigc_watermark": True,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="H3 水印视频提示词",
                duration_seconds=5,
                aspect_ratio="16:9",
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(submit_payload["aigc_watermark"], True)

    async def test_minimax_h3_first_frame_payload_omits_ratio(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-h3-frame-1"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "content": {"url": "https://cdn.example.com/h3-frame.mp4"},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                    "default_params": {
                        "resolution": "768P",
                        "duration": 5,
                        "ratio": "16:9",
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="H3 首帧视频提示词",
                duration_seconds=5,
                aspect_ratio="16:9",
                first_frame_url="https://cdn.example.com/first-frame.png",
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(result["taskMode"], "image_to_video")
        self.assertNotIn("ratio", submit_payload)
        self.assertEqual(submit_payload["resolution"], "768P")
        self.assertEqual(submit_payload["content"][1], {
            "type": "image_url",
            "image_url": {"url": "https://cdn.example.com/first-frame.png"},
            "role": "first_frame",
        })

    async def test_minimax_h3_reference_images_are_sent_in_reference_mode(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-h3-reference-1"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "content": {"url": "https://cdn.example.com/h3-reference.mp4"},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        references = [
            {"image_url": f"https://cdn.example.com/ref-{index}.png"}
            for index in range(1, 12)
        ]

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                    "default_params": {
                        "resolution": "768P",
                        "duration": 5,
                        "ratio": "16:9",
                        "max_reference_images": 9,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="H3 多参考视频提示词",
                duration_seconds=5,
                aspect_ratio="16:9",
                reference_images=references,
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        image_items = [item for item in submit_payload["content"] if item.get("type") == "image_url"]
        self.assertEqual(result["taskMode"], "reference_to_video")
        self.assertEqual(len(image_items), 9)
        self.assertEqual({item["role"] for item in image_items}, {"reference_image"})
        self.assertEqual(image_items[0]["image_url"]["url"], "https://cdn.example.com/ref-1.png")
        self.assertEqual(image_items[-1]["image_url"]["url"], "https://cdn.example.com/ref-9.png")
        self.assertEqual(submit_payload["ratio"], "16:9")

    async def test_minimax_h3_zero_max_reference_images_uses_provider_default_multi_reference_limit(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"task_id": "task-h3-reference-zero-max"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "content": {"url": "https://cdn.example.com/h3-reference.mp4"},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        references = [
            {"image_url": f"https://cdn.example.com/ref-{index}.png"}
            for index in range(1, 4)
        ]

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                    "default_params": {
                        "resolution": "768P",
                        "duration": 5,
                        "ratio": "16:9",
                        "max_reference_images": 0,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 5,
                    },
                },
                prompt="H3 多参考视频提示词",
                duration_seconds=4,
                aspect_ratio="16:9",
                reference_images=references,
            )

        submit_payload = mock_client.post.await_args.kwargs["json"]
        image_items = [item for item in submit_payload["content"] if item.get("type") == "image_url"]
        self.assertEqual(len(image_items), 3)
        self.assertEqual(submit_payload["duration"], 4)
        self.assertEqual(image_items[-1]["image_url"]["url"], "https://cdn.example.com/ref-3.png")

    async def test_minimax_h3_rejects_mixed_reference_and_first_frame_modes(self):
        with self.assertRaises(ModelProfileError) as ctx:
            await generate_video_asset(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                },
                prompt="H3 mixed-input mode must be rejected",
                duration_seconds=5,
                aspect_ratio="16:9",
                first_frame_url="https://cdn.example.com/first-frame.png",
                reference_images=[{"image_url": "https://cdn.example.com/ref-1.png"}],
            )
        self.assertIn("互斥", str(ctx.exception))

    async def test_75api_minimax_h3_uses_image_conditioned_wire_contract(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"id": "75-task-1"}

        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "completed",
            "video_url": "https://cdn.example.com/75-task-1.mp4",
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = submit_response
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await generate_video_asset(
                {
                    "provider": "75api-minimax-h3",
                    "base_url": "https://www.75api.com",
                    "model_name": "minimax_h3_no_audios",
                    "api_key": "75-secret-test-key",
                    "default_params": {
                        "resolution": "768p",
                        "max_reference_images": 8,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 10,
                    },
                },
                prompt="75api H3 多参考视频提示词",
                duration_seconds=6,
                aspect_ratio="9:16",
                reference_images=[
                    {"image_url": "https://cdn.example.com/ref-1.png"},
                    {"image_url": "https://cdn.example.com/ref-2.png"},
                ],
            )

        submit_url = mock_client.post.await_args.args[0]
        submit_payload = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(submit_url, "https://www.75api.com/v1/videos")
        self.assertEqual(result["externalTaskId"], "75-task-1")
        self.assertEqual(result["taskMode"], "reference_to_video")
        self.assertEqual(result["previewUrl"], "https://cdn.example.com/75-task-1.mp4")
        self.assertEqual(submit_payload, {
            "model": "minimax_h3_no_audios",
            "prompt": "75api H3 多参考视频提示词",
            "seconds": "6",
            "aspect_ratio": "9:16",
            "resolution": "768p",
            "images": [
                "https://cdn.example.com/ref-1.png",
                "https://cdn.example.com/ref-2.png",
            ],
        })
        self.assertNotIn("audios", submit_payload)

    async def test_75api_minimax_h3_rejects_text_only_and_out_of_range_duration(self):
        profile = {
            "provider": "75api-minimax-h3",
            "base_url": "https://www.75api.com",
            "model_name": "minimax_h3_no_audios",
            "api_key": "75-secret-test-key",
        }
        with self.assertRaises(ModelProfileError) as text_ctx:
            await generate_video_asset(profile, prompt="text-only", duration_seconds=5, aspect_ratio="16:9")
        self.assertIn("不支持文生视频", str(text_ctx.exception))

        with self.assertRaises(ModelProfileError) as duration_ctx:
            await generate_video_asset(
                profile,
                prompt="too short",
                duration_seconds=4,
                aspect_ratio="16:9",
                first_frame_url="https://cdn.example.com/first.png",
            )
        self.assertIn("5–15 秒", str(duration_ctx.exception))

    async def test_reconcile_75api_minimax_h3_falls_back_to_authenticated_content_url(self):
        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {"status": "completed", "id": "75-task-content"}
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await reconcile_75api_minimax_h3_generation(
                {
                    "provider": "75api-minimax-h3",
                    "base_url": "https://www.75api.com",
                    "model_name": "minimax_h3_no_audios",
                    "api_key": "75-secret-test-key",
                },
                external_task_id="75-task-content",
            )

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["previewUrl"], "https://www.75api.com/v1/videos/75-task-content/content")
        self.assertTrue(result["providerContentRequiresAuth"])

    async def test_reconcile_poyo_generation_recovers_finished_result(self):
        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "finished",
            "result": {"images": [{"imageUrl": "https://cdn.example.com/poyo-recovered.png"}]},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await reconcile_poyo_generation(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                },
                external_task_id="task-poyo-recover-1",
            )

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["externalTaskId"], "task-poyo-recover-1")
        self.assertEqual(result["previewUrl"], "https://cdn.example.com/poyo-recovered.png")

    async def test_reconcile_minimax_h3_generation_recovers_finished_result(self):
        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "succeeded",
            "task": {"content": {"url": "https://cdn.example.com/h3-recovered.mp4"}},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await reconcile_minimax_h3_generation(
                {
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "api_key": "mk-secret-test-key",
                },
                external_task_id="task-h3-recover-1",
            )

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["externalStatus"], "succeeded")
        self.assertEqual(result["previewUrl"], "https://cdn.example.com/h3-recovered.mp4")

    async def test_reconcile_minimax_h3_generation_treats_fail_and_expired_as_failed(self):
        for provider_status in ("fail", "expired"):
            with self.subTest(provider_status=provider_status):
                status_response = Mock()
                status_response.raise_for_status.return_value = None
                status_response.json.return_value = {
                    "task": {
                        "status": provider_status,
                        "error": {"message": f"{provider_status} from metaso"},
                    },
                }

                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.get.return_value = status_response

                with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
                    with self.assertRaises(ModelProfileError) as ctx:
                        await reconcile_minimax_h3_generation(
                            {
                                "provider": "minimax-h3-async",
                                "base_url": "https://metaso.cn/api/minimax",
                                "model_name": "MiniMax-H3",
                                "api_key": "mk-secret-test-key",
                            },
                            external_task_id=f"task-h3-{provider_status}",
                        )

                self.assertIn(f"{provider_status} from metaso", str(ctx.exception))
                self.assertEqual(ctx.exception.external_status, provider_status)

    async def test_reconcile_poyo_generation_reports_running_state(self):
        status_response = Mock()
        status_response.raise_for_status.return_value = None
        status_response.json.return_value = {
            "status": "running",
            "progress": 92,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = status_response

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await reconcile_poyo_generation(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                },
                external_task_id="task-poyo-recover-2",
            )

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["externalStatus"], "running")

    async def test_reconcile_poyo_generation_retries_after_rate_limit(self):
        rate_limited = Mock()
        rate_limited.status_code = 429
        rate_limited.json.return_value = {"detail": "rate limited"}
        rate_limit_error = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=httpx.Request("GET", "https://api.poyo.ai/api/generate/status/task-poyo-recover-3"),
            response=rate_limited,
        )

        success_response = Mock()
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {
            "status": "finished",
            "result": {"images": [{"imageUrl": "https://cdn.example.com/poyo-after-retry.png"}]},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.side_effect = [rate_limit_error, success_response]

        with patch("api.generation_adapters.httpx.AsyncClient", return_value=mock_client):
            result = await reconcile_poyo_generation(
                {
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "gpt-image-2",
                    "api_key": "secret-test-key",
                },
                external_task_id="task-poyo-recover-3",
            )

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["previewUrl"], "https://cdn.example.com/poyo-after-retry.png")


if __name__ == "__main__":
    unittest.main()
