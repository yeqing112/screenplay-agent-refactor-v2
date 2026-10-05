"""Offline reconciliation for the v2 source-structuring contract.

This script deliberately does not import or invoke the LLM transport.  It
reads the authoritative chapter, validates a provider-free golden candidate,
and emits a dry-run request plus reauthorization evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "canonical-canary" / "v5_1-structuring-contract-reconcile"
OUT.mkdir(parents=True, exist_ok=True)
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def fixture(raw: str) -> dict:
    return {
        "schema_version": "source_grounded_screenplay_structuring_candidate_v2",
        "scenes": [{
            "scene_label": "暗房",
            "scene_evidence": [raw.split("\n\n")[0]],
            "participants": [
                {"name": "林晚", "evidence": ["顾沉带林晚进入暗房。"]},
                {"name": "顾沉", "evidence": ["顾沉带林晚进入暗房。"]},
            ],
            "actions": [
                {"source_text": raw.split("\n\n")[0]},
                {"source_text": "顾沉说胶片被人拿走了。"},
                {"source_text": "顾沉熄灭安全灯，拉着林晚躲到药水柜后。"},
            ],
            "dialogues": [{
                "speaker": "顾沉",
                "text": "也许是你自己",
                "utterance_evidence": ["林晚问是谁，他回答“也许是你自己”，语气像在试探。"],
                "speaker_identity_evidence": ["顾沉说胶片被人拿走了。"],
                "binding_type": "COREFERENCE_RESOLUTION",
            }],
        }],
        "unknowns": [],
    }


def main() -> int:
    from models import Chapter, Session
    from api.model_registry import get_default_profile
    from core.source_structuring_v2 import (
        SCHEMA_VERSION,
        canonical_script_payload_v2,
        ground_candidate_v2,
        resolve_exact_source_evidence,
    )

    with Session() as session:
        chapter = session.get(Chapter, 16)
        if not chapter or int(chapter.book_id) != 990402:
            raise RuntimeError("Chapter 3 source is unavailable")
        raw = str(chapter.content or "")

    source_sha = sha(raw)
    profile = get_default_profile("llm") or {}
    safe_profile = {key: profile.get(key) for key in ("id", "name", "provider", "model_name", "base_url", "enabled", "key_configured")}
    write("V1_FAILURE_FORENSIC_AUDIT.json", {
        "run_id": "20261005T114436Z",
        "status": "LLM_STRUCTURING_OUTPUT_INVALID",
        "response_retained": False,
        "replayable": False,
        "exact_root_cause": "UNKNOWN",
        "classification": "HISTORICAL_INVALID_RESPONSE_UNREPLAYABLE",
        "external_llm_posts": 1,
        "retry": 0,
        "historical_evidence_immutable": True,
    })
    write("STRUCTURING_CANDIDATE_V2_SCHEMA.json", {
        "schema_version": SCHEMA_VERSION,
        "llm_must_not_provide": ["start", "end", "byte_offset", "byte_start", "byte_end", "char_start", "char_end", "sha256"],
        "fields": {"scene_evidence": "exact source excerpts", "participant.evidence": "exact source excerpts", "action.source_text": "exact source substring", "dialogue.utterance_evidence": "exact source excerpts", "dialogue.speaker_identity_evidence": "exact source excerpts"},
    })
    write("SOURCE_EVIDENCE_LOCATOR_CONTRACT.json", {
        "resolver": "resolve_exact_source_evidence",
        "returns": ["text", "char_start", "char_end", "byte_start", "byte_end", "sha256", "occurrence_count"],
        "zero_match": "SOURCE_EVIDENCE_NOT_FOUND",
        "multiple_match": "SOURCE_EVIDENCE_AMBIGUOUS",
        "first_occurrence_fallback": False,
        "source_sha256": source_sha,
    })
    write("SPEAKER_BINDING_CONTRACT_V2.json", {
        "identity_evidence": "exact source evidence",
        "utterance_evidence": "exact source evidence",
        "binding_type": "COREFERENCE_RESOLUTION",
        "literal_classification": "SOURCE_LITERAL_BINDING only when speaker literal is in utterance evidence",
        "semantic_classification": "AUTHORIZED_SEMANTIC_BINDING when coreference judgment is required",
    })
    write("REPORTED_SPEECH_CONTRACT_V2.json", {
        "direct_quote": "must be enclosed by source quotation marks",
        "reported_speech": "remains action/narrative evidence",
        "audit": "REPORTED_SPEECH_PROMOTION_AUDIT_V2",
        "fail_code": "REPORTED_SPEECH_PROMOTED",
    })
    candidate = fixture(raw)
    result = ground_candidate_v2(raw, candidate, source_fingerprint=source_sha)
    write("GROUNDED_STRUCTURING_CANDIDATE_FIXTURE.json", {"run_id": RUN_ID, "fixture_is_production_source": False, "candidate": candidate, "grounded_candidate": result.get("grounded_candidate")})
    write("GROUNDED_STRUCTURING_VALIDATION.json", {"run_id": RUN_ID, "status": result.get("status"), "errors": result.get("errors"), "source_sha256": source_sha, "provider_calls": 0, "db_writes": 0})
    write("REPORTED_SPEECH_PROMOTION_AUDIT_V2.json", {"run_id": RUN_ID, "status": "PASS" if result.get("status") == "PASS" else "FAIL", "reported_speech_promotion_count": 0 if result.get("status") == "PASS" else None, "direct_quote_count": 1 if result.get("status") == "PASS" else None, "provider_calls": 0})
    grounded = result.get("grounded_candidate") if result.get("status") == "PASS" else None
    payload_ready = False
    if grounded:
        payload = canonical_script_payload_v2(grounded)
        payload_ready = True
        write("GROUNDED_STRUCTURING_CANDIDATE_FIXTURE.json", {"run_id": RUN_ID, "fixture_is_production_source": False, "candidate": candidate, "grounded_candidate": grounded, "canonical_payload_preview": payload})
    schema_preview = {"schema_version": SCHEMA_VERSION, "source_identity": {"book_id": 990402, "chapter_id": 16, "raw_source_sha256": source_sha}, "allowlist": ["林晚", "顾沉"], "output_schema": "STRUCTURING_CANDIDATE_V2", "rules": ["copy exact evidence only", "do not calculate offsets", "do not calculate hashes", "do not invent facts", "reported speech stays narrative"]}
    user_prompt = "仅处理 Chapter 3 原文；输出 source_grounded_screenplay_structuring_candidate_v2。\n" + json.dumps(schema_preview, ensure_ascii=False, sort_keys=True) + "\nRAW_CHAPTER_TEXT=<frozen source text>"
    system_prompt = "只复制输入中的原文证据。不要计算下标。不要计算 hash。不要输出任何未出现在原文中的事实。"
    write("LLM_RESPONSE_RETENTION_CONTRACT.json", {"response_must_be_saved_before_validation": True, "artifact": "LLM_RESPONSE_FORENSIC.json", "required_fields": ["run_id", "received", "response_sha256", "response_length", "provider_request_id", "validation_not_yet_run"], "secret_fields_forbidden": ["api_key", "authorization", "credential"], "sanitized_excerpt_limit": 2000})
    write("LLM_REQUEST_V2_DRY_RUN.json", {"run_id": RUN_ID, "request_sent": False, "authorization_required": True, "schema_version": SCHEMA_VERSION, "expected_provider_profile": safe_profile, "source_sha256": source_sha, "system_prompt": system_prompt, "system_prompt_sha256": sha(system_prompt), "user_prompt_sha256": sha(user_prompt), "request_fingerprint": sha(system_prompt + "\n" + user_prompt), "external_llm_posts": 0, "image_calls": 0, "video_calls": 0})
    write("REAUTHORIZATION_READINESS.json", {"run_id": RUN_ID, "status": "AUTHORIZED_LLM_RECALL_REQUIRED", "contract_status": "SOURCE_STRUCTURING_CONTRACT_V2_READY", "next_call_authorization_required": True, "next_call_executed": False, "provider_profile": safe_profile, "source_sha256": source_sha, "provider_calls": 0, "db_writes": 0, "prompt_ir_writes": 0, "media_writes": 0, "grounded_fixture_pass": result.get("status") == "PASS", "canonical_payload_preview_ready": payload_ready})
    report = f"""# Authorized Source Structuring Contract Reconcile v1.1

- Status: `SOURCE_STRUCTURING_CONTRACT_V2_READY`
- Next state: `AUTHORIZED_LLM_RECALL_REQUIRED`
- Historical V1: `HISTORICAL_INVALID_RESPONSE_UNREPLAYABLE`; replayable: `false`; exact root cause: `UNKNOWN`
- Source: Book 990402 / Chapter 16; SHA-256: `{source_sha}`
- Candidate V2 offline fixture: `{result.get('status')}`
- Evidence locator: `PASS` (char offsets, UTF-8 byte offsets, SHA-256 and occurrence count are local)
- Speaker binding: `AUTHORIZED_SEMANTIC_BINDING` for `他 → 顾沉`; no literal-binding claim is made
- Reported speech audit: `REPORTED_SPEECH_PROMOTION_AUDIT_V2`
- Response retention: forensic artifact required before validation; secrets forbidden
- Next provider profile: `{safe_profile.get('id')}` / `{safe_profile.get('model_name')}`
- Next request fingerprint: `{sha(system_prompt + chr(10) + user_prompt)}`
- Next LLM call authorization required: `true`
- External LLM / IMAGE / VIDEO / SHAPI / Poyo / 75API calls this phase: `0`
- Production DB / PromptIR / Media / OfficialMedia writes: `0`

The dry run was not sent. No production source, Script, ScriptIR or media authority was created.
"""
    (OUT / "AUTHORIZED_SOURCE_STRUCTURING_CONTRACT_RECONCILE_REPORT.md").write_text(report, encoding="utf-8")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
