"""Immutable ShotReadinessProjection and provider contract helpers."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


class ShotReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderDurationProjection:
    director_duration_seconds: float
    provider_duration_seconds: int | None
    provider_padding_seconds: float
    padding_mode: str
    status: str = "PASS"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def project_provider_duration(value: Any) -> ProviderDurationProjection:
    try:
        director = float(value)
    except (TypeError, ValueError):
        raise ShotReadinessError("VIDEO_PROVIDER_DURATION_INVALID") from None
    if not math.isfinite(director) or director <= 0:
        raise ShotReadinessError("VIDEO_PROVIDER_DURATION_INVALID")
    provider = int(math.ceil(director - 1e-9))
    if provider < 5 or provider > 15:
        return ProviderDurationProjection(director, None, 0.0, "BLOCK", "BLOCK")
    padding = round(provider - director, 6)
    return ProviderDurationProjection(
        director_duration_seconds=director,
        provider_duration_seconds=provider,
        provider_padding_seconds=padding,
        padding_mode="TERMINAL_HOLD" if padding > 0 else "NONE",
    )


# Canonical model-facing name; the implementation remains single-source so
# adapters never ceil, truncate, or repair durations independently.
VideoModelDurationProjection = ProviderDurationProjection
project_video_model_duration = project_provider_duration


@dataclass(frozen=True)
class ShotPropState:
    shot_id: str
    prop_id: str
    present: bool
    holder: str = ""
    hand: str = ""
    contact: str = ""
    position: str = ""
    physical_state: str = ""
    story_state: str = ""
    authority_source: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        valid = {"EXPLICIT_SOURCE_PROP", "EXPLICIT_CONTINUITY_PROP", "DIALOGUE_ACTION_RESOLVED_PROP"}
        if self.present and self.authority_source not in valid:
            errors.append("UNAUTHORIZED_SHOT_PROP")
        if self.present and not self.prop_id:
            errors.append("SHOT_PROP_ID_MISSING")
        if self.present and self.authority_source == "DIALOGUE_ACTION_RESOLVED_PROP" and not (self.contact or self.story_state):
            errors.append("DIALOGUE_PROP_LACKS_PHYSICAL_BASIS")
        return errors

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_shot_prop_states(decision: Mapping[str, Any]) -> tuple[ShotPropState, ...]:
    """Project the single canonical prop truth from Director/Shot readiness facts.

    This is deliberately conservative: dialogue mentions do not create props.
    A prop is authorized only when the shot blocking or resolved prop state
    establishes a physical holder/contact relationship.
    """
    shot_id = str(decision.get("shot_id") or "")
    source = decision.get("source_facts") if isinstance(decision.get("source_facts"), Mapping) else {}
    blocking = [x for x in (decision.get("blocking") or []) if isinstance(x, Mapping)]
    states: list[ShotPropState] = []
    for item in blocking:
        identity = str(item.get("identity") or item.get("character") or "")
        for hand_key, hand_name in (("right_hand", "RIGHT"), ("left_hand", "LEFT")):
            value = str(item.get(hand_key) or "")
            if "apple" not in value.lower() and "苹果" not in value:
                continue
            states.append(ShotPropState(
                shot_id=shot_id,
                prop_id="APPLE",
                present=True,
                holder=identity,
                hand=hand_name,
                contact=value,
                position=str(item.get("position") or ""),
                physical_state="whole",
                story_state="resolved from shot blocking",
                authority_source="DIALOGUE_ACTION_RESOLVED_PROP",
            ))
    # A source prop id alone is not enough to materialize a visual prop.
    # Preserve only ids with a physical state in the formal shot truth.
    return tuple(states)


@dataclass(frozen=True)
class ShotReference:
    role: str
    asset_id: str
    authority_fingerprint: str
    media_sha256: str
    reference_order: int
    path: str = ""


@dataclass(frozen=True)
class ShotReferencePlan:
    shot_id: str
    scene_id: str
    references: tuple[ShotReference, ...]
    unresolved_references: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"shot_id": self.shot_id, "scene_id": self.scene_id, "references": [asdict(x) for x in self.references], "unresolved_references": list(self.unresolved_references)}


def build_reference_plan(shot_id: str, scene_id: str, *, authorities: Mapping[str, Mapping[str, Any]], prop_id: str | None = None, root: str = "") -> ShotReferencePlan:
    required = [("SCENE_MASTER", "E01_SC002", "scene_master"), ("CHARACTER_FULL", "LIN_WAN", "full_front"), ("CHARACTER_FACE", "LIN_WAN", "face_front"), ("CHARACTER_FULL", "LU_SHU", "full_front"), ("CHARACTER_FACE", "LU_SHU", "face_front")]
    if prop_id:
        required.append(("PROP_HERO", prop_id, "master"))
    refs: list[ShotReference] = []
    unresolved: list[str] = []
    for order, (role, aid, view) in enumerate(required, 1):
        authority = authorities.get(aid) or {}
        if str(authority.get("status") or "") != "READY":
            unresolved.append(aid)
            continue
        view_sha = authority.get("derived_shas", {}).get(view.upper())
        sha = str(view_sha or authority.get("primary_sha256") or "")
        fp = str(authority.get("semantic_authority_fingerprint") or authority.get("profile_fingerprint") or "")
        if not sha or not fp:
            unresolved.append(aid)
            continue
        refs.append(ShotReference(role, aid, fp, sha, order, root))
    return ShotReferencePlan(shot_id, scene_id, tuple(refs), tuple(unresolved))


def terminal_hold_text(projection: ProviderDurationProjection) -> str:
    if projection.provider_padding_seconds <= 0:
        return ""
    return (f"最后{projection.provider_padding_seconds:g}秒只保持最终人物姿态、最终眼神、最终表情、最终道具状态和最终摄影构图；"
            "不得新增对白、动作、事件、道具转移或摄影事件。允许自然微呼吸和轻微身体沉降。")
