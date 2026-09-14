from core.director_overdirecting import detect_over_directing


def test_over_directing_requires_evidence_for_movement_and_auxiliary_shots():
    result = detect_over_directing(
        [{"plan_shot_id": "S01", "camera": {"movement": "tracking"}}, {"plan_shot_id": "AUX1", "auxiliary_type": "reaction", "camera": {"movement": "static"}}],
        opportunities=[], baseline_shot_count=1, allowed_auxiliary_count=0,
    )
    codes = {item["code"] for item in result["issues"]}
    assert "GRATUITOUS_CAMERA_MOVEMENT" in codes
    assert "UNNECESSARY_REACTION_SHOT" in codes
    assert "SHOT_INFLATION" in codes


def test_supported_auxiliary_shot_is_not_flagged_as_unnecessary():
    result = detect_over_directing(
        [{"plan_shot_id": "AUX1", "auxiliary_type": "insert", "camera": {"movement": "static"}, "why_this_shot": "呈现关键道具状态"}],
        opportunities=[{"type": "OPP_PROP_EMPHASIS", "eligible": True}], baseline_shot_count=1, allowed_auxiliary_count=1,
    )
    assert not any(item["code"] == "UNNECESSARY_INSERT" for item in result["issues"])
