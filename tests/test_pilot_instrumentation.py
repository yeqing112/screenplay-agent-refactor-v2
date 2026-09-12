from unittest.mock import patch

import httpx

from core.llm import call_llm
from core.pilot_instrumentation import PilotInvocationRecorder


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{\"ok\":true}"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_tokens_details": {"cached_tokens": 40},
                },
            },
            request=httpx.Request("POST", url),
        )


def _profile():
    return {
        "id": "pilot-test-mimo",
        "provider": "mimo",
        "base_url": "https://mimo.invalid/v1",
        "api_key": "test-key",
        "model_name": "mimo-v2.5",
        "default_params": {"thinking": {"type": "disabled"}},
    }


def test_pilot_span_captures_unmodified_llm_call_with_pipeline_scope():
    recorder = PilotInvocationRecorder()
    with patch("core.llm.httpx.Client", return_value=_FakeClient()):
        with recorder.span(stage="Fact Resolver", episode=1, scene="码头", shot=3):
            result = call_llm("return json", retries=1, estimated_tokens=1, model_profile=_profile())

    assert result == '{"ok":true}'
    assert len(recorder.records) == 1
    extra = recorder.records[0]["extra"]
    assert extra["pilot_stage"] == "Fact Resolver"
    assert extra["pilot_episode"] == 1
    assert extra["pilot_scene"] == "码头"
    assert extra["pilot_shot"] == 3
    summary = recorder.summary()
    assert summary["total_calls"] == 1
    assert summary["total_prompt_tokens"] == 100
    assert summary["total_cached_tokens"] == 40
    assert summary["cache_hit_rate"] == 0.4
    assert summary["stages"]["Fact Resolver"]["total_calls"] == 1


def test_scoped_sink_and_explicit_callback_both_receive_the_same_safe_record():
    recorder = PilotInvocationRecorder()
    explicit = []
    with patch("core.llm.httpx.Client", return_value=_FakeClient()):
        with recorder.span(stage="ShotPlan", repair_attempt=2, provider_mode="mock"):
            call_llm(
                "return json",
                retries=1,
                estimated_tokens=1,
                model_profile=_profile(),
                audit_callback=explicit.append,
                audit_extra={"mode": "pilot"},
            )

    assert len(explicit) == 1
    assert len(recorder.records) == 1
    assert explicit[0] == recorder.records[0]
    assert recorder.records[0]["extra"]["mode"] == "pilot"
    assert recorder.records[0]["extra"]["pilot_repair_attempt"] == 2
    assert recorder.records[0]["extra"]["provider_mode"] == "mock"

