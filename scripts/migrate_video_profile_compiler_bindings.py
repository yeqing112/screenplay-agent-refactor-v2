"""Explicit, auditable migration for persisted 75api H3 video profiles."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.model_registry import list_profiles, resolve_defaults, save_registry

OUT = ROOT / "docs" / "video-compiler" / "v1-closure" / "MODEL_PROFILE_COMPILER_BINDING_MIGRATION.json"


def _safe(profile: dict) -> dict:
    return {key: profile.get(key) for key in ("id", "provider", "model_name", "video_compiler_id", "model_family")}


def migrate(*, promote_default_model: bool = False) -> dict:
    profiles = list_profiles(include_sensitive=True)
    defaults = resolve_defaults()
    changes: list[dict] = []
    normalized: list[dict] = []
    for profile in profiles:
        item = dict(profile)
        if str(item.get("provider") or "") == "75api-minimax-h3" and str(item.get("model_name") or "") in {"minimax_h3", "minimax_h3_no_audios"}:
            before = _safe(item)
            item["video_compiler_id"] = "minimax-h3"
            item["model_family"] = "minimax-h3"
            if promote_default_model:
                item["model_name"] = "minimax_h3"
            after = _safe(item)
            if before != after:
                changes.append({"profile_id": item.get("id"), "provider": item.get("provider"), "model_name": after.get("model_name"), "before": before, "after": after})
        normalized.append(item)
    if changes:
        result = save_registry(profiles=normalized, defaults=defaults)
        normalized = result.get("profiles") or normalized
    audit = {"status": "PASS", "migration": "MODEL_PROFILE_COMPILER_BINDING_MIGRATION", "changes": changes, "api_keys_recorded": False, "real_image_calls": 0, "real_video_calls": 0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    print(json.dumps(migrate(promote_default_model="--promote-default-model" in sys.argv), ensure_ascii=False, indent=2))
