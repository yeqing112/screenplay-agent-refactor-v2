import copy

from core.provider_structured_output_qualification import compile_provider_strict_schema, fingerprint, validate_json_schema_subset
from core.source_entity_proposal import entity_candidate_fingerprint
from core.source_entity_semantic_verification import (
    KIND_VERDICTS,
    MENTION_VERDICTS,
    VERIFICATION_VERSION,
    build_verification_schema,
    compile_verified_entity_registry,
    recompute_lineage_reconciliation,
    validate_frozen_proposal_registry,
    validate_verification_coverage,
    validate_verification_evidence_scope,
    verification_summary,
)


def lineage_fixture():
    origin_hash = "source-hash"
    migration_payload = {"migration_version": "migration-v1", "provider_calls": 0}
    reconciliation_payload = {"policy_version": "salvage-v1", "source_response_sha256": "response-hash"}
    migration_fp = fingerprint(migration_payload)
    reconciliation_fp = fingerprint(reconciliation_payload)
    lineage = {
        "origin_source_locator": {"book_id": 990402, "chapter_id": 16, "chapter_seq": 3},
        "origin_source_kind": "BOOK_CHAPTER",
        "origin_source_package_id": "book:990402",
        "origin_source_raw_hash": origin_hash,
        "origin_source_version_id": f"chapter:16:sha256:{origin_hash}",
        "migration_fingerprint": migration_fp,
        "reconciliation_fingerprint": reconciliation_fp,
        "reconciliation_policy_version": "salvage-v1",
        "structuring_response_fingerprint": "response-hash",
    }
    envelope_fields = {
        "migration_fingerprint": migration_fp,
        "origin_source_kind": "BOOK_CHAPTER",
        "origin_source_package_id": "book:990402",
        "origin_source_raw_hash": origin_hash,
        "origin_source_version_id": f"chapter:16:sha256:{origin_hash}",
        "reconciliation_fingerprint": reconciliation_fp,
        "reconciliation_policy_version": "salvage-v1",
        "structuring_response_fingerprint": "response-hash",
    }
    actual = {"book_id": 990402, "chapter_id": 16, "chapter_seq": 3, "raw_byte_length": 25, "raw_sha256": origin_hash, "title": "Chapter 16"}
    expected_origin = {"book_id": 990402, "chapter_id": 16, "chapter_seq": 3, "expected_raw_byte_length": 25, "expected_raw_sha256": origin_hash, "expected_title": " Chapter 16 "}
    v776_freeze = {"status": "PASS", "book_id": 990453, "source_package_id": "book:990402", "source_fingerprint": origin_hash, "source_unit_fingerprint": "units-fp", "source_unit_count": 12}
    frozen_manifest = {"status": "FROZEN_COMPLETE_SELF_CONSISTENT", "persistence_run_id": "run-1", "origin": {"book_id": 990402, "chapter_id": 16, "chapter_seq": 3, "raw_byte_length": 25, "raw_sha256": origin_hash}, "migration_fingerprint": migration_fp, "reconciliation_fingerprint": reconciliation_fp, "forensic_sha256": "response-hash"}
    migration_payload["provider_calls"] = 0
    migration = {"status": "PASS", "migration": migration_payload, "migration_fingerprint": fingerprint(migration_payload)}
    migration_fp = migration["migration_fingerprint"]
    lineage["migration_fingerprint"] = migration_fp
    envelope_fields["migration_fingerprint"] = migration_fp
    frozen_manifest["migration_fingerprint"] = migration_fp
    reconciliation = {"status": "PASS", "reconciliation": reconciliation_payload, "reconciliation_fingerprint": reconciliation_fp}
    args = {
        "new_book": {"status": "PASS", "new_book_not_origin": True, "persistence_run_id": "run-1", "book": {"id": 990453, "status": "imported"}},
        "frozen_source_lineage": {"status": "PASS", "placeholder_scan": {"placeholders": []}, "source_lineage": lineage},
        "origin_refreeze": {"status": "PASS", "actual": actual, "expected": expected_origin},
        "authority_envelope_audit": {"status": "PASS", "stale_status": "FRESH", "lineage_fields": envelope_fields},
        "runtime_book_id": 990453,
        "runtime_source_fingerprint": origin_hash,
        "runtime_origin_source_package_id": "book:990402",
        "runtime_authority_envelope": envelope_fields,
        "v776_source_freeze": v776_freeze,
        "migration_artifact": migration,
        "reconciliation_artifact": reconciliation,
        "frozen_manifest": frozen_manifest,
        "production_db_after": {"new_book_id": 990453},
        "expected": {"target_book_id": 990453, "origin_source_book_id": 990402, "origin_source_package_id": "book:990402", "origin_chapter_id": 16, "origin_chapter_seq": 3, "origin_source_raw_hash": origin_hash, "source_unit_fingerprint": "units-fp"},
    }
    return args


def registry_fixture():
    candidates = []
    proposal_entities = {}
    assignments = []
    for index, (kind, surface, evidence, unit) in enumerate([
        ("OBJECT", "object alpha", "EV_A", "UNIT_A"),
        ("LOCATION", "room beta", "EV_B", "UNIT_B"),
    ], start=1):
        ref = f"PEC_{index:04d}"
        candidate = {"schema_version": "source_entity_candidate_v1", "kind": kind, "surface_form": surface, "evidence_refs": [evidence], "source_unit_refs": [unit]}
        fp = entity_candidate_fingerprint(candidate)
        candidates.append((ref, candidate, fp))
        assignments.append({"proposal_entity_ref": ref, "status": "PROPOSED", "authority": "UNTRUSTED_PROPOSED", "fingerprint": fp, "candidate_index": index - 1, "entity": candidate})
        proposal_entities[ref] = {"ref": ref, "kind": kind, "surface_form": surface, "authority": "UNTRUSTED_PROPOSED", "evidence_refs": [evidence], "source_unit_refs": [unit], "fingerprint": fp}
    canonical = {"SCENE_A": {"ref": "SCENE_A", "kind": "SCENE", "authority": "CANONICAL_RUNTIME"}}
    entities = {**canonical, **proposal_entities}
    registry = {"schema_version": "source_proposal_entity_registry_v1", "authority_boundary": "fixture", "entities": entities, "fingerprint": fingerprint(entities), "status": "PASS", "proposal_entity_count": 2, "canonical_entity_count": 1, "persisted": False}
    assignment = {"rows": assignments, "fingerprint": fingerprint(assignments), "id_owner": "program", "provider_supplied_id": False, "provider_owned_ids": False}
    return registry, assignment, candidates


def valid_payload():
    return {"schema_version": VERIFICATION_VERSION, "results": [
        {"proposal_entity_ref": "PEC_0002", "mention_verdict": "EXPLICITLY_EVIDENCED", "kind_verdict": "SUPPORTED", "evidence_refs": ["EV_B"]},
        {"proposal_entity_ref": "PEC_0001", "mention_verdict": "EXPLICITLY_EVIDENCED", "kind_verdict": "SUPPORTED", "evidence_refs": ["EV_A"]},
    ]}


def test_cross_book_lineage_passes_when_all_provenance_matches():
    result = recompute_lineage_reconciliation(**lineage_fixture())
    assert result["status"] == "PASS"
    assert result["target_book_id"] == 990453
    assert result["origin_source_book_id"] == 990402
    assert result["cross_book_source"] is True
    assert result["cross_book_is_not_itself_a_mismatch"] is True


def test_cross_book_difference_alone_is_not_a_lineage_failure():
    args = lineage_fixture()
    args["runtime_book_id"] = 990454
    args["new_book"]["book"]["id"] = 990454
    args["production_db_after"]["new_book_id"] = 990454
    args["expected"]["target_book_id"] = 990454
    result = recompute_lineage_reconciliation(**args)
    assert result["status"] == "PASS"
    assert result["cross_book_source"] is True


def test_lineage_package_raw_hash_authority_and_migration_drift_block():
    for location, key, value in [
        ("authority_envelope_audit", "origin_source_package_id", "book:elsewhere"),
        ("origin_refreeze", "actual", {"book_id": 990402, "chapter_id": 16, "chapter_seq": 3, "raw_byte_length": 25, "raw_sha256": "other", "title": "Chapter 16"}),
        ("migration_artifact", "migration_fingerprint", "changed"),
        ("reconciliation_artifact", "reconciliation_fingerprint", "changed"),
    ]:
        args = lineage_fixture()
        if location == "authority_envelope_audit":
            args[location]["lineage_fields"][key] = value
        else:
            args[location][key] = value
        assert recompute_lineage_reconciliation(**args)["status"] == "BLOCKED"


def test_frozen_proposal_registry_fingerprint_and_candidate_payload_are_bound():
    registry, assignment, _ = registry_fixture()
    result = validate_frozen_proposal_registry(registry_artifact=registry, assignment_artifact=assignment, expected_registry_fingerprint=registry["fingerprint"], expected_assignment_fingerprint=assignment["fingerprint"], expected_count=2)
    assert result["status"] == "PASS"
    assert set(result["candidates"]) == {"PEC_0001", "PEC_0002"}
    changed = copy.deepcopy(registry)
    changed["entities"]["PEC_0001"]["surface_form"] = "locally changed"
    assert validate_frozen_proposal_registry(registry_artifact=changed, assignment_artifact=assignment, expected_registry_fingerprint=registry["fingerprint"], expected_assignment_fingerprint=assignment["fingerprint"], expected_count=2)["status"] == "BLOCKED"


def test_verification_transport_schema_is_strict_and_dynamic():
    internal = build_verification_schema(proposal_refs=["PEC_0002", "PEC_0001"], evidence_refs=["EV_A", "EV_B"])
    compiled = compile_provider_strict_schema(internal)
    assert compiled["audit"]["status"] == "PASS"
    assert compiled["schema"]["additionalProperties"] is False
    assert compiled["schema"]["properties"]["results"]["minItems"] == 2
    payload = valid_payload()
    assert validate_json_schema_subset(payload, compiled["schema"])["status"] == "PASS"
    payload["results"][0]["replacement_kind"] = "OBJECT"
    assert validate_json_schema_subset(payload, compiled["schema"])["status"] == "BLOCKED"


def test_exact_pec_coverage_allows_order_change_but_blocks_missing_duplicate_unknown():
    value = valid_payload()
    assert validate_verification_coverage(value, expected_refs=["PEC_0001", "PEC_0002"])["status"] == "PASS"
    missing = {**value, "results": value["results"][:1]}
    assert "MISSING_PEC_REF" in validate_verification_coverage(missing, expected_refs=["PEC_0001", "PEC_0002"])["errors"]
    duplicate = {**value, "results": [value["results"][0], {**value["results"][0], "mention_verdict": "AMBIGUOUS"}]}
    assert "DUPLICATE_PEC_REF" in validate_verification_coverage(duplicate, expected_refs=["PEC_0001", "PEC_0002"])["errors"]
    unknown = {**value, "results": [value["results"][0], {**value["results"][1], "proposal_entity_ref": "PEC_9999"}]}
    assert "UNKNOWN_PEC_REF" in validate_verification_coverage(unknown, expected_refs=["PEC_0001", "PEC_0002"])["errors"]


def test_verifier_evidence_must_be_subset_of_each_frozen_candidate():
    _, _, rows = registry_fixture()
    candidates = {ref: {"evidence_refs": candidate["evidence_refs"]} for ref, candidate, _ in rows}
    payload = valid_payload()
    coverage = validate_verification_coverage(payload, expected_refs=list(candidates))
    assert validate_verification_evidence_scope(coverage["results_by_ref"], candidates=candidates)["status"] == "PASS"
    laundered = {**payload, "results": [dict(payload["results"][0]), dict(payload["results"][1])]}
    laundered["results"][1]["evidence_refs"] = ["EV_B"]
    coverage = validate_verification_coverage(laundered, expected_refs=list(candidates))
    scope = validate_verification_evidence_scope(coverage["results_by_ref"], candidates=candidates)
    assert scope["status"] == "BLOCKED"
    assert scope["cross_candidate_evidence_laundering_blocked"] is True


def test_verdict_enums_and_program_compilation_never_promotes():
    assert set(MENTION_VERDICTS) == {"EXPLICITLY_EVIDENCED", "NOT_EXPLICITLY_EVIDENCED", "AMBIGUOUS"}
    assert set(KIND_VERDICTS) == {"SUPPORTED", "UNSUPPORTED", "AMBIGUOUS"}
    registry, assignment, rows = registry_fixture()
    freeze = validate_frozen_proposal_registry(registry_artifact=registry, assignment_artifact=assignment, expected_registry_fingerprint=registry["fingerprint"], expected_assignment_fingerprint=assignment["fingerprint"], expected_count=2)
    valid = valid_payload()
    coverage = validate_verification_coverage(valid, expected_refs=list(freeze["candidates"]))
    compiled = compile_verified_entity_registry(canonical_entities={"SCENE_A": {"kind": "SCENE"}}, candidates=freeze["candidates"], results_by_ref=coverage["results_by_ref"])
    assert compiled["status"] == "SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED"
    assert compiled["registry"]["canonical_promotions"] == 0
    assert all(value["canonical"] is False and value["authority"] == "SEMANTICALLY_VERIFIED_PROPOSAL" for value in compiled["registry"]["proposal_entities"].values())
    assert compiled["registry"]["canonical_runtime_entities"]["SCENE_A"]["authority"] == "CANONICAL_RUNTIME"
    assert compiled["registry"]["fingerprint"] == compile_verified_entity_registry(canonical_entities={"SCENE_A": {"kind": "SCENE"}}, candidates=freeze["candidates"], results_by_ref=coverage["results_by_ref"])["registry"]["fingerprint"]


def test_ambiguous_and_rejected_states_are_distinct_with_rejection_precedence():
    registry, assignment, _ = registry_fixture()
    freeze = validate_frozen_proposal_registry(registry_artifact=registry, assignment_artifact=assignment, expected_registry_fingerprint=registry["fingerprint"], expected_assignment_fingerprint=assignment["fingerprint"], expected_count=2)
    value = valid_payload()
    value["results"][0]["mention_verdict"] = "AMBIGUOUS"
    compiled = compile_verified_entity_registry(canonical_entities={}, candidates=freeze["candidates"], results_by_ref=validate_verification_coverage(value, expected_refs=list(freeze["candidates"]))["results_by_ref"])
    assert compiled["status"] == "SOURCE_ENTITY_SEMANTIC_REVIEW_REQUIRED"
    assert compiled["registry"]["proposal_entities"]["PEC_0002"]["authority"] == "ENTITY_SEMANTIC_REVIEW_REQUIRED"
    assert compiled["registry"]["proposal_entities"]["PEC_0002"]["verification_state"] == "ENTITY_SEMANTIC_REVIEW_REQUIRED"
    value["results"][1]["kind_verdict"] = "UNSUPPORTED"
    rejected = compile_verified_entity_registry(canonical_entities={}, candidates=freeze["candidates"], results_by_ref=validate_verification_coverage(value, expected_refs=list(freeze["candidates"]))["results_by_ref"])
    assert rejected["status"] == "SOURCE_ENTITY_PROPOSAL_REVISION_BOUNDARY_REQUIRED"
    rejected_pec = rejected["registry"]["proposal_entities"]["PEC_0001"]
    assert rejected_pec["verification_state"] == "ENTITY_PROPOSAL_REJECTED"
    assert rejected_pec["authority"] == "REJECTED_PROPOSAL"
    assert rejected["rejected_count"] == 1


def test_summary_keeps_entity_completeness_unproven():
    registry, assignment, _ = registry_fixture()
    freeze = validate_frozen_proposal_registry(registry_artifact=registry, assignment_artifact=assignment, expected_registry_fingerprint=registry["fingerprint"], expected_assignment_fingerprint=assignment["fingerprint"], expected_count=2)
    payload = valid_payload()
    by_ref = validate_verification_coverage(payload, expected_refs=list(freeze["candidates"]))["results_by_ref"]
    compiled = compile_verified_entity_registry(canonical_entities={}, candidates=freeze["candidates"], results_by_ref=by_ref)
    summary = verification_summary(by_ref, compiled)
    assert summary["entity_semantic_completeness"] == "NOT_PROVEN"
    assert summary["canonical_promotions"] == 0
