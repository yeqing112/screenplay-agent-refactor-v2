import pytest

from core.asset_semantic_compliance import AssetSemanticComplianceAudit, CharacterSemanticAuthority, ViewPoseCompliance, semantic_gate
from core.autonomous_visual_assets import CharacterAuthority


def _audit(view="MASTER", **kwargs):
    values = dict(
        view_id=view, asset_type="CHARACTER", status="PASS", canonical_identity_match=True,
        canonical_costume_match=True, allowed_accessories=["narrow wristwatch"],
        detected_accessories=["narrow wristwatch"], detected_props=[], unauthorized_accessories=[],
        unauthorized_props=[], extra_people=False, text_or_watermark=False,
        view_pose_compliance=95, framing_compliance=95, critical_view_violation=[], violations=[],
        judge_status="VISION_JUDGE_EXECUTED", semantic_authority_fingerprint="fp",
    )
    values.update(kwargs)
    return AssetSemanticComplianceAudit(**values)


def test_character_semantic_authority_derives_allowed_and_forbidden_entities():
    authority = CharacterSemanticAuthority.from_character({
        "id": "LIN_WAN", "name": "林晚", "description": "jacket",
        "semantic_authority": {"allowed_costume": ["light grey-blue jacket"], "allowed_accessories": ["narrow wristwatch"], "allowed_story_props": []},
    })
    assert authority.allowed_accessories == ["narrow wristwatch"]
    assert authority.allowed_story_props == []
    assert "handbag" in authority.forbidden_persistent_props


def test_consistent_unauthorized_prop_fails_semantic_gate():
    audit = _audit(unauthorized_props=["black shoulder bag"], detected_props=["black shoulder bag"], status="FAIL", violations=["UNAUTHORIZED_PROP"])
    assert not audit.passes
    assert not semantic_gate([audit], master=_audit())


def test_view_pose_mismatch_blocks_view():
    pose = ViewPoseCompliance("FACE_PROFILE", "FAIL", 60, 95, ["VIEW_POSE_NOT_COMPLIANT"], [], "VISION_JUDGE_EXECUTED")
    assert not pose.passes
    assert not _audit("FACE_PROFILE", view_pose_compliance=60, critical_view_violation=["VIEW_POSE_NOT_COMPLIANT"], status="FAIL").passes


def test_character_authority_requires_semantic_master_and_derived_pass():
    primary = {"sha256": "master", "generation_execution_id": "m1"}
    derived = {"FACE_FRONT": {"sha256": "face", "generation_execution_id": "d1"}}
    from core.autonomous_asset_generation import MediaEvidenceBinding
    evidence = MediaEvidenceBinding("FACE_FRONT", 1, "master", "face", "m1", "d1", "judge", "vision", "req", "resp", {}, {}, "now", "now")
    from core.autonomous_visual_assets import CharacterConsistencyAudit
    identity = CharacterConsistencyAudit("FACE_FRONT", "PASS", True, 95, 95, 95, 95, 95, 95, [], [], "VISION_JUDGE_EXECUTED", 1, evidence)
    with pytest.raises(ValueError, match="CHARACTER_MASTER_SEMANTIC_GATE_FAILED"):
        CharacterAuthority.lock(character_id="LIN_WAN", name="林晚", primary=primary, derived=derived, audits=[identity], global_judge={"status": "PASS", "same_character": True}, semantic_audits=[_audit("FACE_FRONT")], master_semantic=_audit(status="FAIL", unauthorized_props=["bag"]))
