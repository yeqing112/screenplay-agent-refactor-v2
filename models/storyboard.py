"""Storyboard model — 分镜头表。"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from .base import Base


class StoryboardShot(Base):
    """分镜头 — 每个 shot 就是分镜表中的一行。"""
    __tablename__ = "storyboard_shots"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)
    episode = Column(Integer, nullable=False)

    # 分镜标识
    scene_name = Column(String, nullable=False)       # 场景名 → visual_locations.name
    shot_id = Column(Integer, nullable=False)          # 全局顺序镜号（整集递增）

    # 对话/叙事
    dialogue = Column(Text, default="")                # 对白/旁白文本
    duration = Column(Integer, default=3)              # 预估时长（秒）

    # 镜头语言
    camera_angle = Column(String, default="MS")        # WS/MS/CU/ECU
    camera_movement = Column(String, default="static") # static/push-in/pan/dolly/zoom/crane
    transition = Column(String, default="cut")         # cut/fade/dissolve/whip
    lighting = Column(Text, default="")

    # 音效
    sound_effects = Column(Text, default="[]")         # JSON 数组
    bgm_mood = Column(String, default="")

    # 动作时序（结构化）
    start_state = Column(Text, default="")             # 镜头开始时状态
    action_process = Column(Text, default="")          # 过程中发生什么
    end_state = Column(Text, default="")               # 镜头结束状态

    # 提示词体系（三层）
    visual_prompt_static = Column(Text, default="")    # 分镜提示词（静态核心画面）
    visual_prompt_motion = Column(Text, default="")    # 视频运动提示词（动态时序）
    visual_prompt_final = Column(Text, default="")     # 合成提示词（后期回填）

    # 资产管理
    asset_links = Column(Text, default="{}")           # JSON: Phase 2 回填资产路径
    asset_status = Column(String, default="pending")   # pending/asset_pending/asset_ready/video_pending/done/failed

    # 元数据
    meta_info = Column(Text, default="{}")              # JSON 扩展
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
