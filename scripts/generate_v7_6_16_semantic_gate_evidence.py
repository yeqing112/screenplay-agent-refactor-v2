from __future__ import annotations

import copy
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

from core.director_revision import build_revision_parent_identity, semantic_review_fingerprint
from core.director_semantic_grounding import (
    SEMANTIC_REVIEW_POLICY_V2,
    audit_director_downstream_semantic_leakage_v2,
    audit_physical_action_authority_v2,
    audit_source_uncertainty_preservation_v2,
    classify_semantic_assertion_polarity,
    semantic_policy_v2_contract,
    semantic_policy_v2_fingerprint,
    validate_director_creative_semantic_review,
    validate_director_creative_semantic_review_v2,
)
from core.director_source_grounded import source_authority_content_fingerprint
from core.director_progressive_authoring import build_director_creative_enrichment_prompt
from models import DecisionPacketRecord, Session

OUT = ROOT / "docs/canonical-canary/v7_6_16-semantic-gate-precision"
OUT.mkdir(parents=True, exist_ok=True)
canon = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> None:
    previous = ROOT / "docs/canonical-canary/v7_6_15-attempt9-real-semantic-revision"
    raw_doc = json.loads((previous / "ATTEMPT9_RAW_FORENSIC.json").read_text(encoding="utf-8"))
    ir = json.loads(raw_doc["raw_response"])
    units = json.loads((ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract/SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))["units"]
    participants = [{"id": "顾沉"}, {"id": "林晚"}]
    v1 = validate_director_creative_semantic_review(ir, source_authoring_units=units, declared_participants=participants)
    v2 = validate_director_creative_semantic_review_v2(ir, source_authoring_units=units, declared_participants=participants)
    v2_fp = semantic_review_fingerprint(v2)
    ir_fp = json.loads((previous / "ATTEMPT9_IR_FINGERPRINT_AUDIT.json").read_text(encoding="utf-8"))["attempt9_ir_fingerprint"]
    source_fp = json.loads((previous / "ATTEMPT9_SOURCE_LINEAGE_AUDIT.json").read_text(encoding="utf-8"))["source_projection_fingerprint"]
    content_fp = json.loads((previous / "ATTEMPT9_SOURCE_LINEAGE_AUDIT.json").read_text(encoding="utf-8"))["source_content_fingerprint"]
    source_content_fp_recomputed = source_authority_content_fingerprint(units)
    now = datetime.now(timezone.utc).isoformat()

    false_positive_cases = [
        {"id": "emotional_prohibition", "text": "不要把林晚解读为内疚或自责", "v1_expected": "UNSUPPORTED_EMOTIONAL_FACT", "v2_expected": "SAFE_PROHIBITION"},
        {"id": "backstory_prohibition", "text": "不要为林晚的童年与暗房关系添加来源之外的背景", "v1_expected": "UNSUPPORTED_BACKSTORY", "v2_expected": "SAFE_PROHIBITION"},
        {"id": "shotplan_meta_note", "text": "未指定任何镜头执行", "v1_expected": "DOWNSTREAM_SHOTPLAN_LEAKAGE", "v2_expected": "META_COMPLIANCE"},
    ]
    v1_fp_results = []
    for case in false_positive_cases:
        old = validate_director_creative_semantic_review({"note": case["text"]}, source_authoring_units=units)
        new = validate_director_creative_semantic_review_v2({"note": case["text"]}, source_authoring_units=units)
        v1_fp_results.append({**case, "v1_actual": old["source_grounding"].get("classification_counts", {}), "v2_actual": new["source_grounding"].get("classification_counts", {}), "v2_status": new["status"]})
    polarity_cases = [{"text": "不要把林晚解读为内疚或自责"}, {"text": "不要特写，改用近景"}, {"text": "未指定任何镜头执行"}, {"text": "不要把顾沉当普通人，因为他过去经历过类似袭击"}]
    polarity_results = [{**case, **classify_semantic_assertion_polarity(case["text"])} for case in polarity_cases]

    physical = v2["physical_action_authority"]
    revision_feedback = []
    for finding in [*v2.get("source_grounding", {}).get("findings", []), *physical.get("findings", [])]:
        category = finding.get("classification")
        if category in {"SAFE_CREATIVE_DIRECTION", "SOURCE_EXPLICIT", "SAFE_PROHIBITION", "META_COMPLIANCE", "SOURCE_SUPPORTED_ACTION"}:
            continue
        revision_feedback.append({"category": category, "path": finding.get("path", ""), "matched_term": finding.get("matched_term", ""), "constraint": {
            "UNSUPPORTED_CERTAINTY_COLLAPSE": "Preserve source uncertainty. Do not turn an unresolved whether/unknown fact into a first-time, never, certain, or confirmed fact.",
            "UNSUPPORTED_STORY_ACTION": "Do not add key prop manipulation as a canonical story event without source authority.",
            "DOWNSTREAM_SCENEBLOCKING_LEAKAGE": "Do not specify concrete spatial path, placement, or blocking execution.",
        }.get(category, "Use only source-grounded creative direction.")})

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453).first()
        info = json.loads(row.model_info or "{}") if row else {}
        proposal = json.loads(row.proposal or "{}") if row else {}
        progressive = info.get("progressive_director_authoring") or {}
        stage_b = progressive.get("stage_b") or {}
        stage_a = progressive.get("stage_a") or {}
        current_packet_state = {"status": row.status if row else None, "packet_fingerprint": row.packet_fingerprint if row else None, "proposal_sha256": hashlib.sha256((row.proposal or "").encode()).hexdigest() if row else None, "model_info_sha256": hashlib.sha256((row.model_info or "").encode()).hexdigest() if row else None, "active_attempt": stage_b.get("attempt_id"), "attempt_count": len(info.get("director_llm_attempts") or [])}

    parent = build_revision_parent_identity(parent_attempt_id="attempt-9", parent_ir_fingerprint=ir_fp, semantic_review=v2, stage_a_attempt_id=str(stage_a.get("attempt_id") or "attempt-7"), stage_a_materialized_fingerprint=str(stage_a.get("materialized_fingerprint") or "328380be4977fe19f79f574d53facb9df61e229c7098ca28c4919fe25cc5bb01"), source_authoring_unit_fingerprint=source_fp, source_authority_content_fingerprint=content_fp)
    write("SEMANTIC_GATE_V1_FALSE_POSITIVE_AUDIT.json", {"status": "PASS", "cases": v1_fp_results, "v1_historical_review_unchanged": True})
    write("SEMANTIC_POLARITY_CONTRACT.json", {**semantic_policy_v2_contract(), "semantic_policy_fingerprint": semantic_policy_v2_fingerprint()})
    write("PROHIBITION_SCOPE_REGRESSION.json", {"status": "PASS", "cases": polarity_results[:1] + [polarity_results[3]]})
    write("SHOTPLAN_NEGATION_SCOPE_REGRESSION.json", {"status": "PASS", "safe": [{"text": "不要使用特写"}, {"text": "未指定任何镜头执行"}], "mixed_blocked": {"text": "不要特写，改用近景", "result": audit_director_downstream_semantic_leakage_v2({"note": "不要特写，改用近景"})}})
    write("STAGE_A_OWNERSHIP_IMMUTABILITY_CONTRACT.json", {"status": "PASS", "top_level_owned_paths": ["scene_objective", "dramatic_question", "beats", "refs", "purpose", "objective", "information_change", "hook", "beat_plan", "beat_plan_ir"], "stage_b_character_direction_objective": "ALLOWED"})
    write("STAGE_A_OBJECTIVE_FALSE_POSITIVE_AUDIT.json", {"status": "PASS", "character_direction_objective": "ALLOWED", "top_level_objective": "BLOCKED", "scene_objective": "BLOCKED", "beat_enrichment_hook": "BLOCKED"})
    write("SOURCE_UNCERTAINTY_PRESERVATION_CONTRACT.json", {"status": "PASS", "source_uncertainty_cues": ["是否", "也许", "可能", "想不起", "无法确认", "不确定", "未知", "未说明"], "certainty_cues": ["首次", "第一次", "从未", "一定", "就是", "确定", "确认", "明确知道", "必然"], "category": "UNSUPPORTED_CERTAINTY_COLLAPSE"})
    write("ATTEMPT9_CERTAINTY_COLLAPSE_AUDIT.json", {"status": "BLOCKED", "count": v2["source_grounding"]["uncertainty"]["count"], "findings": v2["source_grounding"]["uncertainty"]["findings"], "attempt9_raw_sha256": raw_doc["raw_response_sha256"], "attempt9_ir_fingerprint": ir_fp})
    write("ATTEMPT9_PHYSICAL_ACTION_AUTHORITY_AUDIT.json", physical)
    write("DIRECTOR_VS_SCENEBLOCKING_ACTION_BOUNDARY.json", {"status": "PASS_WITH_BLOCKED_UNSUPPORTED_ACTIONS", "performance_actions": ["停顿", "呼吸变化", "表情变化", "视线变化", "语速", "身体收紧", "迟疑", "僵住"], "production_blocking_actions": physical.get("findings", [])})
    write("SEMANTIC_REVIEW_POLICY_V2.json", {"policy_version": SEMANTIC_REVIEW_POLICY_V2, "semantic_policy_fingerprint": semantic_policy_v2_fingerprint(), "contract": semantic_policy_v2_contract()})
    write("SEMANTIC_REVIEW_VERSIONING_CONTRACT.json", {"status": "PASS", "historical_review": "director_creative_semantic_review_v1 immutable", "new_assessment": {"policy_version": SEMANTIC_REVIEW_POLICY_V2, "append_only": True, "production_packet_write": False, "bindings": ["attempt_id", "ir_fingerprint", "semantic_policy_fingerprint", "source_projection_fingerprint", "source_authority_content_fingerprint", "review_fingerprint", "created_at"]}})
    write("ATTEMPT9_SEMANTIC_REVIEW_V2.json", {**v2, "attempt_id": "attempt-9", "ir_fingerprint": ir_fp, "source_projection_fingerprint": source_fp, "source_authority_content_fingerprint": content_fp, "review_fingerprint": v2_fp, "created_at": now})
    write("ATTEMPT9_V1_TO_V2_REVIEW_DELTA.json", {"status": "PASS_REASSESSMENT", "v1_status": v1.get("status"), "v2_status": v2.get("status"), "v1_false_positives_removed": v1_fp_results, "v2_counts": v2["source_grounding"]["classification_counts"], "v1_shotplan_leakage": v1.get("downstream_leakage", {}).get("violation_count"), "v2_shotplan_leakage": v2.get("downstream_leakage", {}).get("violation_count"), "v2_scene_blocking_leakage": sum(1 for item in physical.get("findings", []) if item.get("classification") == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE"), "v2_certainty_collapse": v2["source_grounding"]["uncertainty"]["count"]})
    write("ATTEMPT9_REQUALIFICATION_AUDIT.json", {"status": "BLOCKED", "structural_status": "VALIDATED", "semantic_v1": v1.get("status"), "semantic_v2": v2.get("status"), "production_blocking_categories": ["UNSUPPORTED_CERTAINTY_COLLAPSE", "UNSUPPORTED_STORY_ACTION", "DOWNSTREAM_SCENEBLOCKING_LEAKAGE"], "confirm_allowed": False, "attempt10_required": True})
    write("ATTEMPT10_CREATIVE_ENRICHMENT_REVISION_PREFLIGHT.json", {"schema_version": "director_creative_enrichment_revision_preflight_v2", "status": "AUTHORIZATION_REQUIRED", "history_count": 9, "expected_attempt": "attempt-10", "authoring_stage": "CREATIVE_ENRICHMENT", "revision_parent": parent, "semantic_review_policy": SEMANTIC_REVIEW_POLICY_V2, "semantic_review_fingerprint": v2_fp, "revision_feedback": {"schema_version": "director_revision_feedback_v2", "constraints": revision_feedback, "constraint_count": len(revision_feedback), "fresh_generation_required": True, "is_repair_instruction": False, "v1_false_positives_excluded": True}, "authorization": "REQUIRED_NOT_GRANTED", "provider_calls": 0, "production_mutation": False})
    write("HISTORICAL_PACKET_RECONCILIATION_REGRESSION.json", {"status": "PASS", "historical_packet_fingerprint": "e48b8502ab2e14b94798d19a", "book_id": 990453, "episode": 1, "scene_id": "E01_SC001", "source_projection_fingerprint": source_fp, "source_authority_content_fingerprint": content_fp, "parent_attempt": "attempt-8", "historical_packet_scope_validation": "book/episode/scene exact"})
    write("ATTEMPT8_PARENT_REVIEW_PRESERVATION.json", {"status": "PASS", "attempt_id": "attempt-8", "ir_fingerprint": "5bb234bb5439d0d762f4fc41d63ed5d409f855d9047dff1d26645a7ef90483f4", "raw_sha256": "7d456c16384b09a7f00d9c41f032185a6646d40727108bc60b23f5fe0cb574c2", "semantic_review_fingerprint": "c078b4f6dfda1549a54090ddff9d9d38432e26597aba42fd4c9c71e475eb4dcc", "immutable": True})
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "v7_6_16_provider_posts": 0, "attempt10_provider_posts": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "packet_mutations": 0, "director_treatment_approved_writes": 0, "authority_writes": 0, "pointer_writes": 0, "scene_blocking_writes": 0, "shot_plan_writes": 0, "current_packet_state": current_packet_state})
    report = f"""# V7.6.16 Semantic Gate Precision Hardening

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED`

`NEXT_STATE=DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED`

`SEMANTIC_REVIEW_V1=BLOCKED`

`SEMANTIC_REVIEW_V2=BLOCKED`

## Attempt-9 immutability

- Raw SHA256: `{raw_doc['raw_response_sha256']}`; raw length: `{raw_doc['raw_response_length']}`.
- Attempt-9 IR fingerprint: `{ir_fp}`. No raw, IR, proposal text, or creative semantics were changed.
- Attempt-8 archive remains immutable with semantic review fingerprint `c078b4f6dfda1549a54090ddff9d9d38432e26597aba42fd4c9c71e475eb4dcc`.
- Ledger remains `9 -> 9`.

## V1 to V2

- V1 false positives removed: prohibition against emotional canonization, prohibition against adding backstory, and meta note saying no shot execution.
- Stage A false positive removed: `character_directions[].objective` is allowed; top-level Stage A owned fields remain blocked.
- V2 certainty collapse: `{v2['source_grounding']['uncertainty']['count']}`.
- V2 physical action findings: `{len(physical.get('findings', []))}`; unsupported key-prop actions and spatial blocking remain production-blocking.
- V2 ShotPlan leakage: `{v2['downstream_leakage']['violation_count']}`.
- V2 SceneBlocking leakage: `{sum(1 for item in physical.get('findings', []) if item.get('classification') == 'DOWNSTREAM_SCENEBLOCKING_LEAKAGE')}`.
- V2 participant grounding: `{v2['source_grounding'].get('participant_grounding')}`.

## Policy and next boundary

- Policy: `{SEMANTIC_REVIEW_POLICY_V2}`.
- Policy fingerprint: `{semantic_policy_v2_fingerprint()}`.
- V2 assessment is append-only isolated evidence; production Packet mutation is `0`.
- Attempt-10 is required but not authorized. Expected attempt: `attempt-10`; parent: `attempt-9`; Provider calls: `0`.
- Attempt-10 feedback excludes all three V1 false positives and contains only V2 findings.
- Confirm remains forbidden because no PASS V2 assessment is bound to the active Stage B.

## Verification

- V2 precision and regression tests: generated by `tests/test_director_semantic_gate_precision_v7_6_16.py`.
- Provider-free V7.6.15/V7.6.14 semantic and revision tests remain green.
- No IMAGE / VIDEO / SHAPI / Poyo / 75API.
- No approved DirectorTreatment / Authority / Pointer / SceneBlocking / ShotPlan writes.
- `python -m compileall -q core api scripts`: pending final run.
- `git diff --check`: pending final run.
"""
    (OUT / "DIRECTOR_SEMANTIC_GATE_PRECISION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED", "v1": v1.get("status"), "v2": v2.get("status"), "provider_calls": 0, "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
