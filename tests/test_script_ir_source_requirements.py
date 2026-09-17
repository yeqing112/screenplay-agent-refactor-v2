from core.script_ir_source_requirements import (
    audit_script_ir_consumers,
    compile_script_ir_source_requirements,
    evaluate_script_ir_source_coverage,
    script_ir_source_requirement_contract,
)


def _source():
    return {
        "episode": 1,
        "title": "门外",
        "scenes": [{
            "name": "门厅",
            "beats": [{"id": "B1", "event": "人物进入"}],
            "camera": "close-up",
            "props": ["钥匙"],
        }],
    }


def test_contract_is_versioned_and_traces_each_blocker_to_real_consumer():
    contract = script_ir_source_requirement_contract()
    assert contract["schema_version"] == "script_ir_source_requirement_contract_v1"
    assert {row["consumer_field"] for row in contract["requirements"]} >= {"scenes", "scenes[].name"}
    assert all(row["consumer_invariant"].startswith("core.script_ir") for row in contract["requirements"])


def test_audit_separates_source_structural_and_later_authoring_fields():
    audit = audit_script_ir_consumers()
    assert audit["status"] == "SCRIPT_IR_CONSUMER_AUDIT"
    assert any(row["field"] == "scenes" for row in audit["source_fields"])
    assert any(row["field"] == "scene_id" for row in audit["deterministic_transforms"])
    assert "camera" in audit["later_authoring"]


def test_compiler_is_deterministic_and_does_not_promote_production_fields():
    first = compile_script_ir_source_requirements(source_structure=_source())
    second = compile_script_ir_source_requirements(source_structure=_source())
    assert first["fingerprint"] == second["fingerprint"]
    assert first["provider_calls"] == 0
    assert first["blocking_requirement_count"] == 2
    assert first["optional_requirement_count"] == 1
    assert not any(row["predicate"] in {"visual_identity", "geometry", "state"} for row in first["requirements"])
    assert first["structural_metadata_requirements"][0]["provenance"] == "deterministic_transform"


def test_missing_scenes_is_fail_closed_and_empty_contract_is_diagnostic():
    requirement_set = compile_script_ir_source_requirements(source_structure={"episode": 1, "scenes": []})
    coverage = evaluate_script_ir_source_coverage(requirement_set, records=[])
    assert coverage["status"] == "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_INSUFFICIENT"
    assert coverage["counts"]["missing"] == 1
    empty = evaluate_script_ir_source_coverage({"requirements": []}, records=[])
    assert empty["status"] == "REQUIREMENT_CONTRACT_EMPTY_ERROR"


def test_complete_source_evidence_is_sufficient_and_structural_metadata_is_separate():
    requirement_set = compile_script_ir_source_requirements(source_structure=_source())
    records = [
        {"fact_key": "episode|scenes|scene_existence|episode", "predicate": "scene_existence", "subject_id": "1", "value": {"minimum": 1, "actual": 1}, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]},
        {"fact_key": "scene|门厅|scene_identity|scene", "predicate": "scene_identity", "subject_id": "门厅", "value": "门厅", "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]},
    ]
    coverage = evaluate_script_ir_source_coverage(requirement_set, records=records)
    assert coverage["status"] == "SCRIPT_IR_SOURCE_CONTRACT_COVERAGE_SUFFICIENT"
    assert coverage["counts"]["covered"] == 2
    assert coverage["source_fact_only_missing_manifest"]["items"] == []
    assert requirement_set["structural_metadata_requirements"]


def test_historical_downstream_requirements_are_not_reclassified_by_compiler():
    requirement_set = compile_script_ir_source_requirements(source_structure=_source())
    predicates = {row["predicate"] for row in requirement_set["requirements"]}
    assert predicates == {"scene_existence", "scene_identity", "event_occurrence"}
