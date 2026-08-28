import unittest
from unittest.mock import AsyncMock, Mock, patch

from api.model_registry import (
    MODEL_REGISTRY_DEFAULTS_KEY,
    MODEL_REGISTRY_PROFILES_KEY,
    get_default_profile,
    resolve_defaults,
    save_registry,
    serialize_registry_payload,
    test_profile_connection,
)
from models import get_kv, init_db, set_kv


class ModelRegistryTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self._original_profiles = get_kv(MODEL_REGISTRY_PROFILES_KEY, "[]")
        self._original_defaults = get_kv(MODEL_REGISTRY_DEFAULTS_KEY, "{}")
        set_kv(MODEL_REGISTRY_PROFILES_KEY, "[]")
        set_kv(MODEL_REGISTRY_DEFAULTS_KEY, "{}")

    def tearDown(self):
        set_kv(MODEL_REGISTRY_PROFILES_KEY, self._original_profiles)
        set_kv(MODEL_REGISTRY_DEFAULTS_KEY, self._original_defaults)

    def test_builtin_defaults_include_embedding_image_and_video(self):
        payload = serialize_registry_payload()
        self.assertIn("embedding", payload["defaults"])
        self.assertIn("image", payload["defaults"])
        self.assertIn("video", payload["defaults"])
        self.assertEqual(payload["default_profiles"]["embedding"]["provider"], "ollama")
        self.assertEqual(payload["default_profiles"]["image"]["provider"], "prototype-task-adapter")
        self.assertEqual(payload["default_profiles"]["video"]["provider"], "prototype-task-adapter")

    def test_save_registry_persists_custom_image_default(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "image-real-1",
                    "name": "Real Image 1",
                    "capability": "image",
                    "provider": "openai-compatible",
                    "base_url": "https://example.invalid/v1",
                    "model_name": "gpt-image-1",
                    "default_params": {"size": "1024x1024"},
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"image": "image-real-1"},
        )
        self.assertEqual(payload["defaults"]["image"], "image-real-1")
        self.assertEqual(get_default_profile("image")["id"], "image-real-1")
        saved_profile = next(item for item in payload["profiles"] if item["id"] == "image-real-1")
        self.assertTrue(saved_profile["key_configured"])
        self.assertNotIn("api_key", saved_profile)

    def test_save_registry_preserves_llm_thinking_default_param(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "llm-mimo-1",
                    "name": "Mimo 2.5",
                    "capability": "llm",
                    "provider": "openai-compatible",
                    "base_url": "https://api.xiaomimimo.com/v1",
                    "model_name": "mimo-v2.5",
                    "default_params": {
                        "temperature": 0.3,
                        "max_tokens": 8192,
                        "thinking": {"type": "disabled"},
                    },
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"llm": "llm-mimo-1"},
        )

        saved_profile = get_default_profile("llm")
        self.assertEqual(saved_profile["default_params"]["thinking"], {"type": "disabled"})
        serialized = next(item for item in payload["profiles"] if item["id"] == "llm-mimo-1")
        self.assertEqual(serialized["default_params"]["thinking"], {"type": "disabled"})
        self.assertNotIn("api_key", serialized)

    def test_save_registry_preserves_existing_api_key_when_frontend_omits_it(self):
        save_registry(
            profiles=[
                {
                    "id": "image-real-1",
                    "name": "Real Image 1",
                    "capability": "image",
                    "provider": "openai-compatible",
                    "base_url": "https://example.invalid/v1",
                    "model_name": "gpt-image-1",
                    "default_params": {"size": "1024x1024"},
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"image": "image-real-1"},
        )

        payload = save_registry(
            profiles=[
                {
                    "id": "image-real-1",
                    "name": "Real Image 1 Updated",
                    "capability": "image",
                    "provider": "openai-compatible",
                    "base_url": "https://example.invalid/v1",
                    "model_name": "gpt-image-1",
                    "default_params": {"size": "1024x1024"},
                    "enabled": True,
                    "api_key": "",
                }
            ],
            defaults={"image": "image-real-1"},
        )
        saved_profile = get_default_profile("image")
        self.assertEqual(saved_profile["api_key"], "secret-test-key")
        serialized = next(item for item in payload["profiles"] if item["id"] == "image-real-1")
        self.assertTrue(serialized["key_configured"])

    def test_save_registry_persists_custom_embedding_default(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "embedding-ollama-1",
                    "name": "Ollama Embedding 1",
                    "capability": "embedding",
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434",
                    "model_name": "bge-m3",
                    "default_params": {"dimension": 1024},
                    "enabled": True,
                }
            ],
            defaults={"embedding": "embedding-ollama-1"},
        )
        self.assertEqual(payload["defaults"]["embedding"], "embedding-ollama-1")
        self.assertEqual(get_default_profile("embedding")["id"], "embedding-ollama-1")

    def test_save_registry_rejects_real_video_as_default_until_adapter_ready(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "video-real-1",
                    "name": "Real Video 1",
                    "capability": "video",
                    "provider": "openai-compatible",
                    "base_url": "https://example.invalid/v1",
                    "model_name": "video-x",
                    "default_params": {"duration_seconds": 5},
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"video": "video-real-1"},
        )
        self.assertEqual(payload["defaults"]["video"], "builtin-mock-video")
        self.assertEqual(get_default_profile("video")["id"], "builtin-mock-video")
        saved_profile = next(item for item in payload["profiles"] if item["id"] == "video-real-1")
        self.assertFalse(saved_profile["is_default"])

    def test_save_registry_allows_poyo_video_as_default(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "video-poyo-1",
                    "name": "PoYo Video 1",
                    "capability": "video",
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "seedance-2",
                    "default_params": {"duration": 5, "supports_first_frame": True},
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"video": "video-poyo-1"},
        )
        self.assertEqual(payload["defaults"]["video"], "video-poyo-1")
        self.assertEqual(get_default_profile("video")["id"], "video-poyo-1")

    def test_save_registry_allows_minimax_h3_video_as_default(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "video-minimax-h3-1",
                    "name": "MiniMax H3",
                    "capability": "video",
                    "provider": "minimax-h3-async",
                    "base_url": "https://metaso.cn/api/minimax",
                    "model_name": "MiniMax-H3",
                    "default_params": {"duration": 5, "resolution": "768P", "ratio": "16:9", "aigc_watermark": False},
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"video": "video-minimax-h3-1"},
        )
        self.assertEqual(payload["defaults"]["video"], "video-minimax-h3-1")
        self.assertEqual(get_default_profile("video")["id"], "video-minimax-h3-1")

    def test_save_registry_allows_poyo_image_as_default(self):
        payload = save_registry(
            profiles=[
                {
                    "id": "image-poyo-1",
                    "name": "PoYo Image 1",
                    "capability": "image",
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "seedream-5.0-lite",
                    "default_params": {"task_modes": ["text_to_image", "image_to_image"]},
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"image": "image-poyo-1"},
        )
        self.assertEqual(payload["defaults"]["image"], "image-poyo-1")
        self.assertEqual(get_default_profile("image")["id"], "image-poyo-1")

    async def test_mock_profile_test_endpoint_returns_ok(self):
        result = await test_profile_connection(profile_id="builtin-mock-image")
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["provider"], "prototype-task-adapter")

    async def test_embedding_profile_test_returns_dimension(self):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3, 0.4]]}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("api.model_registry.httpx.AsyncClient", return_value=mock_client):
            result = await test_profile_connection(
                profile_payload={
                    "name": "Embed Test",
                    "capability": "embedding",
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434",
                    "model_name": "nomic-embed-text",
                }
            )

        self.assertTrue(result["ok"])
        self.assertIn("4 维向量", result["message"])
        self.assertEqual(result["profile"]["default_params"]["dimension"], 4)

    async def test_real_video_profile_test_returns_blocked_message(self):
        result = await test_profile_connection(
            profile_payload={
                "name": "Video Blocked",
                "capability": "video",
                "provider": "openai-compatible",
                "base_url": "https://example.invalid/v1",
                "model_name": "video-x",
                "api_key": "secret-test-key",
            }
        )
        self.assertFalse(result["ok"])
        self.assertIn("尚未接入", result["message"])

    async def test_poyo_profile_test_returns_validation_only_message(self):
        result = await test_profile_connection(
            profile_payload={
                "name": "PoYo Image",
                "capability": "image",
                "provider": "poyo-async",
                "base_url": "https://api.poyo.ai",
                "model_name": "gpt-image-2",
                "api_key": "secret-test-key",
                "default_params": {"task_modes": ["text_to_image"]},
            }
        )
        self.assertTrue(result["ok"])
        self.assertIn("扣费任务", result["message"])

    async def test_minimax_h3_profile_test_returns_validation_only_message(self):
        result = await test_profile_connection(
            profile_payload={
                "name": "MiniMax H3",
                "capability": "video",
                "provider": "minimax-h3-async",
                "base_url": "https://metaso.cn/api/minimax",
                "model_name": "MiniMax-H3",
                "api_key": "secret-test-key",
                "default_params": {"duration": 5, "resolution": "768P", "ratio": "16:9", "aigc_watermark": False},
            }
        )
        self.assertTrue(result["ok"])
        self.assertIn("MiniMax H3", result["message"])
        self.assertIn("不会发起真实扣费", result["message"])

    async def test_profile_test_falls_back_to_payload_when_profile_id_is_missing(self):
        result = await test_profile_connection(
            profile_id="missing-poyo-profile",
            profile_payload={
                "id": "missing-poyo-profile",
                "name": "PoYo Image Draft",
                "capability": "image",
                "provider": "poyo-async",
                "base_url": "https://api.poyo.ai",
                "model_name": "gpt-image-2",
                "default_params": {"task_modes": ["text_to_image"]},
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["provider"], "poyo-async")
        self.assertEqual(result["profile"]["model_name"], "gpt-image-2")

    def test_resolve_defaults_falls_back_to_builtin_when_saved_default_missing_or_disabled(self):
        save_registry(
            profiles=[
                {
                    "id": "video-disabled",
                    "name": "Disabled Video",
                    "capability": "video",
                    "provider": "openai-compatible",
                    "base_url": "https://example.invalid/v1",
                    "model_name": "video-x",
                    "enabled": False,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"video": "video-disabled"},
        )
        defaults = resolve_defaults()
        self.assertEqual(defaults["video"], "builtin-mock-video")


if __name__ == "__main__":
    unittest.main()
