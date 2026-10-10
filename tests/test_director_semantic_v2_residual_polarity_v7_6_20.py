"""Provider-free V7.6.20 polarity hardening regressions."""
from __future__ import annotations

import json
from pathlib import Path

from core.director_semantic_grounding import (
    audit_director_downstream_semantic_leakage_v2,
    audit_director_source_grounding_v2,
    audit_physical_action_authority_v2,
    classify_semantic_assertion_polarity,
    semantic_policy_v2_contract,
    semantic_policy_v2_fingerprint,
    validate_director_creative_semantic_review_v2,
)


def _audit(text: str):
    return audit_physical_action_authority_v2({"note": text})


def test_physical_prohibition_and_meta_clauses_are_safe():
    for text in (
        "不得打开铁盒。",
        "不要让林晚拿起海鸥别针。",
        "禁止顾沉把林晚带到铁盒前。",
        "未新增任何关键道具动作。",
        "不得打开铁盒、拿起别针、取走胶片或交出钥匙。",
    ):
        result = _audit(text)
        assert result["status"] == "PASS", (text, result)
        assert result["findings"] == []


def test_positive_physical_actions_still_block():
    assert _audit("林晚打开铁盒。")["findings"][0]["classification"] == "UNSUPPORTED_STORY_ACTION"
    assert _audit("林晚拿起海鸥别针。")["findings"][0]["classification"] == "UNSUPPORTED_STORY_ACTION"
    assert _audit("顾沉把林晚带到铁盒前。")["findings"][0]["classification"] == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE"


def test_physical_mixed_clauses_fail_closed_with_and_without_punctuation():
    for text in (
        "不得打开铁盒，但拿起海鸥别针。",
        "不得打开铁盒但随后拿起海鸥别针",
    ):
        result = _audit(text)
        assert result["status"] == "BLOCKED", (text, result)
        assert any(item["matched_term"] == "拿起海鸥别针" for item in result["findings"])


def test_shotplan_meta_compliance_and_prohibitions_are_safe():
    for text in (
        "未新增任何镜头执行。",
        "未添加机位、焦段或运镜信息。",
        "没有新增具体镜头方案。",
        "不得使用特写。",
    ):
        result = audit_director_downstream_semantic_leakage_v2({"note": text})
        assert result["status"] == "PASS", (text, result)
        assert result["violations"] == []


def test_shotplan_positive_and_mixed_clauses_still_block():
    for text, term in (
        ("使用特写。", "特写"),
        ("改用近景。", "近景"),
        ("镜头缓慢推进。", "镜头"),
        ("使用 50mm 焦段。", "焦段"),
        ("未新增镜头执行，但使用特写。", "特写"),
        ("未新增镜头执行但改用近景", "近景"),
    ):
        result = audit_director_downstream_semantic_leakage_v2({"note": text})
        assert result["status"] == "BLOCKED", (text, result)
        assert any(item["matched_term"] == term for item in result["violations"])


def test_polarity_split_does_not_treat_enumeration_as_mixed():
    assert classify_semantic_assertion_polarity("不得打开铁盒、拿起别针、取走胶片或交出钥匙")["polarity"] == "PROHIBITION"
    assert classify_semantic_assertion_polarity("不得打开铁盒但随后拿起海鸥别针")["polarity"] == "MIXED_CLAUSE"


def test_source_grounding_matches_shared_polarity_contract():
    safe = audit_director_source_grounding_v2({"note": "未新增任何镜头执行"})
    assert safe["status"] == "PASS"
    assert all(item["polarity"] in {"META_COMPLIANCE", "MIXED_CLAUSE"} for item in safe["findings"])
    mixed = audit_director_source_grounding_v2({"note": "不得打开铁盒但随后拿起海鸥别针"})
    assert mixed["status"] == "PASS"  # physical scanner owns this action boundary
    assert mixed["findings"][0]["polarity"] == "MIXED_CLAUSE"


def test_policy_fingerprint_migrates_and_contract_records_new_behavior():
    contract = semantic_policy_v2_contract()
    assert contract["physical_action"]["polarity_aware"] is True
    assert contract["physical_action"]["mixed_clause_fail_closed"] is True
    assert contract["shotplan"]["meta_compliance_aware"] is True
    assert "未新增" in contract["polarity"]["meta_compliance_prefixes"]
    assert semantic_policy_v2_fingerprint() != "9df29513e7bf0433dae06b148b60e93f9afcb5517fd63d75a8b7b98c3994b501"


def test_attempt9_current_v2_keeps_true_violations():
    root = Path(__file__).resolve().parents[1]
    raw_doc = json.loads((root / "docs/canonical-canary/v7_6_15-attempt9-real-semantic-revision/ATTEMPT9_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    ir = json.loads(raw_doc["raw_response"])
    units = json.loads((root / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract/SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))["units"]
    review = validate_director_creative_semantic_review_v2(ir, source_authoring_units=units, declared_participants=[{"id": "顾沉"}, {"id": "林晚"}])
    physical = review["physical_action_authority"]["findings"]
    assert review["status"] == "BLOCKED"
    assert sum(item["classification"] == "UNSUPPORTED_STORY_ACTION" for item in physical) == 1
    assert sum(item["classification"] == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE" for item in physical) == 2
    assert review["downstream_leakage"]["violation_count"] == 0


def test_attempt10_diagnostic_false_positives_are_removed_without_authority():
    root = Path(__file__).resolve().parents[1]
    raw_doc = json.loads((root / "docs/canonical-canary/v7_6_19-stage-b-structural-completeness/ATTEMPT10_DIAGNOSTIC_SEMANTIC_V2.json").read_text(encoding="utf-8"))
    # The V7.6.19 evidence is historical; reassess its immutable raw fixture
    # through the current runtime rather than rewriting historical JSON.
    raw_fixture = json.loads((root / "docs/canonical-canary/v7_6_18-attempt10-real-semantic-v2-revision/ATTEMPT10_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    source = json.loads((root / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract/SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))
    current = validate_director_creative_semantic_review_v2(json.loads(raw_fixture["raw_response"]), source_authoring_units=source["units"], declared_participants=[{"id": "顾沉"}, {"id": "林晚"}])
    assert current["status"] == "PASS"
    assert current["physical_action_authority"]["status"] == "PASS"
    assert current["downstream_leakage"]["status"] == "PASS"
    assert raw_doc["status"] == "DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID"
