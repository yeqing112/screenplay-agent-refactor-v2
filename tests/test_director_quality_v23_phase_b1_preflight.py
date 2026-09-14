from pathlib import Path

from scripts.run_director_quality_v2_3_phase_b1_preflight import build_preflight


def test_phase_b1_preflight_is_provider_free_and_requires_mimo_profile():
    packet = build_preflight(
        profile={
            "id": "mimo-profile",
            "provider": "openai-compatible",
            "model_name": "mimo-v2.5",
            "capability": "llm",
            "enabled": True,
            "key_configured": True,
            "api_key": "DO-NOT-EMIT",
            "base_url": "https://example.invalid/v1",
        },
        golden_path=Path("artifacts/director-quality-v2-1-golden-scenes.json"),
        offline_path=Path("artifacts/director-quality-v2-3-offline-benchmark-current.json"),
        scene_limit=12,
    )
    assert packet["ready_for_confirmation"] is True
    assert packet["real_mimo_calls"] == 0
    assert packet["confirmation_required"] is True
    assert packet["scene_count"] == 12
    assert packet["opportunity_summary"]["total_count"] > 0
    assert packet["safety"] == {"production": 0, "storyboard": 0, "media": 0, "object_storage": 0}
    assert "DO-NOT-EMIT" not in str(packet)


def test_phase_b1_preflight_fails_closed_when_evidence_is_short():
    packet = build_preflight(
        profile={
            "id": "mimo-profile",
            "provider": "openai-compatible",
            "model_name": "mimo-v2.5",
            "capability": "llm",
            "enabled": True,
            "key_configured": True,
            "base_url": "https://example.invalid/v1",
        },
        golden_path=Path("artifacts/director-quality-v2-1-golden-scenes.json"),
        offline_path=Path("artifacts/director-quality-v2-3-offline-benchmark-current.json"),
        scene_limit=24,
    )
    assert packet["ready_for_confirmation"] is False
    assert packet["real_mimo_calls"] == 0
