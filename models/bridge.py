"""Bridge models — 场景×人物×道具的关联表。"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from .base import Base


class SceneCharacter(Base):
    """场景-人物桥接表：角色在某个场景中的具体状态。

    VisualLocation(name=episode) ←→ CharacterProfile(name)
    """
    __tablename__ = "scene_characters"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)

    # 关联：场景名 + 集号 → VisualLocation
    location_name = Column(String, nullable=False)
    episode = Column(Integer, nullable=False)

    # 关联：角色名 → CharacterProfile
    character_name = Column(String, nullable=False)

    # 在该场景中的具体状态
    state = Column(Text, default="")           # "浑身酒气，头发被扯乱"
    outfit = Column(Text, default="")          # 该场景中实际穿着（可覆盖 profile 通用描述）
    makeup = Column(Text, default="")          # 该场景中妆容
    expression = Column(Text, default="")      # 表情基调（"恐惧中带着倔强"）
    action = Column(Text, default="")          # 该场景中关键动作
    dialogue_tone = Column(Text, default="")   # 该场景中说话语气

    # 元数据
    importance = Column(String, default="medium")
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.now)


class SceneProp(Base):
    """场景-道具桥接表：某个道具在具体场景中的状态。

    VisualLocation(name=episode) ←→ VisualProp(name)
    """
    __tablename__ = "scene_props"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False)

    # 关联场景
    location_name = Column(String, nullable=False)
    episode = Column(Integer, nullable=False)

    # 关联道具
    prop_name = Column(String, nullable=False)

    # 在该场景中的具体状态
    placement = Column(Text, default="")       # 摆放位置（"茶几上，已碎裂"）
    in_use_by = Column(String, default="")     # 使用角色名
    condition = Column(Text, default="")       # 状态（"完好" / "破碎" / "磨损"）

    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
