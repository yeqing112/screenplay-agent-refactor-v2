from __future__ import annotations

import json

from scripts.run_director_quality_v3_phase1_2 import _format_eligible, provider_free_preflight, _load_records


def test_phase1_2_format_repair_requires_pure_protocol_errors():
    assert _format_eligible({}, "", [{"code": "NESTED_FIELD_SHAPE_INVALID"}])
    assert not _format_eligible({}, "", [{"code": "NESTED_FIELD_SHAPE_INVALID"}, {"code": "FACT_INVENTION"}])
    assert not _format_eligible({}, "", [{"code": "UNKNOWN_BEAT_REFERENCE"}])
    assert _format_eligible(None, "parse failure", [])


def test_phase1_2_provider_free_preflight_is_three_scene_and_side_effect_free():
    profile = {"id": "test", "provider": "openai-compatible", "model_name": "mimo-v2.5", "capability": "llm"}
    result = provider_free_preflight(_load_records(), profile)
    assert result["status"] == "PASS"
    assert result["real_mimo_calls"] == 0
    assert result["shotplan"] == 0
    assert result["media"] == 0
    assert result["ci"] == "not_run"

