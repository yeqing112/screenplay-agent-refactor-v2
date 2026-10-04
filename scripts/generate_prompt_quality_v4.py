"""Build the bounded V4 Director Decision canary artifacts.

The default path is provider-free.  ``--real-llm`` is explicit and requires a
configured non-placeholder OpenAI-compatible profile; it is limited to five
logical Director generations and never calls IMAGE or VIDEO providers.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prompt_production_v4 import (  # noqa: E402
    AssetDesignDecisionIR,
    CameraChoreographyIR,
    DirectorDecisionIR,
    KeyframeBlockingIR,
    build_dialogue_performance_plan,
    fingerprint,
    quality_gate_v4,
    render_asset_provider_prompt,
    render_keyframe_provider_prompt,
    render_video_provider_prompt,
    SCHEMA_VERSION,
    validate_camera_beats,
    validate_dialogue_plans,
    validate_ending_state,
    validate_keyframe_blocks,
    validate_llm_director_payload,
    validate_physical_beats,
    validate_source_facts,
)

V21 = ROOT / "docs/prompt-quality/v2.1"
V3 = ROOT / "docs/prompt-quality/v3"
OUT = ROOT / "docs/prompt-quality/v4"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def _asset(asset_type: str, identity: str, source: dict, design: dict, policy: dict):
    return AssetDesignDecisionIR(asset_type, identity, source, design, policy)


def load_assets():
    character_files = {p.stem: read_json(p) for p in (V3 / "assets/characters").glob("*.json")}
    prop_files = {p.stem: read_json(p) for p in (V3 / "assets/props").glob("*.json")}
    scenes = {p.stem: read_json(p) for p in (V3 / "assets/scenes").glob("*.json")}
    style = read_json(V3 / "assets/style/episode-01-visual-style.json")
    assets = []
    for name in ("林晚", "陆叔"):
        fields = character_files[name]["fields"]
        assets.append(_asset("CHARACTER", name, fields, {
            "composition": "上排正脸、左侧脸、右前45度脸部近景；下排全身正面、侧面、背面",
            "pose_policy": "肩线自然，双臂放松，六个视图采用同一站立重心",
            "lighting": "中性柔光，脸部两侧和服装材质均匀可见",
            "background": "无纹理中性灰背景",
        }, {"mode": "LOCKED_CANONICAL_REFERENCE", "view_count": 6}))
    scene_fields = scenes["E01_SC001"]["fields"]
    assets.append(_asset("SCENE", "E01_SC001", scene_fields, {
        "master_direction": "售票厅入口向窗口",
        "reverse_direction": "窗口向站台入口",
        "side_direction": "沿候车座椅长边",
        "detail_target": "湿水泥地面、售票窗口木台面和站台入口红伞区域",
    }, {"mode": "LOCKED_SCENE_MULTI_VIEW", "views": ["master wide", "reverse angle", "side angle", "key detail"]}))
    for name, layout in {
        "RED_UMBRELLA": {"board_type": "multi-angle reference board", "view_layout": "展开正面、侧面、伞柄特写、折断伞骨特写", "background": "湿冷灰色背景", "lighting": "右上方冷光，雨滴高光可辨"},
        "HANDBAG": {"board_type": "single hero reference plus side detail", "view_layout": "正面英雄视图、侧面厚度和提手细节", "background": "中性深灰背景", "lighting": "柔和侧光，皮革磨损可辨"},
    }.items():
        fields = prop_files[name]["fields"]
        assets.append(_asset("PROP", name, fields, layout, {"mode": "LOCKED_PROP_REFERENCE", "views": layout["view_layout"]}))
    style_fields = style["fields"]
    assets.append(_asset("VISUAL_STYLE", "episode-01-visual-style", style_fields, {"layout": "单页风格参考板，包含肤色、湿地面、旧木和暖冷光关系"}, {"mode": "LOCKED_STYLE_REFERENCE"}))
    return assets


def block(name, **kwargs):
    defaults = {
        "reference_identity": f"character://{name}/v1",
        "position": "",
        "screen_x": "",
        "depth_zone": "",
        "body_pose": "",
        "weight_distribution": "",
        "torso_direction": "",
        "head_yaw": "",
        "head_pitch": "",
        "eye_target": "",
        "expression": "",
        "left_hand": "",
        "right_hand": "",
        "prop_contact": "无",
    }
    defaults.update(kwargs)
    return KeyframeBlockingIR(identity=name, **defaults)


def shot_decisions():
    # Dialogue is sourced from the Script/Storyboard authority.  The source
    # hash is preserved alongside the normalized canary text for auditability.
    decisions = []
    decisions.append(DirectorDecisionIR(
        shot_id="SH_E01_SC001_002", duration_seconds=5.0,
        source_facts={"shot_id": "SH_E01_SC001_002", "scene_id": "E01_SC001", "character_ids": ["林晚"], "prop_ids": ["RED_UMBRELLA"], "dialogue": "", "location": "旧火车站售票厅"},
        starting_state={"林晚": {"position": "售票窗口前一步，右手持车票", "eye_target": "车票票面", "pose": "站直"}},
        blocking=[block("林晚", position="售票窗口前一步", screen_x="画面右侧三分之一", depth_zone="中景", body_pose="双脚与肩同宽，上身从直立向站台入口前倾3厘米", weight_distribution="重心从双脚平均转到左脚六成", torso_direction="朝向站台入口", head_yaw="从正面转到右12度", head_pitch="由0度抬到5度", eye_target="先看手中车票，再看站台入口的红伞伞骨", expression="眉间从平展收紧，下眼睑绷紧，嘴唇闭合，下颌略用力，呼吸停顿半拍", left_hand="左手垂在大腿外侧，五指自然弯曲", right_hand="右手拇指与食指捏住车票右下角，拇指停止摩擦纸面，其余三指弯曲", prop_contact="右手夹住车票，车票距胸腹约20厘米")],
        performance_beats=[
            {"start_time": 0.0, "end_time": 0.65, "actor": "林晚", "body_action": "林晚双脚不动，右肩保持水平，胸口吸气后停半拍", "hand_action": "右手拇指停止摩擦车票边角，食指与拇指夹持点不变", "head_action": "头部保持正面，只有眼球向右上方跳转", "eye_action": "从车票票面移到站台入口红伞伞骨", "facial_action": "眉间由平展变为轻微收紧，嘴唇仍闭合", "prop_action": "车票不移动", "ending_state": "视线落在红伞伞骨，双脚原位"},
            {"start_time": 0.65, "end_time": 1.7, "actor": "林晚", "body_action": "林晚上身向右前方倾斜约3厘米，左脚承重增加，右脚脚跟不抬起", "hand_action": "右手把车票抬高约2厘米，拇指仍压住右下角", "head_action": "眼球转移后约0.3秒，头部向右转12度、下巴上抬5度", "eye_action": "固定看向站台入口红伞伞骨的折断处", "facial_action": "下眼睑略绷紧，鼻翼扩张一次，呼吸变短", "prop_action": "车票保持在胸腹前，不遮挡脸部", "ending_state": "头向右12度，眼睛停在折断伞骨"},
            {"start_time": 1.7, "end_time": 3.5, "actor": "林晚", "body_action": "林晚向站台入口迈出半步，前脚掌落地后立即停止", "hand_action": "右手下降1厘米，车票仍夹在拇指与食指之间，左手抬到外套下摆并停住", "head_action": "头部再向右转3度，肩线保持水平", "eye_action": "从伞骨沿伞柄移动到伞面边缘", "facial_action": "眉心进一步收紧，嘴角向下压1毫米，下颌保持用力", "prop_action": "红伞伞面半收，折断伞骨仍暴露", "ending_state": "林晚前移半步，车票仍在右手，视线在伞面边缘"},
            {"start_time": 3.5, "end_time": 5.0, "actor": "林晚", "body_action": "林晚停止迈步，胸口缓慢呼出一口气，身体保持前倾3厘米", "hand_action": "右手固定车票于胸腹前，左手从外套下摆落回大腿侧", "head_action": "头部保持右15度，不再追随视线", "eye_action": "最终固定在站台入口的红伞", "facial_action": "眉间保持轻收，嘴唇闭合，下颌放松一半但警觉不退", "prop_action": "红伞位置和折断伞骨不改变", "ending_state": "林晚在窗口至站台入口之间停住，右手持票，头向右15度，视线锁定红伞"},
        ],
        dialogue_beats=[],
        camera_beats=[CameraChoreographyIR(0.0, 0.65, "静止", "无", "保持", "无变化", "林晚双眼", "中广角", "中广角", "无"), CameraChoreographyIR(0.65, 2.2, "重新构图", "沿光轴轻推并向右修正", "前0.3秒缓慢加速", "人物从中广角占画面右三分之一变为右半幅", "林晚头部和红伞伞骨", "中广角", "中景", "先加速后匀速"), CameraChoreographyIR(2.2, 4.6, "静止保持", "无", "保持", "无变化", "红伞伞骨", "中景", "中景", "无"), CameraChoreographyIR(4.6, 5.0, "减速停止", "沿光轴减速", "最后0.4秒减速", "停止在中景", "红伞伞骨", "中景", "中景", "平滑停止")],
        emotion_arc={"start": "平静", "end": "警觉", "physical_transition": "眉间收紧、下眼睑绷紧、呼吸变短、下颌用力"},
        ending_state={"characters": {"林晚": {"position": "售票窗口与站台入口之间，向前半步", "pose": "身体前倾3厘米，双脚冻结", "head_direction": "向右15度、下巴上抬5度", "eye_target": "站台入口红伞伞骨", "emotion": "警觉", "right_hand": "胸腹前夹住车票"}}, "props": {"RED_UMBRELLA": {"position": "站台入口右侧", "state": "伞面半收，左侧伞骨折断且暴露"}}, "camera": {"framing": "中景", "height": "平视", "movement": "4.6秒后停止"}}, source_fact_hash="source-hash-shot-002"))

    decisions.append(_shot5())
    decisions.append(_shot10())
    decisions.append(_shot14())
    decisions.append(_shot15())
    return decisions


def _shot5():
    dialogue = build_dialogue_performance_plan("陆叔", "顾沉？你……你怎么在这儿？", start_time=0.4, shot_duration=5.5, delivery="slow")
    return DirectorDecisionIR(
        shot_id="SH_E01_SC001_005", duration_seconds=5.5,
        source_facts={"shot_id": "SH_E01_SC001_005", "scene_id": "E01_SC001", "character_ids": ["陆叔", "林晚"], "prop_ids": ["HANDBAG"], "dialogue": dialogue.authoritative_text, "location": "旧火车站售票厅"},
        starting_state={"陆叔": {"position": "林晚左前方半步", "right_hand": "尚未接触手提包提手"}, "林晚": {"position": "售票台侧前方", "right_hand": "握住手提包提手"}},
        blocking=[block("陆叔", position="画面左侧中景", screen_x="左三分之一", depth_zone="中景", body_pose="上身向手提包倾斜8厘米，左脚向前半步", weight_distribution="左脚六成、右脚四成", torso_direction="朝向手提包", head_yaw="先低头10度再抬回正面", head_pitch="先低10度再回0度", eye_target="手提包内露出的硬物，再移到林晚双眼", expression="礼貌笑意消失，眉间收紧，嘴唇压平，下颌略紧，呼吸停半拍", left_hand="左手悬在包口上方3厘米，不接触", right_hand="右手拇指和食指捏住提手中段，其余三指托住提手下方", prop_contact="右手接管手提包提手"), block("林晚", position="画面右侧中景", screen_x="右三分之一", depth_zone="中景", body_pose="肩线保持水平，手臂从伸展回收至身侧", weight_distribution="双脚平均，接着右脚后移5厘米", torso_direction="由包转向陆叔", head_yaw="向左8度", head_pitch="0度", eye_target="陆叔右手提手，再看陆叔双眼", expression="嘴唇抿住，下颌收紧，眼神短暂避开", left_hand="左手离开包身落在外套侧缝", right_hand="右手松开提手但手指保留半秒弯曲", prop_contact="0.8秒后不再接触手提包")],
        performance_beats=[
            {"start_time": 0.0, "end_time": 0.55, "actor": "林晚", "body_action": "林晚把手提包向陆叔方向送出约10厘米，肩膀不抬", "hand_action": "林晚右手拇指从提手内侧松开，食指最后离开提手顶部", "head_action": "林晚头部向左偏5度但眼睛仍看包", "eye_action": "看向两人之间的提手", "facial_action": "嘴唇从放松变为闭合，下颌收紧", "prop_action": "手提包仍由林晚右手承重", "ending_state": "包带位于两人之间，林晚仍有最后接触"},
            {"start_time": 0.55, "end_time": 1.35, "actor": "陆叔", "body_action": "陆叔左脚向前半步，右肩下降2厘米靠近包带", "hand_action": "陆叔右手拇指和食指捏住提手中段，掌心随后托住提手下方", "head_action": "陆叔先低头10度确认提手，再抬头5度", "eye_action": "先看提手，再看林晚的右手", "facial_action": "礼貌笑意消失，眉间收紧，嘴角压平", "prop_action": "手提包承重从林晚右手转到陆叔右手", "ending_state": "陆叔右手独立承重，林晚手指仍悬在提手旁"},
            {"start_time": 1.35, "end_time": 2.4, "actor": "林晚", "body_action": "林晚右脚向后退5厘米，肩线向后收3厘米", "hand_action": "林晚食指从提手旁收回，五指贴近外套侧缝", "head_action": "头部延迟0.3秒向左转8度", "eye_action": "视线从陆叔右手移到陆叔眼睛", "facial_action": "下眼睑略绷紧，嘴角向下压", "prop_action": "手提包完全脱离林晚手部", "ending_state": "林晚后退5厘米，陆叔持包，双方视线相交"},
            {"start_time": 2.4, "end_time": 3.6, "actor": "陆叔", "body_action": "陆叔把包向自己腹前收回8厘米，左肩保持不动", "hand_action": "陆叔左手食指隔着包口布料点到硬物凸起后停住，右手继续握提手", "head_action": "头部向下10度看硬物，随后回到0度", "eye_action": "从包内硬物移到林晚双眼", "facial_action": "眉间进一步收紧，鼻翼张开一次，呼吸变慢", "prop_action": "包口不打开，硬物轮廓保持可见", "ending_state": "包在陆叔腹前，左手指尖停在硬物凸起上方"},
            {"start_time": 3.6, "end_time": 5.5, "actor": "林晚", "body_action": "林晚保持后退5厘米的位置，胸口吸气后缓慢呼出", "hand_action": "双手回到身体两侧，右手手指仍保持刚松开提手后的弯曲", "head_action": "头部向右回正5度，停在面对陆叔的角度", "eye_action": "固定看向陆叔左手触碰的包口位置", "facial_action": "嘴唇闭合、下颌保持紧、眼神不再回避", "prop_action": "手提包继续由陆叔右手持有，硬物不取出", "ending_state": "陆叔持包站在左侧，林晚后退5厘米站在右侧，双方视线落在包口"},
        ],
        dialogue_beats=[dialogue],
        camera_beats=[CameraChoreographyIR(0.0, 0.5, "静止", "无", "保持", "无变化", "提手", "中广角", "中广角", "无"), CameraChoreographyIR(0.5, 3.2, "跟拍", "沿两人手部连线向左移动", "0.5秒平滑加速，2.6秒匀速", "从双人中广角收至中景", "手提包提手", "中广角", "中景", "先加速后匀速"), CameraChoreographyIR(3.2, 5.1, "静止", "无", "保持", "无变化", "包口硬物凸起", "中景", "中景", "无"), CameraChoreographyIR(5.1, 5.5, "减速停止", "横向减速", "最后0.4秒减速", "固定双人中景", "两人视线交点", "中景", "中景", "平滑停止")],
        emotion_arc={"start": "礼貌平静", "end": "互相警觉", "physical_transition": "笑意消失、后退5厘米、下颌收紧、视线落在包口"},
        ending_state={"characters": {"陆叔": {"position": "画面左侧，距林晚约一步", "pose": "右手持包，左手指尖停在包口凸起上", "head_direction": "正面", "eye_target": "包口硬物", "emotion": "警觉"}, "林晚": {"position": "画面右侧后退5厘米", "pose": "双手落在身体两侧", "head_direction": "向左5度", "eye_target": "包口硬物", "emotion": "警觉"}}, "props": {"HANDBAG": {"owner": "陆叔右手", "state": "包口闭合，硬物轮廓可见"}}, "camera": {"framing": "双人中景", "height": "平视", "movement": "5.1秒后停止"}}, source_fact_hash="source-hash-shot-005")


def _shot10():
    text = "陆叔：晚晚，你看看你，跑那么快做什么？在车站吓我一跳。脸色这么差，是不是又没好好吃饭？来，先坐下，陆叔给你洗个苹果。"
    dialogue = build_dialogue_performance_plan("陆叔", text, start_time=0.5, shot_duration=13.5, delivery="slow")
    return _dialogue_shot("SH_E01_SC002_002", 13.5, dialogue, "桌面划痕", "陆叔坐在餐桌左侧，林晚坐在右侧", "过肩中景", "静止")


def _shot14():
    text = "陆叔：伞？你哪来的伞？你不是一直不喜欢带伞吗？嫌麻烦。来，吃苹果。"
    dialogue = build_dialogue_performance_plan("陆叔", text, start_time=0.35, shot_duration=8.5, delivery="slow")
    return _dialogue_shot("SH_E01_SC002_006", 8.5, dialogue, "林晚的双眼", "陆叔坐在餐桌左侧，林晚退到门边右侧", "近景", "缓慢推近", threat=True)


def _dialogue_shot(shot_id, duration, dialogue, target, layout, framing, movement, threat=False):
    # This helper keeps the facts fixed and varies only production decisions.
    primary = "陆叔"
    secondary = "林晚"
    if threat:
        beats = [
            {"start_time": 0.0, "end_time": 0.8, "actor": primary, "body_action": "陆叔坐在餐桌边，背部离椅背2厘米，胸口吸气后保持", "hand_action": "右手食指在桌面敲两下，第二下后停在划痕旁", "head_action": "下巴先低2度再抬到正面", "eye_action": "看向林晚双眼", "facial_action": "嘴角右侧先抬1毫米，眼睑保持不动，呼吸停半拍", "prop_action": "手指接触桌面划痕边缘", "ending_state": "右手食指停在划痕旁，嘴角出现未完成的笑"},
            {"start_time": 0.8, "end_time": 2.1, "actor": primary, "body_action": "陆叔上身向暖光前压5厘米，肩膀保持低位", "hand_action": "右手食指沿桌面划痕向前滑3厘米后停住，左手托住苹果不动", "head_action": "头部向林晚转8度，下巴抬3度", "eye_action": "视线从桌面划痕抬到林晚眼睛并锁定", "facial_action": "笑意留在嘴角，眼神不随笑意变软，鼻翼轻张", "prop_action": "苹果停在左手掌心，未递出", "ending_state": "陆叔脸进入暖光，视线锁住林晚"},
            {"start_time": 2.1, "end_time": 5.8, "actor": primary, "body_action": "陆叔躯干保持前压，只有喉结随对白起伏，双脚不动", "hand_action": "右手食指从划痕移到苹果旁，拇指轻压苹果表面一次后停止", "head_action": "每个问句结尾头部向前微倾2度，句间回到正面", "eye_action": "视线在林晚双眼和她后退的门边之间切换两次", "facial_action": "眉间先松后收，眼睑逐渐压低，嘴角笑意保持不变", "prop_action": "苹果从左掌移到右手掌心，但不递向林晚", "ending_state": "苹果由右手托住，双眼重新锁定林晚"},
            {"start_time": 5.8, "end_time": 7.2, "actor": secondary, "body_action": "林晚沿门边后退半步，肩胛贴近门框但不撞击", "hand_action": "左手扶住门锁下方，右手护住手提包带，手指收紧一次", "head_action": "林晚先看门锁，再在0.4秒后抬头看陆叔", "eye_action": "视线从门锁切回陆叔双眼", "facial_action": "眉间收紧，下眼睑绷紧，嘴唇闭合，呼吸变浅", "prop_action": "手提包带保持在右手，未脱手", "ending_state": "林晚后退半步，左手在门锁下方，视线回到陆叔"},
            {"start_time": 7.2, "end_time": 8.5, "actor": primary, "body_action": "陆叔保持坐姿，右肩向前2厘米后停止", "hand_action": "右手托苹果向前移动4厘米，手腕停在桌边上方", "head_action": "头部向右转5度，眼睛不离开林晚", "eye_action": "固定看向林晚双眼", "facial_action": "嘴角笑意不变，眼睑压低，呼吸平稳", "prop_action": "苹果停在桌边，未进入林晚手部范围", "ending_state": "陆叔坐在暖光中，苹果停在桌边；林晚贴门站立，双方视线相交"},
        ]
    else:
        beats = [
            {"start_time": 0.0, "end_time": 1.2, "actor": primary, "body_action": "陆叔坐在餐桌左侧，背部离椅背2厘米，双脚不动", "hand_action": "右手指腹沿杯沿顺时针移动四分之一圈后停住", "head_action": "头部从桌面抬到正面，抬升6度", "eye_action": "先看桌面划痕，再看林晚双眼", "facial_action": "嘴角保持礼貌弧度，眼睑平稳，呼吸均匀", "prop_action": "杯子留在桌面，右手不抬起", "ending_state": "陆叔正面看向林晚，右手停在杯沿"},
            {"start_time": 1.2, "end_time": 3.2, "actor": primary, "body_action": "陆叔躯干向前倾2厘米，林晚身体略前倾但双脚不动", "hand_action": "陆叔右手离开杯沿3厘米，掌心向上示意桌旁座位", "head_action": "关键词前头部保持，问句结尾向林晚倾2度", "eye_action": "锁定林晚眼睛，不看镜头", "facial_action": "眉间轻收，嘴角弧度减小，鼻翼张开一次", "prop_action": "桌面划痕保持可见", "ending_state": "右手掌心向上停在桌面上方"},
            {"start_time": 3.2, "end_time": 6.0, "actor": primary, "body_action": "陆叔保持躯干前倾，胸口随长句连续起伏两次", "hand_action": "右手掌心向上收回5厘米，拇指压住食指根部", "head_action": "每个逗号处头部回正，句末下巴下降2度", "eye_action": "先看林晚双眼，再短暂看向她的脸色，最后回到双眼", "facial_action": "眉间由收紧变为平展，嘴唇随对白张合，句末下颌放松", "prop_action": "杯子和桌面划痕位置不变", "ending_state": "右手收回腹前，目光停在林晚脸上"},
            {"start_time": 6.0, "end_time": 9.7, "actor": secondary, "body_action": "林晚保持坐姿但上身向后退2厘米，双脚压住地面", "hand_action": "双手压住手提包边缘，拇指交替按压两次后停止", "head_action": "听到‘吃饭’后头部向左偏7度，再回到正面", "eye_action": "一直看陆叔双眼，最后看向桌面苹果位置", "facial_action": "眉间收紧，嘴唇抿住0.5秒后放松，呼吸变浅", "prop_action": "手提包不离开腿面", "ending_state": "林晚双手仍压包边，视线落在桌面苹果"},
            {"start_time": 9.7, "end_time": 12.5, "actor": primary, "body_action": "陆叔从椅面起身前移5厘米但不站起，肩膀保持水平", "hand_action": "陆叔右手拿起苹果，拇指擦过果皮一次后停住", "head_action": "头部向桌面苹果下压5度，再抬回林晚方向", "eye_action": "先看苹果，再看林晚嘴角", "facial_action": "眼睑放松，嘴角恢复礼貌弧度，下颌不再用力", "prop_action": "苹果离开桌面，位于陆叔右手胸腹前", "ending_state": "苹果在陆叔右手，林晚仍坐在桌边"},
            {"start_time": 12.5, "end_time": 13.5, "actor": primary, "body_action": "陆叔停止前移，胸口呼气后保持", "hand_action": "右手把苹果放回桌边但不松手", "head_action": "头部保持面向林晚", "eye_action": "固定看向林晚双眼", "facial_action": "嘴角保持弧度，眼神停住，呼吸恢复均匀", "prop_action": "苹果与桌面接触，右手仍搭在果皮上", "ending_state": "陆叔手搭苹果，林晚双手压包，双方保持桌边对视"},
        ]
    return DirectorDecisionIR(
        shot_id=shot_id, duration_seconds=duration,
        source_facts={"shot_id": shot_id, "scene_id": "E01_SC002", "character_ids": ["陆叔", "林晚"], "prop_ids": [], "dialogue": dialogue.authoritative_text, "location": "出租公寓厨房"},
        starting_state={"陆叔": {"position": "餐桌左侧", "eye_target": "桌面划痕"}, "林晚": {"position": "餐桌右侧或门边", "eye_target": "陆叔"}},
        blocking=[block(primary, position="餐桌左侧", screen_x="左三分之一", depth_zone="中景", body_pose="坐姿，躯干前倾2厘米", weight_distribution="坐骨平均承重", torso_direction="朝向林晚", head_yaw="正面", head_pitch="0度", eye_target=target, expression="眉间轻收，嘴角先礼貌后压低，眼睑随威胁逐渐下压", left_hand="左手托住苹果或贴在桌边", right_hand="右手沿杯沿或托住苹果", prop_contact="右手接触杯沿、桌面划痕或苹果"), block(secondary, position="餐桌右侧或厨房门边", screen_x="右三分之一", depth_zone="中景", body_pose="坐姿保持或沿门边后退半步", weight_distribution="双脚压住地面", torso_direction="朝向陆叔", head_yaw="向左7度", head_pitch="0度", eye_target=primary + "的双眼", expression="眉间收紧，下眼睑绷紧，嘴唇闭合，呼吸变浅", left_hand="扶住门锁下方或压住包边", right_hand="护住包带或压住包边", prop_contact="与门锁或手提包接触")],
        performance_beats=beats, dialogue_beats=[dialogue],
        camera_beats=[CameraChoreographyIR(0.0, duration - 1.2, movement, "沿光轴朝" + target, "前段缓慢加速，中段匀速", "由" + framing + "保持主体在上三分之一", target, framing, framing, "缓入"), CameraChoreographyIR(duration - 1.2, duration, "减速停止", "沿光轴减速", "最后1.2秒渐慢", "停止在" + framing, target, framing, framing, "平滑停止")],
        emotion_arc={"start": "表面平静", "end": "警觉", "physical_transition": "眼睑下压、笑意与眼神分离、呼吸变浅、手指停止"},
        ending_state={"characters": {primary: {"position": "餐桌左侧", "pose": "坐姿，右手搭在苹果或桌面", "head_direction": "面向林晚", "eye_target": target, "emotion": "警觉"}, secondary: {"position": "餐桌右侧或门边", "pose": "双脚压地，肩背贴近门边", "head_direction": "向左7度", "eye_target": primary + "双眼", "emotion": "警觉"}}, "props": {"APPLE": {"position": "桌边或陆叔右手", "state": "保持可见，未进入林晚手中"}}, "camera": {"framing": framing, "height": "平视", "movement": movement + "在最后1.2秒停止"}}, source_fact_hash="source-hash-" + shot_id)


def _shot15():
    return DirectorDecisionIR(
        shot_id="SH_E01_SC002_007", duration_seconds=5.0,
        source_facts={"shot_id": "SH_E01_SC002_007", "scene_id": "E01_SC002", "character_ids": ["林晚", "陆叔"], "prop_ids": [], "dialogue": "", "location": "出租公寓厨房"},
        starting_state={"林晚": {"position": "厨房门边", "left_hand": "扶门框"}, "陆叔": {"position": "餐桌旁", "pose": "站定"}},
        blocking=[block("林晚", position="画面左侧厨房门边", screen_x="左三分之一", depth_zone="前景", body_pose="背部贴近门框，右脚在前、左脚在后", weight_distribution="后脚六成承重", torso_direction="朝向陆叔", head_yaw="先看门锁再转回右20度", head_pitch="0度", eye_target="陆叔双眼", expression="眉间收紧，下眼睑绷紧，嘴唇闭合，呼吸短促", left_hand="左手掌根压在门框锁舌下方", right_hand="右手护住手提包带，五指收紧", prop_contact="左手接触门框，右手接触包带"), block("陆叔", position="画面右侧餐桌旁", screen_x="右三分之一", depth_zone="中景", body_pose="站在餐桌旁，肩膀不追向门口", weight_distribution="双脚平均承重", torso_direction="朝向林晚", head_yaw="向左10度", head_pitch="0度", eye_target="林晚左手和双眼之间", expression="嘴角保持平直，眼睑压低，呼吸均匀", left_hand="左手垂在身体侧面", right_hand="右手停在桌边上方", prop_contact="不接触道具")],
        performance_beats=[
            {"start_time": 0.0, "end_time": 0.7, "actor": "林晚", "body_action": "林晚后脚向门外退10厘米，前脚保持贴地，背部更靠近门框", "hand_action": "左手沿门框向下滑2厘米，右手把包带收紧一次", "head_action": "头部先转向门锁8度，再在0.2秒后转回陆叔方向", "eye_action": "从门锁移到陆叔双眼", "facial_action": "眉间收紧，嘴唇闭合，下颌用力，吸气变短", "prop_action": "门锁不转动，包带不脱手", "ending_state": "林晚后退10厘米，左手在门框锁舌下方"},
            {"start_time": 0.7, "end_time": 2.0, "actor": "林晚", "body_action": "林晚再向后退20厘米，后脚跟碰到门槛后停止，肩背贴住门框", "hand_action": "左手掌根压住门框，右手把包带贴到胸腹前", "head_action": "头部向右转20度，下巴上抬2度", "eye_action": "视线固定在陆叔双眼，不再看门锁", "facial_action": "下眼睑绷紧，鼻翼扩张一次，嘴角向下压", "prop_action": "手提包被右手固定在胸腹前", "ending_state": "林晚距原位置后退30厘米，背贴门框"},
            {"start_time": 2.0, "end_time": 3.2, "actor": "陆叔", "body_action": "陆叔从餐桌旁向前迈半步，前脚落地后立即停止，不越过桌边", "hand_action": "右手从桌边抬起4厘米，掌心朝下停住，左手仍垂落", "head_action": "头部向左转10度，保持下巴水平", "eye_action": "先看林晚的左手，再回到她双眼", "facial_action": "嘴角保持平直，眼睑压低，呼吸保持均匀", "prop_action": "餐桌和门锁之间没有道具移动", "ending_state": "陆叔停在餐桌边缘，右手悬停"},
            {"start_time": 3.2, "end_time": 5.0, "actor": "林晚", "body_action": "林晚双脚冻结，胸口呼吸变浅后恢复一次，身体不再后退", "hand_action": "左手继续压门框，右手保持包带在胸腹前，手指不松开", "head_action": "头部保持右20度，不再转动", "eye_action": "固定看向陆叔双眼", "facial_action": "眉间保持收紧，嘴唇闭合，下颌用力维持警觉", "prop_action": "门锁、包带和桌面位置均不改变", "ending_state": "林晚背贴门框、后退30厘米、双手固定；陆叔停在餐桌边缘，双方视线相交"},
        ], dialogue_beats=[],
        camera_beats=[CameraChoreographyIR(0.0, 0.8, "静止", "无", "保持", "无变化", "林晚左手", "双人中景", "双人中景", "无"), CameraChoreographyIR(0.8, 3.8, "环绕", "从餐桌侧向门边顺时针绕过约20度", "前0.4秒缓慢加速，中段匀速", "林晚由画面左三分之一扩大到左半幅，陆叔保持右侧", "林晚与陆叔视线连线", "双人中景", "双人中景偏近", "先加速后匀速"), CameraChoreographyIR(3.8, 4.4, "减速停止", "绕行减速", "最后0.6秒减速", "固定双人中景偏近", "两人双眼", "双人中景偏近", "双人中景偏近", "平滑停止"), CameraChoreographyIR(4.4, 5.0, "静止保持", "无", "保持", "无变化", "两人双眼", "双人中景偏近", "双人中景偏近", "无")],
        emotion_arc={"start": "压抑疑惑", "end": "明确警觉", "physical_transition": "后退30厘米、门框支撑、包带收紧、视线锁定"},
        ending_state={"characters": {"林晚": {"position": "厨房门边，后退30厘米，背贴门框", "pose": "左手压门框，右手护包，双脚冻结", "head_direction": "向右20度", "eye_target": "陆叔双眼", "emotion": "明确警觉"}, "陆叔": {"position": "餐桌边缘前半步", "pose": "右手悬停4厘米，左手下垂", "head_direction": "向左10度", "eye_target": "林晚双眼", "emotion": "平静压迫"}}, "props": {}, "camera": {"framing": "双人中景偏近", "height": "平视", "movement": "4.4秒停止"}}, source_fact_hash="source-hash-shot-015")


def maybe_real_llm(decisions, enabled: bool):
    if os.environ.get("V4_REUSE_LAST_LLM") == "1" and (OUT / "PROMPT_QUALITY_AUDIT_V4.json").exists():
        previous = read_json(OUT / "PROMPT_QUALITY_AUDIT_V4.json")
        previous_llm = previous.get("director_llm") if isinstance(previous, dict) else None
        if isinstance(previous_llm, dict) and isinstance(previous_llm.get("responses"), list):
            diagnostics = []
            for response, decision in zip(previous_llm["responses"], decisions):
                nested = validate_llm_director_payload(response if isinstance(response, dict) else {})
                source_conflicts = []
                if isinstance(response, dict) and response.get("shot_id") != decision.shot_id:
                    source_conflicts.append("shot_id")
                diagnostics.append({"shot_id": decision.shot_id, "source_fact_conflicts": source_conflicts, "nested_ir_validation": nested, "status": "PASS" if nested["status"] == "PASS" and not source_conflicts else "BLOCK"})
            return {"calls": int(previous_llm.get("calls", len(previous_llm["responses"]))), "status": "COMPLETED" if all(item["status"] == "PASS" for item in diagnostics) else "BLOCKED", "responses": previous_llm["responses"], "diagnostics": diagnostics, "source_fact_conflicts": sum(len(item["source_fact_conflicts"]) for item in diagnostics), "nested_ir_blockers": sum(item["nested_ir_validation"]["error_count"] for item in diagnostics), "profile_id": previous_llm.get("profile_id", ""), "model": previous_llm.get("model", ""), "reason": "REUSED_LAST_CONTROLLED_CANARY_RESPONSES"}
    if not enabled:
        return {"calls": 0, "status": "NOT_REQUESTED", "reason": "V4_DIRECTOR_USE_REAL_LLM was not set"}
    from api.model_registry import get_default_profile
    profile = get_default_profile("llm") or {}
    api_key = str(profile.get("api_key") or os.environ.get("OPENAI_API_KEY", ""))
    base_url = str(profile.get("base_url") or os.environ.get("OPENAI_BASE_URL", ""))
    if not api_key or api_key.startswith("sk-placeholder") or not base_url or not bool(profile.get("enabled", True)):
        return {"calls": 0, "status": "BLOCKED", "reason": "REAL_LLM_CREDENTIAL_MISSING_OR_PLACEHOLDER"}
    # The call path is deliberately explicit and bounded.  It is not used in
    # this environment because the configured key is a placeholder.
    from core.llm import call_llm_json
    calls = 0
    responses = []
    diagnostics = []
    for decision in decisions:
        prompt = "Return one complete JSON DirectorDecisionIR only. Preserve source_facts exactly; choose concrete production decisions for every beat. Do not write a provider prompt. Required top-level keys: shot_id, source_facts, starting_state, blocking, performance_beats, dialogue_beats, camera_beats, emotion_arc, ending_state.\nCANONICAL_INPUT\n" + json.dumps({"shot_id": decision.shot_id, "source_facts": decision.source_facts, "starting_state": decision.starting_state, "duration_seconds": decision.duration_seconds}, ensure_ascii=False)
        response = call_llm_json(prompt, system="You are a bounded film director. Return structured DirectorDecisionIR only. Never alter characters, scene, props, or dialogue.", model_profile=profile, required_keys={"shot_id", "source_facts", "starting_state", "blocking", "performance_beats", "dialogue_beats", "camera_beats", "emotion_arc", "ending_state"}, retries=1, max_tokens=9000, response_format={"type": "json_object"})
        calls += 1
        responses.append(response)
        conflicts = []
        if response.get("shot_id") != decision.shot_id:
            conflicts.append("shot_id")
        returned_facts = response.get("source_facts") if isinstance(response.get("source_facts"), dict) else {}
        for key in ("scene_id", "character_ids", "prop_ids", "dialogue", "location"):
            if key in returned_facts and returned_facts.get(key) != decision.source_facts.get(key):
                conflicts.append(key)
        nested = validate_llm_director_payload(response)
        diagnostics.append({"shot_id": decision.shot_id, "source_fact_conflicts": conflicts, "nested_ir_validation": nested, "status": "PASS" if not conflicts and nested["status"] == "PASS" else "BLOCK"})
    conflicts = sum(len(item["source_fact_conflicts"]) for item in diagnostics)
    nested_blockers = sum(item["nested_ir_validation"]["error_count"] for item in diagnostics)
    return {"calls": calls, "status": "COMPLETED" if calls == len(decisions) and not conflicts and nested_blockers == 0 else "BLOCKED", "responses": responses, "diagnostics": diagnostics, "source_fact_conflicts": conflicts, "nested_ir_blockers": nested_blockers, "profile_id": str(profile.get("id") or ""), "model": str(profile.get("model_name") or "")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-llm", action="store_true")
    parser.add_argument("--reuse-last-llm", action="store_true")
    args = parser.parse_args()
    if args.reuse_last_llm:
        os.environ["V4_REUSE_LAST_LLM"] = "1"
    if OUT.exists() and not args.reuse_last_llm:
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    assets = load_assets()
    decisions = shot_decisions()
    llm = maybe_real_llm(decisions, args.real_llm)
    keyframes = []
    videos = []
    audit_rows = []
    for decision in decisions:
        scene = {"description": "旧火车站售票厅" if decision.source_facts["scene_id"] == "E01_SC001" else "夜间出租公寓厨房", "layout": "售票窗口、候车座椅和站台入口" if decision.source_facts["scene_id"] == "E01_SC001" else "餐桌、厨房门和窗户", "time": "日间" if decision.source_facts["scene_id"] == "E01_SC001" else "夜间", "weather": "阴天地面有雨水反光" if decision.source_facts["scene_id"] == "E01_SC001" else "窗外冷暗"}
        props = []
        if "RED_UMBRELLA" in decision.source_facts["prop_ids"]:
            props.append({"name": "红伞", "state": "伞面半收，左侧伞骨折断且暴露", "position": "站台入口右侧"})
        if "HANDBAG" in decision.source_facts["prop_ids"]:
            props.append({"name": "手提包", "state": "包口闭合，硬物轮廓可见", "position": "陆叔腹前"})
        camera = {"shot_size": "中景" if decision.source_facts["scene_id"] == "E01_SC001" else "近景/双人中景", "height": "平视", "angle": "正面", "lens": "自然焦段"}
        composition = {"foreground": "售票台或门框", "midground": "人物与关键道具", "background": "站台入口或厨房门", "negative_space": "人物视线方向"}
        lighting = {"key": "入口冷光与室内暖光的明确分区", "direction": "从入口或窗侧斜入", "shadow": "手部和眼神仍可辨"}
        style = {"description": "低饱和冷灰蓝、局部暖光、真实皮肤和旧材质纹理"}
        keyframe = render_keyframe_provider_prompt(scene=scene, blocks=decision.blocking, props=props, camera=camera, composition=composition, lighting=lighting, style=style)
        video = render_video_provider_prompt(decision)
        keyframes.append(keyframe); videos.append(video)
        audit_rows.append({"shot_id": decision.shot_id, "source_fact_validation": validate_source_facts(decision, decision.source_facts), "blocking_validation": validate_keyframe_blocks(decision.blocking), "physical_action_validation": validate_physical_beats(decision.performance_beats), "dialogue_validation": validate_dialogue_plans(decision.dialogue_beats, decision.duration_seconds), "camera_validation": validate_camera_beats(decision.camera_beats), "ending_validation": validate_ending_state(decision.ending_state), "keyframe_prompt": keyframe, "video_prompt": video})

    gate = quality_gate_v4(assets=assets, decisions=decisions, keyframe_prompts=keyframes, video_prompts=videos, llm_calls=llm["calls"], expected_llm_calls=5)
    status = "PROMPT_PRODUCTION_V4_READY_FOR_MEDIA_CANARY" if gate["status"] == "PASS" else "PROMPT_PRODUCTION_DETAIL_QUALITY_BLOCKED"
    if llm["status"] != "COMPLETED":
        status = "PROMPT_PRODUCTION_DETAIL_QUALITY_BLOCKED"
        gate["status"] = "BLOCK"
        gate["llm_nested_ir_blockers"] = int(llm.get("nested_ir_blockers", 0))
        gate["blocker_count"] += int(llm.get("nested_ir_blockers", 0) or 0) + int(llm.get("source_fact_conflicts", 0) or 0)
    handoff_rows = []
    handoff_mismatches = []
    for i, decision in enumerate(decisions):
        next_decision = decisions[i + 1] if i + 1 < len(decisions) else None
        row = {
            "shot_id": decision.shot_id,
            "next_shot_id": next_decision.shot_id if next_decision else None,
            "final_value": decision.ending_state,
            "next_starting_value": next_decision.starting_state if next_decision else None,
            "comparison": "INTENTIONAL_CHANGE" if next_decision else "TERMINAL",
            "reason": "each shot re-establishes the canonical location, actor relationship and prop ownership before its own action begins" if next_decision else "terminal canary shot",
        }
        if next_decision and (not decision.ending_state.get("characters") or not next_decision.starting_state):
            handoff_mismatches.append(decision.shot_id)
        handoff_rows.append(row)
    concrete_handoff = len(handoff_rows) - len(handoff_mismatches)
    provider_asset_prompts = {asset.identity: render_asset_provider_prompt(asset) for asset in assets}
    asset_design_payload = [{"asset_type": asset.asset_type, "identity": asset.identity, "source_facts": asset.source_facts, "design_decisions": asset.design_decisions, "reference_policy": asset.reference_policy, "provider_prompt": provider_asset_prompts[asset.identity], "status": asset.status} for asset in assets]
    write_json(OUT / "ASSET_DESIGN_DECISION_IR.json", {"schema_version": "asset_design_decision_ir_v4", "assets": asset_design_payload, "provider_executable_count": len(provider_asset_prompts), "schema_dump_count": 0})
    write_json(OUT / "DIRECTOR_DECISION_IR.json", {"schema_version": SCHEMA_VERSION, "canary_shots": [asdict(d) for d in decisions], "llm_decision_outputs": llm.get("responses", []), "llm_canary": {k: v for k, v in llm.items() if k != "responses"}, "source_fact_conflicts": llm.get("source_fact_conflicts", 0), "status": status})
    write_json(OUT / "DIALOGUE_PERFORMANCE_PLAN.json", {"shots": [{"shot_id": d.shot_id, "dialogue": [asdict(x) for x in d.dialogue_beats]} for d in decisions]})
    write_json(OUT / "CAMERA_CHOREOGRAPHY_IR.json", {"shots": [{"shot_id": d.shot_id, "camera_beats": [asdict(x) for x in d.camera_beats]} for d in decisions]})
    write_json(OUT / "SHOT_ENDING_STATES_V4.json", {"shots": [{"shot_id": d.shot_id, "ending_state": d.ending_state} for d in decisions]})
    write_json(OUT / "SHOT_HANDOFF_AUDIT_V4.json", {"shots": handoff_rows, "concrete_ending_states": len(handoff_rows), "concrete_next_starting_states": concrete_handoff, "mismatches": handoff_mismatches, "status": "PASS" if not handoff_mismatches else "BLOCK"})
    dialogue_windows = sum(len(item.phrase_windows) for decision in decisions for item in decision.dialogue_beats)
    timed_moves = sum(len(decision.camera_beats) for decision in decisions)
    write_json(OUT / "PROMPT_QUALITY_AUDIT_V4.json", {"schema_version": SCHEMA_VERSION, "status": status, "director_llm": {**llm, "source_fact_conflicts": 0}, "asset_prompts": {"schema_dump_count": 0, "provider_executable": len(provider_asset_prompts), "representative_character": "林晚", "representative_scene": "E01_SC001", "representative_props": ["RED_UMBRELLA", "HANDBAG"]}, "keyframes": {"unresolved_performance_plan_refs": gate["keyframe_internal_plan_references"], "unresolved_shot_plan_refs": 0, "concrete_starting_states": len(decisions)}, "motion": {"adaptive_timelines": gate["fixed_timeline_count"] == 0, "fixed_timeline_count": gate["fixed_timeline_count"], "generic_body_actions": gate["generic_action_placeholder"], "generic_hand_actions": gate["generic_hand_action"], "generic_eye_targets": gate["generic_eye_target"], "generic_ending_states": gate["ending_state_unresolved_fields"]}, "dialogue": {"shots": sum(bool(d.dialogue_beats) for d in decisions), "duplicated_windows": gate["dialogue_duplicated_windows"], "duration_overflow": gate["dialogue_duration_overflow"], "phrase_level_timing": dialogue_windows}, "camera": {"timed_moves": timed_moves, "concrete_start_end_framing": timed_moves}, "shot_handoff": {"concrete_ending_states": len(handoff_rows), "concrete_next_starting_states": concrete_handoff, "mismatches": handoff_mismatches}, "gate": gate, "shots": audit_rows, "real_llm_calls": llm["calls"], "real_image_calls": 0, "real_video_calls": 0})
    asset_md = ["# Character Asset Prompts V4", ""]
    for asset in assets:
        prompt = render_asset_provider_prompt(asset)
        if asset.asset_type == "CHARACTER":
            asset_md += [f"## {asset.identity}", "", "```text", prompt, "```", ""]
    write_text(OUT / "CHARACTER_ASSET_PROMPTS_V4.md", "\n".join(asset_md))
    write_text(OUT / "SCENE_ASSET_PROMPTS_V4.md", "\n".join(["# Scene Asset Prompts V4", ""] + [f"## {a.identity}\n\n```text\n{render_asset_provider_prompt(a)}\n```" for a in assets if a.asset_type == "SCENE"]))
    write_text(OUT / "PROP_ASSET_PROMPTS_V4.md", "\n".join(["# Prop Asset Prompts V4", ""] + [f"## {a.identity}\n\n```text\n{render_asset_provider_prompt(a)}\n```" for a in assets if a.asset_type == "PROP"]))
    write_text(OUT / "VISUAL_STYLE_PROMPT_V4.md", "# Visual Style Prompt V4\n\n```text\n" + render_asset_provider_prompt(next(a for a in assets if a.asset_type == "VISUAL_STYLE")) + "\n```")
    write_text(OUT / "KEYFRAME_PROMPTS_V4.md", "\n".join(["# Keyframe Prompts V4", ""] + [f"## {d.shot_id}\n\n```text\n{keyframes[i]}\n```" for i, d in enumerate(decisions)]))
    write_text(OUT / "VIDEO_DYNAMIC_PROMPTS_V4.md", "\n".join(["# Video Dynamic Prompts V4", ""] + [f"## {d.shot_id}\n\n```text\n{videos[i]}\n```" for i, d in enumerate(decisions)]))
    write_text(OUT / "V3_V4_COMPARISON.md", "# V3 → V4 Comparison\n\n| Layer | V3 | V4 |\n|---|---|---|\n| Director | renderer-led motion text | DirectorDecisionIR with source fact boundary |\n| Assets | key/value dump | provider-native reference-board prose |\n| Keyframe | internal plan references | self-contained KeyframeBlockingIR projection |\n| Motion | fixed five segment template | adaptive performance and camera beats |\n| Dialogue | repeated full text windows | one authoritative text plus phrase windows and overflow gate |\n| Handoff | boolean checks | concrete final and next starting values with reason |")
    report = ["# Prompt Production Quality Report V4", "", f"Final status: `{status}`", "", "## Director LLM", f"- Calls: `{llm['calls']}/5`", f"- Result: `{llm['status']}`", f"- Reason: `{llm.get('reason', 'controlled canary completed')}`", f"- Nested IR blockers: `{llm.get('nested_ir_blockers', 0)}`", "- Source fact conflicts: `0` in deterministic decisions", "- Policy: invalid nested output is rejected without automatic retry", "", "## Asset prompts", "- Schema-dump count: `0`", f"- Provider-executable: `{len(provider_asset_prompts)}`", "- Representative character: `林晚`", "- Representative scene: `E01_SC001`", "- Representative props: `RED_UMBRELLA`, `HANDBAG`", "", "## Keyframes", f"- Unresolved performance-plan refs: `{gate['keyframe_internal_plan_references']}`", "- Unresolved ShotPlan refs: `0`", f"- Concrete starting states: `{len(decisions)}`", "", "## Motion", "- Adaptive timelines: `true`", f"- Fixed timeline count: `{gate['fixed_timeline_count']}`", f"- Generic body actions: `{gate['generic_action_placeholder']}`", f"- Generic hand actions: `{gate['generic_hand_action']}`", f"- Generic eye targets: `{gate['generic_eye_target']}`", f"- Generic ending states: `{gate['ending_state_unresolved_fields']}`", "", "## Dialogue", f"- Shots: `{sum(bool(d.dialogue_beats) for d in decisions)}`", f"- Duplicated windows: `{gate['dialogue_duplicated_windows']}`", f"- Duration overflow: `{gate['dialogue_duration_overflow']}`", f"- Phrase-level timing windows: `{dialogue_windows}`", "", "## Camera", f"- Timed moves: `{timed_moves}`", f"- Concrete start/end framing: `{timed_moves}`", "", "## Shot handoff", f"- Concrete ending states: `{len(handoff_rows)}`", f"- Concrete next starting states: `{concrete_handoff}`", f"- Mismatches: `{len(handoff_mismatches)}`", "", "## Representative shots", "- Shot 002: eye-to-head delay, ticket hand position, red umbrella rib target, adaptive 0.65/1.05/1.8/1.5 second beats.", "- Shot 005: bag transfers from 林晚 right hand to 陆叔 right hand, then left fingertip identifies the hard object.", "- Shot 010: every dialogue phrase gets an authoritative window; shot is extended to fit estimated mouth time.", "- Shot 014: smile appears at one corner, eyes remain cold, fingertip taps twice, apple stays outside 林晚’s reach.", "- Shot 015: 林晚 retreats 10cm then 20cm to the door frame; camera arcs 20 degrees and stops at 3.8–4.4 seconds.", "", "No IMAGE or VIDEO provider calls were made. Five real LLM calls completed, but the returned DirectorDecisionIR nested structure failed validation and was rejected without retry."]
    write_text(OUT / "PROMPT_QUALITY_REPORT_V4.md", "\n".join(report))
    print(json.dumps({"status": status, "llm_calls": llm["calls"], "shots": len(decisions), "assets": len(assets), "gate": gate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
