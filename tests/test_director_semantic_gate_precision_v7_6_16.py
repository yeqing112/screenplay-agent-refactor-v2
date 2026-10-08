import json
from pathlib import Path

from core.director_semantic_grounding import (
    audit_director_downstream_semantic_leakage_v2,
    audit_physical_action_authority_v2,
    audit_source_uncertainty_preservation_v2,
    classify_semantic_assertion_polarity,
    semantic_policy_v2_fingerprint,
    validate_semantic_review_assessment_binding,
    validate_director_creative_semantic_review_v2,
)


SOURCE = [{"text": "她想不起自己童年是否来过这里。"}]


def test_prohibition_scope_and_meta_compliance_are_not_positive_claims():
    safe = validate_director_creative_semantic_review_v2({"prohibited_interpretations": ["不要把林晚解读为内疚或自责", "不要为林晚的童年与暗房关系添加来源之外的背景"], "note": "未指定任何镜头执行"}, source_authoring_units=SOURCE)
    assert safe["status"] == "PASS"
    assert safe["source_grounding"]["classification_counts"]["SAFE_PROHIBITION"] == 2
    assert safe["source_grounding"]["classification_counts"]["META_COMPLIANCE"] == 1


def test_mixed_prohibition_clause_remains_fail_closed():
    review = validate_director_creative_semantic_review_v2({"note": "不要把林晚理解为内疚，因为她其实一直很愧疚。"}, source_authoring_units=SOURCE)
    assert review["status"] == "BLOCKED"
    assert review["source_grounding"]["classification_counts"]["UNSUPPORTED_EMOTIONAL_FACT"] == 1


def test_shotplan_negation_scope_and_mixed_clause():
    assert audit_director_downstream_semantic_leakage_v2({"note": "不要给海鸥别针特写"})["status"] == "PASS"
    mixed = audit_director_downstream_semantic_leakage_v2({"note": "不要使用特写，改用近景"})
    assert mixed["status"] == "BLOCKED"
    assert any(item["matched_term"] == "近景" for item in mixed["violations"])
    assert audit_director_downstream_semantic_leakage_v2({"note": "未指定任何镜头执行"})["status"] == "PASS"


def test_stage_a_ownership_allows_stage_b_character_objective():
    allowed = validate_director_creative_semantic_review_v2({"character_directions": [{"character_ref": "林晚", "objective": "保持不确定"}]})
    assert allowed["stage_a_immutability_violations"] == []
    blocked = validate_director_creative_semantic_review_v2({"objective": "改写来源目标"})
    assert "objective" in blocked["stage_a_immutability_violations"]
    assert validate_director_creative_semantic_review_v2({"scene_objective": "新增事实"})["status"] == "BLOCKED"


def test_uncertainty_collapse_is_blocked_but_uncertainty_preserving_direction_is_safe():
    unsafe = audit_source_uncertainty_preservation_v2({"note": "林晚首次进入暗房"}, source_authoring_units=SOURCE)
    assert unsafe["status"] == "BLOCKED"
    assert unsafe["findings"][0]["classification"] == "UNSUPPORTED_CERTAINTY_COLLAPSE"
    safe = audit_source_uncertainty_preservation_v2({"note": "表演上呈现出仿佛第一次进入的陌生感，但不得确认实际是否来过"}, source_authoring_units=SOURCE)
    assert safe["status"] == "PASS"


def test_physical_action_contract_is_explicit_and_blocking():
    audit = audit_physical_action_authority_v2({"note": "林晚打开铁盒，再拾起烧焦胶片与海鸥别针；顾沉把林晚带到铁盒前"}, source_authoring_units=SOURCE)
    assert audit["status"] == "BLOCKED"
    assert {item["classification"] for item in audit["findings"]} == {"UNSUPPORTED_STORY_ACTION", "DOWNSTREAM_SCENEBLOCKING_LEAKAGE"}
    assert audit_physical_action_authority_v2({"note": "林晚停顿，视线迟疑，呼吸变化"}, source_authoring_units=SOURCE)["status"] == "PASS"


def test_attempt9_provider_free_reassessment_has_no_v1_mutation():
    root = Path(__file__).resolve().parents[1]
    raw_doc = json.loads((root / "docs/canonical-canary/v7_6_15-attempt9-real-semantic-revision/ATTEMPT9_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    ir = json.loads(raw_doc["raw_response"])
    units = json.loads((root / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract/SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))["units"]
    review = validate_director_creative_semantic_review_v2(ir, source_authoring_units=units, declared_participants=[{"id": "顾沉"}, {"id": "林晚"}])
    assert review["status"] == "BLOCKED"
    assert review["policy_version"] == "director_creative_semantic_review_v2"
    assert review["source_grounding"]["classification_counts"]["UNSUPPORTED_CERTAINTY_COLLAPSE"] >= 1
    assert semantic_policy_v2_fingerprint() == review["semantic_policy_fingerprint"]
    assert raw_doc["raw_response_sha256"] == "8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589"


def test_polarity_contract_is_explicit():
    assert classify_semantic_assertion_polarity("不要特写")["polarity"] == "PROHIBITION"
    assert classify_semantic_assertion_polarity("未指定任何镜头执行")["polarity"] == "META_COMPLIANCE"
    assert classify_semantic_assertion_polarity("不要特写，改用近景")["polarity"] == "MIXED_CLAUSE"


def test_v2_assessment_binding_is_versioned_and_fail_closed():
    assessment = {
        "policy_version": "director_creative_semantic_review_v2",
        "semantic_policy_fingerprint": semantic_policy_v2_fingerprint(),
        "attempt_id": "attempt-9",
        "ir_fingerprint": "ir-fp",
        "status": "PASS",
    }
    assert validate_semantic_review_assessment_binding(assessment, attempt_id="attempt-9", ir_fingerprint="ir-fp")["status"] == "PASS"
    assert validate_semantic_review_assessment_binding(assessment, attempt_id="attempt-10", ir_fingerprint="ir-fp")["status"] == "BLOCKED"
    assert validate_semantic_review_assessment_binding({**assessment, "semantic_policy_fingerprint": "old"}, attempt_id="attempt-9", ir_fingerprint="ir-fp")["status"] == "BLOCKED"
