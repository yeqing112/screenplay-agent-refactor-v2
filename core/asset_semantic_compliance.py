"""Semantic purity contracts for canonical character and prop media."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Iterable, Mapping


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CharacterSemanticAuthority:
    """Canonical semantic boundary derived from Character/Variant/Prop bindings."""

    character_id: str
    name: str
    allowed_costume: list[str] = field(default_factory=list)
    allowed_accessories: list[str] = field(default_factory=list)
    allowed_story_props: list[str] = field(default_factory=list)
    forbidden_persistent_props: list[str] = field(default_factory=list)
    source_fingerprint: str = ""

    @classmethod
    def from_character(cls, character: Mapping[str, Any]) -> "CharacterSemanticAuthority":
        semantic = dict(character.get("semantic_authority") or {})
        allowed_costume = [str(item) for item in semantic.get("allowed_costume") or []]
        if not allowed_costume:
            allowed_costume = [str(character.get("description") or "")]
        allowed_accessories = [str(item) for item in semantic.get("allowed_accessories") or []]
        allowed_story_props = [str(item) for item in semantic.get("allowed_story_props") or []]
        forbidden = [str(item) for item in semantic.get("forbidden_persistent_props") or [
            "handbag", "shoulder bag", "crossbody bag", "backpack", "umbrella", "suitcase", "shopping bag",
            "phone", "weapon", "food", "document", "unrelated story prop",
        ]]
        payload = {
            "character_id": character.get("id"), "name": character.get("name"),
            "allowed_costume": allowed_costume, "allowed_accessories": allowed_accessories,
            "allowed_story_props": allowed_story_props, "forbidden_persistent_props": forbidden,
        }
        return cls(str(character.get("id") or ""), str(character.get("name") or ""), allowed_costume, allowed_accessories, allowed_story_props, forbidden, _fingerprint(payload))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ViewPoseCompliance:
    view_id: str
    status: str
    view_pose_compliance: int
    framing_compliance: int
    critical_view_violation: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    judge_status: str = ""
    score_scale: str = "0-100"

    def __post_init__(self) -> None:
        if self.score_scale != "0-100" or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100 for value in (self.view_pose_compliance, self.framing_compliance)):
            raise ValueError("VIEW_POSE_INVALID_SCORE_SCALE")

    @property
    def passes(self) -> bool:
        return self.status == "PASS" and self.view_pose_compliance >= 85 and self.framing_compliance >= 85 and not self.critical_view_violation


@dataclass(frozen=True)
class AssetSemanticComplianceAudit:
    view_id: str
    asset_type: str
    status: str
    canonical_identity_match: bool
    canonical_costume_match: bool
    allowed_accessories: list[str] = field(default_factory=list)
    detected_accessories: list[str] = field(default_factory=list)
    detected_props: list[str] = field(default_factory=list)
    unauthorized_accessories: list[str] = field(default_factory=list)
    unauthorized_props: list[str] = field(default_factory=list)
    extra_people: bool = False
    text_or_watermark: bool = False
    view_pose_compliance: int = 100
    framing_compliance: int = 100
    critical_view_violation: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    judge_status: str = ""
    attempt_number: int = 1
    semantic_authority_fingerprint: str = ""
    score_scale: str = "0-100"

    def __post_init__(self) -> None:
        if self.score_scale != "0-100" or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100 for value in (self.view_pose_compliance, self.framing_compliance)):
            raise ValueError("SEMANTIC_JUDGE_INVALID_SCORE_SCALE")

    @property
    def passes(self) -> bool:
        return (
            self.status == "PASS" and self.canonical_identity_match and self.canonical_costume_match
            and not self.unauthorized_accessories and not self.unauthorized_props
            and not self.extra_people and not self.text_or_watermark
            and self.view_pose_compliance >= 85 and self.framing_compliance >= 85
            and not self.critical_view_violation
        )


def semantic_gate(audits: Iterable[AssetSemanticComplianceAudit], *, master: AssetSemanticComplianceAudit | None = None) -> bool:
    rows = list(audits)
    return bool(master and master.passes and rows and all(row.passes for row in rows))


__all__ = ["AssetSemanticComplianceAudit", "CharacterSemanticAuthority", "ViewPoseCompliance", "semantic_gate"]
