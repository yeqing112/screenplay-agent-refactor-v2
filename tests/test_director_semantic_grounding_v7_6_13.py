from core.director_semantic_grounding import (
    audit_director_downstream_semantic_leakage,
    audit_director_source_grounding,
    build_creative_enrichment_revision_preflight,
    build_semantic_claim_inventory,
    validate_director_creative_semantic_review,
)
from core.director_progressive_authoring import build_director_creative_enrichment_prompt
import api.director_treatment_api as director_api


SOURCE = [
    {"source_type": "SOURCE_ACTION", "text": "顾沉熄灭安全灯，拉着林晚躲到药水柜后。"},
    {"source_type": "SOURCE_ACTION", "text": "顾沉带林晚进入暗房。"},
    {"source_type": "SOURCE_DIALOGUE", "speaker": "顾沉", "text": "也许是你自己"},
    {"source_type": "SOURCE_FACT", "text": "暗房中央摆着一只铁盒，盒盖上贴着母亲的手写标签。"},
]


def test_source_grounding_known_regressions():
    assert audit_director_source_grounding({"x": "药水味"}, source_authoring_units=SOURCE)["status"] == "BLOCKED"
    assert audit_director_source_grounding({"x": "顾沉熄灯时保持果断"}, source_authoring_units=SOURCE)["status"] == "PASS"
    assert audit_director_source_grounding({"x": "顾沉对这种威胁并不陌生"}, source_authoring_units=SOURCE)["classification_counts"]["UNSUPPORTED_CHARACTER_KNOWLEDGE"] == 1
    assert audit_director_source_grounding({"x": "也许是你自己带来怀疑与压力"}, source_authoring_units=SOURCE)["status"] == "PASS"
    assert audit_director_source_grounding({"x": "顾沉知道门外的人是谁"}, source_authoring_units=SOURCE)["status"] == "BLOCKED"
    assert audit_director_source_grounding({"x": "林晚关注母亲留下的标签"}, source_authoring_units=SOURCE)["status"] == "PASS"
    assert audit_director_source_grounding({"x": "林晚怨恨母亲"}, source_authoring_units=SOURCE)["status"] == "BLOCKED"


def test_downstream_scanner_has_categories_and_false_positive_guards():
    assert audit_director_downstream_semantic_leakage({"visual_priority": ["视觉重点是海鸥别针"]})["status"] == "PASS"
    assert audit_director_downstream_semantic_leakage({"rhythm": "节奏从心理压力转向外部威胁"})["status"] == "PASS"
    result = audit_director_downstream_semantic_leakage({"visual_priority": ["海鸥别针特写"]})
    assert result["status"] == "BLOCKED"
    assert result["violations"][0]["category"] == "SHOT_SIZE"
    assert audit_director_downstream_semantic_leakage({"button": "最后一帧画面停在林晚脸上"})["status"] == "BLOCKED"
    assert audit_director_downstream_semantic_leakage({"exit": "结束在信任裂痕"})["status"] == "PASS"


def test_semantic_review_blocks_shotplan_and_unsupported_claims_but_inventory_is_complete():
    ir = {"visual_priority": ["海鸥别针特写"], "character_directions": [{"character_ref": "顾沉", "direction": "顾沉知道门外的人是谁"}]}
    inventory = build_semantic_claim_inventory(ir)
    assert inventory["claim_count"] == 2
    review = validate_director_creative_semantic_review(ir, source_authoring_units=SOURCE, declared_participants=[{"id": "顾沉"}])
    assert review["status"] == "BLOCKED"
    assert "DOWNSTREAM_SHOTPLAN_LEAKAGE" in review["reasons"]
    assert "SOURCE_GROUNDING_BLOCKED" in review["reasons"]


def test_semantic_review_blocks_stage_a_fields_leaking_into_stage_b():
    review = validate_director_creative_semantic_review({"scene_objective": "改写来源目标", "beat_enrichments": []}, source_authoring_units=SOURCE)
    assert review["status"] == "BLOCKED"
    assert "STAGE_A_IMMUTABILITY_VIOLATION" in review["reasons"]


def test_revision_boundary_is_append_only_and_provider_free():
    result = build_creative_enrichment_revision_preflight(history_count=8)
    assert result["expected_attempt"] == "attempt-9"
    assert result["authorization"] == "NOT_GRANTED"
    assert result["provider_calls"] == 0
    assert result["production_mutation"] is False


def test_future_stage_b_prompt_has_read_only_source_contract_and_binding():
    beat_plan = {"beats": [{"beat_ref": "B1", "refs": ["SAU_ACTION_001"], "purpose": "建立压力", "objective": "进入", "information_change": "未知", "hook": False}]}
    system, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=beat_plan, declared_participants=[{"name": "顾沉"}], source_authoring_units=SOURCE, source_authoring_unit_fingerprint="source-fp")
    assert "SOURCE_AUTHORING_UNITS" in prompt
    assert "SOURCE_GROUNDING_RULE" in prompt
    assert "STAGE_B_SHOTPLAN_BOUNDARY" in prompt
    identity = director_api.build_director_creative_enrichment_provider_request(
        scene_id="E01_SC001", materialized_beat_plan=beat_plan, stage_a_materialized_fingerprint="stage-a-fp",
        declared_participants=[{"name": "顾沉"}], source_authoring_units=SOURCE, source_authoring_unit_fingerprint="source-fp",
        profile={"id": "p", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}},
        profile_snapshot={"profile_id": "p", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True},
    )
    assert identity["source_authoring_unit_fingerprint"] == "source-fp"
    assert identity["provider_request_payload_v2"]["source_authoring_unit_fingerprint"] == "source-fp"
    assert identity["prompt_fingerprint"] != "9b60b1245e10288c405b9f04a2d092b66f687a36a7c992fa6a41d232ebef53e9"
