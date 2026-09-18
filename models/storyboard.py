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
    # Production authority identity. Legacy rows may remain NULL and are
    # intentionally not eligible for production without explicit migration.
    scene_id = Column(String, nullable=True, index=True)
    plan_shot_id = Column(String, nullable=True, index=True)
    materialization_set_id = Column(Integer, nullable=True, index=True)
    source_shot_plan_id = Column(Integer, nullable=True, index=True)
    source_shot_plan_revision = Column(Integer, nullable=True)
    source_shot_plan_authority_fingerprint = Column(String, nullable=True, index=True)
    projection_fingerprint = Column(String, nullable=True, index=True)
    materialization_status = Column(String, nullable=False, default="LEGACY")
    shot_id = Column(Integer, nullable=False)          # 全局顺序镜号（整集递增）

    # 对话/叙事
    dialogue = Column(Text, default="")                # 对白/旁白文本
    duration = Column(Integer, default=3)              # 预估时长（秒）

    # 镜头语言
    camera_angle = Column(String, default="MS")        # WS/MS/CU/ECU
    camera_movement = Column(String, default="static") # static/push-in/pan/dolly/zoom/crane
    camera_speed = Column(String, default="slow")      # slow/medium/fast
    shot_purpose = Column(String, default="emotion")   # establishing/action/reveal/emotion...
    transition = Column(String, default="cut")         # cut/fade/dissolve/whip
    lighting = Column(Text, default="")

    # 导演情绪弧线（JSON：{start, end, intensity}）。保留为结构化字段，
    # 同时在 meta_info 中继续兼容旧版本扩展数据。
    emotion_arc = Column(Text, default="{}")

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

    # V2 unified state protocol; ``asset_status`` and legacy status semantics
    # remain for compatibility while these fields become production authority.
    execution_status = Column(String, default="queued", nullable=False)
    quality_status = Column(String, default="draft", nullable=False)
    production_status = Column(String, default="blocked", nullable=False)
    workflow_profile = Column(String, default="creative_draft", nullable=False)

    # 元数据
    meta_info = Column(Text, default="{}")              # JSON 扩展
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class StoryboardMaterializationSet(Base):
    """Versioned deterministic projection of one authoritative ShotPlan."""

    __tablename__ = "storyboard_materialization_sets"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    shot_plan_id = Column(Integer, nullable=False, index=True)
    shot_plan_revision = Column(Integer, nullable=False)
    shot_plan_payload_hash = Column(String, nullable=False)
    shot_plan_authority_fingerprint = Column(String, nullable=False, index=True)
    expected_shot_count = Column(Integer, nullable=False)
    materialized_shot_count = Column(Integer, nullable=False, default=0)
    ordered_plan_shot_ids = Column(Text, nullable=False, default="[]")
    set_payload_fingerprint = Column(String, nullable=False, unique=True)
    materializer_version = Column(String, nullable=False)
    materializer_policy_version = Column(String, nullable=False)
    authority_envelope_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="MATERIALIZED")
    stale_status = Column(String, nullable=False, default="FRESH")
    stale_reasons = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.now)
    activated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.now)


class StoryboardMaterializationPointer(Base):
    """Explicit scene -> current materialization set selection."""

    __tablename__ = "storyboard_materialization_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    scene_id = Column(String, nullable=False, index=True)
    materialization_set_id = Column(Integer, nullable=False, unique=True)
    shot_plan_id = Column(Integer, nullable=False)
    shot_plan_revision = Column(Integer, nullable=False)
    set_payload_fingerprint = Column(String, nullable=False)
    qualification_state = Column(String, nullable=False, default="MATERIALIZED")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
