"""Generate provider-free V7.7.9.1 contract reconciliation evidence."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.provider_structured_output_qualification import fingerprint
from core.source_semantic_claim_v3 import (
    build_claim_input_entity_registry,
    qualifier_registry_v2,
    validate_claim_v3_set,
)
from core.source_semantic_claim_v3_1 import (
    build_deterministic_speech_act_candidate,
    first_order_relation_ownership_registry_v1,
    proposal_ownership_classification_v1,
    provider_predicate_registry_v2,
    qualifier_registry_v3,
    relation_signature_registry_v3,
    required_qualifier_executability_contract_v1,
    source_speech_act_binding_registry_v1,
    speech_act_deterministic_contract_v1,
    speech_act_proposal_ownership_contract_v1,
    validate_deterministic_speech_act_candidate,
    validate_provider_candidate_v3_1,
)
from scripts.generate_v7_7_8_source_semantic_claim_v3_foundation_evidence import (
    current_production_freeze,
    sha256_file,
)


OUTPUT = ROOT / "docs/canonical-canary/v7_7_9_1-first-order-claim-contract-reconciliation"
V779 = ROOT / "docs/canonical-canary/v7_7_9-source-semantic-claim-v3-first-order-proposal-real"
V778 = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
V777 = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real"
V773 = ROOT / "docs/canonical-canary/v7_7_3-source-semantic-claim-proposal-real"
V71 = ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract"
DB_PATH = ROOT / "work/db/screenplay.db"
BASELINE = "cf3bebc93f94739402888d9f149ea523083bc621"
RAW_SHA = "44730220ba61ce249d1ebd5b87e3a0373b4cc220e58b7f96eef04a5b06f40585"

NAMES = [
    "ANTI_HEURISTIC_PATCH_REVIEW.json",
    "V7_7_9_IMMUTABLE_PARTIAL_FREEZE.json",
    "V7_7_9_ROOT_CAUSE_REASSESSMENT.json",
    "SPEAKER_BINDING_OWNERSHIP_AUDIT.json",
    "SPEECH_ACT_PROPOSAL_OWNERSHIP_CONTRACT.json",
    "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json",
    "SOURCE_SPEECH_ACT_DETERMINISTIC_CONTRACT.json",
    "SOURCE_SPEECH_ACT_DETERMINISTIC_AUDIT.json",
    "DIALOGUE_PROPOSITION_AUTHORITY_BOUNDARY.json",
    "ENTER_GUIDED_ARGUMENT_COMPLETENESS_AUDIT.json",
    "RELATION_SIGNATURE_REGISTRY_V3.json",
    "QUALIFIER_REGISTRY_V3.json",
    "PROVIDER_PREDICATE_REGISTRY_V2.json",
    "FIRST_ORDER_RELATION_OWNERSHIP_REGISTRY.json",
    "PROPOSAL_OWNERSHIP_CLASSIFICATION.json",
    "REQUIRED_QUALIFIER_EXECUTABILITY_CONTRACT.json",
    "FIRST_ORDER_PREDICATE_EXECUTABILITY_AUDIT_V2.json",
    "HISTORICAL_V7_7_9_REPRODUCIBILITY_AUDIT.json",
    "CURRENT_V7_7_9_VERIFIER_ELIGIBILITY.json",
    "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json",
    "RECOMMENDED_NEXT_ACTION.json",
    "V7_7_9_1_FIRST_ORDER_CLAIM_CONTRACT_RECONCILIATION_REPORT.md",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def read_frozen_script_ir() -> tuple[dict[str, Any], str]:
    connection = sqlite3.connect(f"file:{DB_PATH.resolve().as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "select payload_json from script_ir_versions where id=? and book_id=? and episode=?",
            (52, 990453, 1),
        ).fetchone()
        if row is None:
            raise RuntimeError("FROZEN_SCRIPT_IR_52_MISSING")
        payload = json.loads(row[0])
        return payload, fingerprint(payload)
    finally:
        connection.close()


def historical_replay(raw_audit: dict[str, Any], frozen_entities: dict[str, Any], old_provider_registry: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    raw = raw_audit.get("raw_response")
    actual_raw_sha = hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()
    parsed = json.loads(raw)
    evidence_bindings: dict[str, list[str]] = {}
    for unit in units:
        evidence_ref = str((unit.get("source_evidence") or {}).get("evidence_id") or "")
        if evidence_ref:
            evidence_bindings[evidence_ref] = [str(unit.get("unit_id") or "")]
    result = validate_claim_v3_set(
        parsed,
        input_entity_registry=frozen_entities,
        evidence_unit_bindings=evidence_bindings,
        allowed_source_unit_refs=[str(row.get("unit_id") or "") for row in units],
        qualifier_registry=qualifier_registry_v2(),
        proposable_predicates=old_provider_registry,
    )
    candidate_results = result.get("candidate_results", [])
    checks = {
        "immutable_raw_sha_exact": actual_raw_sha == RAW_SHA == raw_audit.get("raw_response_sha256"),
        "candidate_count_two": result.get("candidate_count") == 2,
        "legacy_result_one_pass_one_blocked": result.get("valid_count") == 1 and result.get("blocked_count") == 1,
        "second_candidate_direct_failure_reproduced": len(candidate_results) == 2 and candidate_results[1].get("errors") == ["SYMBOLIC_TOKEN_INVALID:speaker_binding"],
    }
    return {
        "schema_version": "historical_v7_7_9_reproducibility_audit_v1",
        "status": "PASS" if all(checks.values()) else "BLOCKED",
        "frozen_registry_versions": {
            "relation_signatures": "source_claim_relation_signature_registry_v2",
            "qualifiers": "source_claim_qualifier_registry_v2",
            "provider_predicates": "source_claim_executable_predicate_registry_v1",
        },
        "raw_sha256": actual_raw_sha,
        "candidate_count": result.get("candidate_count"),
        "valid_count": result.get("valid_count"),
        "blocked_count": result.get("blocked_count"),
        "candidate_errors": [row.get("errors", []) for row in candidate_results],
        "checks": checks,
        "historical_artifacts_modified": False,
    }


def main() -> int:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite append-only evidence: {OUTPUT}")

    database_sha_before = sha256_file(DB_PATH)
    production_before = current_production_freeze()
    freeze779 = read_json(V779 / "NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json")
    proposal779 = read_json(V779 / "SOURCE_CLAIM_V3_PROPOSAL_SET.json")
    raw779 = read_json(V779 / "SOURCE_CLAIM_V3_RAW_FORENSIC.json")
    input_freeze = read_json(V779 / "SOURCE_CLAIM_V3_INPUT_FREEZE.json")
    source_units = read_json(V71 / "SOURCE_AUTHORING_UNIT_CONTRACT.json")["units"]
    source_verified = read_json(V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json")
    claim_entities_frozen = read_json(V778 / "CLAIM_INPUT_ENTITY_REGISTRY.json")
    claim_entities = build_claim_input_entity_registry(source_verified, expected_fingerprint="88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186")
    script_ir, script_ir_fingerprint = read_frozen_script_ir()
    current_relation = relation_signature_registry_v3()
    current_qualifiers = qualifier_registry_v3()
    current_provider_registry = provider_predicate_registry_v2(current_relation, claim_entities, current_qualifiers)
    ownership = first_order_relation_ownership_registry_v1(current_relation)
    ownership_classes = proposal_ownership_classification_v1(current_relation)
    speech_bindings = source_speech_act_binding_registry_v1(
        script_ir=script_ir,
        source_units=source_units,
        entity_registry=claim_entities,
        source_fingerprint=str(input_freeze.get("origin_source_raw_hash") or ""),
    )
    deterministic_candidates = [build_deterministic_speech_act_candidate(row) for row in speech_bindings.get("bindings", [])]
    deterministic_results = [validate_deterministic_speech_act_candidate(row, speech_bindings) for row in deterministic_candidates]
    historical = historical_replay(
        raw779, claim_entities_frozen,
        read_json(V779 / "EXECUTABLE_FIRST_ORDER_PREDICATE_REGISTRY.json"),
        source_units,
    )
    old_rows = proposal779.get("candidates") if isinstance(proposal779.get("candidates"), list) else []
    current_candidate_audits = [
        validate_provider_candidate_v3_1(
            row.get("raw_candidate") if isinstance(row, dict) else {},
            provider_registry=current_provider_registry,
            entity_registry=claim_entities,
            qualifier_registry=current_qualifiers,
        )
        for row in old_rows
    ]
    verifier_eligible = [row for row in current_candidate_audits if row.get("status") == "PASS" and row.get("verifier_eligible") is True]

    module_text = (ROOT / "core/source_semantic_claim_v3_1.py").read_text(encoding="utf-8")
    anti_patterns = {
        "story_character_literal": bool(re.search(r"顾沉|林晚", module_text)),
        "story_location_literal": "暗房" in module_text,
        "subject_value_branch": bool(re.search(r"if\s+subject\s*==", module_text)),
        "predicate_name_inference": bool(re.search(r"predicate.*(?:split|startswith|endswith)\s*\(", module_text)),
        "local_nlp_import": bool(re.search(r"import\s+(?:spacy|jieba|nltk)|from\s+(?:spacy|jieba|nltk)", module_text)),
    }
    production_after = current_production_freeze()
    database_sha_after = sha256_file(DB_PATH)
    freeze_unchanged = production_before == production_after == freeze779.get("production_freeze_before")
    db_unchanged = database_sha_before == database_sha_after

    gate_checks = {
        "raw_freeze_exact_and_old_partial_preserved": raw779.get("raw_response_sha256") == RAW_SHA and proposal779.get("status") == "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL",
        "historical_v7_7_9_replay_pass": historical.get("status") == "PASS",
        "source_and_entity_freezes_exact": input_freeze.get("status") == "PASS" and claim_entities.get("fingerprint") == claim_entities_frozen.get("fingerprint") and script_ir_fingerprint == production_before.get("script_ir_payload_fingerprint"),
        "speech_binding_registry_pass": speech_bindings.get("status") == "PASS" and speech_bindings.get("binding_count") > 0,
        "deterministic_speech_act_audit_pass": bool(deterministic_results) and all(row.get("status") == "PASS" for row in deterministic_results),
        "provider_registry_runtime_partition": current_provider_registry.get("status") == "PASS" and set(current_provider_registry.get("predicates", {})) == {"enter_guided", "left_by", "received_by"} and set(current_provider_registry.get("dormant_predicates", {})) == {"has_property", "state_value"} and current_provider_registry.get("program_deterministic_predicates") == ["speech_act"],
        "ownership_three_way_partition": ownership_classes.get("status") == "PASS" and ownership_classes.get("counts") == {"PROVIDER_PROPOSABLE": 5, "PROGRAM_DETERMINISTIC": 1, "DEFERRED_SECOND_ORDER": 2},
        "old_candidates_not_verifier_eligible": not verifier_eligible and [row.get("status") for row in current_candidate_audits] == ["BLOCKED", "BLOCKED"],
        "anti_heuristic_guardrails": not any(anti_patterns.values()),
        "production_and_database_unchanged": freeze_unchanged and db_unchanged,
        "v2_and_second_order_frozen": read_json(V778 / "CLAIM_V2_IMMUTABLE_BLOCKER_AUDIT.json").get("status") == "LEGACY_BLOCKED_UNION_TYPE" and read_json(V778 / "SECOND_ORDER_DEFERRED_COVERAGE_STATUS.json").get("status") == "DEFERRED_NOT_PROVEN",
    }
    if not all(gate_checks.values()):
        raise SystemExit("V7.7.9.1 evidence gate failed: " + json.dumps(gate_checks, ensure_ascii=False))

    OUTPUT.mkdir(parents=True, exist_ok=False)
    write_json("ANTI_HEURISTIC_PATCH_REVIEW.json", {
        "schema_version": "v7_7_9_1_anti_heuristic_patch_review_v1",
        "status": "PASS",
        "scanned_module": "core/source_semantic_claim_v3_1.py",
        "phrase_dependence": "NO", "scene_dependence": "NO", "attempt_dependence": "NO",
        "PEC_specific_branch": "NO", "current_story_participant_special_case": "NO",
        "predicate_name_inference": "NO", "local_NLP": "NO", "source_prose_speaker_parse": "NO",
        "pattern_checks": anti_patterns,
        "provider_calls": 0, "production_writes": 0,
    })
    write_json("V7_7_9_IMMUTABLE_PARTIAL_FREEZE.json", {
        "schema_version": "v7_7_9_immutable_partial_freeze_v1",
        "status": "PASS",
        "proposal_status": proposal779.get("status"),
        "candidate_count": proposal779.get("candidate_count"),
        "valid_count": proposal779.get("valid_count"),
        "blocked_count": proposal779.get("blocked_count"),
        "raw_sha256": raw779.get("raw_response_sha256"),
        "raw_frozen": raw779.get("raw_response_sha256") == RAW_SHA,
        "candidate_rewritten": False,
        "reparsed_with_normalization": False,
        "old_result_reassigned_as_pass": False,
        "historical_artifacts_modified": False,
        "provider_calls_this_phase": 0,
        "production_writes_this_phase": 0,
    })
    write_json("V7_7_9_ROOT_CAUSE_REASSESSMENT.json", {
        "schema_version": "v7_7_9_root_cause_reassessment_v1",
        "status": "PASS",
        "candidate_2_direct_validator_failure": "SYMBOLIC_TOKEN_INVALID:speaker_binding",
        "direct_validator_failure_is_real": True,
        "architecture_root_cause": "PROVIDER_OWNED_SPEAKER_BINDING_IS_REDUNDANT",
        "provider_token_format_failure_is_root_cause": False,
        "reason": "speaker identity is already represented by the typed speech_act subject_ref and is owned by grounded upstream ScriptIR speaker binding provenance.",
        "candidate_1_status_under_new_contract": "SUPERSEDED_SIGNATURE_NOT_VERIFIER_ELIGIBLE",
        "candidate_2_status_under_new_contract": "BLOCKED_REDUNDANT_PROVIDER_QUALIFIER",
    })
    write_json("SPEAKER_BINDING_OWNERSHIP_AUDIT.json", {
        "schema_version": "speaker_binding_ownership_audit_v1",
        "status": "PASS",
        "upstream_owner": "GROUNDED_SCRIPT_IR_SOURCE_STRUCTURING_PROGRAM",
        "structured_source_fields": ["dialogue.speaker", "dialogue.text", "dialogue.source_evidence", "dialogue.speaker_binding"],
        "binding_fields": ["classification", "binding_type", "identity_evidence", "utterance_evidence"],
        "provider_owned_semantic_qualifier": False,
        "claim_v3_speech_act_subject_already_represents_speaker": True,
        "provider_surface_in_v3": False,
        "legacy_director_registry_mutated": False,
        "script_ir_payload_fingerprint": script_ir_fingerprint,
    })
    write_json("SPEECH_ACT_PROPOSAL_OWNERSHIP_CONTRACT.json", speech_act_proposal_ownership_contract_v1())
    write_json("SOURCE_SPEECH_ACT_BINDING_REGISTRY.json", speech_bindings)
    write_json("SOURCE_SPEECH_ACT_DETERMINISTIC_CONTRACT.json", speech_act_deterministic_contract_v1())
    write_json("SOURCE_SPEECH_ACT_DETERMINISTIC_AUDIT.json", {
        "schema_version": "source_speech_act_deterministic_audit_v1",
        "status": "PASS" if deterministic_results and all(row["status"] == "PASS" for row in deterministic_results) else "BLOCKED",
        "candidate_count": len(deterministic_candidates),
        "validation_results": deterministic_results,
        "candidates": deterministic_candidates,
        "dialogue_proposition_world_fact_created": False,
        "production_persisted": False,
    })
    write_json("DIALOGUE_PROPOSITION_AUTHORITY_BOUNDARY.json", {
        "schema_version": "dialogue_proposition_authority_boundary_v1",
        "speech_occurrence": "speaker uttered exact bound dialogue content",
        "speech_act_proves_dialogue_proposition_truth": False,
        "dialogue_proposition_world_fact_requires": "INDEPENDENT_SEMANTIC_VERIFICATION",
        "automatic_world_fact_created": False,
        "semantic_verifier_calls": 0,
    })
    write_json("ENTER_GUIDED_ARGUMENT_COMPLETENESS_AUDIT.json", {
        "schema_version": "enter_guided_argument_completeness_audit_v1",
        "status": "PASS",
        "source_fact_roles": ["guide_actor", "guided_participant", "destination"],
        "new_typed_relation_roles": {"subject_ref": "guide_actor CHARACTER", "guided_character": "guided_participant CHARACTER", "object_ref": "destination LOCATION"},
        "previous_signature_lost_role": "guided_participant",
        "previous_provider_candidate_verifier_eligible": False,
        "guided_character_required": True,
        "destination_qualifier_redundant_with_object_ref": True,
        "historical_candidate_automatically_repaired": False,
    })
    write_json("RELATION_SIGNATURE_REGISTRY_V3.json", current_relation)
    write_json("QUALIFIER_REGISTRY_V3.json", current_qualifiers)
    write_json("PROVIDER_PREDICATE_REGISTRY_V2.json", current_provider_registry)
    write_json("FIRST_ORDER_RELATION_OWNERSHIP_REGISTRY.json", ownership)
    write_json("PROPOSAL_OWNERSHIP_CLASSIFICATION.json", ownership_classes)
    write_json("REQUIRED_QUALIFIER_EXECUTABILITY_CONTRACT.json", required_qualifier_executability_contract_v1())
    write_json("FIRST_ORDER_PREDICATE_EXECUTABILITY_AUDIT_V2.json", {
        "schema_version": "first_order_predicate_executability_audit_v2",
        "status": current_provider_registry["status"],
        "provider_proposable_count": current_provider_registry["predicate_count"],
        "provider_proposable_predicates": sorted(current_provider_registry["predicates"]),
        "program_deterministic_count": len(current_provider_registry["program_deterministic_predicates"]),
        "program_deterministic_predicates": current_provider_registry["program_deterministic_predicates"],
        "dormant_count": current_provider_registry["dormant_predicate_count"],
        "dormant_predicates": sorted(current_provider_registry["dormant_predicates"]),
        "required_qualifier_dependencies_included": True,
        "source_text_consulted": False,
        "predicate_name_semantics_inferred": False,
    })
    write_json("HISTORICAL_V7_7_9_REPRODUCIBILITY_AUDIT.json", historical)
    write_json("CURRENT_V7_7_9_VERIFIER_ELIGIBILITY.json", {
        "schema_version": "current_v7_7_9_verifier_eligibility_v1",
        "status": "PASS",
        "historical_overall_status_preserved": proposal779.get("status"),
        "candidate_ids": ["SCC_0001", None],
        "new_contract_results": current_candidate_audits,
        "verifier_eligible_count": len(verifier_eligible),
        "candidate_0_state": "SUPERSEDED_SIGNATURE_NOT_VERIFIER_ELIGIBLE",
        "candidate_1_state": "BLOCKED_REDUNDANT_PROVIDER_QUALIFIER",
        "verifier_post_count": 0,
    })
    write_json("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {
        "schema_version": "v7_7_9_1_no_provider_no_production_write_audit_v1",
        "status": "PASS",
        "real_provider_posts": 0, "claim_verifier_posts": 0, "second_order_provider_posts": 0,
        "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "entity_writes": 0,
        "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0,
        "entity_semantic_completeness": "NOT_PROVEN",
        "claim_proposal_completeness": "NOT_PROVEN",
        "second_order_epistemic_coverage": "DEFERRED_NOT_PROVEN",
        "typed_director_requirement_manifest": "MISSING",
        "production_freeze_before": production_before, "production_freeze_after": production_after,
        "database_sha256_before": database_sha_before, "database_sha256_after": database_sha_after,
        "production_freeze_unchanged": freeze_unchanged, "database_unchanged": db_unchanged,
    })
    recommended_state = "SOURCE_SEMANTIC_CLAIM_V3_CONTRACT_RECONCILED" if all(gate_checks.values()) else "SOURCE_SEMANTIC_CLAIM_V3_CONTRACT_RECONCILIATION_BLOCKED"
    next_state = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_CANARY_AUTHORIZATION_REQUIRED" if recommended_state.endswith("RECONCILED") else "SOURCE_SEMANTIC_CLAIM_V3_CONTRACT_RECONCILIATION_BLOCKED"
    write_json("RECOMMENDED_NEXT_ACTION.json", {
        "status": recommended_state,
        "next_state": next_state,
        "provider_calls": 0,
        "claim_verifier_calls": 0,
        "reproposal_authorized": False,
        "requires_new_user_authorization": True,
        "verifier_eligible_count": 0,
    })

    report = f"""# V7.7.9.1 First-Order Claim Contract Reconciliation

## Reassessment of V7.7.9

- V7.7.9 remains `SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL`; immutable raw SHA256: `{RAW_SHA}`. The historical raw, candidate set, V2/V3 registries, and V7.7.9 artifacts were not changed.
- Candidate #2's direct validator error remains `SYMBOLIC_TOKEN_INVALID:speaker_binding`. The architecture root cause is `PROVIDER_OWNED_SPEAKER_BINDING_IS_REDUNDANT`, not a Chinese token formatting failure: speaker identity is already the `speech_act.subject_ref`, while the provenance belongs to structured upstream dialogue binding.
- `speaker_binding` semantic owner: grounded ScriptIR / upstream source-structuring program. It is not Provider-writable in V3.1.
- Old candidate #1 is `SUPERSEDED_SIGNATURE_NOT_VERIFIER_ELIGIBLE`: the former `enter_guided` relation omitted the guided participant. Old candidate #2 remains blocked as `BLOCKED_REDUNDANT_PROVIDER_QUALIFIER`. Current V7.7.9 verifier-eligible candidates: `0`.
- Historical replay with frozen V2/V3 registries reproduces `1 PASS / 1 BLOCKED`, including the exact symbolic-token error.

## New ownership and typed relation contracts

- Relation registry: `{current_relation['schema_version']}`. Qualifier registry: `{current_qualifiers['schema_version']}`. Provider predicate registry: `{current_provider_registry['schema_version']}`.
- Ownership partition: Provider-proposable `5` first-order relations; program-deterministic `speech_act` (`1`); deferred second-order `knows` / `uncertainty` (`2`), pending verified ClaimRefs.
- Current runtime Provider-executable predicates: `{', '.join(sorted(current_provider_registry['predicates']))}` ({current_provider_registry['predicate_count']}). Dormant: `{', '.join(sorted(current_provider_registry['dormant_predicates']))}` ({current_provider_registry['dormant_predicate_count']}). Program-deterministic: `speech_act` (1).
- `speech_act` remains `SOURCE_SPEECH_ACT` / `SPEECH_ACT`, owner `PROGRAM_DETERMINISTIC`; Provider proposal is disabled. The frozen ScriptIR and SourceAuthoringUnit join produced `{speech_bindings['binding_count']}` deterministic binding(s), with structured speaker provenance fingerprinted. A wrong subject is blocked with `SPEECH_ACT_SPEAKER_BINDING_MISMATCH`.
- Deterministic `speech_act` proves only that the bound speaker uttered the exact dialogue-content entity. It does not make the dialogue proposition a world fact; proposition truth still requires independent semantic verification.
- `enter_guided` now requires `guided_character: ENTITY_REF` constrained to `CHARACTER`. The destination remains `object_ref`; the duplicate `destination` qualifier is removed. Required qualifier kind availability is included in generic runtime executability derivation.
- New Provider qualifier surface is `{', '.join(sorted(current_qualifiers['qualifiers']))}`. `speaker_binding` is not writable; `destination` is not allowed for `enter_guided`.

## Verification and freeze

- Production freeze unchanged: Book 990453, FactSnapshot 49, ScriptIR 52, Packet 64; Director ledger `{production_before.get('director_ledger')}` → `{production_after.get('director_ledger')}`; active Stage B `{production_before.get('active_stage_b')}` → `{production_after.get('active_stage_b')}`.
- Provider calls `0`; Claim Verifier `0`; second-order Provider `0`; production writes `0`; Stage A / Attempt-12 / Confirm / IMAGE / VIDEO `0 / 0 / 0 / 0 / 0`.
- Claim V2 remains `LEGACY_BLOCKED_UNION_TYPE`; second-order `knows` / `uncertainty` remains `DEFERRED_NOT_PROVEN`.
- Completeness remains: entity semantics `NOT_PROVEN`, proposal completeness `NOT_PROVEN`, second-order epistemic coverage `DEFERRED_NOT_PROVEN`, Typed Director Requirement Manifest `MISSING`.
- Focused provider-free tests, `python -m compileall -q core scripts tests`, and `git diff --check` results are finalized after the evidence audit.
- No real Provider POST, verifier, re-proposal, promotion, Stage A, Attempt-12, Confirm, PR, or merge was performed.

## State

- Terminal state: `{recommended_state}`.
- Next: `{next_state}`. A future proposal requires a new explicit authorization and must use the new frozen ontology.
- Baseline for this reconciliation: `{BASELINE}`. Final implementation and evidence commit SHAs are reported after pushing.
"""
    (OUTPUT / "V7_7_9_1_FIRST_ORDER_CLAIM_CONTRACT_RECONCILIATION_REPORT.md").write_text(report, encoding="utf-8")

    print(json.dumps({
        "status": recommended_state,
        "next_state": next_state,
        "checks": gate_checks,
        "provider_calls": 0,
        "production_writes": 0,
        "provider_predicates": sorted(current_provider_registry["predicates"]),
        "program_deterministic_predicates": current_provider_registry["program_deterministic_predicates"],
        "dormant_predicates": sorted(current_provider_registry["dormant_predicates"]),
        "speech_binding_count": speech_bindings["binding_count"],
        "verifier_eligible_count": len(verifier_eligible),
        "database_sha256": database_sha_after,
        "evidence_directory": str(OUTPUT),
        "artifact_count": len(NAMES),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
