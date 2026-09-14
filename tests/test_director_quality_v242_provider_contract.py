import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from core.director_tail_repair_ir import REPAIR_IR_SCHEMA_VERSION
from core.director_tail_repair_provider_contract import (
    REPAIR_IR_REQUIRED_KEYS,
    build_provider_output_contract,
    build_provider_system_prompt,
)
from core.llm import call_llm_json
from core.llm import call_llm
from core.director_tail_repair_request import build_repair_request
from core.director_tail_repair_executor import _minimal_context


ROOT = Path(__file__).resolve().parents[1]


def _runner_module():
    spec = importlib.util.spec_from_file_location(
        "director_quality_v242_runner",
        ROOT / "scripts" / "run_director_quality_v2_4_targeted_tail_pilot.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_provider_contract_is_derived_from_repair_ir_and_never_requests_canonical_patch():
    contract = build_provider_output_contract()
    assert set(contract["required_keys"]) == set(REPAIR_IR_REQUIRED_KEYS)
    assert contract["schema_version"] == REPAIR_IR_SCHEMA_VERSION
    prompt = build_provider_system_prompt()
    assert REPAIR_IR_SCHEMA_VERSION in prompt
    assert "director_creative_patch_v1" not in prompt
    assert "patches" in prompt


def test_preflight_blocks_the_v241_contract_mismatch():
    runner = _runner_module()
    alignment = runner.build_provider_contract_alignment(
        provider_system_prompt="Return director_creative_patch_v1",
        provider_required_keys={"schema_version", "patches", "auxiliary_shot_proposals"},
        executor_required_schema=REPAIR_IR_SCHEMA_VERSION,
        json_parse_retries=1,
    )
    assert alignment["aligned"] is False
    assert "REPAIR_PROVIDER_SYSTEM_PROMPT_MISMATCH" in alignment["blockers"]
    assert "REPAIR_PROVIDER_REQUIRED_KEYS_MISMATCH" in alignment["blockers"]
    assert "NESTED_JSON_RETRY_ENABLED" in alignment["blockers"]


def test_valid_contract_handshake_is_ready_without_provider_call():
    runner = _runner_module()
    alignment = runner.build_provider_contract_alignment()
    assert alignment["aligned"] is True
    assert alignment["json_parse_retries"] == 0
    assert alignment["canonical_paths_requested"] is False


def test_call_llm_json_zero_parser_retries_makes_one_provider_call():
    calls = []

    def fake_call(*args, **kwargs):
        calls.append((args, kwargs))
        return '{"wrong": true}'

    with patch("core.llm.call_llm", side_effect=fake_call):
        with pytest.raises(ValueError):
            call_llm_json(
                "repair",
                required_keys=set(REPAIR_IR_REQUIRED_KEYS),
                json_parse_retries=0,
            )
    assert len(calls) == 1


def test_provider_adapter_uses_ir_required_keys_and_disables_parser_retry():
    runner = _runner_module()
    captured = {}

    def fake_call(*args, **kwargs):
        captured.update(kwargs)
        return {"schema_version": REPAIR_IR_SCHEMA_VERSION}

    with patch.object(runner, "call_llm_json", fake_call, create=True):
        # Patch the imported boundary used by the helper at call time.
        with patch("core.llm.call_llm_json", fake_call):
            runner.call_provider_repair({"schema_version": "director_tail_repair_request_v1"}, profile={"id": "p"})
    assert captured["required_keys"] == set(REPAIR_IR_REQUIRED_KEYS)
    assert captured["json_parse_retries"] == 0
    assert REPAIR_IR_SCHEMA_VERSION in captured["system"]
    assert "director_creative_patch_v1" not in captured["system"]


def test_executor_base_request_comes_from_request_builder_ssot():
    kwargs = {
        "root_cause": "WEAK_EDIT_STRATEGY",
        "record": {"relevant_beats": [{"beat_id": "B1"}], "relevant_shots": [{"plan_shot_id": "S1"}], "quality_issues": []},
        "opportunities": [],
        "contract": {"scene": {"scene_id": "S"}, "immutable_projection": {"shots": []}, "source_beat_map": {}},
        "strategy": {"edit": "tight"},
        "target_metric": {"EDIT_RHYTHM": 0.2},
        "previous_intervention": None,
    }
    actual = _minimal_context(**kwargs)
    expected = build_repair_request(
        root_cause=kwargs["root_cause"],
        target_dimensions=["EDIT_RHYTHM"],
        relevant_opportunities=[],
        relevant_beats=kwargs["record"]["relevant_beats"],
        relevant_shots=kwargs["record"]["relevant_shots"],
        strategy_subset=kwargs["strategy"],
        immutable_contract={"immutable_fields": list(__import__("core.director_creative_contract", fromlist=["IMMUTABLE_FIELDS"]).IMMUTABLE_FIELDS), "scene": {"scene_id": "S"}, "shots": [], "source_beat_map": {}},
        validator_findings=[],
        previous_intervention=None,
        target_metric=kwargs["target_metric"],
    )
    assert actual["schema_version"] == "director_tail_repair_request_v1"
    assert "protocol_version" not in actual
    assert actual["request_fingerprint"] == expected["request_fingerprint"]


def test_metrics_separate_semantic_attempts_from_http_requests():
    runner = _runner_module()
    result = runner.run_targeted_tail_pilot(
        pilot_path=ROOT / "artifacts" / "director-quality-v2-4-b2-freeze.json",
        repair_callable=lambda request: {},
        audit_records=[],
    )
    assert result["metrics"]["semantic_attempt_count"] >= 0
    assert result["metrics"]["provider_http_request_count"] == 0
    assert result["metrics"]["provider_http_request_count_status"] == "observed"
    assert "root_cause_attempt_coverage" in result
    assert "repair_acceptance_rate" in result


def test_llm_audit_records_bounded_shape_and_each_transport_attempt():
    import httpx

    class RetryClient:
        calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            self.calls += 1
            if self.calls == 1:
                return httpx.Response(500, text="temporary", request=httpx.Request("POST", url))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"schema_version":"director_tail_repair_ir_v1","token":"secret"}'}}]},
                request=httpx.Request("POST", url),
            )

    records = []
    profile = {"id": "p", "base_url": "https://provider.invalid/v1", "api_key": "k", "model_name": "m"}
    with patch("core.llm.httpx.Client", return_value=RetryClient()), patch("core.llm.time.sleep"):
        value = call_llm("prompt", model_profile=profile, retries=2, estimated_tokens=1, audit_callback=records.append, audit_extra={"stage": "test"})
    assert "director_tail_repair_ir_v1" in value
    assert len(records) == 2
    assert records[0]["extra"]["transport_retry"] is True
    assert records[1]["extra"]["transport_retry"] is False
    assert records[1]["top_level_keys"] == ["schema_version", "token"]
    assert "secret" not in records[1]["response_debug_excerpt"]
