from pathlib import Path

from scripts.finalize_director_quality_v2_3_phase_b_report import build_final_metrics, write_final_artifacts


ROOT = Path(__file__).resolve().parents[1]


def test_final_report_fails_closed_when_b2_is_missing(tmp_path):
    b1_path = ROOT / "artifacts" / "director-quality-v2-3-phase-b1-pilot-20260914T030654Z.json"
    b1 = __import__("json").loads(b1_path.read_text(encoding="utf-8"))
    metrics = build_final_metrics(b1=b1, b2=None, b1_path=b1_path, b2_path=tmp_path / "missing.json")
    assert metrics["status"] == "NOT_READY"
    assert metrics["reasons"]
    assert metrics["phase_b2"]["available"] is False


def test_final_report_writes_four_artifact_types_without_provider(tmp_path):
    b2 = {
        "protocol_version": "director-quality-v2-3-phase-b2-pilot",
        "pilot_mode": "real_mimo_phase_b2_artifact_only",
        "scene_count": 24,
        "summary": {"director_quality": {"mean": 80, "median": 85, "p10": 70, "min": 60}, "creative_value": {"mean": 75}, "contract_pass_rate": 1.0},
        "shadow_gate": {"status": "SAFE_BUT_NOT_VALUABLE"},
        "side_effects": {"production_rows_written": 0},
        "production_shadow": {"enabled": False},
        "scenes": [],
        "artifacts": {"opportunity_analysis": {}, "tail_analysis": {}},
    }
    metrics = build_final_metrics(b1=None, b2=b2)
    outputs = write_final_artifacts(metrics=metrics, output_dir=tmp_path)
    assert set(outputs) == {"metrics", "report", "opportunity_analysis", "tail_analysis"}
    assert all(Path(path).exists() for path in outputs.values())
    assert f"Status: **{metrics['status']}**" in Path(outputs["report"]).read_text(encoding="utf-8")
