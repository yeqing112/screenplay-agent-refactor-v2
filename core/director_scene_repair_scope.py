"""Authoritative scope for scene-level creative repair."""
from __future__ import annotations

SCENE_REPAIR_SCOPE_SCHEMA_VERSION = "director_scene_repair_scope_v1"
SCENE_MUTABLE_FIELDS = (
    "camera.*", "composition.*", "performance_direction.*", "emotion.*",
    "edit.*", "information_strategy.*", "why_this_shot", "purpose",
    "dramatic_function", "visual_emphasis",
)
SCENE_IMMUTABLE_FIELDS = (
    "scene_id", "scene_name", "beat_id", "beat_order", "event", "dialogue",
    "participants", "character_id", "asset_bindings", "prop_ownership",
    "location", "scene_canonical", "entry_state", "exit_state",
    "continuity_contract", "continuity", "source_spatial_facts", "spatial_source",
    "chronology", "plan_shot_id", "shot_count", "shot_order",
)
SCENE_ALLOWED_DIMENSIONS = (
    "DRAMATIC_CLARITY", "SHOT_MOTIVATION", "EMOTIONAL_PROGRESSION",
    "VISUAL_STORYTELLING", "SPATIAL_CLARITY", "PERFORMANCE_DIRECTION",
    "EDIT_RHYTHM", "INFORMATION_STRATEGY", "POWER_DYNAMICS", "SHOT_DIVERSITY",
)

__all__ = ["SCENE_REPAIR_SCOPE_SCHEMA_VERSION", "SCENE_MUTABLE_FIELDS", "SCENE_IMMUTABLE_FIELDS", "SCENE_ALLOWED_DIMENSIONS"]
