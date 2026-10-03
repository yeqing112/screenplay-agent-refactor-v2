from __future__ import annotations

import inspect

from core.prompt_production_v3 import (
    build_character_asset_prompt,
    build_performance_plan,
    build_timecoded_motion_ir,
    quality_gate_v3,
    render_timecoded_video_prompt,
)


def _ready_character():
    fields = {
        "face": "椭圆脸，短黑发，冷静目光",
        "costume": "深色外套",
        "reference_board_views": "正脸、左侧、右侧、全身",
        "consistency_constraints": "身份、比例、服装保持一致",
        "required_fields": ["face", "costume", "reference_board_views", "consistency_constraints"],
    }
    return build_character_asset_prompt("canonical-character", fields)


def _plan(dialogue=None):
    dialogue = dialogue or []
    segments = [
        {
            "start_time": 0.0,
            "end_time": 0.8,
            "actor": "actor-a",
            "body_action": "重心稳定",
            "hand_action": "手指停在桌边",
            "head_action": "头部保持",
            "eye_action": "看向目标",
            "facial_action": "眉间收紧",
            "dialogue": "N/A",
            "dialogue_delivery": "N/A",
            "lip_sync_window": "N/A",
            "prop_action": "保持道具位置",
            "interaction_target": "actor-b",
            "camera_action": "静止",
            "emotion_start": "平静",
            "emotion_end": "注意",
            "ending_state": "保持姿态",
        },
        {
            "start_time": 0.8,
            "end_time": 1.8,
            "actor": "actor-a",
            "body_action": "向前半步",
            "hand_action": "抬手指向目标",
            "head_action": "头部转向目标",
            "eye_action": "锁定目标",
            "facial_action": "嘴角收紧",
            "dialogue": dialogue[0]["text"] if dialogue else "N/A",
            "dialogue_delivery": "低声",
            "lip_sync_window": "0.8–1.8" if dialogue else "N/A",
            "prop_action": "不改变",
            "interaction_target": "actor-b",
            "camera_action": "轻微推近",
            "emotion_start": "注意",
            "emotion_end": "警觉",
            "ending_state": "指向保持",
        },
        {
            "start_time": 1.8,
            "end_time": 5.0,
            "actor": "actor-a",
            "body_action": "停住",
            "hand_action": "手停在最终位置",
            "head_action": "头部保持",
            "eye_action": "视线固定",
            "facial_action": "表情稳定",
            "dialogue": "N/A",
            "dialogue_delivery": "N/A",
            "lip_sync_window": "N/A",
            "prop_action": "进入最终状态",
            "interaction_target": "actor-b",
            "camera_action": "停止",
            "emotion_start": "警觉",
            "emotion_end": "克制",
            "ending_state": "可衔接姿态",
        },
    ]
    return build_performance_plan(
        shot_id="shot-test",
        characters=[{"identity": "actor-a"}],
        dialogue=dialogue,
        emotion_arc=[{"start_time": 0.0, "end_time": 5.0, "from": "平静", "to": "克制"}],
        body_movement=segments,
        hand_movement=[],
        head_movement=[],
        eye_movement=[],
        facial_changes=[],
        interaction_beats=[],
        prop_interaction=[],
        camera_movement=[{"start_time": 0.0, "end_time": 5.0, "action": "停止"}],
        ending_pose={"position": "桌边", "pose": "稳定", "eye_direction": "actor-b"},
    )


def test_asset_prompt_requires_rich_reference_fields():
    blocked = build_character_asset_prompt("missing-character", {"required_fields": ["face", "reference_board_views"]})
    assert blocked.readiness == "ASSET_PROMPT_NOT_READY"
    ready = _ready_character()
    assert ready.readiness == "ASSET_PROMPT_READY"
    assert "正脸" in ready.provider_prompt
    assert ready.reference_policy["status"] == "LOCKED"


def test_timecoded_motion_preserves_required_performance_fields_and_disables_audio():
    motion = build_timecoded_motion_ir(_plan())
    assert motion.dialogue_audio_generated is False
    assert len(motion.segments) == 3
    required = {"body_action", "hand_action", "head_action", "eye_action", "facial_action", "prop_action", "camera_action", "ending_state"}
    assert required <= motion.segments[0].keys()
    assert motion.segments[-1]["end_time"] == 5.0


def test_dialogue_is_visual_lip_timing_only():
    plan = _plan([{"speaker": "actor-a", "text": "授权对白", "start_time": 0.8, "end_time": 1.8, "delivery": "低声"}])
    motion = build_timecoded_motion_ir(plan)
    rendered = render_timecoded_video_prompt(
        first_frame_prompt="首帧",
        plan=plan,
        motion=motion,
        ending_state=plan.ending_pose,
        camera_timeline=plan.camera_movement,
    )
    assert rendered["dialogue_audio_generated"] is False
    assert "对白/口型" in rendered["prompt"]
    assert "0.8–1.8" in rendered["prompt"]


def test_quality_gate_catches_generic_placeholder_and_internal_leak():
    asset = _ready_character()
    plan = _plan()
    motion = build_timecoded_motion_ir(plan)
    clean = {"prompt": "身体动作明确，镜头在时间段内停止"}
    passed = quality_gate_v3(assets=[asset], keyframes=[clean], videos=[clean], motions=[motion], plans=[plan])
    assert passed["status"] == "PASS"
    bad = {"prompt": "自然反应，action_id=hidden"}
    blocked = quality_gate_v3(assets=[asset], keyframes=[bad], videos=[bad], motions=[motion], plans=[plan])
    assert blocked["generic_placeholder_count"] > 0
    assert blocked["internal_token_leak_count"] > 0
    assert blocked["status"] == "BLOCK"


def test_production_renderer_has_no_fixture_specific_names():
    source = inspect.getsource(__import__("core.prompt_production_v3", fromlist=["*"]))
    for token in ("林晚", "顾沉", "陆叔", "售票员", "RED_UMBRELLA", "E01_SC001", "BOOK_990401"):
        assert token not in source
