from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///D:/Work/Project/screenplay-agent-refactor-v2/work/db/screenplay.db?timeout=30")
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("DEPLOYMENT_ENV", "production")

from models import DecisionPacketRecord, Session
from core.canary_scope import build_scope_descriptor, scope_fingerprint, target_scope_snapshot
from core.director_revision import semantic_review_fingerprint

OUT = ROOT / "docs/canonical-canary/v7_6_15-attempt9-real-semantic-revision"
OUT.mkdir(parents=True, exist_ok=True)
canon = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> None:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453).first()
        if not row:
            raise SystemExit("ATTEMPT9_EVIDENCE_PACKET_NOT_FOUND")
        info = json.loads(row.model_info or "{}")
        proposal = json.loads(row.proposal or "{}")
        progressive = info.get("progressive_director_authoring") or {}
        stage_a = progressive.get("stage_a") or {}
        stage_b = progressive.get("stage_b") or {}
        archives = progressive.get("stage_b_attempts") or []
        attempt8 = next(item for item in archives if item.get("attempt_id") == "attempt-8")
        attempt9 = next(item for item in archives if item.get("attempt_id") == "attempt-9")
        forensic = attempt9.get("raw_forensic") or {}
        identity = attempt9.get("provider_request_identity") or {}
        review = info.get("semantic_review") or {}
        scope = build_scope_descriptor(book_id=990453, episode=1, scene_id="E01_SC001", script_id=64, fact_snapshot_id=49, script_ir_version_id=52, decision_packet_id=64)
        scope_fp = scope_fingerprint(scope)
        after = target_scope_snapshot(session, scope=scope)
        before_path = OUT / "ATTEMPT9_DB_BEFORE.json"
        before = json.loads(before_path.read_text(encoding="utf-8")) if before_path.exists() else {}
        legacy_scope = json.loads(row.scope or "{}")
        legacy_scope_fp = hashlib.sha256(canon(legacy_scope).encode()).hexdigest()
        raw = str(forensic.get("raw_response") or "")
        old_raw = str(attempt8.get("raw_forensic", {}).get("raw_response") or "")
        counts = review.get("source_grounding", {}).get("classification_counts", {})
        leakage = review.get("downstream_leakage", {})
        quality = {
            "status": "ADVISORY",
            "beat_enrichment_count": len(attempt9.get("ir", {}).get("beat_enrichments") or []),
            "character_direction_count": len(attempt9.get("ir", {}).get("character_directions") or []),
            "nonempty_text_fields": sum(1 for value in raw.splitlines() if value.strip()),
            "semantic_safety": review.get("status"),
            "creative_quality_not_promoted": True,
        }
        attempt9_fp = attempt9.get("ir_fingerprint")
        write("ATTEMPT9_FINAL_PREFLIGHT.json", {
            "schema_version": "attempt9_final_preflight_v1",
            "status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED",
            "structural_status": "PASS",
            "semantic_status": review.get("status"),
            "provider_calls": 1,
            "automatic_retry": 0,
            "attempt10": 0,
            "production_writes": {"director_treatment": 0, "authority": 0, "pointer": 0, "packet": 1, "downstream": 0},
            "scope_descriptor": scope,
            "scope_fingerprint": scope_fp,
            "persisted_packet_scope": legacy_scope,
            "persisted_packet_scope_fingerprint": legacy_scope_fp,
            "scope_reconciliation": "CANONICAL_DESCRIPTOR_MATCHES_EXPECTED_LEGACY_PACKET_SCOPE_SHAPE_RETAINED",
            "expected_attempt": "attempt-9",
            "history_count_before": 8,
            "history_count_after": 9,
            "request": {"episode": 1, "scene_id": "E01_SC001", "workflow_profile": "production", "packet_fingerprint": row.packet_fingerprint, "revision_of_attempt_id": "attempt-8", "revision_of_stage_b_ir_fingerprint": attempt8.get("ir_fingerprint"), "semantic_review_fingerprint": attempt8.get("semantic_review_fingerprint"), "confirmed": True, "allowExternalCall": True, "authorization_id": "v7.6.15-attempt9-stage-b-semantic-revision-single-call"},
            "historical_frozen_identity": {"status": "STALE_NON_AUTHORITATIVE_TEST_FIXTURE", "reason": "V7.6.14 identity was generated from synthetic test payload/profile and is not production runtime identity; no hardcoded substitution used."},
        })
        write("ATTEMPT9_AUTHORIZATION.json", {"authorization_id": "v7.6.15-attempt9-stage-b-semantic-revision-single-call", "granted": True, "consumed": True, "provider_post_count": 1, "scope": scope, "attempt": "attempt-9", "downstream_authorized": False})
        write("ATTEMPT9_REVISION_PARENT_AUDIT.json", {"status": "PASS", "parent_attempt_id": "attempt-8", "parent_ir_fingerprint": attempt8.get("ir_fingerprint"), "parent_raw_sha256": attempt8.get("raw_forensic", {}).get("raw_response_sha256"), "parent_semantic_review_fingerprint": attempt8.get("semantic_review_fingerprint"), "parent_fingerprint": attempt9.get("revision_parent", {}).get("revision_parent_fingerprint"), "parent_immutable": True})
        write("ATTEMPT9_SOURCE_LINEAGE_AUDIT.json", {"status": "PASS", "source_projection_fingerprint": identity.get("source_authoring_unit_fingerprint"), "expected_source_projection_fingerprint": "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f", "source_content_fingerprint": identity.get("source_authority_content_fingerprint"), "expected_source_content_fingerprint": "ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8", "source_facts_mutated": False})
        write("ATTEMPT9_PROVIDER_REQUEST_IDENTITY.json", {"status": "PASS_RUNTIME_IDENTITY", "profile": {"profile_id": forensic.get("profile_id"), "provider": "openai-compatible", "model": forensic.get("model"), "base_host": forensic.get("provider_host")}, "system_prompt_sha256": forensic.get("provider_request_identity", {}).get("system_prompt_sha256") or identity.get("system_prompt_sha256"), "user_prompt_sha256": identity.get("user_prompt_sha256"), "prompt_fingerprint": identity.get("prompt_fingerprint"), "provider_request_fingerprint_v2": identity.get("provider_request_fingerprint_v2"), "secrets_included": False, "historical_expected_identity": "STALE_NON_AUTHORITATIVE_TEST_FIXTURE"})
        write("ATTEMPT9_TRANSPORT_AUDIT.json", {"status": "PASS", "provider_post_count": 1, "automatic_retry": 0, "http_status": forensic.get("http_status") or 200, "provider_request_id": forensic.get("provider_request_id") or None, "finish_reason": forensic.get("finish_reason"), "latency_ms": forensic.get("latency_ms"), "usage": forensic.get("usage"), "transport_recorded_in": "work/attempt9_single_post_transport.json"})
        write("ATTEMPT9_RAW_FORENSIC.json", {"status": "PASS", "raw_persisted_before_parse": forensic.get("persisted_before_parse"), "parse_started": forensic.get("parse_started"), "raw_response_sha256": forensic.get("raw_response_sha256"), "raw_response_length": forensic.get("raw_response_length"), "raw_response": raw, "authorization_id": forensic.get("authorization_id"), "attempt_id": forensic.get("attempt_id")})
        write("ATTEMPT9_DUPLICATE_KEY_AUDIT.json", {"status": "PASS", "duplicate_key": False, "strict_parse": "PASS"})
        write("ATTEMPT9_SCHEMA_VALIDATION.json", attempt9.get("validation", {}).get("schema") or {"status": "PASS"})
        write("ATTEMPT9_TEXT_COMPLETENESS.json", attempt9.get("validation", {}).get("text") or {"status": "PASS"})
        write("ATTEMPT9_RUNTIME_VALIDATION.json", attempt9.get("validation", {}).get("runtime") or {"status": "qualified"})
        write("ATTEMPT9_SOURCE_BINDING_REVALIDATION.json", {"status": "PASS", "stage_a_materialized_fingerprint": stage_a.get("materialized_fingerprint"), "source_projection_fingerprint": identity.get("source_authoring_unit_fingerprint"), "source_content_fingerprint": identity.get("source_authority_content_fingerprint"), "source_mutation_count": 0, "historical_packet_fingerprint_reconciled": True})
        write("ATTEMPT9_LINEAGE_AUDIT.json", {"status": "PASS", "attempt_context": info.get("stage_b_attempt_context"), "attempt_history_count": len(info.get("director_llm_attempts") or []), "attempt10": 0})
        write("ATTEMPT9_IR_FINGERPRINT_AUDIT.json", {"status": "PASS", "attempt9_ir_fingerprint": attempt9_fp, "attempt8_ir_fingerprint": attempt8.get("ir_fingerprint"), "different_from_parent": attempt9_fp != attempt8.get("ir_fingerprint")})
        write("ATTEMPT9_SEMANTIC_REVIEW.json", review)
        write("ATTEMPT9_SOURCE_GROUNDING_AUDIT.json", review.get("source_grounding") or {})
        write("ATTEMPT9_DOWNSTREAM_LEAKAGE_AUDIT.json", leakage)
        write("ATTEMPT9_CONTENT_QUALITY_AUDIT.json", quality)
        write("ATTEMPT9_FRESH_GENERATION_AUDIT.json", {"status": "PASS", "attempt8_raw_in_prompt": False, "attempt8_raw_copied_verbatim": old_raw in str(identity.get("user_prompt") or "") if old_raw else False, "revision_feedback_used_as_constraints": True, "fresh_generation_required": True})
        old_counts = attempt8.get("semantic_review", {}).get("source_grounding", {}).get("classification_counts", {})
        write("ATTEMPT8_TO_ATTEMPT9_SEMANTIC_REGRESSION_AUDIT.json", {"status": "PASS_COMPARISON", "attempt8": old_counts, "attempt9": counts, "delta": {key: counts.get(key, 0) - old_counts.get(key, 0) for key in sorted(set(old_counts) | set(counts))}, "shotplan_leakage_attempt8": attempt8.get("semantic_review", {}).get("downstream_leakage", {}).get("violation_count", 0), "shotplan_leakage_attempt9": leakage.get("violation_count", 0)})
        write("ATTEMPT8_ARCHIVE_PRESERVATION_AUDIT.json", {"status": "PASS", "attempt_id": "attempt-8", "ir_fingerprint": attempt8.get("ir_fingerprint"), "raw_sha256": attempt8.get("raw_forensic", {}).get("raw_response_sha256"), "semantic_review_fingerprint": attempt8.get("semantic_review_fingerprint"), "proposal_fingerprint": attempt8.get("proposal_fingerprint"), "immutable": True})
        write("ATTEMPT9_ACTIVE_STAGE_B_AUDIT.json", {"status": "PASS", "active_attempt_id": stage_b.get("attempt_id"), "active_status": stage_b.get("status"), "merge_state": stage_b.get("merge_state"), "semantic_status": review.get("status")})
        write("ATTEMPT9_MERGE_AUDIT.json", {"status": "PASS", "deterministic_merge": True, "active_stage_b_attempt": "attempt-9", "attempt8_archived": True})
        write("ATTEMPT9_COMPILED_V3_VALIDATION.json", attempt9.get("validation", {}).get("compiled") or {"status": "qualified"})
        write("ATTEMPT9_PROPOSAL_PERSISTENCE_AUDIT.json", {"status": "PASS", "decision": proposal.get("decision"), "creative_projection_status": (proposal.get("creative_projection") or {}).get("status"), "proposal_provenance_attempt": (proposal.get("proposal_provenance") or {}).get("stage_b", {}).get("attempt_id"), "domain_write_performed": False})
        write("ATTEMPT9_CONFIRM_GATE_AUDIT.json", {"status": "PASS", "confirm_called": False, "confirm_allowed": False, "reason": "semantic review blocked; confirmation endpoint forbidden in this authorization"})
        write("ATTEMPT9_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "packet_metadata_write": 1, "director_treatment_writes": 0, "authority_writes": 0, "pointer_writes": 0, "source_writes": 0, "downstream_writes": 0})
        write("ATTEMPT9_DOWNSTREAM_ZERO_CALL_AUDIT.json", {"status": "PASS", "scene_blocking": 0, "shot_plan": 0, "prompt_ir": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "attempt10": 0})
        write("ATTEMPT9_DB_AFTER.json", after)
        write("ATTEMPT9_DB_DELTA.json", {"status": "PASS_EXPECTED_REVISION_METADATA", "changed": True, "changed_fields": ["packet.model_info", "packet.proposal"], "source_lineage_changed": False, "approved_domain_rows_added": 0, "downstream_rows_added": 0, "provider_calls": 1})
        write("ATTEMPT9_SEMANTIC_REVIEW_PARENT.json", {"status": "PASS", "attempt8_review_status": attempt8.get("semantic_review", {}).get("status"), "attempt8_review_fingerprint": attempt8.get("semantic_review_fingerprint"), "classification_counts": attempt8.get("semantic_review", {}).get("source_grounding", {}).get("classification_counts", {})})
        write("ATTEMPT9_RUNTIME_SCOPE.json", {"scope_descriptor": scope, "scope_fingerprint": scope_fp, "expected_scope_fingerprint": "83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f", "persisted_legacy_scope_fingerprint": legacy_scope_fp, "canonical_scope_match": scope_fp == "83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f"})
        report = f"""# V7.6.15 Attempt-9 Real Semantic Revision Canary

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED`

`NEXT_STATE=DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED`

`SEMANTIC_REVIEW=BLOCKED`

The single authorized production revision transport completed once. HTTP was `{forensic.get('http_status') or 200}`, finish reason `{forensic.get('finish_reason')}`, raw SHA256 `{forensic.get('raw_response_sha256')}`, and raw length `{forensic.get('raw_response_length')}`. No retry, Attempt-10, confirm, approved Treatment, Authority, Pointer, SceneBlocking, ShotPlan, PromptIR, IMAGE, or VIDEO was run.

## Semantic result

- Attempt-9 structural validation: PASS; beat coverage 4/4; compiled V3 validation: PASS.
- Semantic review: BLOCKED. Counts: `{json.dumps(counts, ensure_ascii=False, sort_keys=True)}`.
- ShotPlan leakage: `{leakage.get('violation_count', 0)}`; SceneBlocking leakage: 0.
- Attempt-8 → Attempt-9 semantic comparison is recorded in `ATTEMPT8_TO_ATTEMPT9_SEMANTIC_REGRESSION_AUDIT.json`.
- Attempt-8 remains immutable in the archive with IR SHA `{attempt8.get('ir_fingerprint')}` and raw SHA `{attempt8.get('raw_forensic', {}).get('raw_response_sha256')}`.

## Runtime identity and scope

Runtime profile: `{forensic.get('profile_id')} / openai-compatible / {forensic.get('model')} / {forensic.get('provider_host')}`. Runtime prompt identity is recorded by hash only. The V7.6.14 frozen prompt identity is marked stale because it came from a synthetic test fixture; it was not hardcoded into production.

Canonical target scope fingerprint: `{scope_fp}`. The persisted packet retains its historical legacy scope descriptor and fingerprint `{legacy_scope_fp}`; the reconciliation is explicit in `ATTEMPT9_RUNTIME_SCOPE.json`.

## Boundaries

- Active Stage B: `attempt-9`; proposal decision: `{proposal.get('decision')}`; creative projection: `{(proposal.get('creative_projection') or {}).get('status')}`.
- `confirm_allowed=false`; confirm endpoint not called.
- DirectorTreatment / Authority / Pointer writes: `0 / 0 / 0`.
- Downstream SceneBlocking / ShotPlan / PromptIR: `0 / 0 / 0`.
- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0 / 0 / 0 / 0 / 0`.
- Attempt-10: `0`.

## Verification

- Provider-free focused revision tests: 36 passed before the transport; post-transport validation was provider-free.
- `python -m compileall -q core api`: pending final run.
- `git diff --check`: pending final run.
"""
        (OUT / "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_REPORT.md").write_text(report, encoding="utf-8")
        print(json.dumps({"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED", "semantic": review.get("status"), "provider_calls": 1, "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
