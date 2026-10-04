import pytest

from core.autonomous_asset_generation import MediaEvidenceBinding
from core.autonomous_visual_assets import (
    AuthorityStatus,
    AutonomousVisualAssetBatch,
    CharacterAuthority,
    CharacterConsistencyAudit,
    PropAuthority,
    PropComplexity,
    PropComplexityPolicy,
    PropConsistencyAudit,
    VisualAssetAuthoritySet,
    authority_stale,
)


def _evidence(view, primary, derived, attempt=1):
    return MediaEvidenceBinding(view, attempt, primary["sha256"], derived["sha256"], primary["generation_execution_id"], derived["generation_execution_id"], "judge", "vision", f"req-{view}-{attempt}", f"resp-{view}-{attempt}", {"score": 95}, {"score": 95}, "2026-10-04T00:00:00Z", "2026-10-04T00:01:00Z")


def _character_audit(view, primary, derived, *, passing=True, attempt=1):
    score = 95 if passing else 40
    return CharacterConsistencyAudit(view, "PASS" if passing else "REPAIR", passing, score, score, score, score, score, score, [], [] if passing else ["different face"], "VISION_JUDGE_EXECUTED", attempt, _evidence(view, primary, derived, attempt))


def _prop_audit(view, primary, derived, *, passing=True):
    score = 95 if passing else 40
    return PropConsistencyAudit(view, "PASS" if passing else "REPAIR", passing, score, score, score, score, score, score, score, [], [] if passing else ["single buckle"], "VISION_JUDGE_EXECUTED", 1, _evidence(view, primary, derived))


def test_character_identity_mismatch_blocks_authority():
    primary = {"sha256": "master", "generation_execution_id": "m1"}; derived = {"sha256": "face", "generation_execution_id": "d1"}
    audit = _character_audit("FACE_FRONT", primary, derived, passing=False)
    with pytest.raises(ValueError, match="CHARACTER_GLOBAL_CONSISTENCY_GATE_FAILED"):
        CharacterAuthority.lock(character_id="LIN_WAN", name="林晚", primary=primary, derived={"FACE_FRONT": derived}, audits=[audit], global_judge={"status": "FAIL", "same_character": False})


def test_character_one_view_repair_preserves_master():
    primary = {"sha256": "master", "generation_execution_id": "m1"}; derived = {"sha256": "face-v2", "generation_execution_id": "d2"}
    audit = _character_audit("FACE_FRONT", primary, derived)
    authority = CharacterAuthority.lock(character_id="LIN_WAN", name="林晚", primary=primary, derived={"FACE_FRONT": derived}, audits=[audit], global_judge={"status": "PASS", "same_character": True})
    assert authority.primary_sha256 == "master"
    assert authority.derived_shas["FACE_FRONT"] == "face-v2"


def test_character_global_judge_required():
    primary = {"sha256": "master", "generation_execution_id": "m1"}; derived = {"sha256": "face", "generation_execution_id": "d1"}; audit = _character_audit("FACE_FRONT", primary, derived)
    with pytest.raises(ValueError, match="CHARACTER_GLOBAL_CONSISTENCY_GATE_FAILED"):
        CharacterAuthority.lock(character_id="LIN_WAN", name="林晚", primary=primary, derived={"FACE_FRONT": derived}, audits=[audit], global_judge={"status": "NOT_RUN", "same_character": True})


def test_prop_hardware_mismatch_blocks_authority():
    primary = {"sha256": "master", "generation_execution_id": "m1"}; derived = {"sha256": "side", "generation_execution_id": "d1"}; audit = _prop_audit("SIDE", primary, derived, passing=False)
    with pytest.raises(ValueError, match="PROP_GLOBAL_CONSISTENCY_GATE_FAILED"):
        PropAuthority.lock(prop_id="HANDBAG", name="HANDBAG", complexity="STORY_CRITICAL", primary=primary, derived={"SIDE": derived}, audits=[audit], global_judge={"status": "FAIL", "same_object": False})


def test_asset_complexity_policy():
    assert PropComplexityPolicy.for_complexity(PropComplexity.LOW).views == ("HERO",)
    assert PropComplexityPolicy.for_complexity("MEDIUM").views == ("HERO", "SIDE")
    policy = PropComplexityPolicy.for_complexity("STORY_CRITICAL", story_views=("DAMAGE_DETAIL",))
    assert "DAMAGE_DETAIL" in policy.views


def test_batch_health_cache_and_authority_set_only_accept_ready():
    plan = AutonomousVisualAssetBatch.plan({"id": 990402}, {"id": 1, "characters": [{"id": "LIN_WAN"}], "props": [{"id": "HANDBAG"}], "scenes": [{"id": "E01_SC002"}]})
    assert plan.summary()["character_ids"] == ["LIN_WAN"]
    with pytest.raises(ValueError, match="REQUIRES_READY"):
        VisualAssetAuthoritySet.build(characters=[], scenes={}, props=[])


def test_authority_stale_on_media_sha_change():
    authority = {"status": AuthorityStatus.READY.value, "primary_sha256": "master-v1", "derived_shas": {"SIDE": "side-v1"}, "profile_fingerprint": "profile", "prompt_fingerprint": "prompt"}
    assert not authority_stale(authority, primary_sha256="master-v1", derived_shas={"SIDE": "side-v1"}, profile_fingerprint="profile", prompt_fingerprint="prompt")
    assert authority_stale(authority, primary_sha256="master-v2", derived_shas={"SIDE": "side-v1"}, profile_fingerprint="profile", prompt_fingerprint="prompt")
