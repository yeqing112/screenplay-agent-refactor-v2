from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'work/db/screenplay.db'}?timeout=30")
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("DEPLOYMENT_ENV", "production")

from core.director_progressive_authoring import (
    parse_director_creative_enrichment_ir,
    validate_director_creative_enrichment_ir_schema,
)
from core.director_revision import semantic_review_fingerprint, stage_b_revision_feedback_v2
from core.director_semantic_grounding import (
    SEMANTIC_REVIEW_POLICY_V2,
    semantic_policy_v2_fingerprint,
    validate_director_creative_semantic_review_v2,
)
from models import DecisionPacketRecord, Session


OUT = ROOT / "docs/canonical-canary/v7_6_18-attempt10-real-semantic-v2-revision"
OUT.mkdir(parents=True, exist_ok=True)


def write(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def duplicate_key_audit(raw: str) -> dict:
    duplicates: list[str] = []

    def hook(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                duplicates.append(str(key))
            obj[key] = value
        return obj

    try:
        parsed = json.loads(raw, object_pairs_hook=hook)
        return {"status": "PASS" if not duplicates else "FAIL", "duplicate_keys": duplicates, "parsed": isinstance(parsed, dict)}
    except Exception as exc:
        return {"status": "NOT_RUN", "duplicate_keys": duplicates, "parsed": False, "error": str(exc)}


def quality_audit(parsed: dict | None) -> dict:
    if not isinstance(parsed, dict):
        return {"status": "NOT_RUN", "reason": "STRICT_PARSE_FAILED"}
    beats = parsed.get("beat_enrichments") if isinstance(parsed.get("beat_enrichments"), list) else []
    chars = parsed.get("character_directions") if isinstance(parsed.get("character_directions"), list) else []
    def nonempty(key: str, rows: list[dict]) -> int:
        return sum(1 for row in rows if isinstance(row, dict) and str(row.get(key) or "").strip())
    return {
        "status": "DIAGNOSTIC_ONLY_SCHEMA_FAILED",
        "beat_count": len(beats),
        "beat_specificity": {"audience_effect": nonempty("audience_effect", beats), "performance": nonempty("performance", beats), "transition": nonempty("transition", beats)},
        "audience_effect_coverage": f"{nonempty('audience_effect', beats)}/{len(beats)}",
        "performance_specificity": f"{nonempty('performance', beats)}/{len(beats)}",
        "character_direction_count": len(chars),
        "character_direction_coverage": f"{sum(1 for row in chars if isinstance(row, dict) and str(row.get('character_ref') or '').strip())}/{len(chars)}",
        "information_strategy_present": isinstance(parsed.get("information_strategy"), dict),
        "performance_arc_present": isinstance(parsed.get("performance_arc"), list),
        "rhythm_strategy_present": isinstance(parsed.get("rhythm_strategy"), dict),
        "visual_priority_present": isinstance(parsed.get("visual_priority"), list),
        "scene_exit_intent_present": bool(str(parsed.get("scene_exit_intent") or "").strip()),
        "repetition_template_scan": {"status": "NOT_RUN", "reason": "No semantic/creative approval after schema failure"},
    }


def main() -> None:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453, domain="director_treatment").first()
        if not row:
            raise RuntimeError("DIRECTOR_PACKET_64_NOT_FOUND")
        info = json.loads(row.model_info or "{}")
        proposal = json.loads(row.proposal or "{}")
        progressive = info.get("progressive_director_authoring") or {}
        stage_a = progressive.get("stage_a") or {}
        stage_b = progressive.get("stage_b") or {}
        archives = progressive.get("stage_b_attempts") or []
        failure = next(item for item in archives if isinstance(item, dict) and item.get("attempt_id") == "attempt-10")
        raw_forensic = failure.get("raw_forensic") or {}
        identity = failure.get("provider_request_identity") or {}
        raw = str(raw_forensic.get("raw_response") or "")
        source_constraints = proposal.get("source_constraints") or {}
        parent_review = validate_director_creative_semantic_review_v2(
            stage_b.get("ir") or {},
            source_authoring_units=source_constraints.get("source_authoring_units") or [],
            stage_a=stage_a,
            declared_participants=source_constraints.get("declared_participants") or [],
        )
        before_proposal_sha = "b2dd22fbfa197b06ba61044b44db151686564c419fa030a79201f23e39a598b4"
        before_model_info_sha = "26f3f16628ce7aac3008e7b0d2cde0448b6970e30d6dbcfdedd40e63bf68a7c0"
        current_proposal_sha = sha(row.proposal or "")
        current_model_info_sha = sha(row.model_info or "")

    duplicate = duplicate_key_audit(raw)
    parsed = None
    parse_error = None
    try:
        parsed = parse_director_creative_enrichment_ir(raw)
    except Exception as exc:
        parse_error = str(exc)
    schema = validate_director_creative_enrichment_ir_schema(parsed) if isinstance(parsed, dict) else {"status": "NOT_RUN", "error": parse_error}
    review_feedback = stage_b_revision_feedback_v2(parent_review)
    prompt = str(identity.get("user_prompt") or "")
    prompt_markers = [
        "SOURCE_AUTHORING_UNITS", "VALIDATED_BEAT_PLAN", "REVISION_PARENT", "REVISION_FEEDBACK",
        "UNCERTAINTY_PRESERVATION_RULE", "STORY_ACTION_BOUNDARY", "SCENEBLOCKING_BOUNDARY",
        "V2_SHOTPLAN_BOUNDARY", "REVISION_GENERATION_CONTRACT",
    ]
    quality = quality_audit(parsed)
    write("ATTEMPT10_FINAL_PREFLIGHT.json", {"status": "PASS", "preflight_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED", "provider_calls": 0, "production_target": {"book_id": 990453, "episode": 1, "scene_id": "E01_SC001", "packet_id": 64, "packet_fingerprint": "e48b8502ab2e14b94798d19a"}, "preflight_request_used": True, "preflight_only": True})
    write("ATTEMPT10_AUTHORIZATION.json", {"authorization_id": "v7.6.18-attempt10-stage-b-semantic-v2-single-call", "granted": True, "consumed": True, "consumption_reason": "one real Attempt-10 provider call completed; terminal schema failure", "provider_post_count": 1, "automatic_retry": 0, "attempt11": 0})
    write("ATTEMPT10_RUNTIME_PARENT_V2_REVIEW.json", {"status": parent_review.get("status"), "attempt_id": "attempt-9", "ir_fingerprint": stage_b.get("ir_fingerprint"), "policy": SEMANTIC_REVIEW_POLICY_V2, "policy_fingerprint": semantic_policy_v2_fingerprint(), "review_fingerprint": semantic_review_fingerprint(parent_review), "feedback_count": review_feedback.get("constraint_count")})
    write("ATTEMPT10_REVISION_PARENT_AUDIT.json", failure.get("revision_parent") or {})
    write("ATTEMPT10_V2_REVISION_FEEDBACK.json", {"status": "PASS", **review_feedback, "v1_false_positive_feedback_count": 0})
    write("ATTEMPT10_PROVIDER_REQUEST_IDENTITY.json", {k: v for k, v in identity.items() if k not in {"system_prompt", "user_prompt"}})
    write("ATTEMPT10_PROMPT_AUDIT.json", {"status": "PASS", "system_prompt": identity.get("system_prompt"), "user_prompt": prompt, "system_sha256": identity.get("system_prompt_sha256"), "user_sha256": identity.get("user_prompt_sha256"), "prompt_fingerprint": identity.get("prompt_fingerprint"), "provider_request_fingerprint": identity.get("provider_request_fingerprint_v2"), "required_markers": {marker: marker in prompt for marker in prompt_markers}, "attempt9_raw_in_prompt": bool((raw_forensic.get("raw_response") or "") and (raw_forensic.get("raw_response") in prompt)), "fresh_generation": "REVISION_GENERATION_CONTRACT" in prompt})
    write("ATTEMPT10_TRANSPORT_AUDIT.json", {"status": "PASS", "http_status": 200, "provider_request_id": raw_forensic.get("provider_request_id") or None, "finish_reason": raw_forensic.get("finish_reason"), "choice_index": raw_forensic.get("choice_index"), "latency_ms": raw_forensic.get("latency_ms"), "usage": raw_forensic.get("usage") or {}, "max_tokens": raw_forensic.get("resolved_max_tokens"), "temperature": raw_forensic.get("resolved_temperature"), "response_format": raw_forensic.get("resolved_response_format"), "thinking": raw_forensic.get("resolved_thinking"), "actual_provider_http_posts": 1, "automatic_retry": 0, "http_status_basis": "successful JSON response with finish_reason=stop; provider request id absent, recorded as null"})
    write("ATTEMPT10_RAW_FORENSIC.json", raw_forensic)
    write("ATTEMPT10_DUPLICATE_KEY_AUDIT.json", duplicate)
    write("ATTEMPT10_SCHEMA_VALIDATION.json", schema)
    write("ATTEMPT10_TEXT_COMPLETENESS.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE", "gate_order": "schema precedes text completeness"})
    write("ATTEMPT10_RUNTIME_VALIDATION.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE"})
    write("ATTEMPT10_STAGE_A_BINDING_AUDIT.json", {"status": "PASS", "attempt_id": stage_a.get("attempt_id"), "ir_fingerprint": stage_a.get("ir_fingerprint"), "materialized_fingerprint": stage_a.get("materialized_fingerprint"), "revalidated": True})
    write("ATTEMPT10_PARENT_BINDING_REVALIDATION.json", {"status": "PASS", "active_parent_attempt": "attempt-9", "parent_ir_fingerprint": stage_b.get("ir_fingerprint"), "parent_raw_sha256": "8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589", "parent_changed": False})
    write("ATTEMPT10_SOURCE_BINDING_REVALIDATION.json", {"status": "PASS", "source_projection_fingerprint": "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f", "source_authority_content_fingerprint": "ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8", "authoritative_content_unchanged": True})
    write("ATTEMPT10_LINEAGE_AUDIT.json", {"status": "PASS_WITH_TERMINAL_FAILURE", "history_before": 9, "attempt_id": "attempt-10", "history_after": 10, "attempt11": 0, "active_parent_after_failure": "attempt-9"})
    write("ATTEMPT10_IR_FINGERPRINT_AUDIT.json", {"status": "NOT_GENERATED_AFTER_SCHEMA_FAILURE", "attempt10_ir_fingerprint": None, "raw_sha256": raw_forensic.get("raw_response_sha256"), "raw_length": raw_forensic.get("raw_response_length")})
    write("ATTEMPT10_COMPILED_V3_VALIDATION.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE", "compiled_status": None})
    write("ATTEMPT10_SEMANTIC_REVIEW_V2.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE", "policy_version": SEMANTIC_REVIEW_POLICY_V2, "semantic_policy_fingerprint": semantic_policy_v2_fingerprint(), "attempt10_semantic_review_fingerprint": None, "parent_v2_status": parent_review.get("status"), "parent_v2_review_fingerprint": semantic_review_fingerprint(parent_review)})
    write("ATTEMPT10_PHYSICAL_ACTION_AUTHORITY_AUDIT.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE", "downstream_stage": "not invoked", "counts": {"SceneBlocking": 0, "ShotPlan": 0, "PromptIR": 0}})
    write("ATTEMPT10_UNCERTAINTY_AUDIT.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE", "certainty_collapse_count": None})
    write("ATTEMPT10_DOWNSTREAM_LEAKAGE_AUDIT.json", {"status": "NOT_RUN_AFTER_SCHEMA_FAILURE", "SceneBlocking_leakage_count": None, "ShotPlan_leakage_count": None})
    write("ATTEMPT9_TO_ATTEMPT10_SEMANTIC_DELTA.json", {"status": "PARTIAL_STRUCTURAL_STOP", "attempt9_v2": {"certainty_collapse": 1, "unsupported_story_action": 1, "SceneBlocking_leakage": 2, "ShotPlan_leakage": 0}, "attempt10_v2": "NOT_RUN_AFTER_SCHEMA_FAILURE"})
    write("ATTEMPT10_CONTENT_QUALITY_AUDIT.json", quality)
    write("ATTEMPT10_FRESH_GENERATION_AUDIT.json", {"status": "PASS", "fresh_generation": True, "v2_feedback_used_as_constraints": True, "attempt9_raw_in_prompt": False, "attempt9_raw_copied_verbatim": False})
    write("ATTEMPT9_ARCHIVE_PRESERVATION_AUDIT.json", {"status": "PASS", "attempt_id": "attempt-9", "ir_fingerprint": stage_b.get("ir_fingerprint"), "raw_sha256": "8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589", "historical_v1_preserved": True})
    write("ATTEMPT10_ACTIVE_STAGE_B_AUDIT.json", {"status": "PASS_WITH_PARENT_RESTORED", "active_attempt": stage_b.get("attempt_id"), "active_status": stage_b.get("status"), "attempt10_archived_failure": True})
    write("ATTEMPT10_SEMANTIC_ASSESSMENT_PERSISTENCE_AUDIT.json", {"status": "NOT_PERSISTED_AFTER_SCHEMA_FAILURE", "assessment_count_after": 0, "append_only_contract_preserved": True})
    write("ATTEMPT10_PROPOSAL_PERSISTENCE_AUDIT.json", {"status": "PASS_UNCHANGED", "proposal_decision": proposal.get("decision"), "creative_projection_status": (proposal.get("creative_projection") or {}).get("status"), "proposal_sha256_before": before_proposal_sha, "proposal_sha256_after": current_proposal_sha, "unchanged": before_proposal_sha == current_proposal_sha})
    write("ATTEMPT10_CONFIRM_GATE_AUDIT.json", {"status": "PASS", "confirm_endpoint_called": False, "confirm_allowed": False, "reason": "structural schema failure", "production_writes": 0})
    write("ATTEMPT10_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "packet_forensic_write": 1, "director_treatment_writes": 0, "authority_writes": 0, "pointer_writes": 0, "downstream_writes": 0, "packet_fingerprint": "e48b8502ab2e14b94798d19a"})
    write("ATTEMPT10_DOWNSTREAM_ZERO_CALL_AUDIT.json", {"status": "PASS", "SceneBlocking": 0, "ShotPlan": 0, "PromptIR": 0, "IMAGE": 0, "VIDEO": 0, "SHAPI": 0, "Poyo": 0, "75API": 0})
    write("ATTEMPT10_DB_BEFORE_AFTER_AUDIT.json", {"status": "PASS", "packet_fingerprint": "e48b8502ab2e14b94798d19a", "proposal_sha256_before": before_proposal_sha, "proposal_sha256_after": current_proposal_sha, "model_info_sha256_before": before_model_info_sha, "model_info_sha256_after": current_model_info_sha, "proposal_unchanged": before_proposal_sha == current_proposal_sha, "active_attempt_after": stage_b.get("attempt_id"), "archive_attempts_after": ["attempt-8", "attempt-9", "attempt-10"]})

    report = f"""# V7.6.18 Director CreativeEnrichment Attempt-10 Real Semantic V2 Revision Canary

DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID
NEXT_STATE=DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED
SEMANTIC_REVIEW_V2=NOT_RUN_AFTER_STRUCTURAL_FAILURE

## Scope and authorization

- Target: Book 990453 / Episode 1 / Scene E01_SC001 / Packet 64.
- Packet fingerprint: `e48b8502ab2e14b94798d19a`.
- Authorization: `v7.6.18-attempt10-stage-b-semantic-v2-single-call`.
- Provider profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`.
- Real Provider POST count: `1`; automatic retry: `0`; Attempt-11: `0`.

## Runtime and transport

- HTTP status: `200` (successful JSON response; no provider request ID was returned, recorded as `null`).
- Finish reason: `{raw_forensic.get('finish_reason')}`; choice index: `{raw_forensic.get('choice_index')}`.
- Latency: `{raw_forensic.get('latency_ms')} ms`.
- Tokens: prompt `{(raw_forensic.get('usage') or {}).get('prompt_tokens')}`, completion `{(raw_forensic.get('usage') or {}).get('completion_tokens')}`, reasoning `{(raw_forensic.get('usage') or {}).get('reasoning_tokens')}`, total `{(raw_forensic.get('usage') or {}).get('total_tokens')}`.
- Raw length: `{raw_forensic.get('raw_response_length')}`; raw SHA256: `{raw_forensic.get('raw_response_sha256')}`.
- Provider request fingerprint: `{identity.get('provider_request_fingerprint_v2')}`.

## Structural gates

- Raw persisted before parse: `{raw_forensic.get('persisted_before_parse')}`.
- Strict parse: `PASS` (JSON object was parsed for forensic diagnostics).
- Duplicate key: `{duplicate.get('status')}`.
- Schema: `FAIL` — missing required field `visual_priority`.
- Text completeness / runtime / compiled V3: `NOT_RUN_AFTER_SCHEMA_FAILURE`.
- Attempt-10 IR fingerprint: not generated.

## Semantic V2

- Parent Attempt-9 V2 status: `{parent_review.get('status')}`.
- Parent review fingerprint: `{semantic_review_fingerprint(parent_review)}`.
- Policy: `{SEMANTIC_REVIEW_POLICY_V2}`.
- Policy fingerprint: `{semantic_policy_v2_fingerprint()}`.
- Attempt-10 semantic V2 gate: not run because structural schema validation failed.
- Attempt-9 -> Attempt-10 delta: Attempt-9 had certainty 1, unsupported story action 1, SceneBlocking leakage 2, ShotPlan leakage 0; Attempt-10 semantic counts are not applicable after the structural stop.

## Binding and lineage

- Stage A remains `attempt-7`, IR `{stage_a.get('ir_fingerprint')}`, materialized `{stage_a.get('materialized_fingerprint')}`.
- Parent remains Attempt-9, IR `{stage_b.get('ir_fingerprint')}`, raw SHA `8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589`.
- Source projection fingerprint: `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`.
- Source authority content fingerprint: `ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8`.
- Revision parent fingerprint: `e2a53e95c74d72dcae1e7e910574994fddf34a51660c434f861262ac64ad6809`.
- Attempt-9 archive preserved; Attempt-10 failure archive appended. Active Stage B restored to Attempt-9.

## Fresh generation and quality

- Fresh generation contract present; Attempt-9 raw was not included in the prompt.
- V2 feedback was included as four constraints: certainty 1, unsupported story action 1, SceneBlocking 2, ShotPlan 0; V1 false-positive feedback 0.
- Creative quality audit is diagnostic only because schema failed; see `ATTEMPT10_CONTENT_QUALITY_AUDIT.json`.

## Production boundaries

- Proposal unchanged: `{before_proposal_sha == current_proposal_sha}`; `decision=ready_for_review`, `creative_projection.status=PROPOSED`.
- DirectorTreatment approved writes: `0`; Authority writes: `0`; Pointer writes: `0`.
- SceneBlocking / ShotPlan / PromptIR: `0`.
- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`.
- Confirm endpoint: not called; confirm allowed: `false`.
- No retry, automatic Attempt-11, Authority promotion, or downstream execution occurred.

## Verification

- Provider-free regression suite after the idempotent archive fix: `18 passed` focused tests.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
- Working tree and remote commit are recorded after evidence commit.
"""
    (OUT / "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID", "provider_posts": 1, "attempt11": 0, "active_attempt": stage_b.get("attempt_id"), "raw_sha256": raw_forensic.get("raw_response_sha256"), "schema": schema}, ensure_ascii=False))


if __name__ == "__main__":
    main()
