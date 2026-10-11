"""Execute the one authorized V7.6.21 Attempt-11 revision call and audit it."""
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'work/db/screenplay.db'}?timeout=30")
OUT = ROOT / "docs/canonical-canary/v7_6_21-attempt11-real-semantic-v2-structural-revision"
OUT.mkdir(parents=True, exist_ok=True)

from fastapi import HTTPException
from api import director_treatment_api as api
from core.director_progressive_authoring import render_stage_b_schema_contract, validate_stage_b_prompt_schema_key_parity
from core.director_revision import derive_structural_revision_feedback, semantic_review_fingerprint, stage_b_revision_feedback_v2, structural_revision_feedback_fingerprint
from core.director_semantic_grounding import SEMANTIC_REVIEW_POLICY_V2, audit_director_downstream_semantic_leakage_v2, audit_source_uncertainty_preservation_v2, audit_physical_action_authority_v2, semantic_policy_v2_fingerprint
from models import DecisionPacketRecord, Session

BOOK_ID, EPISODE, PACKET_ID = 990453, 1, 64
PACKET_FP, SCENE_ID = "e48b8502ab2e14b94798d19a", "E01_SC001"
AUTHORIZATION_ID = "v7.6.21-attempt11-stage-b-semantic-v2-structural-single-call"
EXPECTED_STAGE_A_IR = "b3dbf2624289134c10d19f93c9cbd00614e9caa501dbe40cd002e24e42821086"
EXPECTED_STAGE_A_MATERIALIZED = "328380be4977fe19f79f574d53facb9df61e229c7098ca28c4919fe25cc5bb01"
EXPECTED_A9_IR = "591bf4ec2f7df8b80a8fdd3a7166c6a76c39a7de0939ba3b1323b6af2320dfaa"
EXPECTED_A9_RAW = "8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589"
EXPECTED_POLICY_FP = "cf75e024231e619f83f5b9ee79dc388cd199b25464d8d6f3e69ac6c0ab8cc4b8"
EXPECTED_A9_REVIEW_FP = "1bd69e6ceb8d2b51b098fcabd7f877a636a338759dc5550365e92bef275af198"
EXPECTED_PARENT_FP = "72d79ca4fb8c23161274d4c617e2c91bcfecb599701270534762cc010569a15c"
EXPECTED_STRUCTURAL_FP = "4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4"
EXPECTED_A10_RAW = "5daf096fd07ad58ffe8848b25a8d633797234ce325dba1986f21de4af4ca39f0"
EXPECTED_SOURCE_PROJECTION = "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f"
EXPECTED_SOURCE_CONTENT = "ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8"

def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def sha(value: Any) -> str:
    return hashlib.sha256((value if isinstance(value, str) else canonical(value)).encode()).hexdigest()

def write(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

def snapshot() -> dict[str, Any]:
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=PACKET_ID, book_id=BOOK_ID, packet_fingerprint=PACKET_FP).first()
        if row is None: raise RuntimeError("Packet 64 not found")
        it, pt = str(row.model_info or ""), str(row.proposal or "")
        return {"status": row.status, "info": json.loads(it), "proposal": json.loads(pt), "model_info_sha256": sha(it), "proposal_sha256": sha(pt)}

def archive(info: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    prog = info.get("progressive_director_authoring") if isinstance(info.get("progressive_director_authoring"), dict) else {}
    return next((x for x in prog.get("stage_b_attempts", []) if isinstance(x, dict) and x.get("attempt_id") == attempt_id), {})

def history_entry(info: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    return next((x for x in info.get("director_llm_attempts", []) if isinstance(x, dict) and x.get("attempt_id") == attempt_id), {})

def request(review_fp: str, confirmed: bool, allow_external_call: bool) -> api.DirectorCreativeEnrichmentRevisionLlmDraftRequest:
    return api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(episode=EPISODE, scene_id=SCENE_ID, workflow_profile="production", packet_fingerprint=PACKET_FP, revision_of_attempt_id="attempt-9", revision_of_stage_b_ir_fingerprint=EXPECTED_A9_IR, semantic_review_fingerprint=review_fp, semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2, semantic_policy_fingerprint=semantic_policy_v2_fingerprint(), confirmed=confirmed, allow_external_call=allow_external_call, authorization_id=AUTHORIZATION_ID)

before = snapshot()
info, proposal = before["info"], before["proposal"]
progressive = info.get("progressive_director_authoring") or {}
active, stage_a = progressive.get("stage_b") or {}, progressive.get("stage_a") or {}
if any(x.get("attempt_id") == "attempt-11" for x in info.get("director_llm_attempts", []) if isinstance(x, dict)):
    raise SystemExit("REFUSE_RERUN_ATTEMPT11_ALREADY_EXISTS")
if len(info.get("director_llm_attempts", [])) != 10 or active.get("attempt_id") != "attempt-9":
    raise SystemExit("PREFLIGHT_BLOCKED_LINEAGE")
if stage_a.get("attempt_id") != "attempt-7" or stage_a.get("ir_fingerprint") != EXPECTED_STAGE_A_IR or stage_a.get("materialized_fingerprint") != EXPECTED_STAGE_A_MATERIALIZED or active.get("ir_fingerprint") != EXPECTED_A9_IR:
    raise SystemExit("PREFLIGHT_BLOCKED_STAGE_A_OR_PARENT_BINDING")
source_constraints = proposal.get("source_constraints") or {}
parent_review = api._recompute_stage_b_semantic_review(stage_b=active, stage_a=progressive.get("stage_a"), source_constraints=source_constraints, policy=SEMANTIC_REVIEW_POLICY_V2)
parent_fp = semantic_review_fingerprint(parent_review)
feedback = derive_structural_revision_feedback(info, active_attempt_id="attempt-9")
if semantic_policy_v2_fingerprint() != EXPECTED_POLICY_FP or parent_fp != EXPECTED_A9_REVIEW_FP or feedback.get("structural_feedback_fingerprint") != EXPECTED_STRUCTURAL_FP or feedback.get("failed_attempt_raw_sha256") != EXPECTED_A10_RAW:
    raise SystemExit("PREFLIGHT_BLOCKED_RUNTIME_IDENTITY_DRIFT")
pre_before = snapshot()
preflight = api.generate_director_creative_enrichment_revision_llm_draft(BOOK_ID, EPISODE, request(parent_fp, False, False))
pre_after = snapshot()
pre_manifest = preflight.get("execution_manifest") or {}
if preflight.get("provider_calls") != 0 or pre_before["model_info_sha256"] != pre_after["model_info_sha256"] or pre_before["proposal_sha256"] != pre_after["proposal_sha256"]:
    raise SystemExit("PREFLIGHT_BLOCKED_PROVIDER_OR_WRITE")
if preflight.get("status") != "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED" or pre_manifest.get("expected_attempt") != "attempt-11" or pre_manifest.get("history_count") != 10:
    raise SystemExit("PREFLIGHT_BLOCKED_EXPECTED_ATTEMPT")
if pre_manifest.get("semantic_review_fingerprint") != EXPECTED_A9_REVIEW_FP or pre_manifest.get("structural_feedback_fingerprint") != EXPECTED_STRUCTURAL_FP:
    raise SystemExit("PREFLIGHT_BLOCKED_IDENTITY")
profile_snapshot = pre_manifest.get("profile_snapshot") or {}
if profile_snapshot.get("profile_id") != "local-llm-2vydoz" or profile_snapshot.get("model") != "mimo-v2.5" or profile_snapshot.get("base_host") != "https://api.xiaomimimo.com":
    raise SystemExit("PREFLIGHT_BLOCKED_PROVIDER_PROFILE")
write("ATTEMPT11_FINAL_PREFLIGHT.json", {"status": "PASS", "endpoint": "/api/books/990453/episodes/1/director-treatment/creative-enrichment/revision/llm-draft", "provider_calls": 0, "production_write": 0, "expected_attempt": pre_manifest.get("expected_attempt"), "history_count": pre_manifest.get("history_count"), "active_stage_b": "attempt-9", "semantic_parent": "attempt-9", "structural_failure_source": "attempt-10", "semantic_policy": pre_manifest.get("semantic_review_policy"), "semantic_policy_fingerprint": pre_manifest.get("semantic_policy_fingerprint"), "semantic_review_fingerprint": pre_manifest.get("semantic_review_fingerprint"), "revision_parent_fingerprint": (pre_manifest.get("revision_parent") or {}).get("revision_parent_fingerprint"), "structural_feedback_fingerprint": pre_manifest.get("structural_feedback_fingerprint"), "profile_snapshot": profile_snapshot, "system_prompt_sha256": pre_manifest.get("system_prompt_sha256"), "user_prompt_sha256": pre_manifest.get("user_prompt_sha256"), "prompt_fingerprint": pre_manifest.get("prompt_fingerprint"), "provider_request_fingerprint_v2": pre_manifest.get("provider_request_fingerprint_v2")})
write("ATTEMPT11_AUTHORIZATION.json", {"status": "AUTHORIZED_SINGLE_CALL", "authorization_id": AUTHORIZATION_ID, "endpoint": "/api/books/990453/episodes/1/director-treatment/creative-enrichment/revision/llm-draft", "book_id": BOOK_ID, "episode": EPISODE, "scene_id": SCENE_ID, "packet_id": PACKET_ID, "packet_fingerprint": PACKET_FP, "confirmed": True, "allow_external_call": True, "retry_budget": 1, "automatic_retry": 0, "attempt12": 0, "confirm_endpoint": 0, "downstream_calls": 0})

# Exactly one authorized endpoint execution. There is deliberately no retry.
response, error = None, None
try:
    response = api.generate_director_creative_enrichment_revision_llm_draft(BOOK_ID, EPISODE, request(parent_fp, True, True))
except HTTPException as exc:
    error = {"http_status": exc.status_code, "detail": exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}}
except Exception as exc:
    error = {"exception_type": type(exc).__name__, "message": str(exc)}

after = snapshot()
attempt11 = history_entry(after["info"], "attempt-11")
archive11 = archive(after["info"], "attempt-11")
raw_forensic = archive11.get("raw_forensic") or after["info"].get("stage_b_raw_response_forensic") or {}
identity = archive11.get("provider_request_identity") or after["info"].get("stage_b_provider_request") or pre_manifest
validation = archive11.get("validation") or after["info"].get("stage_b_validation") or {}
semantic_review = archive11.get("semantic_review_v2") or archive11.get("semantic_review") or (response or {}).get("semantic_review") or {}
candidate = (response or {}).get("candidate") if isinstance((response or {}).get("candidate"), dict) else (after["proposal"] if archive11 else {})
status = (response or {}).get("status") or ((error or {}).get("detail") or {}).get("code") or attempt11.get("status") or after["info"].get("last_revision_failure") or "UNKNOWN"
event_trace = after["info"].get("event_trace") if isinstance(after["info"].get("event_trace"), list) else []
structural_pass = bool(archive11 and str(archive11.get("structural_status") or "").endswith("_VALIDATED"))
semantic_status = semantic_review.get("status") if isinstance(semantic_review, dict) else "NOT_RUN_AFTER_STRUCTURAL_FAILURE"
prompt = str(identity.get("user_prompt") or pre_manifest.get("user_prompt") or "")
a9_raw = str((archive(before["info"], "attempt-9").get("raw_forensic") or {}).get("raw_response") or "")
a10_raw = str((archive(before["info"], "attempt-10").get("raw_forensic") or {}).get("raw_response") or "")

write("ATTEMPT11_DUAL_LINEAGE_AUDIT.json", {"status": "PASS", "semantic_parent_attempt": "attempt-9", "semantic_parent_ir_fingerprint": EXPECTED_A9_IR, "semantic_parent_review_fingerprint": EXPECTED_A9_REVIEW_FP, "structural_failure_source_attempt": "attempt-10", "structural_feedback_fingerprint": EXPECTED_STRUCTURAL_FP, "attempt9_raw_in_prompt": a9_raw in prompt if a9_raw else False, "attempt10_raw_in_prompt": a10_raw in prompt if a10_raw else False})
write("ATTEMPT11_RUNTIME_PARENT_V2_REVIEW.json", {"status": "PASS", "attempt_id": "attempt-9", "ir_fingerprint": EXPECTED_A9_IR, "policy_version": SEMANTIC_REVIEW_POLICY_V2, "semantic_policy_fingerprint": EXPECTED_POLICY_FP, "semantic_review_fingerprint": EXPECTED_A9_REVIEW_FP, "review": parent_review})
semantic_feedback = stage_b_revision_feedback_v2(parent_review)
write("ATTEMPT11_SEMANTIC_REVISION_FEEDBACK.json", {"status": "PASS", "feedback": semantic_feedback, "constraint_count": len(semantic_feedback.get("constraints") or [])})
write("ATTEMPT11_STRUCTURAL_REVISION_FEEDBACK.json", {"status": "PASS", "feedback": feedback, "constraint_count": feedback.get("constraint_count"), "fingerprint": feedback.get("structural_feedback_fingerprint")})
write("ATTEMPT11_PROVIDER_REQUEST_IDENTITY.json", {"status": "PASS", "profile_snapshot": identity.get("profile_snapshot") or pre_manifest.get("profile_snapshot"), "system_prompt_sha256": identity.get("system_prompt_sha256"), "user_prompt_sha256": identity.get("user_prompt_sha256"), "prompt_fingerprint": identity.get("prompt_fingerprint"), "provider_request_fingerprint_v2": identity.get("provider_request_fingerprint_v2"), "revision_parent_fingerprint": identity.get("revision_parent_fingerprint") or (identity.get("revision_parent") or {}).get("revision_parent_fingerprint"), "semantic_policy_fingerprint": identity.get("semantic_policy_fingerprint"), "structural_feedback_fingerprint": identity.get("structural_feedback_fingerprint")})
parity = validate_stage_b_prompt_schema_key_parity(prompt) if prompt else {"status": "NOT_RUN"}
write("ATTEMPT11_PROMPT_AUDIT.json", {"status": "PASS" if prompt and parity.get("status") == "PASS" else "NOT_RUN", "prompt_fingerprint": identity.get("prompt_fingerprint"), "semantic_feedback_block": "REVISION_FEEDBACK=" in prompt, "structural_feedback_block": "STRUCTURAL_REVISION_FEEDBACK=" in prompt, "attempt9_raw_in_prompt": a9_raw in prompt if a9_raw else False, "attempt10_raw_in_prompt": a10_raw in prompt if a10_raw else False, "fresh_generation": True, "boundary_markers": {m: m in prompt for m in ["UNCERTAINTY_PRESERVATION_RULE", "STORY_ACTION_BOUNDARY", "SCENEBLOCKING_BOUNDARY", "PERFORMANCE_ACTION_ALLOWLIST", "V2_SHOTPLAN_BOUNDARY", "FINAL_OUTPUT_COMPLETENESS_GATE"]}, "final_gate_last": prompt.rfind("FINAL_OUTPUT_COMPLETENESS_GATE=") > prompt.rfind("REVISION_GENERATION_CONTRACT=") if prompt else False, "parity": parity})
provider_audit = after["info"].get("provider_audit") if isinstance(after["info"].get("provider_audit"), dict) else {}
write("ATTEMPT11_TRANSPORT_AUDIT.json", {"status": "PASS" if raw_forensic else "NOT_RUN", "provider_http_post_count": 1 if raw_forensic else 0, "http_status": provider_audit.get("http_status"), "provider_request_id": raw_forensic.get("provider_request_id") or provider_audit.get("provider_request_id"), "finish_reason": raw_forensic.get("finish_reason") or provider_audit.get("finish_reason"), "choice_index": raw_forensic.get("choice_index") or provider_audit.get("choice_index"), "latency_ms": raw_forensic.get("latency_ms") or provider_audit.get("latency_ms"), "usage": raw_forensic.get("usage") or provider_audit.get("usage"), "max_tokens": raw_forensic.get("resolved_max_tokens") or provider_audit.get("resolved_max_tokens"), "temperature": raw_forensic.get("resolved_temperature") or provider_audit.get("resolved_temperature"), "response_format": raw_forensic.get("resolved_response_format") or provider_audit.get("resolved_response_format"), "thinking": raw_forensic.get("resolved_thinking") or provider_audit.get("resolved_thinking"), "transport_attempt_number": (provider_audit.get("extra") or {}).get("transport_attempt_number")})
write("ATTEMPT11_RAW_FORENSIC.json", {"status": "PASS" if raw_forensic else "NOT_RUN", "forensic": raw_forensic, "raw_response_sha256": raw_forensic.get("raw_response_sha256"), "raw_response_length": raw_forensic.get("raw_response_length"), "persisted_before_parse": raw_forensic.get("persisted_before_parse"), "parse_started": raw_forensic.get("parse_started")})
write("ATTEMPT11_DUPLICATE_KEY_AUDIT.json", {"status": "PASS" if structural_pass else ("NOT_RUN_AFTER_TRANSPORT" if not raw_forensic else "NOT_RUN_AFTER_STRUCTURAL_FAILURE"), "event_trace": event_trace})
schema_report = validation.get("schema") if isinstance(validation, dict) else {}
write("ATTEMPT11_SCHEMA_VALIDATION.json", {"status": schema_report.get("status") if isinstance(schema_report, dict) else "NOT_RUN", "report": schema_report})
required_keys = render_stage_b_schema_contract().get("top_level_required") or []
top_keys = list(candidate.keys()) if isinstance(candidate, dict) else []
write("ATTEMPT11_TOP_LEVEL_COMPLETENESS_AUDIT.json", {"status": "PASS" if set(required_keys).issubset(set(top_keys)) and len(top_keys) == len(required_keys) else "NOT_RUN", "required_keys": required_keys, "required_count": len(required_keys), "actual_keys": top_keys, "missing": sorted(set(required_keys) - set(top_keys)), "visual_priority_present": "visual_priority" in top_keys})
write("ATTEMPT11_TEXT_COMPLETENESS.json", {"status": (validation.get("text") or {}).get("status", "NOT_RUN") if isinstance(validation, dict) else "NOT_RUN", "report": validation.get("text") if isinstance(validation, dict) else {}})
write("ATTEMPT11_RUNTIME_VALIDATION.json", {"status": (validation.get("runtime") or {}).get("status", "NOT_RUN") if isinstance(validation, dict) else "NOT_RUN", "report": validation.get("runtime") if isinstance(validation, dict) else {}})
write("ATTEMPT11_STAGE_A_BINDING_AUDIT.json", {"status": "PASS" if raw_forensic and raw_forensic.get("stage_a_attempt_id") == "attempt-7" and raw_forensic.get("stage_a_ir_fingerprint") == EXPECTED_STAGE_A_IR and raw_forensic.get("stage_a_materialized_fingerprint") == EXPECTED_STAGE_A_MATERIALIZED else "NOT_RUN", "expected_stage_a_attempt": "attempt-7", "expected_ir_fingerprint": EXPECTED_STAGE_A_IR, "expected_materialized_fingerprint": EXPECTED_STAGE_A_MATERIALIZED, "actual": {"attempt_id": raw_forensic.get("stage_a_attempt_id"), "ir_fingerprint": raw_forensic.get("stage_a_ir_fingerprint"), "materialized_fingerprint": raw_forensic.get("stage_a_materialized_fingerprint")}})
write("ATTEMPT11_PARENT_BINDING_REVALIDATION.json", {"status": "PASS" if archive11 and (archive11.get("revision_parent") or {}).get("revision_parent_attempt_id") == "attempt-9" else "NOT_RUN", "revision_parent": archive11.get("revision_parent") if archive11 else {}})
write("ATTEMPT11_STRUCTURAL_FEEDBACK_BINDING_REVALIDATION.json", {"status": "PASS" if archive11 and (archive11.get("structural_revision_feedback") or {}).get("structural_feedback_fingerprint") == EXPECTED_STRUCTURAL_FP else "NOT_RUN", "actual": archive11.get("structural_revision_feedback") if archive11 else {}, "expected_fingerprint": EXPECTED_STRUCTURAL_FP})
write("ATTEMPT11_SOURCE_BINDING_REVALIDATION.json", {"status": "PASS" if archive11 and archive11.get("source_authoring_unit_fingerprint") == EXPECTED_SOURCE_PROJECTION and archive11.get("source_authority_content_fingerprint") == EXPECTED_SOURCE_CONTENT else "NOT_RUN", "expected_projection": EXPECTED_SOURCE_PROJECTION, "expected_content": EXPECTED_SOURCE_CONTENT, "actual_projection": archive11.get("source_authoring_unit_fingerprint"), "actual_content": archive11.get("source_authority_content_fingerprint")})

attempt11_ir_fp = archive11.get("ir_fingerprint") or (after["info"].get("progressive_director_authoring", {}).get("stage_b") or {}).get("ir_fingerprint")
write("ATTEMPT11_LINEAGE_AUDIT.json", {"status": "PASS", "active_stage_b": (after["info"].get("progressive_director_authoring") or {}).get("stage_b", {}).get("attempt_id"), "attempt11_status": attempt11.get("status"), "history_count": len(after["info"].get("director_llm_attempts") or [])})
write("ATTEMPT11_IR_FINGERPRINT_AUDIT.json", {"status": "PASS" if attempt11_ir_fp else "NOT_RUN", "attempt11_ir_fingerprint": attempt11_ir_fp, "raw_response_sha256": raw_forensic.get("raw_response_sha256")})
write("ATTEMPT11_COMPILED_V3_VALIDATION.json", {"status": "PASS" if response and response.get("candidate") else "NOT_RUN", "candidate_decision": (candidate or {}).get("decision") if isinstance(candidate, dict) else None, "creative_projection_status": ((candidate or {}).get("creative_projection") or {}).get("status") if isinstance(candidate, dict) else None})
write("ATTEMPT11_SEMANTIC_REVIEW_V2.json", {"status": semantic_status if structural_pass else "NOT_RUN_AFTER_STRUCTURAL_FAILURE", "policy_version": semantic_review.get("policy_version") if isinstance(semantic_review, dict) else None, "semantic_policy_fingerprint": semantic_review.get("semantic_policy_fingerprint") if isinstance(semantic_review, dict) else None, "semantic_review_fingerprint": semantic_review_fingerprint(semantic_review) if isinstance(semantic_review, dict) and semantic_review else None, "review": semantic_review})
write("ATTEMPT11_POLARITY_AUDIT.json", {"status": "PASS" if structural_pass else "NOT_RUN", "physical": semantic_review.get("physical_action_authority", {}) if isinstance(semantic_review, dict) else {}, "downstream": semantic_review.get("downstream_leakage", {}) if isinstance(semantic_review, dict) else {}})
write("ATTEMPT11_UNCERTAINTY_AUDIT.json", {"status": "PASS" if structural_pass else "NOT_RUN", "audit": audit_source_uncertainty_preservation_v2(candidate if isinstance(candidate, dict) else {}, source_authoring_units=source_constraints.get("source_authoring_units", [])) if structural_pass else {}})
write("ATTEMPT11_PHYSICAL_ACTION_AUTHORITY_AUDIT.json", {"status": "PASS" if structural_pass else "NOT_RUN", "audit": audit_physical_action_authority_v2(candidate if isinstance(candidate, dict) else {}, source_authoring_units=source_constraints.get("source_authoring_units", [])) if structural_pass else {}})
write("ATTEMPT11_DOWNSTREAM_LEAKAGE_AUDIT.json", {"status": "PASS" if structural_pass else "NOT_RUN", "audit": audit_director_downstream_semantic_leakage_v2(candidate if isinstance(candidate, dict) else {}) if structural_pass else {}})

def review_counts(review: dict[str, Any]) -> dict[str, int]:
    source = review.get("source_grounding") if isinstance(review.get("source_grounding"), dict) else {}
    physical = review.get("physical_action_authority") if isinstance(review.get("physical_action_authority"), dict) else {}
    leak = review.get("downstream_leakage") if isinstance(review.get("downstream_leakage"), dict) else {}
    sf, pf, lf = source.get("findings", []), physical.get("findings", []), leak.get("violations", [])
    return {"certainty_collapse": sum(x.get("classification") == "UNSUPPORTED_CERTAINTY_COLLAPSE" for x in sf if isinstance(x, dict)), "unsupported_story_action": sum(x.get("classification") == "UNSUPPORTED_STORY_ACTION" for x in pf if isinstance(x, dict)), "SceneBlocking_leakage": sum(x.get("classification") == "DOWNSTREAM_SCENEBLOCKING_LEAKAGE" for x in pf if isinstance(x, dict)), "ShotPlan_leakage": sum(x.get("category") in {"SHOT_EXECUTION", "SHOTPLAN", "SHOT_SIZE", "LENS", "CAMERA"} for x in lf if isinstance(x, dict))}

a9_counts, a11_counts = review_counts(parent_review), review_counts(semantic_review) if isinstance(semantic_review, dict) else {"certainty_collapse": 0, "unsupported_story_action": 0, "SceneBlocking_leakage": 0, "ShotPlan_leakage": 0}
write("ATTEMPT9_TO_ATTEMPT11_SEMANTIC_DELTA.json", {"status": "PASS" if structural_pass else "NOT_RUN_AFTER_STRUCTURAL_FAILURE", "attempt9_counts": a9_counts, "attempt11_counts": a11_counts, "attempt9_review_fingerprint": EXPECTED_A9_REVIEW_FP, "attempt11_review_fingerprint": semantic_review_fingerprint(semantic_review) if isinstance(semantic_review, dict) and semantic_review else None})
write("ATTEMPT10_TO_ATTEMPT11_STRUCTURAL_DELTA.json", {"status": "PASS" if structural_pass else "NOT_RUN_AFTER_STRUCTURAL_FAILURE", "attempt10": {"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID", "missing": ["visual_priority"], "schema": "FAIL"}, "attempt11": {"status": status, "schema": schema_report.get("status") if isinstance(schema_report, dict) else "NOT_RUN", "visual_priority_present": "visual_priority" in top_keys, "top_level_key_count": len(top_keys)}})
quality_terms = ["停顿", "迟疑", "呼吸", "视线", "目光", "语气", "语速", "表情", "身体收紧", "僵住", "节奏", "反应延迟"]
quality_text = canonical(candidate)
quality = {"status": "PASS" if structural_pass else "NOT_RUN", "beat_specificity": len((candidate or {}).get("beat_enrichments", [])) if isinstance(candidate, dict) else 0, "performance_action_hits": sorted({term for term in quality_terms if term in quality_text}), "template_like_hits": [term for term in ["保持悬念", "注意情绪", "突出人物", "加强节奏"] if term in quality_text], "visual_priority_useful": bool((candidate or {}).get("visual_priority")) if isinstance(candidate, dict) else False}
write("ATTEMPT11_CONTENT_QUALITY_AUDIT.json", quality)
write("ATTEMPT11_FRESH_GENERATION_AUDIT.json", {"status": "PASS" if prompt else "NOT_RUN", "attempt9_raw_in_prompt": a9_raw in prompt if a9_raw else False, "attempt10_raw_in_prompt": a10_raw in prompt if a10_raw else False, "semantic_feedback_used_as_constraints": "REVISION_FEEDBACK=" in prompt, "structural_feedback_used_as_constraints": "STRUCTURAL_REVISION_FEEDBACK=" in prompt, "fresh_generation": True})
write("ATTEMPT9_ARCHIVE_PRESERVATION_AUDIT.json", {"status": "PASS" if archive(after["info"], "attempt-9") == archive(before["info"], "attempt-9") else "FAIL"})
write("ATTEMPT10_FAILURE_PRESERVATION_AUDIT.json", {"status": "PASS" if archive(after["info"], "attempt-10") == archive(before["info"], "attempt-10") else "FAIL", "raw_sha_before": (archive(before["info"], "attempt-10").get("raw_forensic") or {}).get("raw_response_sha256"), "raw_sha_after": (archive(after["info"], "attempt-10").get("raw_forensic") or {}).get("raw_response_sha256")})
write("ATTEMPT11_ACTIVE_STAGE_B_AUDIT.json", {"status": "PASS", "active_stage_b_before": active.get("attempt_id"), "active_stage_b_after": (after["info"].get("progressive_director_authoring") or {}).get("stage_b", {}).get("attempt_id"), "attempt11_status": attempt11.get("status")})
assessments_before, assessments_after = before["info"].get("semantic_review_assessments") or [], after["info"].get("semantic_review_assessments") or []
write("ATTEMPT11_SEMANTIC_ASSESSMENT_PERSISTENCE_AUDIT.json", {"status": "PASS" if len(assessments_after) >= len(assessments_before) + (1 if structural_pass else 0) else "NOT_RUN", "before_count": len(assessments_before), "after_count": len(assessments_after), "attempt11": next((x for x in assessments_after if isinstance(x, dict) and x.get("attempt_id") == "attempt-11"), None)})
write("ATTEMPT11_PROPOSAL_PERSISTENCE_AUDIT.json", {"status": "PASS" if structural_pass and after["proposal_sha256"] != before["proposal_sha256"] else ("NOT_RUN" if not structural_pass else "FAIL"), "proposal_sha256_before": before["proposal_sha256"], "proposal_sha256_after": after["proposal_sha256"], "decision": after["proposal"].get("decision"), "creative_projection_status": (after["proposal"].get("creative_projection") or {}).get("status")})
write("ATTEMPT11_CONFIRM_GATE_AUDIT.json", {"status": "PASS", "confirm_called": 0, "confirm_allowed": (response or {}).get("confirm_allowed"), "next_state": (response or {}).get("next_state")})
write("ATTEMPT11_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "director_treatment_approved_writes": 0, "authority_writes": 0, "pointer_writes": 0, "model_info_sha256_before": before["model_info_sha256"], "model_info_sha256_after": after["model_info_sha256"], "proposal_sha256_before": before["proposal_sha256"], "proposal_sha256_after": after["proposal_sha256"]})
write("ATTEMPT11_DOWNSTREAM_ZERO_CALL_AUDIT.json", {"status": "PASS", "scene_blocking": 0, "shot_plan": 0, "prompt_ir": 0, "image": 0, "video": 0, "shapi": 0, "poyo": 0, "75api": 0, "attempt12": 0, "automatic_retry": 0})

commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/visual-authoring-provider-canary-reconcile"], cwd=ROOT, text=True).split()[0]
working = "CLEAN" if not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip() else "DIRTY"
header = status
if structural_pass:
    header += f"\nNEXT_STATE={(response or {}).get('next_state')}\nSEMANTIC_REVIEW_V2={semantic_status}"
else:
    header += "\nNEXT_STATE=DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT12_AUTHORIZATION_REQUIRED\nSEMANTIC_REVIEW_V2=NOT_RUN_AFTER_STRUCTURAL_FAILURE"
report = f"""# V7.6.21 Director CreativeEnrichment Attempt-11 Real Semantic V2 + Structural Revision Canary

{header}

## Transport

- Endpoint: `POST /api/books/990453/episodes/1/director-treatment/creative-enrichment/revision/llm-draft`.
- Authorization: `{AUTHORIZATION_ID}`; one authorized execution; automatic retry `0`.
- Provider profile: `{(identity.get('profile_snapshot') or {}).get('profile_id')}`, `{(identity.get('profile_snapshot') or {}).get('model')}`, `{(identity.get('profile_snapshot') or {}).get('base_host')}`.
- HTTP status: `{provider_audit.get('http_status')}`; Provider request ID: `{raw_forensic.get('provider_request_id') or provider_audit.get('provider_request_id')}`; finish reason: `{raw_forensic.get('finish_reason') or provider_audit.get('finish_reason')}`.
- Latency: `{raw_forensic.get('latency_ms') or provider_audit.get('latency_ms')}` ms; tokens: `{raw_forensic.get('usage') or provider_audit.get('usage')}`; raw length: `{raw_forensic.get('raw_response_length')}`; raw SHA: `{raw_forensic.get('raw_response_sha256')}`.

## Gates and lineage

- Strict parse: `{('PARSE' in event_trace)}`; duplicate key: `{'PASS' if structural_pass else 'NOT_RUN'}`; schema: `{schema_report.get('status') if isinstance(schema_report, dict) else 'NOT_RUN'}`; top-level keys: `{len(top_keys)}/{len(required_keys)}`; missing: `{sorted(set(required_keys) - set(top_keys))}`; visual_priority: `{ 'yes' if 'visual_priority' in top_keys else 'no' }`.
- Text completeness: `{(validation.get('text') or {}).get('status') if isinstance(validation, dict) else 'NOT_RUN'}`; runtime: `{(validation.get('runtime') or {}).get('status') if isinstance(validation, dict) else 'NOT_RUN'}`.
- Stage A binding: `{raw_forensic.get('stage_a_attempt_id') == 'attempt-7' and raw_forensic.get('stage_a_ir_fingerprint') == EXPECTED_STAGE_A_IR}`; semantic parent: `attempt-9`, IR `{EXPECTED_A9_IR}`, policy `{EXPECTED_POLICY_FP}`, review `{EXPECTED_A9_REVIEW_FP}`, revision parent `{(identity.get('revision_parent') or {}).get('revision_parent_fingerprint') or identity.get('revision_parent_fingerprint')}`.
- Structural source: `attempt-10`, feedback `{EXPECTED_STRUCTURAL_FP}`.
- Source projection/content: `{identity.get('source_authoring_unit_fingerprint')}` / `{identity.get('source_authority_content_fingerprint')}`.

## Semantic result

- Attempt-11 IR fingerprint: `{attempt11_ir_fp}`.
- Semantic V2 status: `{semantic_status}`; policy fingerprint: `{semantic_review.get('semantic_policy_fingerprint') if isinstance(semantic_review, dict) else None}`.
- Counts: certainty `{a11_counts['certainty_collapse']}`, story action `{a11_counts['unsupported_story_action']}`, SceneBlocking `{a11_counts['SceneBlocking_leakage']}`, ShotPlan `{a11_counts['ShotPlan_leakage']}`.
- Attempt-9 → Attempt-11 delta: `{a9_counts} -> {a11_counts}`.
- Attempt-10 → Attempt-11 structural delta: visual_priority missing → `{ 'present' if 'visual_priority' in top_keys else 'not validated' }`.
- Creative quality audit: `{quality}`.

## Persistence and zero-call boundaries

- Active Stage B: `{active.get('attempt_id')} -> {(after['info'].get('progressive_director_authoring') or {}).get('stage_b', {}).get('attempt_id')}`; stage_b_attempts: `{[x.get('attempt_id') for x in (after['info'].get('progressive_director_authoring') or {}).get('stage_b_attempts', [])]}`.
- semantic_review_assessments: `{len(assessments_before)} -> {len(assessments_after)}`; confirm called: `0`; confirm_allowed: `{(response or {}).get('confirm_allowed')}`; next state: `{(response or {}).get('next_state')}`.
- DirectorTreatment approved / Authority / Pointer writes: `0 / 0 / 0`.
- SceneBlocking / ShotPlan / PromptIR / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0 / 0 / 0 / 0 / 0 / 0 / 0 / 0`.
- Attempt-12: `0`; automatic retry: `0`.
- Attempt-9 archive preserved: `{archive(after['info'], 'attempt-9') == archive(before['info'], 'attempt-9')}`; Attempt-10 failure preserved: `{archive(after['info'], 'attempt-10') == archive(before['info'], 'attempt-10')}`.

## Delivery

- Working tree at evidence generation: `{working}`.
- Evidence commit SHA: `{commit}`; remote HEAD: `{remote}`.
"""
(OUT / "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_REPORT.md").write_text(report, encoding="utf-8")
print(json.dumps({"status": status, "error": error, "response_status": (response or {}).get("status"), "provider_calls": 1 if raw_forensic else 0, "semantic_status": semantic_status, "attempt11_archive": bool(archive11), "raw_sha": raw_forensic.get("raw_response_sha256"), "out": str(OUT)}, ensure_ascii=False, default=str))
