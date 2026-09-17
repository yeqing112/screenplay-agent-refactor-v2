import json

from core.fact_coverage import MissingFactManifest, build_missing_fact_manifest, script_ir_gate
from core.fact_coverage_verifier import run_targeted_missing_fact_extraction, verify_fact_coverage
from core.targeted_missing_fact_extraction import extract_targeted_missing_facts, merge_fact_snapshot_records
from core.fact_snapshot import build_fact_snapshot


def _req(**overrides):
    base = {"subject_type": "character", "subject_id": "林晚", "predicate": "gender", "scope": "global", "consumer": "script_ir", "required": True}
    base.update(overrides)
    return base


def _source(value="female"):
    return f"FACT: subject_type=character; subject_id=林晚; predicate=gender; value={value}\n"


def test_missing_fact_manifest_distinguishes_absent_and_insufficient_evidence():
    records = [{"subject_type": "character", "subject_id": "林晚", "predicate": "gender", "scope": "global", "value": "female", "authority": "derived_fact", "status": "proposed", "evidence": []}]
    result = build_missing_fact_manifest([_req(), _req(subject_id="林远", predicate="age")], records)
    assert result["status"] == "FACT_COVERAGE_INSUFFICIENT"
    reasons = {item["entity"]: item["missing_reason"] for item in result["missing_fact_manifest"]["items"]}
    assert reasons["林晚"] == "INSUFFICIENT_EVIDENCE"
    assert reasons["林远"] == "ABSENT"


def test_missing_fact_manifest_has_formal_round_trip_schema():
    result = build_missing_fact_manifest([_req()], [])
    manifest = MissingFactManifest.from_dict(result["missing_fact_manifest"])
    assert manifest.to_dict() == result["missing_fact_manifest"]
    assert manifest.schema_version == "missing_fact_manifest_v1"


def test_targeted_extraction_successfully_extracts_only_manifest_fact():
    coverage = verify_fact_coverage(records=[], requirements=[_req()])
    result = extract_targeted_missing_facts(_source(), {}, coverage["missing_fact_manifest"])
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["value"] == "female"
    assert not result["unresolved"]
    assert result["provider_calls"] == 0


def test_unreliable_natural_language_is_unresolved_not_a_guess():
    coverage = verify_fact_coverage(records=[], requirements=[_req()])
    result = extract_targeted_missing_facts("林晚看起来很像女性。", {}, coverage["missing_fact_manifest"])
    assert not result["candidates"]
    assert result["unresolved"][0]["reason"] == "NO_RELIABLE_EVIDENCE"


def test_conflicting_source_declarations_are_preserved_as_unresolved():
    coverage = verify_fact_coverage(records=[], requirements=[_req()])
    result = extract_targeted_missing_facts(_source("female") + _source("male"), {}, coverage["missing_fact_manifest"])
    assert not result["candidates"]
    assert result["unresolved"][0]["reason"] == "CONFLICTING_SOURCE_DECLARATIONS"


def test_evidence_locator_and_value_support_are_validated():
    coverage = verify_fact_coverage(records=[], requirements=[_req()])
    extracted = extract_targeted_missing_facts(_source(), {}, coverage["missing_fact_manifest"])
    candidate = extracted["candidates"][0].copy()
    candidate["value"] = "male"
    merged = merge_fact_snapshot_records({"book_id": 1, "episode": 1, "records": []}, [candidate], coverage["missing_fact_manifest"], extracted["source_index"])
    assert not merged["added"]
    assert merged["unresolved"][0]["reason"] == "CANDIDATE_REJECTED"
    assert any(error["code"] == "EVIDENCE_VALUE_UNSUPPORTED" for error in merged["unresolved"][0]["errors"])


def test_existing_authoritative_fact_wins_and_candidate_cannot_overwrite():
    existing = {"subject_type": "character", "subject_id": "林晚", "predicate": "gender", "scope": "global", "value": "female", "authority": "source_text", "status": "confirmed", "evidence": [{"anchor_ref": "E0001", "excerpt": _source(), "source_raw_hash": "hash", "verified": True}]}
    coverage = verify_fact_coverage(records=[existing], requirements=[_req(expected_value="female")])
    assert coverage["status"] == "FACT_COVERAGE_SUFFICIENT"
    assert script_ir_gate(coverage)["allowed"] is True
    # A different candidate is rejected by candidate validation and does not
    # silently replace the authoritative value.
    source = _source("male")
    before = build_fact_snapshot([existing], book_id=1, episode=1)
    missing = {"items": [{**_req(expected_value="female"), "fact_key": "character|林晚|gender|global"}]}
    extracted = extract_targeted_missing_facts(source, before, missing)
    assert not extracted["candidates"]


def test_merge_adds_candidate_and_changes_revision_hash():
    coverage = verify_fact_coverage(records=[], requirements=[_req()])
    extracted = extract_targeted_missing_facts(_source(), {"book_id": 1, "episode": 1, "records": []}, coverage["missing_fact_manifest"])
    merged = merge_fact_snapshot_records({"book_id": 1, "episode": 1, "records": [], "payload_hash": ""}, extracted["candidates"], coverage["missing_fact_manifest"], extracted["source_index"])
    assert merged["added"]
    assert merged["changed"] is True
    assert merged["revision"] == 1
    assert merged["snapshot"]["records"][0]["evidence"][0]["verified"] is True


def test_recheck_opens_script_ir_only_after_coverage_is_sufficient():
    reqs = [_req()]
    initial = {"book_id": 1, "episode": 1, "records": [], "payload_hash": ""}
    result = run_targeted_missing_fact_extraction(source_material=_source(), current_snapshot=initial, requirements=reqs)
    assert result["coverage_before"]["status"] == "FACT_COVERAGE_INSUFFICIENT"
    assert result["coverage_after"]["status"] == "FACT_COVERAGE_SUFFICIENT"
    assert result["coverage_after"]["script_ir_gate"]["status"] == "SCRIPT_IR_ALLOWED"
    assert result["provider_calls"] == 0


def test_merge_remains_blocked_when_no_reliable_candidate_exists():
    result = run_targeted_missing_fact_extraction(source_material="没有结构化事实声明。", current_snapshot={"book_id": 1, "episode": 1, "records": []}, requirements=[_req()])
    assert result["coverage_after"]["status"] == "FACT_COVERAGE_INSUFFICIENT"
    assert result["coverage_after"]["script_ir_gate"]["status"] == "BLOCKED_PENDING_TARGETED_MISSING_FACTS"
    assert result["merge"]["changed"] is False


def test_irrelevant_fact_is_not_modified():
    reqs = [_req()]
    unrelated = {"subject_type": "prop", "subject_id": "钥匙", "predicate": "state", "scope": "global", "value": "closed", "authority": "source_text", "status": "confirmed", "evidence": [{"anchor_ref": "E0001", "excerpt": _source(), "source_raw_hash": "x", "verified": True}]}
    result = run_targeted_missing_fact_extraction(_source(), {"book_id": 1, "episode": 1, "records": [unrelated]}, reqs)
    records = result["merge"]["snapshot"]["records"]
    assert any(row["subject_type"] == "prop" for row in records)
    assert any(row["subject_type"] == "character" for row in records)


def test_idempotency_second_merge_has_no_new_revision():
    reqs = [_req()]
    initial = {"book_id": 1, "episode": 1, "records": []}
    first = run_targeted_missing_fact_extraction(_source(), initial, reqs)
    second = run_targeted_missing_fact_extraction(_source(), first["merge"]["snapshot"], reqs)
    assert first["extraction"]["result_fingerprint"] == second["extraction"]["result_fingerprint"]
    assert second["merge"]["changed"] is False
    assert second["merge"]["revision"] == first["merge"]["revision"]


def test_invalid_candidate_scope_is_rejected():
    coverage = verify_fact_coverage(records=[], requirements=[_req()])
    extracted = extract_targeted_missing_facts(_source(), {}, coverage["missing_fact_manifest"])
    candidate = extracted["candidates"][0]
    candidate["predicate"] = "age"
    merged = merge_fact_snapshot_records({"book_id": 1, "episode": 1, "records": []}, [candidate], coverage["missing_fact_manifest"], extracted["source_index"])
    assert merged["unresolved"][0]["reason"] == "OUT_OF_SCOPE"


def test_manifest_and_extraction_are_deterministic_json_safe():
    reqs = [_req()]
    a = run_targeted_missing_fact_extraction(_source(), {"book_id": 1, "episode": 1, "records": []}, reqs)
    b = run_targeted_missing_fact_extraction(_source(), {"book_id": 1, "episode": 1, "records": []}, reqs)
    assert json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)
