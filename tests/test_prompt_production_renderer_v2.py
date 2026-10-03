import copy

import pytest

from core.prompt_production import (
    PromptProductionError,
    build_context,
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
