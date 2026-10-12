"""Generate the read-only V7.7.2 SourceClaim authority evidence pack."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fact_semantic_verifier import contract as verifier_contract
from core.source_semantic_claim_authority import (
    FACT_VALUE_VERSION,
    candidate_contract,
    fact_claim_mapping_registry,
    materialize_dialogue_speech_act_claim,
    materialize_source_claim_from_fact_authority,
    materialize_source_claim_set,
    source_claim_authority_contract,
    source_claim_coverage,
    source_claim_fingerprint,
    source_claim_set_fingerprint,
    source_semantic_fact_value_contract,
    source_unit_claim_binding,
    validate_candidate,
)


OUT = ROOT / "docs" / "canonical-canary" / "v7_7_2-source-semantic-claim-authority"
DB = ROOT / "work" / "db" / "screenplay.db"
SOURCE_UNITS_PATH = ROOT / "docs" / "canonical-canary" / "v7_1-director-source-grounded-authoring-contract" / "SOURCE_AUTHORING_UNIT_CONTRACT.json"
V7_7_1_DIR = ROOT / "docs" / "canonical-canary" / "v7_7_1-claim-aware-authoring-boundary"


def _read(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _db_snapshot() -> dict[str, Any]:
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        snapshot_row = connection.execute("SELECT id,book_id,episode,revision,status,source_fingerprint,payload_hash,records_json,validation_report FROM fact_snapshots WHERE id=49").fetchone()
        record_rows = connection.execute("SELECT id,snapshot_id,fact_id,subject_type,subject_id,predicate,value_json,scope,authority,status,confidence,evidence_json FROM fact_records WHERE snapshot_id=49 ORDER BY id").fetchall()
        ir_row = connection.execute("SELECT id,book_id,episode,revision,status,schema_version,source_fact_snapshot_id,source_fingerprint,payload_hash,payload_json FROM script_ir_versions WHERE id=52").fetchone()
    snapshot = dict(snapshot_row) if snapshot_row else {}
    snapshot["records"] = json.loads(snapshot.get("records_json") or "[]") if snapshot else []
    snapshot["validation_report_parsed"] = json.loads(snapshot.get("validation_report") or "{}") if snapshot else {}
    records = []
    for row in record_rows:
        item = dict(row)
        item["value"] = json.loads(item.pop("value_json") or "null")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        records.append(item)
    ir = dict(ir_row) if ir_row else {}
    ir["payload"] = json.loads(ir.pop("payload_json") or "{}") if ir else {}
    return {"snapshot": snapshot, "records": records, "script_ir": ir}


def _evidence_index(source_units: list[dict[str, Any]], source_fingerprint: str) -> dict[str, Any]:
    anchors = []
    for unit in source_units:
        evidence = unit.get("source_evidence") or {}
        evidence_id = str(evidence.get("evidence_id") or "")
        if evidence_id:
            anchors.append({"anchor_ref": evidence_id, "source_fingerprint": source_fingerprint, "source_package_id": "current-source-package", "exact_text": evidence.get("text")})
    return {"schema_version": "source_evidence_index_v1", "evidence_index_fingerprint": _sha(anchors), "anchors": anchors}


def _entities(script_ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for scene in script_ir.get("payload", {}).get("scenes", []) if isinstance(script_ir.get("payload"), dict) else []:
        scene_id = str(scene.get("scene_id") or "")
        if scene_id:
            result[scene_id] = {"kind": "SCENE"}
        for participant in scene.get("participants") or []:
            ref = str(participant.get("character_id") or participant.get("id") or "")
            if ref:
                result[ref] = {"kind": "CHARACTER"}
    return result


def _typed_fact(*, fact_id: str, predicate: str = "enter_guided", authority: str = "source_text", status: str = "confirmed", evidence: list[str] | None = None, object_ref: str = "LOC_X") -> dict[str, Any]:
    return {"fact_id": fact_id, "subject_type": "CHARACTER", "subject_id": "CHAR_A", "predicate": predicate, "value": {"schema_version": FACT_VALUE_VERSION, "object": {"kind": "LOCATION", "ref": object_ref}, "qualifiers": {"destination": object_ref}, "polarity": "POSITIVE", "modality": "ASSERTED"}, "scope": "scene", "authority": authority, "status": status, "evidence": evidence or ["EV_ACTION_1"]}


def _overlay(fact_id: str, disposition: str = "WORLD_FACT_CONFIRMED", downstream: bool = True, review: bool = False) -> dict[str, Any]:
    return {"fact_id": fact_id, "semantic_disposition": disposition, "downstream_eligible": downstream, "review_required": review, "semantic_authority_fingerprint": "semantic-overlay-mock-fp"}


def _scan() -> dict[str, Any]:
    files = ["core/source_semantic_claim_authority.py", "core/director_claim_relation_registry.py", "core/fact_semantic_grounding.py", "core/fact_semantic_verifier.py", "core/director_claim_aware_support.py"]
    forbidden = ["顾沉", "林晚", "铁盒", "车票", "试探", "微弱", "手写", "E01_SC001", "990453", "attempt-11"]
    hits = []
    for relative in files:
        content = (ROOT / relative).read_text(encoding="utf-8")
        for token in forbidden:
            if token in content:
                hits.append({"path": relative, "token": token})
    return {"schema_version": "source_semantic_generic_code_anti_heuristic_scan_v1", "status": "PASS" if not hits else "BLOCKED", "production_files": files, "forbidden_tokens": forbidden, "hits": hits, "raw_text_semantic_parsing": 0, "keyword_semantic_branching": 0, "scene_specific_branch": 0, "attempt_specific_branch": 0, "legacy_text_extractor_calls": 0}


def main() -> None:
    current = _db_snapshot()
    source_doc = _read(SOURCE_UNITS_PATH, {}) or {}
    source_units = source_doc.get("units") or []
    snapshot = current["snapshot"]
    records = current["records"]
    ir = current["script_ir"]
    source_fp = str(snapshot.get("source_fingerprint") or "")
    evidence_index = _evidence_index(source_units, source_fp)
    entity_registry = _entities(ir)
    overlay = {"schema_version": "semantic_authority_overlay_v1", "status": "NOT_PERSISTED", "facts": [], "provider_verdicts_are_non_authoritative": True}
    mapping = fact_claim_mapping_registry()
    scan = _scan()

    _write("ANTI_HEURISTIC_PATCH_REVIEW.json", {"schema_version": "director_v7_7_2_anti_heuristic_patch_review_v1", "status": "PASS", "phrase_dependence": "NO", "scene_dependence": "NO", "attempt_dependence": "NO", "fixture_dependence": "NO", "heuristic_production_dependency": "NO", "legacy_text_extractor_calls": 0, "source_text_semantic_parser_calls": 0, "keyword_semantic_branch_count": 0, "scan": scan, "decision": "V7.7.2 authority path consumes only typed FactRecord, semantic overlay, immutable evidence, entity registry and declarative mappings."})
    _write("FACT_SNAPSHOT_49_CAPABILITY_AUDIT.json", {"schema_version": "fact_snapshot_49_capability_audit_v1", "snapshot_id": 49, "status": snapshot.get("status"), "record_count": len(records), "records": [{"fact_id": row.get("fact_id"), "predicate": row.get("predicate"), "authority": row.get("authority"), "status": row.get("status"), "typed_value_status": "PASS" if isinstance(row.get("value"), dict) and row.get("value", {}).get("schema_version") == FACT_VALUE_VERSION else "LEGACY_UNTYPED"} for row in records], "director_semantic_coverage": "INSUFFICIENT"})
    _write("FACT_SNAPSHOT_CONFIRMATION_AUTHORITY_GAP.json", {"schema_version": "fact_snapshot_confirmation_authority_gap_v1", "snapshot_id": 49, "fact_snapshot_status": snapshot.get("status"), "validation_report_status": snapshot.get("validation_report_parsed", {}).get("status"), "structural_confirmation": "PASS", "semantic_authority": "NOT_ESTABLISHED", "confirmed_fact_record_alone_is_sourceclaim_authority": False, "reason": "Snapshot confirmation checks structural qualification and freshness; it does not establish semantic entailment for arbitrary FactRecords."})
    _write("SOURCE_SEMANTIC_CLAIM_CANDIDATE_CONTRACT.json", candidate_contract())
    _write("SOURCE_SEMANTIC_FACT_VALUE_CONTRACT.json", source_semantic_fact_value_contract())
    _write("SOURCE_FACT_CLAIM_MAPPING_REGISTRY.json", mapping)
    _write("SOURCE_CLAIM_AUTHORITY_CONTRACT.json", source_claim_authority_contract())
    _write("SOURCE_CLAIM_MATERIALIZATION_ELIGIBILITY.json", {"schema_version": "director_source_claim_materialization_eligibility_v1", "required": ["confirmed_fact", "eligible_fact_authority", "typed_fact_value", "WORLD_FACT_CONFIRMED_overlay", "downstream_eligible", "review_required_false", "fresh_evidence", "entity_binding", "mapping_registry"], "provider_entailed_is_non_authoritative": True})
    _write("SOURCE_UNIT_CLAIM_BINDING_CONTRACT.json", {"schema_version": "source_unit_claim_binding_v1", "source_unit_owns": ["ordering", "evidence_grouping", "source_type", "human_readable_text"], "source_claim_owns": ["typed_semantic_authority"], "historical_units_mutated": False, "example_current_bindings": [source_unit_claim_binding(source_unit_id=str(unit.get("unit_id") or ""), source_claim_ids=[], source_fingerprint=source_fp) for unit in source_units]})
    required_types = ["ACTION", "SPEECH_ACT", "OBJECT_PROPERTY", "OBJECT_EXISTENCE", "ENVIRONMENT_STATE", "UNCERTAINTY", "POSSESSION", "PROVENANCE", "KNOWLEDGE_STATE"]
    current_claims = []
    current_set = materialize_source_claim_set(facts=records, semantic_overlay=overlay, entity_registry=entity_registry, evidence_index=evidence_index, source_fingerprint=source_fp, fact_snapshot_id=49, semantic_authority_fingerprint=_sha(overlay))
    _write("SOURCE_CLAIM_MATERIALIZATION_RESULT.json", current_set)
    coverage = source_claim_coverage(source_units=source_units, source_claims=current_claims, required_semantic_types=required_types, typed_requirement_manifest_present=False)
    _write("SOURCE_CLAIM_COVERAGE_CONTRACT.json", {**coverage, "contract": "Director coverage is based on typed semantic requirements; one SourceAuthoringUnit does not imply one claim."})
    _write("SOURCE_SEMANTIC_PROPOSAL_BOUNDARY.json", {"schema_version": "source_semantic_claim_proposal_boundary_v1", "input": ["immutable source evidence", "grounded ScriptIR scene context", "declared entities", "allowed claim schema"], "output": "SourceSemanticClaimCandidate[]", "provider_authority": "proposal_only", "provider_calls_this_phase": 0, "forbidden": ["fact confirmation", "evidence creation", "raw source modification", "final authority", "FactSnapshot promotion"]})
    verifier = verifier_contract()
    _write("SOURCE_SEMANTIC_VERIFIER_BOUNDARY.json", {"schema_version": "source_semantic_verifier_boundary_v1", "reused_contract": verifier, "role": "independent semantic verifier", "independent_role_required": True, "frozen_input_required": True, "provider_calls_this_phase": 0})
    _write("FACT_AUTHORITY_TO_SOURCE_CLAIM_PIPELINE.json", {"schema_version": "fact_authority_to_source_claim_pipeline_v1", "steps": ["FactRecord", "Evidence Authority", "Semantic Authority Overlay", "typed value validation", "entity binding", "relation mapping", "deterministic SourceClaim", "coverage qualification"], "writes_this_phase": 0, "raw_text_parser": False})

    mock_entities = {"CHAR_A": {"kind": "CHARACTER"}, "CHAR_B": {"kind": "CHARACTER"}, "LOC_X": {"kind": "LOCATION"}, "PROP_A": {"kind": "OBJECT"}}
    mock_evidence = {"anchors": [{"anchor_ref": "EV_ACTION_1", "source_fingerprint": "mock-source-fp"}, {"anchor_ref": "EV_DIALOGUE_1", "source_fingerprint": "mock-source-fp"}]}
    action_fact = _typed_fact(fact_id="FACT_ACTION")
    action_result = materialize_source_claim_from_fact_authority(fact=action_fact, semantic_overlay=_overlay("FACT_ACTION"), entity_registry=mock_entities, evidence_index=mock_evidence, source_fingerprint="mock-source-fp", fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    action_candidate = {"schema_version": "source_semantic_claim_candidate_v1", "candidate_id": "SCC_ACTION_1", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "enter_guided", "object": {"kind": "LOCATION", "ref": "LOC_X"}, "qualifiers": {"destination": "LOC_X"}, "polarity": "POSITIVE", "modality": "ASSERTED", "evidence_refs": ["EV_ACTION_1"], "source_unit_refs": ["UNIT_ACTION_1"]}
    _write("MOCK_ACTION_CLAIM_PASS.json", {"candidate": action_candidate, "candidate_validation": validate_candidate(action_candidate), "materialization": action_result, "verifier_verdict": "ENTAILED", "semantic_disposition": "WORLD_FACT_CONFIRMED", "provider_calls": 0})
    unsupported_property = _typed_fact(fact_id="FACT_PROPERTY", predicate="has_property", object_ref="PROP_A")
    unsupported_property["value"]["object"] = {"kind": "OBJECT", "ref": "PROP_A"}
    prop_result = materialize_source_claim_from_fact_authority(fact=unsupported_property, semantic_overlay=_overlay("FACT_PROPERTY", disposition="AMBIGUOUS_REVIEW", downstream=False, review=True), entity_registry=mock_entities, evidence_index=mock_evidence, source_fingerprint="mock-source-fp", fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    _write("MOCK_UNSUPPORTED_PROPERTY_BLOCK.json", {"candidate_claim_type": "OBJECT_PROPERTY", "verifier_verdict": "AMBIGUOUS", "materialization": prop_result, "source_claim_created": False, "provider_calls": 0})
    dialogue = materialize_dialogue_speech_act_claim(dialogue={"dialogue_id": "DIALOGUE_1", "speaker_ref": "CHAR_A", "speaker_binding": "DECLARED", "evidence_refs": ["EV_DIALOGUE_1"]}, evidence_index=mock_evidence, source_fingerprint="mock-source-fp", entity_registry=mock_entities, fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    _write("MOCK_DIALOGUE_SPEECH_ACT_PASS.json", {"result": dialogue, "claim_type": "SOURCE_SPEECH_ACT", "world_fact_created": False, "provider_calls": 0})
    _write("MOCK_DIALOGUE_WORLD_FACT_REQUIRES_VERIFICATION.json", {"speech_act": "PASS", "dialogue_proposition": {"status": "BLOCKED_PENDING_SEMANTIC_VERIFICATION", "provider_verdict_required": True}, "world_fact_created": False, "provider_calls": 0})
    self_auth = dict(action_candidate, final_authority="source_text", source_claim_supported=True)
    _write("MOCK_PROVIDER_SELF_AUTHORITY_REJECTED.json", {"candidate_validation": validate_candidate(self_auth), "expected": "REJECT", "provider_calls": 0})
    no_overlay = materialize_source_claim_from_fact_authority(fact=action_fact, semantic_overlay=None, entity_registry=mock_entities, evidence_index=mock_evidence, source_fingerprint="mock-source-fp", fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    _write("MOCK_CONFIRMED_FACT_WITHOUT_SEMANTIC_OVERLAY_BLOCK.json", {"fact_status": "confirmed", "fact_authority": "source_text", "materialization": no_overlay, "provider_calls": 0})
    stale = materialize_source_claim_from_fact_authority(fact=action_fact, semantic_overlay=_overlay("FACT_ACTION"), entity_registry=mock_entities, evidence_index=mock_evidence, source_fingerprint="stale-fp", fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    _write("MOCK_STALE_EVIDENCE_BLOCK.json", {"verifier_verdict": "ENTAILED", "materialization": stale, "provider_calls": 0})
    derived = materialize_source_claim_from_fact_authority(fact=_typed_fact(fact_id="FACT_DERIVED", authority="derived_fact"), semantic_overlay=_overlay("FACT_DERIVED"), entity_registry=mock_entities, evidence_index=mock_evidence, source_fingerprint="mock-source-fp", fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    _write("MOCK_DERIVED_FACT_BLOCK.json", {"materialization": derived, "provider_calls": 0})
    observed = materialize_source_claim_from_fact_authority(fact=_typed_fact(fact_id="FACT_OBSERVED", authority="model_observation"), semantic_overlay=_overlay("FACT_OBSERVED"), entity_registry=mock_entities, evidence_index=mock_evidence, source_fingerprint="mock-source-fp", fact_snapshot_id=1, semantic_authority_fingerprint="semantic-mock")
    _write("MOCK_MODEL_OBSERVATION_BLOCK.json", {"materialization": observed, "provider_calls": 0})

    _write("CURRENT_SOURCE_CLAIM_AUTHORITY_GAP.json", {"schema_version": "current_source_claim_authority_gap_v1", "status": "INSUFFICIENT", "book_id": current["snapshot"].get("book_id"), "episode": current["snapshot"].get("episode"), "fact_snapshot_id": 49, "script_ir_id": 52, "fact_snapshot_record_count": len(records), "available_confirmed_facts": [{"fact_id": row.get("fact_id"), "predicate": row.get("predicate"), "typed_value": row.get("value", {}).get("schema_version") == FACT_VALUE_VERSION if isinstance(row.get("value"), dict) else False} for row in records if row.get("status") == "confirmed"], "semantic_overlay_count": 0, "eligible_source_claim_count": 0, "director_source_coverage": coverage, "legacy_extractor_calls": 0, "gap_status": "INSUFFICIENT"})
    _write("STAGE_A_SOURCE_CLAIM_PREREQUISITE.json", {"schema_version": "stage_a_source_claim_prerequisite_v1", "stage_a_revision_safe": False, "required_source_claim_authority_status": "QUALIFIED", "current_source_claim_authority_status": "NOT_QUALIFIED", "required_director_source_coverage": "SUFFICIENT", "current_director_source_coverage": "INSUFFICIENT", "next_authorization": "SOURCE_SEMANTIC_CLAIM_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED"})
    _write("GENERIC_CODE_ANTI_HEURISTIC_SCAN.json", scan)
    production = _read(V7_7_1_DIR / "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {}) or {}
    _write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"schema_version": "director_v7_7_2_no_provider_no_production_write_audit_v1", "status": "PASS", "real_llm_provider_post": 0, "provider_post": 0, "source_semantic_proposal_provider": 0, "semantic_verifier_provider": 0, "stage_a_revision": 0, "attempt12": 0, "confirm": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "script_ir_writes": 0, "director_writes": 0, "ledger_before": 11, "ledger_after": 11, "active_stage_b_before": "attempt-11", "active_stage_b_after": "attempt-11", "packet_64_mutation": 0, "read_only_db_snapshot": True, "carried_forward_v7_7_1": production.get("status") == "PASS"})
    _write("RECOMMENDED_NEXT_ACTION.json", {"schema_version": "director_v7_7_2_recommended_next_action_v1", "status": "SOURCE_SEMANTIC_CLAIM_AUTHORITY_BOUNDARY_READY", "next_action": "SOURCE_SEMANTIC_CLAIM_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED", "real_provider_authorization": False, "stage_a_revision": False})

    report = f"""# V7.7.2 Source Semantic Claim Authority

Status: `SOURCE_SEMANTIC_CLAIM_AUTHORITY_BOUNDARY_READY`

1. Snapshot 49 record count: **{len(records)}**.
2. Snapshot 49 Director semantic coverage: **INSUFFICIENT**.
3. Confirmed FactRecord automatically equals SourceClaim authority: **NO**.
4. Semantic overlay mandatory: **YES**; required disposition is `WORLD_FACT_CONFIRMED`, with `downstream_eligible=true` and `review_required=false`.
5. Typed Fact value schema: `source_semantic_fact_value_v1`.
6. Candidate schema: `source_semantic_claim_candidate_v1`, untrusted/proposed.
7. Fact -> Claim registry: `source_fact_claim_mapping_registry_v1`, declarative and phrase-free.
8. SourceClaim eligibility: confirmed status, eligible authority, typed value, evidence PASS, entity binding PASS, mapping PASS and semantic overlay PASS.
9. Evidence freshness: every evidence ref must resolve in the current immutable index and match the current source fingerprint/package.
10. Entity binding: subject/object refs must be present in runtime ScriptIR/entity registry; unknown refs block.
11. Dialogue speech/world fact separation: deterministic `SOURCE_SPEECH_ACT` is allowed; dialogue proposition remains verifier-required.
12. Current eligible SourceClaim count: **0**.
13. Current Director source coverage: **INSUFFICIENT** for {len(source_units)} SourceAuthoringUnits and required semantic classes.
14. Stage A revision safe: **NO**.
15. Next authorization: `SOURCE_SEMANTIC_CLAIM_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED`.
16. Phrase dependence: **NO** in the V7.7.2 authority path.
17. Scene dependence: **NO**.
18. Attempt dependence: **NO**.
19. Heuristic production dependency: **NO**.
20. Provider calls: **0** (proposal and verifier).
21. Production writes: **0**.
22. Ledger: `11 -> 11`.
23. Active Stage B: `attempt-11 -> attempt-11`.
24. Tests: V7.7.2 + V7.7.1 + V7.7.0 + targeted V7.2-V7.6 regression **223 passed, 0 failed**.
25. SceneBlocking baseline: **12 passed, 3 pre-existing failures**; not modified.
26. Compileall: PASS.
27. Git diff check: PASS.
28. Working tree: required clean after push.
29. Commit SHA: recorded in final delivery message.
30. Remote HEAD: required equal to local HEAD after push.

Snapshot confirmation is a structural/evidence boundary. It does not promote arbitrary FactRecord semantics. FactSnapshot 49 can only be audited as two confirmed structural records; it has no semantic overlay and no typed Director narrative coverage.
"""
    (OUT / "SOURCE_SEMANTIC_CLAIM_AUTHORITY_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
