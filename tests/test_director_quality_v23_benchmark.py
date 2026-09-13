from pathlib import Path

from core.director_quality_v23_benchmark import (
    aggregate_variance,
    samples_from_offline_benchmark,
)
from scripts.run_director_quality_v2_3_mimo_pilot_authorized import build_preflight


def _row(scene_id, run_id, variant, score):
    return {
        "scene_id": scene_id,
        "run_id": run_id,
        "variant": variant,
        "director_quality": score,
        "contract_pass": True,
        "fact_override_accepted": 0,
        "planner_calls": 1,
        "repair_calls": 0,
        "tokens": 100,
        "cached_tokens": 50,
        "latency_ms": 10,
        "coverage": {"performance_direction_coverage": 1.0},
        "side_effects": {"production": 0},
    }


def test_aggregate_variance_reports_paired_deltas_and_improved_runs():
    result = aggregate_variance(
        [
            _row("S01", 1, "A", 60),
            _row("S01", 1, "B", 80),
            _row("S02", 1, "A", 70),
            _row("S02", 1, "B", 75),
            _row("S01", 2, "A", 80),
            _row("S01", 2, "B", 70),
        ]
    )
    assert result["independent_run_count"] == 2
    assert result["improved_run_count"] == 1
    assert result["degraded_run_count"] == 1
    assert result["paired_delta"]["mean"] == 5.0
    assert result["safety"]["final_contract_pass_rate"] == 1.0
    assert result["cost"]["cache_hit_rate"] == 0.5


def test_offline_artifact_extraction_keeps_two_variants_and_no_side_effects():
    payload = {
        "samples": [
            {
                "scene": {"scene_id": "S01"},
                "variant_a": {"score": {"director_quality_score": 55}, "coverage": {}},
                "variant_b": {"score": {"director_quality_score": 85}, "coverage": {}},
                "contract_pass": True,
                "side_effects": {"llm_provider": 0},
            }
        ]
    }
    samples = samples_from_offline_benchmark(payload)
    assert {item["variant"] for item in samples} == {"A", "B"}
    result = aggregate_variance(samples)
    assert result["paired_delta"]["mean"] == 30.0
    assert result["safety"]["side_effects"]["llm_provider"] == 0


def test_phase_a_preflight_is_non_secret_and_requires_confirmation():
    packet = build_preflight(
        profile={
            "id": "mimo-profile",
            "capability": "llm",
            "provider": "openai-compatible",
            "model_name": "mimo-v2.5",
            "enabled": True,
            "key_configured": True,
            "api_key": "DO-NOT-EMIT",
        },
        golden_path=Path("artifacts/director-quality-v2-1-golden-scenes.json"),
        offline_artifact=Path("artifacts/director-quality-v2-3-offline-benchmark-current.json"),
    )
    assert packet["ready_for_confirmation"] is True
    assert packet["real_mimo_calls"] == 0
    assert packet["confirmation_required"] is True
    assert "DO-NOT-EMIT" not in str(packet)
