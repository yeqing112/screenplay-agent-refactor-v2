from pathlib import Path

from scripts.run_director_quality_v2_3_offline_benchmark import run


ROOT = Path(__file__).resolve().parents[1]


def test_v23_offline_benchmark_uses_shared_frozen_scenes_and_no_provider_calls():
    result = run(
        golden_path=ROOT / "artifacts" / "director-quality-v2-1-golden-scenes.json",
        recovery_path=ROOT / "artifacts" / "director-quality-v2-2-2-recovery-pilot-20260913T180409Z.json",
        scene_limit=2,
    )
    assert result["scene_count"] == 2
    assert result["variants"]["B"] == "deterministic Strategy V2 planner"
    assert result["real_mimo"]["executed"] is False
    assert result["safety"]["fact_override_accepted"] == 0
    assert result["safety"]["side_effects"]["llm_provider"] == 0
    assert set(result["quality"]["variant_b"]) == {"mean", "median", "stddev", "p25", "p75"}
    assert all(item["variant_b"]["quality_trace"]["unknown_root_cause_count"] == 0 for item in result["samples"])
