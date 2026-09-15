import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"


def test_final_recanary_captured_exactly_three_calls_and_failed_closed():
    result = json.loads((ART / "director-quality-v3-final-shot-architecture-recanary-real.json").read_text(encoding="utf-8"))
    assert result["authorized_calls"] == 3
    assert result["attempted_calls"] == 3
    assert result["creative_generation_count"] == 3
    assert result["semantic_retry_count"] == 0
    assert result["format_retry_count"] == 0
    assert result["repair_retry_count"] == 0
    assert result["transport_retry_count"] == 0
    assert result["status"] == "DIRECTOR_V3_FINAL_SHOT_ARCHITECTURE_RECANARY_FAILED"
    assert result["ready_for_production_shotplan"] is False
    assert result["human_preference_review"] == "NOT_RECORDED"


def test_final_recanary_requested_evidence_is_present_and_raw_is_immutable():
    for suffix in ("report.md", "comparison.json", "atomicity.json", "reaction.json", "topology.json", "director-qa.json"):
        assert (ART / f"director-quality-v3-final-shot-architecture-recanary-{suffix}").exists()
    for scene_dir in (ART / "director-quality-v3-final-shot-architecture-recanary-scenes").iterdir():
        assert (scene_dir / "raw-response.txt").exists()
        fingerprint = json.loads((scene_dir / "raw-fingerprint.json").read_text(encoding="utf-8"))
        assert fingerprint["immutable"] is True
