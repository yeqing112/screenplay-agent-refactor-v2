from __future__ import annotations

from core.prompt_production_v4 import (
    AssetDesignDecisionIR,
    CameraChoreographyIR,
    DirectorDecisionIR,
    DialoguePerformancePlan,
    KeyframeBlockingIR,
    build_dialogue_performance_plan,
    quality_gate_v4,
    render_asset_provider_prompt,
    render_keyframe_provider_prompt,
    render_video_provider_prompt,
    validate_source_facts,
    validate_llm_director_payload,
    validate_dialogue_plans,
)


def _block(name="林晚"):
    return KeyframeBlockingIR(
        identity=name,
        reference_identity=f"character://{name}/v1",
        position="售票窗口前一步",
        screen_x="画面右侧三分之一",
        depth_zone="中景",
        body_pose="双脚分开与肩同宽，上身向站台入口前倾",
        weight_distribution="重心在左脚，右脚脚跟未抬起",
        torso_direction="朝向站台入口",
        head_yaw="向右12度",
        head_pitch="下巴上抬5度",
        eye_target="站台入口的红伞伞骨",
        expression="眉间轻收、下眼睑绷紧、嘴唇闭合、下颌略用力、呼吸停顿半拍",
        left_hand="左手垂在大腿外侧，五指自然弯曲",
        right_hand="右手拇指与食指捏住车票右下角，其余三指弯曲",
        prop_contact="右手接触车票，车票距离胸腹约20厘米",
    )


def _decision(shot_id="shot-1", duration=5.0, dialogue=None):
    beats = [
        {"start_time": 0.0, "end_time": 1.2, "actor": "林晚", "body_action": "右脚向后退半步，左脚保持原位，肩膀不抬起", "hand_action": "右手拇指停止摩擦车票，票角保持在胸腹前", "head_action": "眼球先向右上移动，0.3秒后头部向右转12度", "eye_action": "看向站台入口的红伞伞骨", "facial_action": "眉间轻收，下眼睑绷紧，嘴唇闭合，下颌用力", "ending_state": "右脚后移半步后停住"},
        {"start_time": 1.2, "end_time": 3.4, "actor": "林晚", "body_action": "上身前倾约3厘米，胸口吸气后停住", "hand_action": "右手抬高4厘米但不松开车票，食指保持弯曲", "head_action": "下巴再抬3度，肩线保持水平", "eye_action": "从伞骨移到伞柄顶端并停留", "facial_action": "眉间保持收紧，鼻翼轻张，呼气变短", "ending_state": "车票仍在右手，视线停在伞柄"},
        {"start_time": 3.4, "end_time": 5.0, "actor": "林晚", "body_action": "上身回到前倾1厘米的位置，双脚不再移动", "hand_action": "右手下降2厘米，拇指与食指仍夹住票角", "head_action": "头部保持右转15度，眼球不再移动", "eye_action": "固定看向站台入口的红伞", "facial_action": "嘴唇重新闭合，眉间维持轻收，呼吸恢复均匀", "ending_state": "右脚后退半步、右手持票、头向右15度并冻结"},
    ]
    dialogue_plans = [dialogue] if dialogue else []
    return DirectorDecisionIR(
        shot_id=shot_id,
        duration_seconds=duration,
        source_facts={"shot_id": shot_id, "scene_id": "scene-1", "character_ids": ["林晚"], "prop_ids": ["红伞"], "dialogue": dialogue.authoritative_text if dialogue else "", "location": "旧火车站售票厅"},
        starting_state={"林晚": {"position": "售票窗口前一步", "eye_target": "车票"}},
        blocking=[_block()],
        performance_beats=beats,
        dialogue_beats=dialogue_plans,
        camera_beats=[CameraChoreographyIR(0.0, 2.0, "静止", "无", "保持", "无变化", "红伞", "中景", "中景", "无")],
        emotion_arc={"start": "平静", "end": "警觉", "physical_transition": "眉间轻收、呼吸变短、下颌用力"},
        ending_state={"characters": {"林晚": {"position": "售票窗口前一步，右脚后退半步", "pose": "上身前倾1厘米，双脚冻结", "head_direction": "向右15度", "eye_target": "站台入口红伞", "emotion": "警觉", "right_hand": "夹住车票右下角"}}, "props": {"红伞": "位于站台入口，伞骨可见"}, "camera": {"framing": "中景", "height": "平视", "movement": "静止"}},
        source_fact_hash="fact-hash",
    )


def test_asset_provider_prompt_is_native_prose_without_schema_dump():
    decision = AssetDesignDecisionIR(
        asset_type="CHARACTER",
        identity="林晚",
        source_facts={"age": "约28岁", "face": "偏窄椭圆脸", "eyes": "眼尾略长", "nose": "鼻梁直", "mouth": "薄唇", "skin": "冷白肤色", "hair": "黑色中长直发", "height_build": "清瘦", "costume": "浅灰蓝外套", "costume_materials": "哑光棉质", "footwear": "深色低跟鞋", "accessories": "窄表"},
        design_decisions={"composition": "上排脸部三视图，下排全身三视图", "pose_policy": "肩线自然，双手放松", "lighting": "均匀柔光", "background": "中性灰"},
        reference_policy={"mode": "LOCKED"},
    )
    prompt = render_asset_provider_prompt(decision)
    assert "人物定妆设定板" in prompt
    assert "identity：" not in prompt
    assert "source：" not in prompt
    assert "16:9" in prompt and "正脸近景" in prompt


def test_keyframe_prompt_is_self_contained_and_names_people():
    prompt = render_keyframe_provider_prompt(
        scene={"description": "旧火车站售票厅", "layout": "售票窗口在左侧，站台入口在后方", "time": "日间", "weather": "阴天"},
        blocks=[_block()],
        props=[{"name": "红伞", "state": "伞骨折断，伞面半收", "position": "站台入口右侧"}],
        camera={"shot_size": "中景", "height": "平视", "angle": "正面", "lens": "自然焦段"},
        composition={"foreground": "售票台", "midground": "林晚", "background": "站台入口", "negative_space": "人物右侧"},
        lighting={"key": "入口冷光", "direction": "从右后方斜入", "shadow": "手部仍可辨"},
        style={"description": "低饱和电影写实"},
    )
    assert "林晚" in prompt
    assert "红伞伞骨" in prompt
    assert all(token not in prompt for token in ("performance plan", "ShotPlan", "previous state", "current framing", "由 performance plan 控制"))


def test_dialogue_validator_blocks_duplicate_windows_and_overflow():
    plan = DialoguePerformancePlan(
        speaker="陆叔",
        authoritative_text="陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。",
        start_time=0.8,
        end_time=2.8,
        delivery="slow",
        phrase_windows=[
            {"text": "陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。", "start_time": 0.8, "end_time": 1.8},
            {"text": "陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。", "start_time": 1.8, "end_time": 2.8},
        ],
        estimated_minimum_seconds=8.0,
        status="DIALOGUE_DURATION_OVERFLOW",
    )
    result = validate_dialogue_plans([plan], 5.0)
    assert result["status"] == "BLOCK"
    assert result["duplicated_windows"]
    assert result["overflow"]


def test_quality_gate_detects_fixed_timeline_and_resolved_decisions_pass():
    decisions = [_decision("shot-1"), _decision("shot-2")]
    # force a different boundary layout to prove the gate is semantic, not count based
    decisions[1].performance_beats[0]["end_time"] = 0.9
    gate = quality_gate_v4(
        assets=[], decisions=decisions,
        keyframe_prompts=[render_keyframe_provider_prompt(scene={"description": "scene", "layout": "layout", "time": "day", "weather": "dry"}, blocks=[_block()], props=[], camera={"shot_size": "medium", "height": "eye", "angle": "front", "lens": "normal"}, composition={"foreground": "desk", "midground": "林晚", "background": "door", "negative_space": "right"}, lighting={"key": "soft", "direction": "left", "shadow": "visible"}, style={"description": "realistic"})],
        video_prompts=[render_video_provider_prompt(decisions[0])],
    )
    assert gate["fixed_timeline_count"] == 0
    assert gate["keyframe_internal_plan_references"] == 0


def test_source_fact_validator_blocks_identity_or_dialogue_drift():
    decision = _decision()
    changed = dict(decision.source_facts)
    changed["character_ids"] = ["未经授权人物"]
    result = validate_source_facts(decision, changed)
    assert result["status"] == "BLOCK"
    assert result["count"] >= 1


def test_llm_nested_ir_validator_fails_closed_on_renderer_shorthand():
    payload = {
        "shot_id": "shot-1",
        "source_facts": {},
        "starting_state": {},
        "blocking": {"actor": {"movement": "完成主要动作"}},
        "performance_beats": [{"time": "0-2s", "action": "自然反应", "emotion": "紧张"}],
        "dialogue_beats": [],
        "camera_beats": [{"time": "0-2s", "movement": "轻微推近"}],
        "emotion_arc": {},
        "ending_state": {},
    }
    result = validate_llm_director_payload(payload)
    assert result["status"] == "BLOCK"
    assert any("blocking_must_be_array" in error for error in result["errors"])
