"""Shared snapshot helpers for scene-reference plans.

The plan, enqueue and apply stages must agree on what makes a scene plan
stale.  Keeping this deterministic helper in ``core`` prevents one stage from
silently accepting an asset change that another stage would reject.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCENE_REFERENCE_SNAPSHOT_FIELDS = (
    "id", "book_id", "name", "category", "style", "description",
    "color_palette", "lighting_mood", "key_props", "episodes", "time_period",
    "visual_prompt_zh", "core_prompt_zh", "scene_mood_zh", "canonical_facts",
    "state_variants", "look_profile", "board_spec", "importance", "notes",
    "shot_ids", "jimeng_ref_name", "negative_prompt", "asset_status", "updated_at",
)


def scene_location_snapshot(row: Any) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for field in SCENE_REFERENCE_SNAPSHOT_FIELDS:
        value = getattr(row, field, "")
        if field == "updated_at" and value is not None and hasattr(value, "isoformat"):
            value = value.isoformat()
        snapshot[field] = str(value if value is not None else "")
    return snapshot


def scene_location_fingerprint(row: Any) -> str:
    payload = json.dumps(scene_location_snapshot(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

