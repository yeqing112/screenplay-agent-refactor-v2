"""Cross-intent semantic consistency gates for video generation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping

from .shot_readiness import ShotPropState
from .video_intent_ir import VideoIntentIR


@dataclass(frozen=True)
class VideoIntentSemanticConsistencyAudit:
    status: str
    checks: Mapping[str, Any]
    conflicts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"checks": dict(self.checks), "conflicts": list(self.conflicts)}


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).lower()


def audit_video_intent_semantics(intent: VideoIntentIR, canonical_props: tuple[ShotPropState, ...] | None = None) -> VideoIntentSemanticConsistencyAudit:
    conflicts: list[str] = []
    checks: dict[str, Any] = {"prop_holder": "PASS", "prop_hand": "PASS", "performance_beats": "PASS", "ending_state": "PASS", "authority": "PASS"}
    props = canonical_props or tuple(ShotPropState(
        intent.shot_id,
        str(item.get("prop_id") or item.get("id") or ""),
        bool(item.get("present")),
        str(item.get("holder") or ""),
        str(item.get("hand") or ""),
        str(item.get("contact") or ""),
        str(item.get("position") or ""),
        str(item.get("physical_state") or ""),
        str(item.get("story_state") or ""),
        str(item.get("authority_source") or ""),
    ) for item in intent.props)
    char_by_id = {x.character_id: x for x in intent.characters}
    for prop in props:
        if not prop.present:
            continue
        if prop.authority_source not in {"EXPLICIT_SOURCE_PROP", "EXPLICIT_CONTINUITY_PROP", "DIALOGUE_ACTION_RESOLVED_PROP"}:
            checks["authority"] = "FAIL"; conflicts.append("UNAUTHORIZED_SHOT_PROP")
        holder = char_by_id.get(prop.holder)
        if holder is None:
            checks["prop_holder"] = "FAIL"; conflicts.append("VIDEO_INTENT_PROP_HOLDER_CONFLICT"); continue
        hand_key = "right_hand" if prop.hand.upper() == "RIGHT" else "left_hand" if prop.hand.upper() == "LEFT" else ""
        holder_hand = str(holder.start_state.get(hand_key) or "") if hand_key else ""
        prop_token = prop.prop_id.lower()
        if not any(token in holder_hand.lower() for token in (prop_token, "apple" if prop.prop_id == "APPLE" else prop_token)):
            checks["prop_hand"] = "FAIL"; conflicts.append("VIDEO_INTENT_PROP_HOLDER_CONFLICT")
        for other in intent.characters:
            if other.character_id == prop.holder:
                continue
            other_text = _text(other.start_state)
            if prop_token in other_text or (prop.prop_id == "APPLE" and "apple" in other_text):
                checks["prop_holder"] = "FAIL"; conflicts.append("VIDEO_INTENT_PROP_HOLDER_CONFLICT")
        performance = _text(intent.performance_beats)
        ending = _text(intent.ending_state)
        if prop.prop_id == "APPLE" and "apple" in performance and prop.holder.lower() not in performance:
            checks["performance_beats"] = "FAIL"; conflicts.append("VIDEO_INTENT_PROP_HOLDER_CONFLICT")
        if prop.prop_id == "APPLE" and "apple" in ending and prop.holder.lower() not in ending:
            checks["ending_state"] = "FAIL"; conflicts.append("VIDEO_INTENT_PROP_HOLDER_CONFLICT")
    conflicts = list(dict.fromkeys(conflicts))
    return VideoIntentSemanticConsistencyAudit("PASS" if not conflicts else "FAIL", checks, tuple(conflicts))


__all__ = ["VideoIntentSemanticConsistencyAudit", "audit_video_intent_semantics"]
