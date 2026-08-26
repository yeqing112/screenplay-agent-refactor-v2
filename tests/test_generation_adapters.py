import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from api.generation_adapters import ModelProfileError, generate_image_asset, generate_video_asset, reconcile_poyo_generation


class GenerationAdaptersTests(unittest.IsolatedAsyncioTestCase):
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
