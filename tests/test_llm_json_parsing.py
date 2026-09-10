import unittest
from unittest.mock import Mock, patch

from core.llm import call_llm, call_llm_json


class LLMJsonParsingTests(unittest.TestCase):
    def test_parses_balanced_json_object_from_wrapped_response(self):
        raw = (
            "好的，结果如下：\n"
            "```json\n"
            "{\"note\": {\"nested\": true}, \"visual_prompt_static\": \"便利店首帧\"}\n"
            "```\n"
            "请查收。"
        )
        with patch("core.llm.call_llm", return_value=raw):
            payload = call_llm_json("prompt", required_keys={"visual_prompt_static"})

        self.assertEqual(payload["visual_prompt_static"], "便利店首帧")
        self.assertEqual(payload["note"]["nested"], True)

    def test_retries_once_when_first_response_is_not_json(self):
        with patch("core.llm.call_llm", side_effect=["不是 JSON", "{\"ok\": true}"]) as mocked:
            payload = call_llm_json("prompt", json_parse_retries=1)

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(mocked.call_count, 2)

    def test_supports_json_response_format_flag(self):
        with patch.dict("os.environ", {"LLM_JSON_RESPONSE_FORMAT": "1"}), patch(
            "core.llm.call_llm",
            return_value="{\"ok\": true}",
        ) as mocked:
            payload = call_llm_json("prompt")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(mocked.call_args.kwargs["response_format"], {"type": "json_object"})

    def test_passes_model_profile_thinking_param_to_chat_completions(self):
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 3},
        }

        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=None)
        client.post.return_value = response

        with patch("core.llm.httpx.Client", return_value=client), patch("core.llm._limiter.wait_if_needed"), patch("core.llm._limiter.record"):
            result = call_llm(
                "prompt",
                retries=1,
                model_profile={
                    "api_key": "unit-test-key",
                    "base_url": "https://example.invalid/v1",
                    "model_name": "mimo-v2.5",
                    "default_params": {
                        "temperature": 0.2,
                        "max_tokens": 2048,
                        "thinking": {"type": "disabled"},
                    },
                },
            )

        self.assertEqual(result, "ok")
        request_payload = client.post.call_args.kwargs["json"]
        self.assertEqual(request_payload["thinking"], {"type": "disabled"})
        self.assertEqual(request_payload["temperature"], 0.2)
        self.assertEqual(request_payload["max_tokens"], 2048)

    def test_zero_retry_budget_still_makes_exactly_one_provider_call(self):
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 3},
        }
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=None)
        client.post.return_value = response

        with patch("core.llm.httpx.Client", return_value=client), patch("core.llm._limiter.wait_if_needed"), patch("core.llm._limiter.record"):
            result = call_llm("prompt", retries=0)

        self.assertEqual(result, "ok")
        self.assertEqual(client.post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
