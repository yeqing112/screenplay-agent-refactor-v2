import copy

import pytest

from core.prompt_production import (
    PromptProductionError,
    build_context,
    compare_semantic_pair,
    render_image_prompt,
    render_video_prompt,
    validate_projection,
)


def fixture_ir():
    return {
        "scene_id": "E01_SC001",
        "plan_shot_id": "SH_E01_SC001_005",
        "storyboard_shot_id": 5,
        "subjects": [{"subject_ref": "陆叔"}, {"subject_ref": "林晚"}],
        "props": [{"prop_ref": "HANDBAG"}],
        "camera": {"framing_class": "MEDIUM_WIDE", "orientation": "EYE_LEVEL", "movement": "TRACK", "movement_target": "陆叔"},
        "continuity": {"axis_ref": "AXIS_LW_GC", "screen_side_assignments": {"陆叔": "RIGHT", "林晚": "LEFT", "顾沉": "CENTER"}, "look_direction": {"陆叔": "SCREEN_LEFT", "林晚": "SCREEN_RIGHT", "顾沉": "SCREEN_LEFT"}},
        "action": {"action_beats": [{"actor_refs": ["陆叔", "林晚"]}, {"actor_refs": ["陆叔", "林晚"]}]},
    }


def test_continuity_actor_scope_is_diagnostic_and_filtered():
    ctx = build_context(fixture_ir(), shot_number=5)
    assert any(item["code"] == "CONTINUITY_ACTOR_OUT_OF_SCOPE" for item in ctx.diagnostics)
    assert "顾沉" not in ctx.continuity["screen_side_assignments"]
    assert "顾沉" not in ctx.continuity["look_direction"]


def test_image_is_natural_language_and_chinese():
    projection = render_image_prompt(build_context(fixture_ir(), shot_number=5))
    assert projection["language"] == "zh-CN"
    assert "SUBJECT:" not in projection["prompt"]
    assert "action_id" not in projection["prompt"]
    assert validate_projection(projection) == []


def test_video_has_start_action_end_and_first_frame():
    projection = render_video_prompt(build_context(fixture_ir(), shot_number=5))
    assert "开始：" in projection["prompt"]
    assert "动作：" in projection["prompt"]
    assert "结束：" in projection["prompt"]
    assert any(ref["role"] == "FIRST_FRAME_REFERENCE" for ref in projection["reference_bindings"])
    assert validate_projection(projection) == []


def test_video_overbudget_is_blocked():
    ir = fixture_ir()
    ir["action"]["action_beats"] = [{}, {}, {}]
    with pytest.raises(PromptProductionError, match="SHOT_ACTION_OVERBUDGET"):
        render_video_prompt(build_context(ir, shot_number=5))


def test_reference_authority_is_required():
    ctx = build_context(fixture_ir(), shot_number=5)
    ctx.reference_bindings[0]["status"] = "STALE"
    with pytest.raises(PromptProductionError, match="GENERATION_REFERENCE_AUTHORITY_NOT_READY"):
        render_image_prompt(ctx)


def test_renderer_version_changes_fingerprint():
    first = render_image_prompt(build_context(fixture_ir(), shot_number=5))
    second = copy.deepcopy(first)
    second["renderer_version"] = "image_prompt_renderer_v2_patch1"
    from core.prompt_production import _fingerprint
    assert _fingerprint(first) != _fingerprint(second)


def test_action_is_semantic_not_shot_number_lookup():
    first = fixture_ir()
    second = fixture_ir()
    first["action"]["action_beats"][0]["description"] = "人物打开窗户"
    second["action"]["action_beats"][0]["description"] = "人物关上抽屉"
    p1 = render_image_prompt(build_context(first, shot_number=1))["prompt"]
    p2 = render_image_prompt(build_context(second, shot_number=1))["prompt"]
    assert p1 != p2
    assert "打开窗户" in p1 and "关上抽屉" in p2


def test_cross_layer_action_camera_and_ending_fail_closed():
    ir = fixture_ir()
    ir["action"]["action_beats"][0]["actor_refs"] = ["售票员"]
    with pytest.raises(PromptProductionError, match="SHOT_SEMANTIC_ACTOR_INTEGRITY"):
        build_context(ir, shot_number=8)
    ir = fixture_ir()
    ir["camera"]["movement_target"] = "售票员"
    with pytest.raises(PromptProductionError, match="SHOT_SEMANTIC_ACTOR_INTEGRITY"):
        build_context(ir, shot_number=8)
    ir = fixture_ir()
    with pytest.raises(PromptProductionError, match="SHOT_SEMANTIC_ACTOR_INTEGRITY"):
        build_context(ir, shot_plan={"subjects": ["陆叔", "林晚"], "exit_state": {"characters": {"陆叔": "center", "林晚": "center", "售票员": "offscreen"}}}, shot_number=5)


def test_pair_semantic_comparison_detects_actor_mismatch():
    image = build_context(fixture_ir(), shot_number=8)
    video_ir = fixture_ir()
    video_ir["subjects"] = [{"subject_ref": "售票员"}, {"subject_ref": "林晚"}]
    video_ir["action"]["action_beats"] = [{"actor_refs": ["售票员", "林晚"]}]
    video_ir["camera"]["movement_target"] = "售票员"
    video = build_context(video_ir, shot_number=8)
    mismatch = compare_semantic_pair(image, video)
    assert any(item["code"] == "IMAGE_VIDEO_ACTOR_SET_MISMATCH" for item in mismatch)


def test_production_renderer_has_no_fixture_coupling():
    from pathlib import Path
    source = (Path(__file__).parents[1] / "core" / "prompt_production.py").read_text(encoding="utf-8")
    for token in ("林晚", "顾沉", "陆叔", "售票员", "E01_SC001", "E01_SC002", "RED_UMBRELLA", "SHOT_ACTIONS"):
        assert token not in source
