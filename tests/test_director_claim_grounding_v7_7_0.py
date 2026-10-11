"""Provider-free ClaimIR and authority tests for V7.7.0."""
from __future__ import annotations

from core.director_claim_authority import authority_matrix, authority_requirement, validate_authority_matrix
from core.director_claim_extraction import extract_claims, project_source_claims
from core.director_claim_grounding import audit_claim_set, evaluate_claim_support
from core.director_claim_ir import claim_fingerprint, make_claim, validate_claim, validate_claim_set


SOURCE = [
    {"unit_id": "SAU_1", "source_order": 1, "source_type": "SOURCE_ACTION", "text": "顾沉带林晚进入暗房。"},
    {"unit_id": "SAU_2", "source_order": 2, "source_type": "SOURCE_ACTION", "text": "铁盒盒盖上贴着母亲的手写标签。"},
    {"unit_id": "SAU_3", "source_order": 3, "source_type": "SOURCE_ACTION", "text": "林晚想不起自己童年是否来过这里。"},
    {"unit_id": "SAU_4", "source_order": 4, "source_type": "SOURCE_ACTION", "text": "顾沉熄灭安全灯。"},
    {"unit_id": "SAU_5", "source_order": 5, "source_type": "SOURCE_ACTION", "text": "那人没有进门，只把一张车票塞进来。"},
]


def _source():
    return project_source_claims(SOURCE)


def _claim(text: str, kind: str, *, subject=None, predicate="", object_=None, origin="STAGE_B", canonicality="CANONICAL_ASSERTION", modality="ASSERTED", authority="SOURCE"):
    return make_claim(claim_id="fixture", source_path="fixture", raw_text=text, claim_type=kind, subject=subject or {}, predicate=predicate, object_=object_ or {}, canonicality=canonicality, modality=modality, authority_required=authority, origin=origin)


def test_claim_contract_and_fingerprint_are_typed_and_stable():
    claim = _claim("顾沉带林晚进入暗房。", "CHARACTER_ACTION", subject={"kind": "CHARACTER", "ref": "顾沉"}, predicate="引导进入", object_={"kind": "CHARACTER", "ref": "林晚"})
    assert validate_claim(claim)["status"] == "PASS"
    moved = dict(claim, source_path="different.path", raw_text="改写文本")
    moved["fingerprint"] = claim_fingerprint(moved)
    assert moved["fingerprint"] == claim["fingerprint"]
    assert validate_claim_set([claim])["status"] == "PASS"


def test_authority_matrix_declares_stage_boundaries():
    assert validate_authority_matrix()["status"] == "PASS"
    assert "SPATIAL_BLOCKING" in authority_matrix()["origins"]["STAGE_B"]["forbidden_claim_types"]
    assert authority_requirement(_claim("可带一点试探感", "PERFORMANCE_OPTION", canonicality="NON_CANONICAL_PERFORMANCE_OPTION", modality="PLAYABLE_OPTION", authority="STAGE_B"))["status"] == "NON_CANONICAL_OPTION"
    assert authority_requirement(_claim("顾沉站在门边", "SPATIAL_BLOCKING"))["status"] == "DOWNSTREAM_FORBIDDEN"


def test_source_projection_supports_narrow_action_entailment_only():
    sources = _source()
    candidate = _claim("顾沉引导林晚进入暗房", "CHARACTER_ACTION", subject={"kind": "CHARACTER", "ref": "顾沉"}, predicate="引导进入", object_={"kind": "CHARACTER", "ref": "林晚"},)
    candidate["qualifiers"] = {"destination": "暗房"}; candidate["fingerprint"] = claim_fingerprint(candidate)
    assert evaluate_claim_support(candidate, source_claims=sources)["support_status"] in {"SUPPORTED_EXPLICIT", "SUPPORTED_ENTAILED"}
    too_specific = _claim("顾沉带林晚到铁盒前", "SPATIAL_BLOCKING", subject={"kind": "CHARACTER", "ref": "顾沉"}, predicate="moves_to", object_={"kind": "LOCATION", "ref": "铁盒前"})
    assert evaluate_claim_support(too_specific, source_claims=sources)["support_status"] == "UNSUPPORTED"


def test_uncertainty_and_certainty_cannot_collapse():
    candidate = _claim("林晚第一次来暗房", "CERTAINTY_ASSERTION", subject={"kind": "CHARACTER", "ref": "林晚"}, predicate="first_or_never", object_={"kind": "EVENT", "ref": "childhood_visit_to_darkroom"})
    result = evaluate_claim_support(candidate, source_claims=_source())
    assert result["support_status"] == "UNSUPPORTED"
    option = _claim("像第一次来", "PERFORMANCE_OPTION", subject={"kind": "CHARACTER", "ref": "林晚"}, predicate="play", object_={"kind": "DIRECTION", "ref": "像第一次来"}, canonicality="NON_CANONICAL_PERFORMANCE_OPTION", modality="PLAYABLE_OPTION", authority="STAGE_B")
    assert evaluate_claim_support(option, source_claims=_source())["support_status"] == "SUPPORTED_AS_NON_CANONICAL_OPTION"


def test_ownership_and_property_do_not_cross_objects():
    sources = _source()
    left_box = _claim("母亲留下铁盒", "OBJECT_PROVENANCE", subject={"kind": "PERSON", "ref": "母亲"}, predicate="left_by", object_={"kind": "OBJECT", "ref": "铁盒"})
    assert evaluate_claim_support(left_box, source_claims=sources)["support_status"] == "UNSUPPORTED"
    ticket_handwritten = _claim("车票背面的手写指令", "OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "车票背面"}, predicate="handwritten", object_={"kind": "PROPERTY", "ref": "handwritten"})
    assert evaluate_claim_support(ticket_handwritten, source_claims=sources)["support_status"] == "AMBIGUOUS_REVIEW_REQUIRED"
    label_handwritten = _claim("铁盒标签手写", "OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "铁盒标签"}, predicate="handwritten", object_={"kind": "PROPERTY", "ref": "handwritten"})
    assert evaluate_claim_support(label_handwritten, source_claims=sources)["support_status"] == "SUPPORTED_EXPLICIT"


def test_environment_and_possession_are_not_inferred():
    sources = _source()
    dim = _claim("在微弱光线下阅读", "ENVIRONMENT_STATE", subject={"kind": "ENVIRONMENT", "ref": "暗房"}, predicate="light_level", object_={"kind": "LIGHT", "ref": "dim"})
    assert evaluate_claim_support(dim, source_claims=sources)["support_status"] == "UNSUPPORTED"
    receive = _claim("接过车票", "OBJECT_POSSESSION", subject={"kind": "CHARACTER", "ref": "林晚"}, predicate="receives", object_={"kind": "OBJECT", "ref": "车票"})
    assert evaluate_claim_support(receive, source_claims=sources)["support_status"] == "AMBIGUOUS_REVIEW_REQUIRED"


def test_delegation_is_meta_safe_and_execution_in_same_clause_is_not():
    document = {"note": "交由下游 SceneBlocking 与 ShotPlan 权威处理"}
    claims = extract_claims(document, origin="STAGE_B")
    delegation = next(x for x in claims if x["claim_type"] == "AUTHORITY_DELEGATION")
    assert evaluate_claim_support(delegation, source_claims=_source())["support_status"] == "META_SAFE"
    unsafe = extract_claims({"note": "交给 ShotPlan 使用特写"}, origin="STAGE_B")
    assert any(x["claim_type"] == "SHOT_EXECUTION" or x["claim_type"] == "SPATIAL_BLOCKING" for x in unsafe)


def test_embedded_mandatory_claims_are_extracted_from_semantic_fields():
    document = {
        "character_directions": [{"character_ref": "顾沉", "objective": "以‘也许是你自己’的暗示试探林晚", "obstacle": "在不惊动林晚的前提下观察她的反应"}],
        "visual_priority": ["车票背面的手写指令", "接过车票", "母亲留下的物件"],
        "beat_enrichments": [{"performance": "在微弱光线下阅读"}],
    }
    claims = extract_claims(document, origin="STAGE_B")
    kinds = {x["claim_type"] for x in claims}
    assert {"CHARACTER_INTENT", "ENVIRONMENT_STATE", "OBJECT_PROPERTY", "OBJECT_POSSESSION", "OBJECT_PROVENANCE"}.issubset(kinds)
    assert len(claims) >= 8


def test_shadow_audit_marks_blocking_claims_and_keeps_safe_metadata():
    claims = extract_claims({"note": "交由下游 SceneBlocking 与 ShotPlan 权威处理", "character_directions": [{"objective": "试探林晚"}]}, origin="STAGE_B")
    audit = audit_claim_set(claims, source_claims=_source())
    assert audit["status"] == "BLOCKED"
    assert any(x["claim_type"] == "AUTHORITY_DELEGATION" and x["support_status"] == "META_SAFE" for x in audit["findings"])
    assert any(x["claim_type"] == "CHARACTER_INTENT" and x["production_blocking"] for x in audit["findings"])


def test_stage_a_and_historical_attempt_fixtures_reproduce_typed_findings():
    import json
    from pathlib import Path
    from scripts.generate_v7_7_0_semantic_grounding_v3_evidence import _raw, _source_ref_map, _stage_b_ref_map, ATTEMPT_PATHS, SOURCE_PATH

    source_doc = json.loads(Path(SOURCE_PATH).read_text(encoding="utf-8"))
    source_claims = project_source_claims(source_doc["units"])
    stage_a = _raw(ATTEMPT_PATHS["STAGE_A"])
    attempt9 = _raw(ATTEMPT_PATHS["ATTEMPT9"])
    stage_a_claims = extract_claims(stage_a, origin="STAGE_A", source_ref_map=_source_ref_map(stage_a))
    attempt9_claims = extract_claims(attempt9, origin="STAGE_B", source_ref_map=_stage_b_ref_map(attempt9, stage_a))
    stage_a_audit = audit_claim_set(stage_a_claims, source_claims=source_claims)
    attempt9_audit = audit_claim_set(attempt9_claims, source_claims=source_claims)
    assert stage_a_audit["status"] == "BLOCKED"
    assert attempt9_audit["status"] == "BLOCKED"
    assert any(item["claim_type"] == "CERTAINTY_ASSERTION" for item in stage_a_audit["findings"])
    assert any(item["claim_type"] == "OBJECT_PROVENANCE" for item in stage_a_audit["findings"])
    assert any(item["claim_type"] == "SPATIAL_BLOCKING" for item in attempt9_audit["findings"])
    assert any(item["claim_type"] == "CHARACTER_ACTION" and "opens" == item["predicate"] for item in attempt9_audit["findings"])
