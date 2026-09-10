import unittest
from unittest.mock import patch

from core.prompt_cache import cache_metrics, canonical_json, llm_request_fingerprint, model_request_snapshot, prompt_fingerprint, summarize_audit_records
from core.llm import _build_audit_record
from api import server as server_module


class PromptCacheTests(unittest.TestCase):
    def test_canonical_json_is_order_independent(self):
        self.assertEqual(
            canonical_json({"b": 2, "a": 1}),
            canonical_json({"a": 1, "b": 2}),
        )

    def test_prompt_fingerprint_changes_when_any_part_changes(self):
        self.assertEqual(prompt_fingerprint("system", {"a": 1}), prompt_fingerprint("system", {"a": 1}))
        self.assertNotEqual(prompt_fingerprint("system", {"a": 1}), prompt_fingerprint("system", {"a": 2}))

    def test_request_identity_changes_with_safe_model_parameters(self):
        profile = {"id": "mimo", "provider": "mimo", "model_name": "mimo-v2.5", "default_params": {"temperature": 0.2, "thinking": {"type": "disabled"}, "api_key": "never"}}
        same = dict(profile)
        changed = {**profile, "default_params": {"temperature": 0.8, "thinking": {"type": "disabled"}}}
        self.assertEqual(model_request_snapshot(profile)["profile_id"], "mimo")
        self.assertNotIn("api_key", canonical_json(model_request_snapshot(profile)))
        self.assertEqual(llm_request_fingerprint(system="s", user="u", profile=profile), llm_request_fingerprint(system="s", user="u", profile=same))
        self.assertNotEqual(llm_request_fingerprint(system="s", user="u", profile=profile), llm_request_fingerprint(system="s", user="u", profile=changed))

    def test_audit_summary_is_safe_when_empty(self):
        self.assertEqual(summarize_audit_records([]), {"attempt_count": 0, "last": {}})

    def test_cache_metrics_reads_mimo_usage_details(self):
        metrics = cache_metrics({
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_tokens_details": {"cached_tokens": 800},
        })
        self.assertEqual(metrics["cached_tokens"], 800)
        self.assertEqual(metrics["cache_hit_rate"], 0.8)

    def test_cache_metrics_is_safe_when_provider_omits_details(self):
        metrics = cache_metrics({"total_tokens": 4})
        self.assertIsNone(metrics["cached_tokens"])
        self.assertIsNone(metrics["cache_hit_rate"])

    def test_audit_record_persists_cache_metrics_without_prompt_text(self):
        record = _build_audit_record(
            system="stable system",
            user="dynamic task",
            vendor_model="mimo-v2.5",
            vendor_host="https://api.xiaomimimo.com/v1",
            profile_id="mimo",
            status=200,
            response_text="{}",
            parse_ok=True,
            usage={"prompt_tokens": 10, "total_tokens": 12, "completion_tokens": 2,
                    "prompt_tokens_details": {"cached_tokens": 7}},
            latency_ms=12.5,
        )
        self.assertEqual(record["usage"]["cached_tokens"], 7)
        self.assertEqual(record["usage"]["cache_hit_rate"], 0.7)
        self.assertEqual(record["latency_ms"], 12.5)
        self.assertNotIn("stable system", record)

    def test_storyboard_compiler_keeps_dynamic_contract_out_of_system_prefix(self):
        captured = []

        def fake_llm(prompt, **kwargs):
            captured.append({"prompt": prompt, **kwargs})
            return {}

        base = {
            "scene_name": "同一场景",
            "bound_assets": [],
            "required_used_assets": [],
            "model_adapter": {},
            "motion_contract": {"start_state": "人物站立", "action_beats": [], "end_state": "人物停下"},
        }
        with patch.object(server_module.llm_client, "call_llm_json", side_effect=fake_llm):
            server_module._call_storyboard_prompt_compiler({**base, "shot_id": "1"})
            server_module._call_storyboard_prompt_compiler({**base, "shot_id": "2", "motion_contract": {"start_state": "人物坐下", "action_beats": [], "end_state": "人物抬头"}})

        self.assertEqual(captured[0]["system"], captured[1]["system"])
        self.assertIn("DELIVERY CONTRACT", captured[0]["prompt"])
        self.assertNotIn("人物坐下", captured[0]["system"])
        self.assertNotEqual(captured[0]["prompt"], captured[1]["prompt"])

    def test_audit_summary_aggregates_provider_cache_usage(self):
        summary = server_module._summarize_llm_audit_records([
            {"vendor_model": "mimo-v2.5", "usage": {"prompt_tokens": 100, "cached_tokens": 40, "completion_tokens": 10, "total_tokens": 110}, "request_fingerprint": "a", "http_status": 200, "parse_ok": True},
            {"vendor_model": "mimo-v2.5", "usage": {"prompt_tokens": 50, "cached_tokens": 25, "completion_tokens": 8, "total_tokens": 58}, "request_fingerprint": "b", "http_status": 200, "parse_ok": True},
        ])
        self.assertEqual(summary["prompt_tokens"], 150)
        self.assertEqual(summary["cached_tokens"], 65)
        self.assertEqual(summary["cache_hit_rate"], round(65 / 150, 6))


if __name__ == "__main__":
    unittest.main()
