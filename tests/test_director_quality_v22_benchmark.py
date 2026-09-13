from pathlib import Path

from scripts.run_director_quality_v2_2_benchmark import run_offline_replay


ROOT = Path(__file__).resolve().parents[1]


def test_v22_offline_replay_is_provider_free_and_keeps_scene_count():
    result = run_offline_replay(
        golden_path=ROOT / "artifacts" / "director-quality-v2-1-golden-scenes.json",
        replay_path=ROOT / "artifacts" / "director-quality-v2-1-mimo-pilot-20260913T093747Z.json",
        scene_limit=2,
    )
    assert result["benchmark_mode"] == "offline_replay"
    assert result["scene_count"] == 2
    assert result["real_pilot"]["executed"] is False
    assert result["side_effects"] == {
        "production_rows_written": 0,
        "storyboard_shots_created": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
        "llm_provider_calls": 0,
    }
    assert result["metrics"]["stages"]["final_contract_pass"]["rate"] == 1.0

