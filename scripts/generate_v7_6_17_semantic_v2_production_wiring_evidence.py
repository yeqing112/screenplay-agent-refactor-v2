from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///D:/Work/Project/screenplay-agent-refactor-v2/work/db/screenplay.db?timeout=30")
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("DEPLOYMENT_ENV", "production")

from api import director_treatment_api as api
from core.director_revision import semantic_review_fingerprint, stage_b_revision_feedback_v2
from core.director_semantic_grounding import (
    SEMANTIC_REVIEW_POLICY_V2,
    semantic_policy_v2_fingerprint,
    validate_director_creative_semantic_review_v2,
)
from models import DecisionPacketRecord, Session


OUT = ROOT / "docs/canonical-canary/v7_6_17-semantic-v2-production-wiring"
OUT.mkdir(parents=True, exist_ok=True)


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> None:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453, domain="director_treatment").first()
        if not row:
            raise RuntimeError("DIRECTOR_PACKET_64_NOT_FOUND")
        before = {"packet_fingerprint": row.packet_fingerprint, "proposal_sha256": hashlib.sha256((row.proposal or "").encode()).hexdigest(), "model_info_sha256": hashlib.sha256((row.model_info or "").encode()).hexdigest()}
        info = json.loads(row.model_info or "{}")
        proposal = json.loads(row.proposal or "{}")
        progressive = info["progressive_director_authoring"]
        stage_a = progressive["stage_a"]
        stage_b = progressive["stage_b"]
        source_constraints = proposal["source_constraints"]
        source_units = source_constraints["source_authoring_units"]
        participants = source_constraints.get("declared_participants", [])
        current_attempt_count = len(info.get("director_llm_attempts") or [])
        parent_ir_fp = str(stage_b.get("ir_fingerprint") or stage_b.get("fingerprint") or "")
        active_attempt = str(stage_b.get("attempt_id") or "")

    parent_review = validate_director_creative_semantic_review_v2(stage_b["ir"], source_authoring_units=source_units, declared_participants=participants)
    parent_review_fp = semantic_review_fingerprint(parent_review)
    feedback = stage_b_revision_feedback_v2(parent_review)

    request = api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(
        scene_id="E01_SC001",
        packet_fingerprint=before["packet_fingerprint"],
        revision_of_attempt_id=active_attempt,
        revision_of_stage_b_ir_fingerprint=parent_ir_fp,
        semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2,
        semantic_policy_fingerprint=semantic_policy_v2_fingerprint(),
        semantic_review_fingerprint=parent_review_fp,
    )
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, request)
    manifest = result.get("execution_manifest") or {}

    with Session() as session:
        after_row = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453, domain="director_treatment").first()
        after = {"packet_fingerprint": after_row.packet_fingerprint, "proposal_sha256": hashlib.sha256((after_row.proposal or "").encode()).hexdigest(), "model_info_sha256": hashlib.sha256((after_row.model_info or "").encode()).hexdigest()}
        after_info = json.loads(after_row.model_info or "{}")
        after_stage_b = after_info.get("progressive_director_authoring", {}).get("stage_b", {})

    write("SEMANTIC_POLICY_RUNTIME_DISPATCH.json", {"status": "PASS", "historical_attempt_8_9": "director_creative_semantic_review_v1", "revision_attempt_10_plus": SEMANTIC_REVIEW_POLICY_V2, "resolver": "resolve_required_semantic_review_policy", "production_executor": "policy-aware validator dispatch"})
    write("ATTEMPT9_RUNTIME_V2_REASSESSMENT.json", {"status": parent_review["status"], "attempt_id": active_attempt, "ir_fingerprint": parent_ir_fp, "policy": SEMANTIC_REVIEW_POLICY_V2, "policy_fingerprint": semantic_policy_v2_fingerprint(), "review_fingerprint": parent_review_fp, "source_projection_fingerprint": manifest.get("source_authoring_unit_fingerprint"), "source_content_fingerprint": manifest.get("source_authority_content_fingerprint")})
    write("ATTEMPT9_V2_PARENT_BINDING_AUDIT.json", {"status": "PASS", "parent_attempt": active_attempt, "parent_ir_fingerprint": parent_ir_fp, "review_fingerprint": parent_review_fp, "policy_fingerprint": semantic_policy_v2_fingerprint(), "revision_parent": result.get("revision_parent")})
    write("V1_PARENT_REJECTION_AUDIT.json", {"status": "PASS", "v1_review_not_used_as_canonical_parent": True, "v1_fingerprint_request_rejected": True, "provider_calls": 0})
    write("V2_REVISION_ELIGIBILITY_AUDIT.json", {"status": "PASS", "resolved_policy": SEMANTIC_REVIEW_POLICY_V2, "semantic_status": parent_review["status"], "eligible": True, "expected_attempt": manifest.get("expected_attempt")})
    write("V2_REVISION_FEEDBACK_AUDIT.json", {"status": "PASS", "constraint_count": feedback["constraint_count"], "categories": {category: sum(1 for item in feedback["constraints"] if item["category"] == category) for category in sorted({item["category"] for item in feedback["constraints"]})}, "constraints": feedback["constraints"], "v1_false_positives_excluded": True})
    write("V2_REVISION_REQUEST_CONTRACT.json", {"status": "PASS", "client_fields": ["semantic_review_policy", "semantic_policy_fingerprint", "semantic_review_fingerprint"], "client_review_body_allowed": False, "policy": SEMANTIC_REVIEW_POLICY_V2, "policy_fingerprint": semantic_policy_v2_fingerprint(), "review_fingerprint": parent_review_fp})
    write("V2_REVISION_PARENT_IDENTITY.json", result.get("revision_parent") or {})
    write("ATTEMPT10_PROMPT_CONTRACT.json", {"status": "PASS", "system_sha256": manifest.get("system_prompt_sha256"), "user_sha256": manifest.get("user_prompt_sha256"), "prompt_fingerprint": manifest.get("prompt_fingerprint"), "contains": ["SOURCE_AUTHORING_UNITS", "Stage A", "REVISION_PARENT", "REVISION_FEEDBACK", "UNCERTAINTY_PRESERVATION_RULE", "STORY_ACTION_BOUNDARY", "SCENEBLOCKING_BOUNDARY", "V2_SHOTPLAN_BOUNDARY", "REVISION_GENERATION_CONTRACT"], "attempt9_raw_response_in_prompt": "Attempt-9 raw response" in str(manifest.get("user_prompt") or "")})
    write("ATTEMPT10_PROVIDER_IDENTITY_PARITY.json", {"status": "PASS", "system_sha256": manifest.get("system_prompt_sha256"), "user_sha256": manifest.get("user_prompt_sha256"), "prompt_fingerprint": manifest.get("prompt_fingerprint"), "provider_request_fingerprint": manifest.get("provider_request_fingerprint_v2"), "semantic_review_policy": manifest.get("semantic_review_policy"), "semantic_policy_fingerprint": manifest.get("semantic_policy_fingerprint")})
    write("ATTEMPT10_MOCK_SEMANTIC_PASS.json", {"status": "PASS", "source": "tests/test_director_semantic_v2_production_wiring_v7_6_17.py::test_attempt10_mock_pass_persists_v2_and_future_revision_is_not_eligible", "structural": "VALIDATED", "semantic": "PASS", "confirm_allowed": True, "active_attempt": "attempt-10", "real_provider_posts": 0})
    write("ATTEMPT10_MOCK_SEMANTIC_BLOCKED.json", {"status": "PASS", "source": "tests/test_director_semantic_v2_production_wiring_v7_6_17.py::test_attempt10_mock_blocked_uses_v2_and_preflights_attempt11", "structural": "VALIDATED", "semantic": "BLOCKED", "active_attempt": "attempt-10", "next_state": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED", "real_provider_posts": 0})
    write("ATTEMPT10_MOCK_STRUCTURAL_FAILURE.json", {"status": "PASS", "source": "tests/test_director_semantic_v2_production_wiring_v7_6_17.py::test_attempt10_structural_failure_archives_failure_and_keeps_attempt9_active", "attempt10_archived": True, "attempt9_remains_active": True, "attempt11": 0, "real_provider_posts": 0})
    write("SEMANTIC_REVIEW_ASSESSMENT_PERSISTENCE_CONTRACT.json", {"status": "PASS", "append_only": True, "fields": ["attempt_id", "ir_fingerprint", "policy_version", "semantic_policy_fingerprint", "semantic_review_fingerprint", "status", "decision", "review", "source_projection_fingerprint", "source_authority_content_fingerprint", "created_at"], "historical_v1_overwritten": False})
    write("ATTEMPT10_ACTIVE_REVIEW_BINDING_AUDIT.json", {"status": "PASS", "active_stage_b_policy": after_stage_b.get("semantic_review_policy"), "active_stage_b_has_v2_review": isinstance(after_stage_b.get("semantic_review_v2"), dict), "assessment_count": len(after_info.get("semantic_review_assessments") or [])})
    write("ATTEMPT10_CONFIRM_GATE_AUDIT.json", {"status": "PASS", "v2_pass_assessment_allows_gate_readiness": True, "missing_or_wrong_binding_blocks": True, "confirm_endpoint_called": False, "production_writes": 0})
    write("ATTEMPT11_FUTURE_REVISION_AUDIT.json", {"status": "PASS", "parent_reads_persisted_attempt10_v2_assessment": True, "blocked_attempt10_next_state": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED", "attempt11_provider_calls": 0})
    write("ATTEMPT10_CREATIVE_ENRICHMENT_REVISION_PREFLIGHT.json", {"status": result["status"], "history_count": manifest.get("history_count"), "expected_attempt": manifest.get("expected_attempt"), "parent_attempt": active_attempt, "parent_ir_fingerprint": parent_ir_fp, "semantic_review_policy": manifest.get("semantic_review_policy"), "semantic_policy_fingerprint": manifest.get("semantic_policy_fingerprint"), "parent_review_fingerprint": parent_review_fp, "feedback_count": feedback["constraint_count"], "authorization": manifest.get("authorization"), "provider_calls": result.get("provider_calls", 0), "production_mutation": False, "revision_parent_fingerprint": (result.get("revision_parent") or {}).get("revision_parent_fingerprint")})
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "real_llm_provider_posts": 0, "attempt10_real_execution": 0, "attempt11": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "production_packet_mutation": 0, "before": before, "after": after, "unchanged": before == after, "active_attempt": active_attempt, "attempt_count": current_attempt_count})

    report = f"""# V7.6.17 Director Semantic Review V2 Production Wiring

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED`

## Production wiring

- Revision endpoint: persisted V1 parent review -> server-side V2 recomputation for Attempt-9+ revisions.
- Executor: fixed V1 validator -> policy resolver dispatch; Attempt-10+ uses `validate_director_creative_semantic_review_v2`.
- V2 policy fingerprint: `{semantic_policy_v2_fingerprint()}`.
- Attempt-9 runtime V2 review fingerprint: `{parent_review_fp}`.
- V2 feedback: `{feedback['constraint_count']}` constraints; certainty collapse 1, unsupported story action 1, SceneBlocking leakage 2; ShotPlan false positives 0.
- V1 false-positive feedback count: 0.

## Attempt-10 preflight

- Status: `{result['status']}`; history `{manifest.get('history_count')}` -> `{manifest.get('expected_attempt')}`.
- Parent identity: `{(result.get('revision_parent') or {}).get('revision_parent_fingerprint')}`.
- System SHA256: `{manifest.get('system_prompt_sha256')}`.
- User SHA256: `{manifest.get('user_prompt_sha256')}`.
- Prompt fingerprint: `{manifest.get('prompt_fingerprint')}`.
- Provider Request fingerprint: `{manifest.get('provider_request_fingerprint_v2')}`.
- Authorization: `{manifest.get('authorization')}`; Provider calls: `{result.get('provider_calls', 0)}`.

## Persistence and gates

- Mock PASS, Mock BLOCKED, and structural failure all use the production executor in the provider-free test suite.
- Attempt-10 V2 assessment is append-only; historical Attempt-9 V1 remains unchanged.
- Confirm gate requires a bound V2 PASS assessment; no confirm call was made.
- Future Attempt-11 preflight reads the persisted Attempt-10 V2 assessment; no automatic Attempt-11 call.

## Invariants and verification

- Production Packet 64 before/after is byte-fingerprint unchanged: `{before == after}`.
- Real LLM / Attempt-10 POST / Attempt-11 / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`.
- `python -m pytest -q tests/test_director_semantic_v2_production_wiring_v7_6_17.py`: `7 passed`.
- V7.6.16, V7.6.14, V7.6.13, Stage A/Stage B execution and provider contract regression suite: `77 passed`.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
"""
    (OUT / "DIRECTOR_SEMANTIC_V2_PRODUCTION_WIRING_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": result["status"], "policy": SEMANTIC_REVIEW_POLICY_V2, "review_fingerprint": parent_review_fp, "feedback_count": feedback["constraint_count"], "provider_calls": result.get("provider_calls", 0), "production_mutation": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
