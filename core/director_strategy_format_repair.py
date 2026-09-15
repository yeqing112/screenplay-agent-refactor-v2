"""Provider-free protocol repair packet for Strategy IR."""
from __future__ import annotations

from typing import Any

from core.director_scene_strategy_semantic_spec import build_provider_skeleton


def build_strategy_format_repair_packet(*, errors: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    """Create a minimal shape/ID repair instruction.

    The packet contains no semantic rewrite instruction and never calls a
    provider.  It is safe to send in a future FORMAT_REPAIR attempt.
    """
    skeleton = build_provider_skeleton(
        scene_id=str(contract.get("scene_id") or ""),
        beat_ids=[str(x) for x in contract.get("beat_ids", [])],
        character_ids=[str(x) for x in contract.get("character_ids", [])],
        fact_ids=[str(x) for x in contract.get("fact_ids", [])],
    )
    normalized = []
    for error in errors or []:
        if isinstance(error, dict):
            normalized.append({key: error[key] for key in ("code", "path", "expected", "allowed", "beat_id", "character_id") if key in error})
        else:
            normalized.append({"code": str(error)})
    return {
        "schema_version": "director_strategy_format_repair_packet_v1",
        "repair_scope": "protocol_only",
        "semantic_rewrite_allowed": False,
        "creative_content_mutation": False,
        "errors": normalized,
        "allowed_beat_ids": list(contract.get("beat_ids", [])),
        "allowed_character_ids": list(contract.get("character_ids", [])),
        "minimal_correct_skeleton": skeleton["minimal_skeleton"],
        "provider_contract": skeleton,
        "provider_calls": 0,
    }


__all__ = ["build_strategy_format_repair_packet"]
