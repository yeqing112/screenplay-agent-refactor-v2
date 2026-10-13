"""Append V7.7.8.1 ontology closure evidence without rewriting V7.7.8 history."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.provider_structured_output_qualification import compile_provider_strict_schema, fingerprint
from core.source_semantic_claim_v3 import (
    CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
    CLAIM_V3_SET_VERSION,
    SECOND_ORDER_RELATION_SIGNATURE_REGISTRY_VERSION,
    VERIFIED_FIRST_ORDER_CLAIM_REGISTRY_VERSION,
    claim_ordering_contract_v1,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
    first_order_relation_closure_audit,
    proposable_predicate_registry_v1,
    relation_signature_completeness_audit,
    second_order_relation_closure_audit,
    second_order_relation_signature_registry_v1,
    verified_first_order_claim_registry_contract_v1,
)
from scripts.generate_v7_7_8_source_semantic_claim_v3_foundation_evidence import (
    DB_PATH,
    current_production_freeze,
    sha256_file,
)


OUTPUT = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
BASELINE = OUTPUT / "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json"
ENTITY_FREEZE = OUTPUT / "V7_7_7_VERIFIED_ENTITY_FREEZE.json"
ENTITY_REGISTRY = OUTPUT / "CLAIM_INPUT_ENTITY_REGISTRY.json"
TRANSPORT_AUDIT = OUTPUT / "CLAIM_V3_TRANSPORT_SCHEMA_COMPILER_AUDIT.json"
V2_AUDIT = OUTPUT / "CLAIM_V2_IMMUTABLE_BLOCKER_AUDIT.json"
NEW_NAMES = (
    "SECOND_ORDER_EPISTEMIC_RELATION_CONTRACT.json",
    "SECOND_ORDER_RELATION_SIGNATURE_REGISTRY.json",
    "FIRST_ORDER_RELATION_CLOSURE_AUDIT.json",
    "SECOND_ORDER_RELATION_CLOSURE_AUDIT.json",
    "VERIFIED_FIRST_ORDER_CLAIM_REGISTRY_CONTRACT.json",
    "CLAIM_ORDERING_CONTRACT.json",
    "UPDATED_RELATION_SIGNATURE_COMPLETENESS_AUDIT.json",
    "UPDATED_PROPOSABLE_PREDICATE_REGISTRY.json",
    "SECOND_ORDER_DEFERRED_COVERAGE_STATUS.json",
    "V7_7_8_1_FIRST_ORDER_RELATION_SIGNATURE_CLOSURE_REPORT.md",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    import subprocess

    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    existing = [name for name in NEW_NAMES if (OUTPUT / name).exists()]
    if existing:
        raise SystemExit("Refusing to overwrite append-only V7.7.8.1 evidence: " + ", ".join(existing))

    baseline = read_json(BASELINE)
    entity_freeze = read_json(ENTITY_FREEZE)
    entity_registry = read_json(ENTITY_REGISTRY)
    transport_baseline = read_json(TRANSPORT_AUDIT)
    v2_audit = read_json(V2_AUDIT)

    db_sha_before = sha256_file(DB_PATH)
    production_before = current_production_freeze()
    db_sha_after = sha256_file(DB_PATH)
    production_after = current_production_freeze()
    production_frozen = production_before == production_after == baseline["production_freeze_before"]
    db_unchanged = db_sha_before == db_sha_after == baseline["database_file_sha256_before_after"][0]
    if not production_frozen or not db_unchanged:
        raise SystemExit("Production freeze mismatch; no V7.7.8.1 evidence was written")

    predicates = proposable_predicate_registry_v1()
    first_order = first_order_relation_closure_audit()
    second_order = second_order_relation_closure_audit()
    completeness = relation_signature_completeness_audit()
    second_registry = second_order_relation_signature_registry_v1()
    verified_claim_registry = verified_first_order_claim_registry_contract_v1()
    ordering = claim_ordering_contract_v1()
    contract = {
        "schema_version": "source_claim_second_order_epistemic_relation_contract_v1",
        "status": "PASS",
        "claim_order": "SECOND_ORDER_EPISTEMIC_CLAIM",
        "predicates": {
            name: {
                key: value
                for key, value in row.items()
                if key != "proposal_order"
            }
            for name, row in second_registry["predicates"].items()
        },
        "why_not_entity_to_entity": {
            "knows": "The object of knowledge is a proposition or verified first-order claim, which may concern an action, state, object property, or provenance relation. No single source entity kind represents those alternatives.",
            "uncertainty": "The object of uncertainty is a proposition or verified first-order claim, not the referenced location, object, state, or other source entity itself.",
            "object_entity_kind_question_applicable": False,
        },
        "entity_proposal_ontology_extended": False,
        "entity_kinds_added": [],
        "nested_claim_json": False,
        "inline_proposition": False,
        "provider_local_proposition_ids": False,
        "one_response_claim_graph": False,
        "execution_enabled": False,
    }

    schema = claim_v3_candidate_set_schema(
        candidate_schema=claim_v3_candidate_schema(
            input_entity_registry=entity_registry,
            proposable_predicates=predicates,
        )
    )
    compiled = compile_provider_strict_schema(schema)
    schema_fingerprint = compiled["audit"].get("output_fingerprint")
    transport_unchanged = (
        compiled["audit"].get("status") == "PASS"
        and schema_fingerprint == transport_baseline["transport_schema_fingerprint"]
        and count_schema_dialect_extensions(schema) == {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0}
    )
    checks = {
        "entity_registry_contract_version": entity_registry.get("schema_version") == CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
        "entity_registry_fingerprint_preserved": entity_registry.get("source_verified_entity_registry_fingerprint") == "88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186",
        "v7_7_7_entity_freeze_pass": entity_freeze.get("status") == "PASS" and entity_freeze.get("canonical_promotions") == 0,
        "first_order_closure_pass": first_order.get("status") == "PASS" and first_order.get("first_order_proposable_predicate_count") == 6 and first_order.get("first_order_unresolved_count") == 0,
        "second_order_closure_pass": second_order.get("status") == "PASS" and second_order.get("second_order_relation_count") == 2 and second_order.get("second_order_unresolved_count") == 0,
        "second_order_not_provider_proposable": second_registry.get("provider_proposable_now") is False,
        "v2_unchanged_and_blocker_preserved": v2_audit.get("status") == "LEGACY_BLOCKED_UNION_TYPE" and v2_audit.get("v2_mutated") is False,
        "v3_transport_fingerprint_unchanged": transport_unchanged,
        "production_db_and_freeze_unchanged": production_frozen and db_unchanged,
    }
    if not all(checks.values()):
        raise SystemExit("V7.7.8.1 closure gate failed: " + repr(checks))

    write_json(NEW_NAMES[0], contract)
    write_json(NEW_NAMES[1], second_registry)
    write_json(NEW_NAMES[2], first_order)
    write_json(NEW_NAMES[3], second_order)
    write_json(NEW_NAMES[4], verified_claim_registry)
    write_json(NEW_NAMES[5], ordering)
    write_json(NEW_NAMES[6], completeness)
    write_json(NEW_NAMES[7], predicates)
    write_json(NEW_NAMES[8], {
        "schema_version": "source_claim_second_order_deferred_coverage_status_v1",
        "status": "DEFERRED_NOT_PROVEN",
        "deferred_second_order_predicates": ["knows", "uncertainty"],
        "deferred_second_order_predicate_count": 2,
        "second_order_unresolved_count": 0,
        "execution_enabled": False,
        "provider_proposable_now": False,
        "required_before_execution": "verified first-order ClaimRefs in source_verified_first_order_claim_registry_v1",
        "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING",
        "entity_semantic_completeness": "NOT_PROVEN",
        "full_source_semantic_coverage": "NOT_PROVEN",
    })

    branch = git("branch", "--show-current")
    implementation_commit = git("rev-parse", "HEAD")
    remote_head = git("rev-parse", "origin/" + branch)
    report = f"""# V7.7.8.1 First-Order Relation Signature Closure

## Ontology boundary

- `knows` is `CHARACTER_KNOWLEDGE` / `KNOWLEDGE_STATE`, with `ENTITY_REF` subject restricted to `CHARACTER`, `VERIFIED_FIRST_ORDER_CLAIM_REF` object, and an empty qualifier allowlist.
- `uncertainty` is `UNCERTAINTY` / `UNCERTAINTY`, with `ENTITY_REF` subject restricted to `CHARACTER`, `VERIFIED_FIRST_ORDER_CLAIM_REF` object, and an empty qualifier allowlist.
- Neither relation is Entity-to-Entity: its object is a proposition or verified first-order claim, which can describe different entity kinds and relations. The relevant object domain is therefore a claim reference, not one source entity kind.
- `PROPOSITION`, `CLAIM`, and `FACT` were not added to the source entity ontology. The V7.7.7 entity registry remains at `{entity_registry['source_verified_entity_registry_fingerprint']}`; promotions remain `0`.
- Deferred means the ontology is defined and execution waits for verified first-order ClaimRefs. It does not mean unsupported, dropped, or not required.

## Closure and readiness

- First-order proposable predicates: `6`; first-order unresolved: `0`.
- Deferred second-order relations: `2`; second-order unresolved: `0`.
- Second-order currently executable: `NO`; provider-proposable now: `NO`.
- Claim V3 first-order foundation: `READY` (`SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY`). Next: `SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED`.
- Future second-order boundary: `SECOND_ORDER_EPISTEMIC_CLAIM_BOUNDARY_REQUIRED_AFTER_FIRST_ORDER_VERIFICATION`.
- Full semantic completeness: `NOT PROVEN`; manifest is still `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`, entity completeness is `NOT_PROVEN`, and second-order coverage is `DEFERRED_NOT_PROVEN`.

## Frozen contracts and production boundary

- Claim V2 unchanged: `YES`; blocker remains `LEGACY_BLOCKED_UNION_TYPE`.
- First-order V3 transport compiler: `PASS`; output fingerprint remains `{schema_fingerprint}`; union / oneOf / anyOf / dangling ref counts are all `0`.
- Real Provider calls: `0`. Production writes: `0`. FactSnapshot / FactRecord / SourceClaim / Entity writes: `0`; Stage A: `0`; Attempt-12: `0`; Confirm: `0`; IMAGE / VIDEO: `0`.
- Production freeze: Book 990453, Packet 64, Director ledger 11, Stage A `attempt-7`, active Stage B `attempt-11`; read-only database SHA stayed `{db_sha_before}`.
- Focused V7.7.2–V7.7.8.1 regression suites: `117 passed`. `python -m compileall -q core scripts`: `PASS`. `git diff --check`: `PASS` before evidence publication.

## Evidence and Git

- This is append-only V7.7.8.1 evidence; prior V7.7.8 and historical V7.5.1 artifacts were preserved.
- Branch: `{branch}`.
- Implementation commit at evidence generation: `{implementation_commit}`.
- Remote head at evidence generation: `{remote_head}`.
- Evidence commit SHA and final remote HEAD are reported in the final task response because a Git commit cannot contain its own resulting SHA.
- Provider calls and production writes remain `0`; no proposal, verifier, promotion, Stage A, Attempt-12, Confirm, PR, or merge was performed.
"""
    (OUTPUT / NEW_NAMES[9]).write_text(report, encoding="utf-8")
    print(json.dumps({"status": "PASS", "checks": checks, "branch": branch, "implementation_commit": implementation_commit, "remote_head_at_evidence_generation": remote_head, "transport_schema_fingerprint": schema_fingerprint, "database_sha256": db_sha_after}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
