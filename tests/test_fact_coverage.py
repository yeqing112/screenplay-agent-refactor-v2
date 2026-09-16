from core.fact_coverage import (
    build_narrative_unit_index,
    canonical_fact_components,
    compile_fact_coverage,
    validate_narrative_unit_completeness,
    validate_coverage_payload,
)


def _overlay(disposition):
    return {"facts": [{"fact_id": "FACT_0001", "semantic_disposition": disposition}]}


def test_canonical_fact_component_ids_are_deterministic_and_not_semantic_claims():
    facts = [{"fact_id": "FACT_0006", "subject_id": "老赵", "predicate": "installed hidden camera equipment", "value": "behind bedroom"}]
    first = canonical_fact_components(facts)
    second = canonical_fact_components(facts)
    assert first["fingerprint"] == second["fingerprint"]
    assert [row["component_id"] for row in first["facts"][0]["components"]] == ["FACT_0006::SUBJECT", "FACT_0006::PREDICATE", "FACT_0006::VALUE"]
    assert first["facts"][0]["runtime_authority"] is False


def test_narrative_units_preserve_source_order_and_anchor_refs():
    anchors = [
        {"anchor_ref": "E0002", "char_start": 1300, "char_end": 1310, "exact_text": "b"},
        {"anchor_ref": "E0001", "char_start": 10, "char_end": 20, "exact_text": "a"},
    ]
    result = build_narrative_unit_index(anchors=anchors, window_size=1200)
    assert result["provider_calls"] == 0
    assert result["units"][0]["anchor_refs"] == ["E0001"]
    assert result["units"][1]["anchor_refs"] == ["E0002"]
    assert result["semantic_interpretation"] is False
    assert result["fingerprint"] == build_narrative_unit_index(anchors=anchors, window_size=1200)["fingerprint"]


def test_world_fact_can_cover_objective_requirement():
    result = compile_fact_coverage(requirements=[{"requirement_id": "REQ_0001", "requirement_type": "EVENT_OCCURRENCE", "source_unit_refs": ["NU_0001"], "supporting_fact_ids": ["FACT_0001"]}], semantic_overlay=_overlay("WORLD_FACT_CONFIRMED"))
    assert result["rows"][0]["coverage_status"] == "COVERED"
    assert result["rows"][0]["review_required"] is False


def test_claim_supported_cannot_cover_objective_but_can_cover_claim_requirement():
    objective = compile_fact_coverage(requirements=[{"requirement_id": "REQ_0001", "requirement_type": "EVENT_OCCURRENCE", "supporting_fact_ids": ["FACT_0001"]}], semantic_overlay=_overlay("CLAIM_SUPPORTED"))
    claim = compile_fact_coverage(requirements=[{"requirement_id": "REQ_0001", "requirement_type": "CLAIM_OR_BELIEF", "supporting_fact_ids": ["FACT_0001"]}], semantic_overlay=_overlay("CLAIM_SUPPORTED"))
    assert objective["rows"][0]["coverage_status"] == "CLAIM_ONLY"
    assert claim["rows"][0]["coverage_status"] == "COVERED"


def test_partial_and_inference_are_not_full_coverage_and_missing_stays_missing():
    requirements = [
        {"requirement_id": "REQ_0001", "requirement_type": "EVENT_OCCURRENCE", "supporting_fact_ids": ["FACT_0001"]},
        {"requirement_id": "REQ_0002", "requirement_type": "CAUSAL_RELATION", "supporting_fact_ids": ["FACT_0001"]},
        {"requirement_id": "REQ_0003", "requirement_type": "OUTCOME", "supporting_fact_ids": []},
    ]
    result = compile_fact_coverage(requirements=requirements, semantic_overlay={"facts": [{"fact_id": "FACT_0001", "semantic_disposition": "PARTIAL_SUPPORT_REVIEW"}, {"fact_id": "FACT_0002", "semantic_disposition": "INFERENCE_PROPOSED"}]})
    assert result["rows"][0]["coverage_status"] == "PARTIALLY_COVERED"
    inference_requirement = {**requirements[1], "supporting_fact_ids": ["FACT_0002"]}
    result = compile_fact_coverage(requirements=[inference_requirement], semantic_overlay={"facts": [{"fact_id": "FACT_0002", "semantic_disposition": "INFERENCE_PROPOSED"}]})
    assert result["rows"][0]["coverage_status"] == "UNSAFE_INFERENCE"
    result = compile_fact_coverage(requirements=[requirements[2]], semantic_overlay={"facts": []})
    assert result["rows"][0]["coverage_status"] == "MISSING"


def test_coverage_schema_validator_is_strict():
    payload = {"requirements": [{"requirement_type": "NOT_A_TYPE", "description": "x", "source_unit_refs": []}], "coverage_claims": [{"requirement_ref": "REQ_X", "fact_refs": ["FACT_bad"], "coverage_verdict": "NOPE"}]}
    result = validate_coverage_payload(payload)
    assert result["status"] == "FAIL"
    assert {row["code"] for row in result["errors"]} >= {"COVERAGE_REQUIREMENT_TYPE_INVALID", "COVERAGE_REQUIREMENT_REF_INVALID", "COVERAGE_FACT_REFS_INVALID", "COVERAGE_VERDICT_INVALID"}


def test_fact_count_and_anchor_percentage_are_diagnostic_only():
    result = compile_fact_coverage(requirements=[{"requirement_id": "REQ_0001", "requirement_type": "OUTCOME", "supporting_fact_ids": []}], semantic_overlay={"facts": [{"fact_id": f"FACT_{index:04d}", "semantic_disposition": "WORLD_FACT_CONFIRMED"} for index in range(1, 8)]})
    assert result["rows"][0]["coverage_status"] == "MISSING"
    assert result["fact_count_diagnostic"] == 7
    assert result["anchor_percentage_shortcut"] is False


def test_narrative_unit_completeness_requires_every_anchor_once_and_boundaries():
    anchors = [{"anchor_ref": f"E{i:04d}", "char_start": i * 10, "char_end": i * 10 + 5, "exact_text": str(i)} for i in range(1, 5)]
    source = {"anchors": anchors, "anchor_count": 4, "source_package_id": "P", "source_version_id": "V", "source_raw_hash": "H"}
    units = build_narrative_unit_index(anchors=anchors, window_size=1200)
    full = {**units, "source_package_id": "P", "source_version_id": "V", "source_raw_hash": "H", "anchor_count": 4, "full_anchor_count": 4}
    result = validate_narrative_unit_completeness(narrative_unit_index=full, source_evidence_index=source, raw_bytes="".join(row["exact_text"] for row in anchors).encode())
    assert result["status"] == "PASS"
    assert result["indexed_anchor_count"] == result["unique_indexed_anchor_count"] == 4
    assert result["first_anchor_indexed"] and result["last_anchor_indexed"]

    broken = {**full, "units": [{**full["units"][0], "anchor_refs": ["E0001", "E0001", "E0002", "E0003"]}]}
    failed = validate_narrative_unit_completeness(narrative_unit_index=broken, source_evidence_index=source)
    assert failed["status"] == "FAIL"
    assert {error["code"] for error in failed["errors"]} >= {"INDEXED_ANCHOR_DUPLICATE", "INDEXED_ANCHOR_MISSING"}
