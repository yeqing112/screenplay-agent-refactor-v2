"""Evidence locked CHARACTER and PROP asset contracts.

The scene canary predates this module.  These contracts deliberately keep
character identity and prop continuity separate from scene topology while
reusing the same immutable media evidence binding.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping

from core.autonomous_asset_generation import MediaEvidenceBinding


class PropComplexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    STORY_CRITICAL = "STORY_CRITICAL"


class AuthorityStatus(str, Enum):
    READY = "READY"
    STALE = "STALE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PropComplexityPolicy:
    complexity: PropComplexity
    views: tuple[str, ...]

    @classmethod
    def for_complexity(cls, complexity: PropComplexity | str, *, story_views: Iterable[str] = ()) -> "PropComplexityPolicy":
        value = PropComplexity(complexity)
        base = {
            PropComplexity.LOW: ("HERO",),
            PropComplexity.MEDIUM: ("HERO", "SIDE"),
            PropComplexity.HIGH: ("HERO", "SIDE", "BACK", "DETAIL"),
            PropComplexity.STORY_CRITICAL: ("HERO", "SIDE", "BACK", "DETAIL"),
        }[value]
        if value is PropComplexity.STORY_CRITICAL:
            base = tuple(dict.fromkeys((*base, *[str(item) for item in story_views])))
        return cls(value, base)


@dataclass(frozen=True)
class CharacterConsistencyAudit:
    view_id: str
    status: str
    same_character: bool
    identity_score: int
    face_score: int
    hair_score: int
    body_proportion_score: int
    costume_score: int
    accessory_score: int
    critical_identity_violations: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    judge_status: str = ""
    attempt_number: int = 1
    media_evidence: MediaEvidenceBinding | None = None
    score_scale: str = "0-100"

    def __post_init__(self) -> None:
        if self.score_scale != "0-100":
            raise ValueError("VISION_JUDGE_INVALID_SCORE_SCALE")
        values = (self.identity_score, self.face_score, self.hair_score, self.body_proportion_score, self.costume_score, self.accessory_score)
        if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100 for value in values):
            raise ValueError("VISION_JUDGE_INVALID_SCORE_SCALE")

    @property
    def passes(self) -> bool:
        return (
            self.status == "PASS" and self.same_character and self.identity_score >= 90 and self.face_score >= 88
            and self.hair_score >= 90 and self.body_proportion_score >= 85 and self.costume_score >= 90
            and self.accessory_score >= 90 and not self.critical_identity_violations
            and self.media_evidence is not None and self.media_evidence.complete
        )


@dataclass(frozen=True)
class PropConsistencyAudit:
    view_id: str
    status: str
    same_object: bool
    shape_score: int
    proportion_score: int
    material_score: int
    color_score: int
    hardware_score: int
    distinctive_features_score: int
    story_state_score: int = 100
    critical_object_violations: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    judge_status: str = ""
    attempt_number: int = 1
    media_evidence: MediaEvidenceBinding | None = None
    score_scale: str = "0-100"

    def __post_init__(self) -> None:
        if self.score_scale != "0-100":
            raise ValueError("VISION_JUDGE_INVALID_SCORE_SCALE")
        values = (self.shape_score, self.proportion_score, self.material_score, self.color_score, self.hardware_score, self.distinctive_features_score, self.story_state_score)
        if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100 for value in values):
            raise ValueError("VISION_JUDGE_INVALID_SCORE_SCALE")

    @property
    def passes(self) -> bool:
        return (
            self.status == "PASS" and self.same_object and self.shape_score >= 90 and self.proportion_score >= 88
            and self.material_score >= 90 and self.color_score >= 90 and self.hardware_score >= 90
            and self.distinctive_features_score >= 90 and not self.critical_object_violations
            and self.media_evidence is not None and self.media_evidence.complete
        )


def _fingerprint(value: Any) -> str:
    if isinstance(value, str) and len(value) == 64:
        return value
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def authority_stale(authority: Mapping[str, Any], *, primary_sha256: str, derived_shas: Mapping[str, str], profile_fingerprint: str = "", prompt_fingerprint: str = "") -> bool:
    """Detect media/profile/prompt drift before an authority is consumed."""

    if str(authority.get("status") or "") != AuthorityStatus.READY.value:
        return True
    if str(authority.get("primary_sha256") or "") != str(primary_sha256):
        return True
    if dict(authority.get("derived_shas") or {}) != dict(derived_shas):
        return True
    for field, current in (("profile_fingerprint", profile_fingerprint), ("prompt_fingerprint", prompt_fingerprint)):
        if current and str(authority.get(field) or "") != str(current):
            return True
    return False


@dataclass(frozen=True)
class CharacterAuthority:
    character_id: str
    name: str
    status: str
    primary_sha256: str
    primary_execution_id: str
    derived_shas: dict[str, str]
    derived_execution_ids: dict[str, str]
    pairwise_audit_count: int
    global_judge_status: str
    profile_fingerprint: str
    prompt_fingerprint: str

    @classmethod
    def lock(cls, *, character_id: str, name: str, primary: Mapping[str, Any], derived: Mapping[str, Mapping[str, Any]], audits: Iterable[CharacterConsistencyAudit], global_judge: Mapping[str, Any], profile_fingerprint: str = "", prompt_fingerprint: str = "") -> "CharacterAuthority":
        rows = list(audits)
        if not primary.get("sha256") or not primary.get("generation_execution_id"):
            raise ValueError("CHARACTER_PRIMARY_EVIDENCE_MISSING")
        if str(global_judge.get("status") or "") != "PASS" or not bool(global_judge.get("same_character")):
            raise ValueError("CHARACTER_GLOBAL_CONSISTENCY_GATE_FAILED")
        if not rows or not all(row.passes for row in rows):
            raise ValueError("CHARACTER_CONSISTENCY_GATE_FAILED")
        required = {row.view_id for row in rows}
        if set(derived) != required:
            raise ValueError("CHARACTER_DERIVED_VIEWS_MISSING")
        master_sha = str(primary["sha256"])
        for row in rows:
            evidence = row.media_evidence
            media = derived[row.view_id]
            if evidence is None or evidence.master_sha256 != master_sha or evidence.derived_sha256 != str(media.get("sha256") or ""):
                raise ValueError("CHARACTER_JUDGE_EVIDENCE_STALE")
            if evidence.master_generation_execution_id != str(primary["generation_execution_id"]) or evidence.derived_generation_execution_id != str(media.get("generation_execution_id") or ""):
                raise ValueError("CHARACTER_EVIDENCE_LINEAGE_MISMATCH")
        return cls(character_id, name, AuthorityStatus.READY.value, master_sha, str(primary["generation_execution_id"]), {key: str(value.get("sha256") or "") for key, value in derived.items()}, {key: str(value.get("generation_execution_id") or "") for key, value in derived.items()}, len(rows), "PASS", profile_fingerprint, prompt_fingerprint)


@dataclass(frozen=True)
class PropAuthority:
    prop_id: str
    name: str
    complexity: str
    status: str
    primary_sha256: str
    primary_execution_id: str
    derived_shas: dict[str, str]
    derived_execution_ids: dict[str, str]
    pairwise_audit_count: int
    global_judge_status: str
    profile_fingerprint: str
    prompt_fingerprint: str

    @classmethod
    def lock(cls, *, prop_id: str, name: str, complexity: PropComplexity | str, primary: Mapping[str, Any], derived: Mapping[str, Mapping[str, Any]], audits: Iterable[PropConsistencyAudit], global_judge: Mapping[str, Any], profile_fingerprint: str = "", prompt_fingerprint: str = "") -> "PropAuthority":
        rows = list(audits)
        if not primary.get("sha256") or not primary.get("generation_execution_id"):
            raise ValueError("PROP_PRIMARY_EVIDENCE_MISSING")
        if str(global_judge.get("status") or "") != "PASS" or not bool(global_judge.get("same_object")):
            raise ValueError("PROP_GLOBAL_CONSISTENCY_GATE_FAILED")
        if not rows or not all(row.passes for row in rows):
            raise ValueError("PROP_CONSISTENCY_GATE_FAILED")
        if set(derived) != {row.view_id for row in rows}:
            raise ValueError("PROP_DERIVED_VIEWS_MISSING")
        for row in rows:
            evidence = row.media_evidence
            media = derived[row.view_id]
            if evidence is None or evidence.master_sha256 != str(primary["sha256"]) or evidence.derived_sha256 != str(media.get("sha256") or ""):
                raise ValueError("PROP_JUDGE_EVIDENCE_STALE")
        return cls(prop_id, name, PropComplexity(complexity).value, AuthorityStatus.READY.value, str(primary["sha256"]), str(primary["generation_execution_id"]), {key: str(value.get("sha256") or "") for key, value in derived.items()}, {key: str(value.get("generation_execution_id") or "") for key, value in derived.items()}, len(rows), "PASS", profile_fingerprint, prompt_fingerprint)


@dataclass(frozen=True)
class VisualAssetAuthoritySet:
    status: str
    character_authorities: dict[str, dict[str, Any]]
    scene_authorities: dict[str, dict[str, Any]]
    prop_authorities: dict[str, dict[str, Any]]
    visual_style_fingerprint: str = ""

    @classmethod
    def build(cls, *, characters: Iterable[CharacterAuthority], scenes: Mapping[str, Mapping[str, Any]], props: Iterable[PropAuthority], visual_style_fingerprint: str = "") -> "VisualAssetAuthoritySet":
        character_rows = {row.character_id: asdict(row) for row in characters}
        prop_rows = {row.prop_id: asdict(row) for row in props}
        scene_rows = {str(key): dict(value) for key, value in scenes.items()}
        all_ready = bool(character_rows) and bool(prop_rows) and bool(scene_rows) and all(row.get("status") == AuthorityStatus.READY.value for row in (*character_rows.values(), *prop_rows.values(), *scene_rows.values()))
        if not all_ready:
            raise ValueError("VISUAL_ASSET_AUTHORITY_SET_REQUIRES_READY_AUTHORITIES")
        return cls(AuthorityStatus.READY.value, character_rows, scene_rows, prop_rows, visual_style_fingerprint)


@dataclass
class AutonomousVisualAssetBatch:
    """Small, provider-neutral batch planner for Book/Episode asset runs."""

    book_id: str | int
    episode_id: str | int
    characters: list[dict[str, Any]] = field(default_factory=list)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    props: list[dict[str, Any]] = field(default_factory=list)
    visual_style: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def plan(cls, book: Mapping[str, Any], episode: Mapping[str, Any]) -> "AutonomousVisualAssetBatch":
        def rows(key: str) -> list[dict[str, Any]]:
            value = episode.get(key) or book.get(key) or []
            return [dict(item) for item in value if isinstance(item, Mapping)]

        return cls(book.get("id") or book.get("book_id") or "", episode.get("id") or episode.get("episode_id") or "", rows("characters"), rows("scenes"), rows("props"), dict(episode.get("visual_style") or book.get("visual_style") or {}))

    def summary(self) -> dict[str, Any]:
        return {"book_id": self.book_id, "episode_id": self.episode_id, "character_ids": [row.get("id") or row.get("name") for row in self.characters], "scene_ids": [row.get("id") or row.get("scene_id") for row in self.scenes], "prop_ids": [row.get("id") or row.get("name") for row in self.props], "visual_style_fingerprint": _fingerprint(self.visual_style)}


__all__ = [
    "AuthorityStatus", "AutonomousVisualAssetBatch", "CharacterAuthority", "CharacterConsistencyAudit", "PropAuthority", "PropComplexity", "PropComplexityPolicy", "PropConsistencyAudit", "VisualAssetAuthoritySet", "authority_stale",
]
