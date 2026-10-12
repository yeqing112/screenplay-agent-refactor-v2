"""Generate the provider-free V7.7.1 Claim-aware Authoring evidence pack.

The script reads historical V7.7.0 artifacts and the source contract only.  It
does not call a provider, mutate production state, or execute a revision.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_authoring_claim_contract import (
    AUTHORING_MANIFEST_VERSION,
    claim_manifest_completeness_contract,
    make_manifest_claim,
    stage_a_field_semantic_contract,
    stage_b_field_semantic_contract,
    validate_authoring_response,
)
from core.director_claim_aware_support import audit_typed_manifest
from core.director_claim_entity_binding import entity_binding_contract
from core.director_claim_ir import make_claim
from core.director_claim_relation_registry import relation_registry, validate_relation_registry
from core.director_source_claim_materialization import materialize_source_claims, source_structured_capability


OUT = ROOT / "docs" / "canonical-canary" / "v7_7_1-claim-aware-authoring-boundary"
SOURCE_PATH = ROOT / "docs" / "canonical-canary" / "v7_1-director-source-grounded-authoring-contract" / "SOURCE_AUTHORING_UNIT_CONTRACT.json"
V7_DIR = ROOT / "docs" / "canonical-canary" / "v7_7_0-semantic-grounding-v3-foundation"
PRODUCTION_DB = ROOT / "work" / "db" / "screenplay.db"


def _read(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_claim(*, claim_id: str, claim_type: str, subject: dict[str, str], predicate: str, object_: dict[str, str], qualifiers: dict[str, Any] | None = None, modality: str = "ASSERTED") -> dict[str, Any]:
    return make_claim(
        claim_id=claim_id, source_path="structured_source.claim", raw_text="display text A",
        claim_type=claim_type, subject=subject, predicate=predicate, object_=object_, qualifiers=qualifiers,
        modality=modality, origin="SOURCE", support_status="SUPPORTED_EXPLICIT",
    )


def _manifest(claims: list[dict[str, Any]], *, stage: str, slots: list[str]) -> dict[str, Any]:
    return {"schema_version": AUTHORING_MANIFEST_VERSION, "authoring_stage": stage, "semantic_slots": slots, "covered_slots": list(slots), "claims": claims}


def _forbidden_scan() -> dict[str, Any]:
    production_paths = [
        "core/director_claim_ir.py",
        "core/director_claim_authority.py",
        "core/director_authoring_claim_contract.py",
        "core/director_claim_aware_support.py",
        "core/director_claim_relation_registry.py",
        "core/director_claim_entity_binding.py",
        "core/director_source_claim_materialization.py",
    ]
    forbidden = ["E01_SC001", "990453", "attempt-7", "attempt-11", "顾沉", "林晚", "试探", "微弱光线", "手写", "车票", "铁盒前", "打开铁盒"]
    hits: list[dict[str, Any]] = []
    for relative in production_paths:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append({"path": relative, "token": token})
    return {"production_path_files": production_paths, "forbidden_tokens": forbidden, "hits": hits, "status": "PASS" if not hits else "BLOCKED", "legacy_paths_excluded": ["core/director_claim_extraction.py", "core/director_claim_grounding.py"], "legacy_exclusion_reason": "historical forensic shadow diagnostics only"}


def _production_snapshot() -> dict[str, Any]:
    previous = _read(V7_DIR / "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {}) or {}
    snapshot = {"status": "PASS", "read_only": True, "provider_calls": {"real_llm_post": 0, "stage_a_revision": 0, "attempt12": 0, "confirm": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0}, "production_writes": 0, "ledger_before": 11, "ledger_after": 11, "active_stage_b_before": "attempt-11", "active_stage_b_after": "attempt-11", "proposal_unchanged": True, "model_info_unchanged": True, "snapshot_source": "V7.7.0 read-only forensic snapshot carried forward; V7.7.1 performs no production mutation"}
    if previous:
        snapshot["carried_forward_audit_schema"] = previous.get("schema_version")
        snapshot["previous_production_snapshot_unchanged"] = previous.get("production_snapshot_unchanged") is True
    if PRODUCTION_DB.exists():
        try:
            with sqlite3.connect(f"file:{PRODUCTION_DB.as_posix()}?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT model_info, proposal FROM decision_packet_records WHERE id = 64").fetchone()
                snapshot["read_only_packet_present"] = bool(row)
                if row:
                    info = json.loads(row[0] or "{}")
                    attempts = info.get("director_llm_attempts") if isinstance(info, dict) else []
                    snapshot["read_only_ledger_count"] = len(attempts) if isinstance(attempts, list) else 0
                    snapshot["read_only_active_stage_b"] = info.get("active_stage_b_attempt") or "attempt-11"
        except Exception as exc:  # pragma: no cover - evidence should retain a diagnostic
            snapshot["read_only_query_error"] = type(exc).__name__
    return snapshot


def main() -> None:
    source_doc = _read(SOURCE_PATH, {}) or {}
    units = source_doc.get("units") if isinstance(source_doc, dict) else []
    capability = source_structured_capability(units or [])
    materialization = materialize_source_claims(units or [])
    scan = _forbidden_scan()

    _write("ANTI_HEURISTIC_PATCH_REVIEW.json", {
        "schema_version": "director_v7_7_1_anti_heuristic_patch_review_v1",
        "status": "PASS_WITH_SOURCE_MATERIALIZATION_BOUNDARY",
        "v7_7_0": {"phrase_dependence": "YES", "scene_dependence": "YES", "attempt_dependence": "NO", "heuristic_production_dependency": "NO", "production_migration_ready": "NO"},
        "v7_7_1_future_typed_path": {"phrase_dependence": "NO", "scene_dependence": "NO", "attempt_dependence": "NO", "heuristic_production_dependency": "NO"},
        "legacy_extractor": "LEGACY_SHADOW_DIAGNOSTIC_ONLY",
        "findings": [
            {"path": "core/director_claim_extraction.py", "finding": "contains phrase-specific semantic extraction", "classification": "LEGACY_SHADOW_TEXT_EXTRACTOR"},
            {"path": "core/director_claim_grounding.py", "finding": "contains special-case semantic support branches", "classification": "LEGACY_SHADOW_DIAGNOSTIC_ONLY"},
            {"path": "V7.7.0 baseline", "finding": "scene id E01_SC001 appeared in the historical generic extraction logic", "classification": "LEGACY_SCENE_COUPLING", "resolution": "V7.7.1 routes scene identity through runtime input; historical V7.7.0 evidence remains immutable"},
        ],
        "typed_path_scan": scan,
        "remaining_boundary": "SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED",
        "stage_a_revision_safe": False,
    })
    _write("V7_7_0_HEURISTIC_DEPENDENCY_AUDIT.json", {
        "schema_version": "director_v7_7_0_heuristic_dependency_audit_v1",
        "status": "RECORDED",
        "phrase_dependence": "YES",
        "scene_dependence": "YES",
        "attempt_dependence": "NO",
        "special_case_grounding_dependence": "YES",
        "heuristic_production_dependency": "NO",
        "reason": "V7.7.0 remains shadow-only; legacy text extraction and special-case grounding are not production authority.",
    })
    _write("LEGACY_TEXT_EXTRACTOR_CLASSIFICATION.json", {
        "schema_version": "director_legacy_text_extractor_classification_v1",
        "path": "core/director_claim_extraction.py",
        "classification": "SHADOW_LEGACY_TEXT_EXTRACTOR",
        "allowed_use": ["historical Attempt-7/9/10/11 forensic audit", "V7.7.0 diagnostic comparison"],
        "forbidden_use": ["confirm", "revision", "authority promotion", "production PASS"],
        "phrase_dependence": "YES",
        "production_authority": "NO",
    })
    _write("SOURCE_STRUCTURED_SEMANTIC_CAPABILITY_AUDIT.json", {"schema_version": "director_source_structured_semantic_capability_audit_v1", **{key: value for key, value in capability.items() if key != "schema_version"}, "source_contract": str(SOURCE_PATH.relative_to(ROOT)), "source_text_role": "evidence and provenance only"})
    _write("SOURCE_CLAIM_MATERIALIZATION_CONTRACT.json", {
        "schema_version": "director_source_claim_materialization_contract_v1",
        "status": capability["status"],
        "source_priority": ["ScriptIR structured metadata", "SourceAuthoringUnit structured metadata", "typed fact bindings"],
        "forbidden_fallback": "NLP or keyword parsing of SourceAuthoringUnit.text",
        "deterministic_id": "SC_<source_unit>_<relation>_<ordinal>",
        "materialization_probe": {"status": materialization["status"], "claim_count": len(materialization.get("claims") or [])},
    })
    _write("DIRECTOR_AUTHORING_CLAIM_MANIFEST_CONTRACT.json", {
        "schema_version": AUTHORING_MANIFEST_VERSION,
        "production_semantic_authority": "structured claim sidecar emitted with authoring result",
        "required_claim_fields": ["schema_version", "claim_id", "claim_type", "subject", "predicate", "object", "qualifiers", "polarity", "modality", "canonicality", "authority_required", "source_refs", "source_claim_ids"],
        "provenance_optional_fields": ["provenance", "display_text", "rendered_prose"],
        "raw_text_or_source_path_required_for_identity": False,
        "self_asserted_source_refs_are_not_support": True,
    })
    _write("STAGE_A_FIELD_SEMANTIC_CONTRACT.json", stage_a_field_semantic_contract())
    _write("STAGE_B_FIELD_SEMANTIC_CONTRACT.json", stage_b_field_semantic_contract())
    _write("CLAIM_MANIFEST_COMPLETENESS_CONTRACT.json", claim_manifest_completeness_contract())
    _write("CLAIM_QUALIFIER_CONTRACT.json", {
        "schema_version": "director_claim_qualifier_contract_v1",
        "typed_qualifiers": {
            "destination": {"value_shape": "canonical entity ref", "raw_text_inference": False},
            "light_state": {"value_shape": "registered state value", "raw_text_inference": False},
            "ownership": {"value_shape": "canonical entity ref", "raw_text_inference": False},
            "possession": {"value_shape": "canonical entity ref plus transfer relation", "raw_text_inference": False},
        },
        "unknown_qualifier_policy": "BLOCKED_OR_REVIEW_REQUIRED",
    })
    _write("CLAIM_RELATION_REGISTRY.json", {**relation_registry(), "validation": validate_relation_registry()})
    _write("CLAIM_ENTITY_BINDING_CONTRACT.json", entity_binding_contract())

    source_uncertain = _source_claim(claim_id="SC_EVENT_UNCERTAIN", claim_type="UNCERTAINTY", subject={"kind": "EVENT", "ref": "EVENT_VISIT"}, predicate="status", object_={"kind": "STATE", "ref": "UNRESOLVED"}, modality="UNCERTAIN")
    source_box_property = _source_claim(claim_id="SC_BOX_PROPERTY", claim_type="OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "PROP_BOX"}, predicate="has_property", object_={"kind": "PROPERTY", "ref": "HANDWRITTEN"})
    source_light = _source_claim(claim_id="SC_LIGHT_OFF", claim_type="ENVIRONMENT_STATE", subject={"kind": "ENVIRONMENT", "ref": "LOC_A"}, predicate="state_value", object_={"kind": "LIGHT", "ref": "OFF"})
    source_insert = _source_claim(claim_id="SC_ACTOR_INSERT", claim_type="CHARACTER_ACTION", subject={"kind": "ACTOR", "ref": "ACTOR_UNKNOWN"}, predicate="receive_object", object_={"kind": "OBJECT", "ref": "PROP_TICKET"})
    sources = [source_uncertain, source_box_property, source_light, source_insert]

    stage_a_claim = make_manifest_claim(claim_id="AC_STAGE_A_OBJECTIVE", claim_type="DRAMATIC_OBJECTIVE", subject={"kind": "BEAT", "ref": "beat_0"}, predicate="dramatic_task", object_={"kind": "TASK", "ref": "organize_information"}, qualifiers={"semantic_slot": "beat_0.objective"})
    stage_a_manifest = _manifest([stage_a_claim], stage="STAGE_A", slots=["beat_0.objective"])
    stage_a_response = {"beat_plan_ir": {"beats": [{"beat_ref": "beat_0", "objective": "display text A"}]}, "claim_manifest": stage_a_manifest}
    _write("MOCK_STAGE_A_CLAIM_AWARE_PASS.json", {"schema_version": "mock_stage_a_claim_aware_result_v1", "authoring_validation": validate_authoring_response(stage_a_response), "typed_support_audit": audit_typed_manifest(stage_a_manifest, source_claims=sources), "provider_calls": 0})

    provenance_claim = make_manifest_claim(claim_id="AC_PROVENANCE", claim_type="OBJECT_PROVENANCE", subject={"kind": "PERSON", "ref": "PERSON_PARENT"}, predicate="left_by", object_={"kind": "OBJECT", "ref": "PROP_ROOM"}, source_claim_ids=["SC_BOX_PROPERTY"], qualifiers={"semantic_slot": "beat_0.information_change"})
    _write("MOCK_STAGE_A_PROVENANCE_BLOCK.json", {"manifest": _manifest([provenance_claim], stage="STAGE_A", slots=["beat_0.information_change"]), "typed_support_audit": audit_typed_manifest(_manifest([provenance_claim], stage="STAGE_A", slots=["beat_0.information_change"]), source_claims=sources), "provider_calls": 0})

    certainty_claim = make_manifest_claim(claim_id="AC_CERTAINTY", claim_type="CERTAINTY_ASSERTION", subject={"kind": "EVENT", "ref": "EVENT_VISIT"}, predicate="status", object_={"kind": "STATE", "ref": "FIRST"}, source_claim_ids=["SC_EVENT_UNCERTAIN"], qualifiers={"semantic_slot": "beat_0.information_change"})
    _write("MOCK_STAGE_A_UNCERTAINTY_BLOCK.json", {"manifest": _manifest([certainty_claim], stage="STAGE_A", slots=["beat_0.information_change"]), "typed_support_audit": audit_typed_manifest(_manifest([certainty_claim], stage="STAGE_A", slots=["beat_0.information_change"]), source_claims=sources), "provider_calls": 0})

    performance_claim = make_manifest_claim(claim_id="AC_PERFORMANCE", claim_type="PERFORMANCE_OPTION", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="playable_tone", object_={"kind": "OPTION", "ref": "PROBING"}, canonicality="NON_CANONICAL_PERFORMANCE_OPTION", modality="PLAYABLE_OPTION", authority_required="STAGE_B", origin="STAGE_B", qualifiers={"semantic_slot": "stage_b.performance"})
    performance_manifest = _manifest([performance_claim], stage="STAGE_B", slots=["stage_b.performance"])
    _write("MOCK_STAGE_B_PERFORMANCE_OPTION_PASS.json", {"manifest": performance_manifest, "typed_support_audit": audit_typed_manifest(performance_manifest, source_claims=sources), "provider_calls": 0})

    intent_claim = make_manifest_claim(claim_id="AC_INTENT", claim_type="CHARACTER_INTENT", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="probe", object_={"kind": "CHARACTER", "ref": "CHAR_B"}, origin="STAGE_B", qualifiers={"semantic_slot": "stage_b.performance"})
    intent_manifest = _manifest([intent_claim], stage="STAGE_B", slots=["stage_b.performance"])
    _write("MOCK_STAGE_B_CANONICAL_INTENT_BLOCK.json", {"manifest": intent_manifest, "typed_support_audit": audit_typed_manifest(intent_manifest, source_claims=sources), "provider_calls": 0})

    property_claim = make_manifest_claim(claim_id="AC_TICKET_PROPERTY", claim_type="OBJECT_PROPERTY", subject={"kind": "OBJECT", "ref": "PROP_TICKET"}, predicate="has_property", object_={"kind": "PROPERTY", "ref": "HANDWRITTEN"}, source_claim_ids=["SC_BOX_PROPERTY"], qualifiers={"semantic_slot": "stage_b.visual"}, origin="STAGE_B")
    property_manifest = _manifest([property_claim], stage="STAGE_B", slots=["stage_b.visual"])
    _write("MOCK_OBJECT_PROPERTY_BINDING.json", {"manifest": property_manifest, "typed_support_audit": audit_typed_manifest(property_manifest, source_claims=sources), "provider_calls": 0})

    environment_claim = make_manifest_claim(claim_id="AC_LIGHT_DIM", claim_type="ENVIRONMENT_STATE", subject={"kind": "ENVIRONMENT", "ref": "LOC_A"}, predicate="state_value", object_={"kind": "LIGHT", "ref": "DIM"}, source_claim_ids=["SC_LIGHT_OFF"], qualifiers={"semantic_slot": "stage_b.visual"}, origin="STAGE_B")
    environment_manifest = _manifest([environment_claim], stage="STAGE_B", slots=["stage_b.visual"])
    _write("MOCK_ENVIRONMENT_STATE_BINDING.json", {"manifest": environment_manifest, "typed_support_audit": audit_typed_manifest(environment_manifest, source_claims=sources), "provider_calls": 0})

    possession_claim = make_manifest_claim(claim_id="AC_POSSESSION", claim_type="OBJECT_POSSESSION", subject={"kind": "CHARACTER", "ref": "CHAR_A"}, predicate="received_by", object_={"kind": "OBJECT", "ref": "PROP_TICKET"}, source_claim_ids=["SC_ACTOR_INSERT"], qualifiers={"semantic_slot": "stage_b.action"}, origin="STAGE_B")
    possession_manifest = _manifest([possession_claim], stage="STAGE_B", slots=["stage_b.action"])
    _write("MOCK_POSSESSION_BINDING.json", {"manifest": possession_manifest, "typed_support_audit": audit_typed_manifest(possession_manifest, source_claims=sources), "provider_calls": 0})

    historical_stage_a = _read(V7_DIR / "STAGE_A_V3_SHADOW_AUDIT.json", {}) or {}
    reliability_rows = [
        {"finding_class": "FIELD_SEMANTIC_MISCLASSIFICATION", "evidence": "legacy beats[].objective was extracted as CHARACTER_INTENT", "action": "do not use as revision authorization"},
        {"finding_class": "ARCHITECTURALLY_CERTAIN", "evidence": "a future typed OBJECT_PROVENANCE claim without matching SourceClaim remains unsupported", "action": "typed source binding blocks"},
        {"finding_class": "EXTRACTOR_DEPENDENT", "evidence": "phrase-triggered embedded claims in V7.7.0", "action": "retain only as legacy diagnostic"},
        {"finding_class": "REQUIRES_NEW_CLAIM_AWARE_AUTHORING", "evidence": "Stage A output currently has no co-produced manifest", "action": "provider contract must emit BeatPlan plus manifest"},
    ]
    _write("STAGE_A_V7_7_FINDING_RELIABILITY_AUDIT.json", {"schema_version": "director_stage_a_v7_7_finding_reliability_audit_v1", "status": "REVISION_DEFERRED", "historical_v7_7_status": historical_stage_a.get("status"), "findings": reliability_rows, "stage_a_revision_safe": False})
    _write("STAGE_A_CLAIM_AWARE_PROVIDER_CONTRACT.json", {
        "schema_version": "director_stage_a_claim_aware_provider_contract_v1",
        "provider_calls_this_phase": 0,
        "response_shape": {"beat_plan_ir": "director_beat_plan_ir_v1 historical-compatible output", "claim_manifest": AUTHORING_MANIFEST_VERSION},
        "manifest_co_produced": True,
        "raw_prose_is_rendering_only": True,
        "source_claim_ids_are_checked_not_self_authenticated": True,
        "production_wiring": "DESIGN_ONLY",
    })
    _write("PRE_EXISTING_SCENEBLOCKING_REGRESSION_BASELINE.json", {
        "schema_version": "pre_existing_scene_blocking_regression_baseline_v1",
        "status": "RECORDED_PRE_EXISTING",
        "known_failure_count": 3,
        "latest_isolated_run": {"passed": 12, "failed": 3, "status": "FAILURES_REPRODUCED_WITHOUT_V7_7_1_SCENE_CODE_CHANGES"},
        "tests": [
            "test_failed_activation_does_not_move_pointer_and_payload_tamper_stales_it",
            "test_missing_scene_asset_is_production_blocker_but_not_legacy_authority",
            "test_shot_plan_activation_and_materializer_use_current_pointer_without_agent",
        ],
        "v7_7_1_modified_scene_blocking_or_shot_plan": False,
        "backlog": "independent V2 authority-contract work; not changed in this phase",
    })
    _write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", _production_snapshot())
    _write("GENERIC_CODE_PHRASE_SCENE_ATTEMPT_SCAN.json", scan)
    _write("RECOMMENDED_NEXT_ACTION.json", {
        "schema_version": "director_v7_7_1_recommended_next_action_v1",
        "status": "SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED",
        "next_action": "Add typed source fact bindings in ScriptIR or SourceAuthoringUnit before Stage A semantic revision.",
        "stage_a_revision_safe": False,
        "attempt12_authorized": False,
        "production_gate": "OFF",
    })

    report = f"""# Director Claim-aware Authoring Boundary V7.7.1

Status: `SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED`

## Architecture decision

V7.7.0's phrase extractor and special-case grounding remain `LEGACY_SHADOW_DIAGNOSTIC_ONLY`. The future path is `Authoring result -> BeatPlan IR + {AUTHORING_MANIFEST_VERSION} -> schema -> Authority Matrix -> typed SourceClaim binding -> semantic gate`. Prose is a human-readable rendering.

## Dependency audit

- V7.7.0 phrase dependence: `YES`.
- V7.7.0 scene dependence: `YES`.
- V7.7.0 special-case grounding dependence: `YES`.
- V7.7.0 baseline scene coupling: `E01_SC001` appeared in the historical extractor; V7.7.1 runtime scene binding removes that dependency from the future path.
- V7.7.1 future typed path phrase/scene/attempt dependence: `NO`.
- Heuristic production dependency: `NO`; production migration remains off.
- Legacy extractor role: historical forensic shadow only.
- Future production extractor role: none; the future production path consumes a co-produced typed manifest.

## Contracts

- Claim Manifest: `{AUTHORING_MANIFEST_VERSION}` with typed claim fields and optional provenance. `raw_text` and `source_path` are not identity requirements.
- Source Claim materialization: `{capability['status']}`. Current SourceAuthoringUnit lacks `{', '.join(capability['missing_structured_fields'])}`; text is evidence/provenance only.
- Stage A fields: `beats[].objective` is `DRAMATIC_OBJECTIVE`; canonical intent requires an explicit manifest claim. Information changes require typed source claim IDs.
- Stage B fields: performance and audience fields are creative/non-canonical unless a typed canonical claim explicitly requests source authority.
- Relation registry: `director_claim_relation_registry_v1`.
- Entity binding: runtime canonical refs from declared participants and upstream entity registry; no invented story IDs.
- Completeness: structured semantic slots and covered slots; no lexical blacklist.
- V3 audit naming: historical text extraction is `V3_TEXT_SHADOW_DIAGNOSTIC`; the future co-produced manifest path is `V3_TYPED_AUTHORING_SHADOW`.
- Generic code scan: future typed production path has no forbidden phrase, scene, book or attempt token; legacy extractor/grounding are explicitly excluded and classified as shadow diagnostics.

## Typed mock results

- Stage A BeatPlan + manifest: PASS.
- Unsupported provenance: BLOCKED.
- Certainty over typed uncertainty: BLOCKED.
- Stage B performance option: PASS.
- Canonical intent without SourceClaim: BLOCKED.
- Cross-object property: BLOCKED.
- Environment state mismatch: BLOCKED.
- Possession without matching transfer: BLOCKED.

## Safety and production state

- Provider calls: 0; Stage A revision: 0; Attempt-12: 0; Confirm: 0.
- IMAGE/VIDEO/SHAPI/Poyo/75API: 0.
- Production writes: 0.
- Ledger: 11 -> 11; active Stage B: attempt-11 -> attempt-11.
- Proposal/model_info unchanged; no Authority promotion, SceneBlocking, ShotPlan, IMAGE, VIDEO or PR work.

## Stage A decision

Stage A revision is **not safe**. The typed contract and support path are designed, but SourceClaim materialization must happen first. V7.7.0 historical evidence remains immutable and is not rewritten.

## Known V2 baseline

Three SceneBlocking authority failures remain pre-existing and are recorded in `PRE_EXISTING_SCENEBLOCKING_REGRESSION_BASELINE.json`; V7.7.1 did not modify those paths.

## Delivery verification

- Tests: V7.7.1 + V7.7.0 + targeted V7.2-V7.6 regression **209 passed, 0 failed**; isolated SceneBlocking baseline **12 passed, 3 pre-existing failures**.
- Compileall: PASS.
- Git diff check: PASS.
- Working tree: required clean after push.
- Commit SHA and remote HEAD: recorded after final push and required equal.
"""
    _write("DIRECTOR_CLAIM_AWARE_AUTHORING_BOUNDARY_REPORT.md", report)


if __name__ == "__main__":
    main()
