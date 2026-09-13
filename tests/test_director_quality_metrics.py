from core.director_quality_metrics import build_director_quality_metrics


def _plan(intensity=5, angle="eye_level"):
    return {
        "shots": [{
            "plan_shot_id": "S01",
            "purpose": "reveal",
            "why_this_shot": "呈现关键反应",
            "camera": {"shot_size": "MS", "angle": angle, "movement": "static", "speed": "slow", "camera_side": "center"},
            "emotion": {"intensity": intensity},
            "composition": {"dominant_subject": "C1"},
            "edit": {"duration_seconds": 3, "cut_reason": "beat_change"},
        }],
    }


def test_metrics_record_three_stages_and_ten_dimensions_separately():
    result = build_director_quality_metrics(
        baseline=_plan(),
        first_candidate=_plan(intensity=6, angle="low_angle"),
        final_candidate=_plan(intensity=7, angle="low_angle"),
        contract_reliability={"schema_pass": True, "patch_path_pass": True, "parse_success": True},
        partial_acceptance={"accepted_patch_count": 1, "rejected_patch_count": 1, "fallback_patch_count": 1},
    )
    assert len(result["director_dimensions"]) == 10
    assert set(result["dimensions"]) == {"baseline", "before_repair", "after_repair"}
    assert result["contract_reliability"]["schema_pass"] is True
    assert result["partial_acceptance"]["rejected_patch_count"] == 1


def test_metrics_promote_schema_rejections_into_contract_reliability():
    result = build_director_quality_metrics(
        baseline=_plan(),
        contract_reliability={
            "schema_pass": False,
            "schema_rejections": [
                {"code": "DIRECTOR_FACT_OVERRIDE", "path": "patches[1].changes.scene_name"},
                {"code": "INVALID_PATCH_VALUE", "path": "patches[2].changes.camera.angle"},
            ],
        },
    )
    reliability = result["contract_reliability"]
    assert reliability["schema_rejection_count"] == 2
    assert reliability["forbidden_field_attempt"] is True
    assert reliability["forbidden_field_attempt_count"] == 1
    assert reliability["fact_override_attempt_count"] == 1
