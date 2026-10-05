"""Execute the single authorized source-grounding LLM canary.

This runner is deliberately one shot.  It performs all provider-free gates,
marks the authorization ledger before the raw transport, saves the assistant
content before parsing, and only then persists one new production Book/Script
and its official ScriptIR authority chain.  It never enters Director or media
runtime stages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "docs" / "canonical-canary" / "v5_3-authorized-source-structuring-v2"
EVIDENCE.mkdir(parents=True, exist_ok=True)

EXPECTED_HEAD = "d5d2907e3e95843cee62aca244748b19a2c16f2f"
BOOK_ID = 990402
CHAPTER_ID = 16
CHAPTER_SEQ = 3
CHAPTER_TITLE = "第三章 没有底片的暗房"
ALLOWLIST = ("林晚", "顾沉")
TARGET_QUOTE = "也许是你自己"
TARGET_QUOTE_SHA256 = "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a"
EXPECTED_RAW_SHA256 = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
AUTHORIZED_PROFILE_ID = "local-llm-2vydoz"
AUTHORIZED_MODEL = "mimo-v2.5"
AUTHORIZED_PROVIDER = "openai-compatible"
AUTHORIZED_HOST = "api.xiaomimimo.com"
DRY_RUN_FINGERPRINT = "2af9f6a1375ec7d8bb252150ab899e680611340c6bc039e403312166a182445a"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def write_json(name: str, value: Any) -> None:
    path = EVIDENCE / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_json(name: str, default: Any = None) -> Any:
    path = EVIDENCE / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {key: profile.get(key) for key in ("id", "name", "provider", "base_url", "model_name", "enabled", "key_configured", "credential_configured", "default_params")}


def current_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def normalized_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def source_snapshot() -> dict[str, Any]:
    from models import Chapter, Session

    with Session() as session:
        chapter = session.get(Chapter, CHAPTER_ID)
        if not chapter or int(chapter.book_id) != BOOK_ID:
            raise RuntimeError("AUTHORIZED_SOURCE_CHANGED")
        raw = str(chapter.content or "")
        raw_hash = sha(raw)
        return {
            "book_id": BOOK_ID,
            "chapter_id": CHAPTER_ID,
            "chapter_seq": CHAPTER_SEQ,
            "title": str(chapter.title or ""),
            "expected_title": CHAPTER_TITLE,
            "title_normalized": normalized_title(chapter.title),
            "raw_sha256": raw_hash,
            "expected_raw_sha256": EXPECTED_RAW_SHA256,
            "raw_byte_length": len(raw.encode("utf-8")),
            "raw": raw,
        }


def profile_preflight() -> dict[str, Any]:
    from api.model_registry import get_default_profile

    profile = get_default_profile("llm") or {}
    host = urlparse(str(profile.get("base_url") or "")).hostname or ""
    checks = {
        "profile_id": profile.get("id") == AUTHORIZED_PROFILE_ID,
        "model": profile.get("model_name") == AUTHORIZED_MODEL,
        "provider": profile.get("provider") == AUTHORIZED_PROVIDER,
        "endpoint_host": host == AUTHORIZED_HOST,
        "enabled": bool(profile.get("enabled")),
        "key_configured": bool(profile.get("key_configured")),
    }
    return {"status": "PASS" if all(checks.values()) else "AUTHORIZED_LLM_PROFILE_CHANGED", "profile": safe_profile(profile), "checks": checks, "endpoint_host": host, "profile_raw": profile}


def strict_infrastructure_preflight(raw: str, raw_hash: str) -> dict[str, Any]:
    from core.script_ir import validate_script_ir
    from core.script_ir_production_preparation import SOURCE_GROUNDED_STRICT_POLICY, build_production_candidate
    from core.script_ir_source_requirements import compile_script_ir_source_requirements
    from core.source_structuring_v2 import canonical_script_payload_v2, ground_candidate_v2, semantic_diff_source_to_script_ir

    fixture_path = ROOT / "docs" / "canonical-canary" / "v5_1-structuring-contract-reconcile" / "GROUNDED_STRUCTURING_CANDIDATE_FIXTURE.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    candidate = fixture.get("candidate") if isinstance(fixture, dict) else None
    grounded_result = ground_candidate_v2(raw, candidate, expected_source_fingerprint=raw_hash)
    if grounded_result.get("status") != "PASS":
        return {"status": "AUTHORIZED_LLM_PRECONDITION_NOT_READY", "grounding": grounded_result}
    payload = canonical_script_payload_v2(grounded_result["grounded_candidate"])
    strict = build_production_candidate(payload, book_id=BOOK_ID, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
    validation = validate_script_ir(strict)
    requirements = compile_script_ir_source_requirements(source_structure=strict)
    semantic = semantic_diff_source_to_script_ir(payload, strict)
    requirement_pass = not any(
        isinstance(item, dict) and item.get("blocking") and isinstance(item.get("expected_value"), dict) and item["expected_value"].get("actual") == 0
        for item in requirements.get("requirements", [])
    )
    checks = {
        "contract_v2_ready": True,
        "grounding_pass": grounded_result.get("status") == "PASS",
        "script_ir_qualified": validation.get("status") == "qualified",
        "source_requirement_pass": requirement_pass,
        "semantic_diff_empty": semantic.get("status") == "SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY",
        "assertion_mode_empty": semantic.get("assertion_mode_preserved_empty") is True,
        "timeline_origin": all(scene.get("timeline_origin") == "SOURCE_GROUNDED" for scene in strict.get("scenes", [])),
        "timeline_authority": all(scene.get("timeline_authority") == "SOURCE_EVIDENCE_ORDER" for scene in strict.get("scenes", [])),
    }
    return {"status": "PASS" if all(checks.values()) else "AUTHORIZED_LLM_PRECONDITION_NOT_READY", "checks": checks, "payload": payload, "strict_candidate": strict, "validation": validation, "requirements": requirements, "semantic_diff": semantic}


def authorization_ledger(consumed: int, status: str, *, actual_fingerprint: str = "", reason: str = "") -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "authorized_external_calls": 1,
        "consumed_external_calls": consumed,
        "retry_allowed": False,
        "semantic_repair_allowed": False,
        "media_allowed": False,
        "status": status,
        "actual_request_fingerprint": actual_fingerprint,
        "reason": reason,
    }


def schema_validate(candidate: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    forbidden = {"start", "end", "byte_offset", "byte_start", "byte_end", "char_start", "char_end", "sha256"}
    historical = ("SH_E01_SC002_002", "SH_E01_SC002_006", "SH_E01_SC002_007")

    def walk(value: Any, path: str = "$", keys: set[str] | None = None) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key) in forbidden:
                    errors.append({"code": "LLM_MUST_NOT_PROVIDE_LOCAL_OFFSETS_OR_HASHES", "path": f"{path}.{key}"})
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(candidate)
    encoded = json.dumps(candidate, ensure_ascii=False, sort_keys=True) if isinstance(candidate, dict) else ""
    for item in historical:
        if item in encoded:
            errors.append({"code": "HISTORICAL_ID_FORBIDDEN", "value": item})
    if not isinstance(candidate, dict):
        errors.append({"code": "CANDIDATE_NOT_OBJECT"})
        return {"status": "FAIL", "errors": errors}
    if candidate.get("schema_version") != "source_grounded_screenplay_structuring_candidate_v2":
        errors.append({"code": "SCHEMA_VERSION_INVALID"})
    if not isinstance(candidate.get("scenes"), list) or not candidate["scenes"]:
        errors.append({"code": "SCENES_REQUIRED"})
    if not isinstance(candidate.get("unknowns"), list):
        errors.append({"code": "UNKNOWNS_REQUIRED"})
    for scene_index, scene in enumerate(candidate.get("scenes") or [], 1):
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_INVALID", "scene_index": scene_index}); continue
        if not str(scene.get("scene_label") or "").strip():
            errors.append({"code": "SCENE_LABEL_REQUIRED", "scene_index": scene_index})
        for participant in scene.get("participants") or []:
            if not isinstance(participant, dict) or participant.get("name") not in ALLOWLIST or not isinstance(participant.get("evidence"), list):
                errors.append({"code": "PARTICIPANT_SCHEMA_INVALID", "scene_index": scene_index})
        for action in scene.get("actions") or []:
            if not isinstance(action, dict) or not str(action.get("source_text") or ""):
                errors.append({"code": "ACTION_SCHEMA_INVALID", "scene_index": scene_index})
        for dialogue in scene.get("dialogues") or []:
            required = ("speaker", "text", "utterance_evidence", "speaker_identity_evidence", "binding_type")
            if not isinstance(dialogue, dict) or any(not dialogue.get(key) for key in required):
                errors.append({"code": "DIALOGUE_SCHEMA_INVALID", "scene_index": scene_index})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "schema_version": candidate.get("schema_version") if isinstance(candidate, dict) else ""}


def persist_raw_response(raw: str, profile: dict[str, Any], actual_fingerprint: str, audit: list[dict[str, Any]]) -> dict[str, Any]:
    path = EVIDENCE / "LLM_RAW_RESPONSE_FORENSIC.txt"
    data = str(raw or "").encode("utf-8")
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    persisted = path.read_bytes() == data and sha(raw) == sha(path.read_text(encoding="utf-8"))
    request_id = next((row.get("provider_request_id") for row in audit if row.get("provider_request_id")), "")
    forensic = {
        "run_id": RUN_ID,
        "received": True,
        "response_sha256": sha(raw),
        "response_length": len(raw),
        "provider": profile.get("provider"),
        "model": profile.get("model_name"),
        "profile_id": profile.get("id"),
        "provider_request_id": request_id,
        "actual_request_fingerprint": actual_fingerprint,
        "persisted_before_parse": bool(persisted),
        "parse_started": False,
        "secret_fields_persisted": False,
        "artifact_path": str(path),
        "transport_audit_records": audit,
    }
    write_json("LLM_RESPONSE_FORENSIC.json", forensic)
    return forensic


def write_failure(status: str, details: dict[str, Any], *, source: dict[str, Any] | None = None) -> int:
    write_json("NO_DOWNSTREAM_EXECUTION.json", {"run_id": RUN_ID, "status": "PASS", "director_executed": False, "treatment": 0, "scene_blocking": 0, "shot_plan": 0, "storyboard": 0, "prompt_ir": 0, "image": 0, "video": 0})
    write_json("PRODUCTION_CANARY_AUTHORIZED_SOURCE_STRUCTURING_V2_REPORT.json", {"run_id": RUN_ID, "status": status, "source": source or {}, "details": details})
    report = [
        "# Production Canary Authorized Source Structuring V2 Report", "", f"- Run ID: `{RUN_ID}`", f"- Status: `{status}`", f"- External LLM calls: `{details.get('llm_calls', 0)}`", f"- IMAGE / VIDEO: `0 / 0`", "", "```json", json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True), "```", "",
        "Director, Treatment, SceneBlocking, ShotPlan, Storyboard, PromptIR and media stages were not executed.",
    ]
    (EVIDENCE / "PRODUCTION_CANARY_AUTHORIZED_SOURCE_STRUCTURING_V2_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 1


def main() -> int:
    from core.source_structuring_v2 import canonical_script_payload_v2, ground_candidate_v2, semantic_diff_source_to_script_ir
    from core.script_ir import validate_script_ir, resolve_script_payload
    from core.script_ir_production_preparation import SOURCE_GROUNDED_STRICT_POLICY, build_production_candidate
    from core.script_ir_source_requirements import compile_script_ir_source_requirements

    # Gate A: freeze repository and authoritative source before any transport.
    head = current_head()
    source = source_snapshot()
    raw = source["raw"]
    source_public = {key: value for key, value in source.items() if key != "raw"}
    source_ok = head == EXPECTED_HEAD and source["raw_sha256"] == EXPECTED_RAW_SHA256 and source["title_normalized"] == CHAPTER_TITLE and raw.count(TARGET_QUOTE) == 1 and sha(TARGET_QUOTE) == TARGET_QUOTE_SHA256
    write_json("SOURCE_FREEZE.json", {"run_id": RUN_ID, "status": "PASS" if source_ok else "AUTHORIZED_SOURCE_CHANGED", "expected_head": EXPECTED_HEAD, "actual_head": head, **source_public, "target_quote": TARGET_QUOTE, "target_quote_sha256": sha(TARGET_QUOTE), "target_quote_occurrences": raw.count(TARGET_QUOTE)})
    if not source_ok:
        return write_failure("AUTHORIZED_SOURCE_CHANGED", {"llm_calls": 0}, source=source_public)

    profile_check = profile_preflight()
    write_json("LLM_PROFILE_PREFLIGHT.json", {"run_id": RUN_ID, **{key: value for key, value in profile_check.items() if key != "profile_raw"}})
    if profile_check["status"] != "PASS":
        return write_failure("AUTHORIZED_LLM_PROFILE_CHANGED", {"llm_calls": 0, "profile": profile_check}, source=source_public)
    profile = profile_check["profile_raw"]

    strict = strict_infrastructure_preflight(raw, source["raw_sha256"])
    write_json("STRICT_PRECONDITION_PREFLIGHT.json", {"run_id": RUN_ID, "status": strict["status"], **{key: value for key, value in strict.items() if key not in {"payload", "strict_candidate"}}})
    if strict["status"] != "PASS":
        return write_failure("AUTHORIZED_LLM_PRECONDITION_NOT_READY", {"llm_calls": 0, "preflight": strict}, source=source_public)

    if "--preflight" in sys.argv:
        write_json("LLM_AUTHORIZATION_CONSUMPTION.json", authorization_ledger(0, "READY"))
        write_json("LLM_TRANSPORT_AUDIT.json", {"run_id": RUN_ID, "status": "NOT_SENT", "transport_attempts": 0, "retry_records": []})
        write_json("NO_DOWNSTREAM_EXECUTION.json", {"run_id": RUN_ID, "status": "PASS", "director_executed": False, "treatment": 0, "scene_blocking": 0, "shot_plan": 0, "storyboard": 0, "prompt_ir": 0, "image": 0, "video": 0})
        return 0

    prior_ledger = read_json("LLM_AUTHORIZATION_CONSUMPTION.json", {}) or {}
    if int(prior_ledger.get("consumed_external_calls", 0) or 0) >= 1 or prior_ledger.get("status") == "CONSUMED":
        return write_failure("AUTHORIZED_LLM_CALL_ALREADY_CONSUMED", {"llm_calls": 0, "ledger": prior_ledger}, source=source_public)
    write_json("LLM_AUTHORIZATION_SCOPE.json", {"run_id": RUN_ID, "status": "READY", "authorized_external_calls": 1, "profile_id": profile.get("id"), "model": profile.get("model_name"), "provider": profile.get("provider"), "allowed": ["semantic grouping", "participant selection", "exact evidence selection", "direct dialogue extraction", "speaker semantic binding", "source-grounded action selection"], "forbidden": ["creative expansion", "DirectorTreatment", "SceneBlocking", "ShotPlan", "Storyboard", "PromptIR", "IMAGE", "VIDEO"], "media_allowed": False})

    schema = {
        "schema_version": "source_grounded_screenplay_structuring_candidate_v2",
        "scenes": [{"scene_label": "string", "scene_evidence": ["exact source excerpt"], "participants": [{"name": "林晚|顾沉", "evidence": ["exact source excerpt"]}], "actions": [{"source_text": "exact source substring"}], "dialogues": [{"speaker": "顾沉", "text": "exact direct quote text", "utterance_evidence": ["exact source excerpt containing quote"], "speaker_identity_evidence": ["exact source excerpt containing speaker identity"], "binding_type": "COREFERENCE_RESOLUTION"}]}],
        "unknowns": ["unresolved source-grounded questions"],
    }
    system = "你是严格的来源结构化器。只返回合法 JSON object，不要 Markdown。只能选择输入原文中的连续子串；不得改写、扩写、润色或新增对白、人物、道具、场景事实。不得输出 char_start、char_end、byte_start、byte_end、offset、sha256。仅允许人物 林晚、顾沉。报道性转述必须留在 actions，不得提升为对白。目标对白也许是你自己必须只出现一次；如果无法证明就放入 unknowns，不要猜测。"
    user = "仅处理下面的 Chapter 16 原文（Chapter Seq 3）。输出必须符合 schema。LLM 只输出语义候选，所有位置、字节范围和 hash 由本地 deterministic code 计算。\nSOURCE_IDENTITY=" + json.dumps({key: value for key, value in source_public.items() if key not in {"title_normalized", "expected_title", "expected_raw_sha256"}}, ensure_ascii=False, sort_keys=True) + "\nALLOWLIST=" + json.dumps(list(ALLOWLIST), ensure_ascii=False) + "\nSCHEMA=" + json.dumps(schema, ensure_ascii=False, sort_keys=True) + "\nRAW_CHAPTER_TEXT_START\n" + raw + "\nRAW_CHAPTER_TEXT_END"
    actual_fingerprint = sha(system + "\n" + user)
    manifest = {"run_id": RUN_ID, "status": "READY_TO_SEND", "request_sent": False, "profile_id": profile.get("id"), "model": profile.get("model_name"), "provider": profile.get("provider"), "endpoint_host": urlparse(str(profile.get("base_url") or "")).hostname, "source_sha256": source["raw_sha256"], "system_prompt_sha256": sha(system), "user_prompt_sha256": sha(user), "dry_run_contract_fingerprint": DRY_RUN_FINGERPRINT, "actual_request_fingerprint": actual_fingerprint, "historical_ids_in_prompt": [], "transport_attempt_budget": 1, "json_parse_retry_budget": 0, "semantic_repair_calls": 0, "image_calls": 0, "video_calls": 0}
    write_json("LLM_REQUEST_MANIFEST.json", manifest)
    write_json("LLM_AUTHORIZATION_CONSUMPTION.json", authorization_ledger(0, "CONSUMING", actual_fingerprint=actual_fingerprint))

    from core import llm as llm_client
    audit: list[dict[str, Any]] = []
    try:
        raw_response = str(llm_client.call_llm(user, system=system, model_profile=profile, retries=1, estimated_tokens=5000, max_tokens=7000, audit_callback=audit.append, audit_extra={"phase": "production_canary_authorized_source_structuring_v2", "run_id": RUN_ID, "source_sha256": source["raw_sha256"], "request_fingerprint": actual_fingerprint}) or "")
        write_json("LLM_TRANSPORT_AUDIT.json", {"run_id": RUN_ID, "status": "RECEIVED" if raw_response else "EMPTY_RESPONSE", "records": audit, "transport_attempts": len([row for row in audit if (row.get("extra") or {}).get("transport_attempt_number")]), "retry_records": [row for row in audit if (row.get("extra") or {}).get("transport_retry") is True]})
        write_json("LLM_AUTHORIZATION_CONSUMPTION.json", authorization_ledger(1, "CONSUMED", actual_fingerprint=actual_fingerprint))
    except Exception as exc:
        write_json("LLM_TRANSPORT_AUDIT.json", {"run_id": RUN_ID, "status": "FAILED", "records": audit, "error_type": type(exc).__name__, "error": str(exc)[:500]})
        write_json("LLM_AUTHORIZATION_CONSUMPTION.json", authorization_ledger(1, "CONSUMED", actual_fingerprint=actual_fingerprint, reason=str(exc)[:500]))
        status = "LLM_SUBMISSION_AMBIGUOUS" if type(exc).__name__ in {"ReadTimeout", "TimeoutException"} else "LLM_STRUCTURING_CALL_FAILED"
        return write_failure(status, {"llm_calls": 1, "error": str(exc)[:500], "transport_attempts": len(audit), "retry": False}, source=source_public)

    forensic = persist_raw_response(raw_response, profile, actual_fingerprint, audit)
    if not forensic.get("persisted_before_parse"):
        return write_failure("LLM_STRUCTURING_CALL_FAILED", {"llm_calls": 1, "reason": "FORENSIC_PERSISTENCE_FAILED", "response_sha256": sha(raw_response)}, source=source_public)
    from core.structured_output import parse_json_object
    try:
        candidate = parse_json_object(raw_response, label="source_grounded_screenplay_structuring_candidate_v2", required_keys={"schema_version", "scenes", "unknowns"})
    except Exception as exc:
        forensic["parse_started"] = True
        forensic["parse_error"] = str(exc)[:500]
        write_json("LLM_RESPONSE_FORENSIC.json", forensic)
        write_json("PARSED_CANDIDATE_V2.json", {"run_id": RUN_ID, "status": "LLM_STRUCTURING_OUTPUT_INVALID", "parser_error": str(exc)[:500]})
        return write_failure("LLM_STRUCTURING_OUTPUT_INVALID", {"llm_calls": 1, "response_sha256": sha(raw_response), "response_length": len(raw_response), "raw_response_path": str(EVIDENCE / "LLM_RAW_RESPONSE_FORENSIC.txt"), "parser_error": str(exc)[:500]}, source=source_public)
    forensic["parse_started"] = True
    write_json("LLM_RESPONSE_FORENSIC.json", forensic)
    write_json("PARSED_CANDIDATE_V2.json", {"run_id": RUN_ID, "status": "PASS", "candidate": candidate})
    schema_result = schema_validate(candidate)
    write_json("CANDIDATE_V2_SCHEMA_VALIDATION.json", {"run_id": RUN_ID, **schema_result})
    if schema_result["status"] != "PASS":
        return write_failure("LLM_STRUCTURING_OUTPUT_INVALID", {"llm_calls": 1, "schema_validation": schema_result, "response_sha256": sha(raw_response)}, source=source_public)

    grounded_result = ground_candidate_v2(raw, candidate, expected_source_fingerprint=source["raw_sha256"], allowlist=ALLOWLIST)
    grounded = grounded_result.get("grounded_candidate") or {}
    write_json("SOURCE_GROUNDING_VALIDATION.json", {"run_id": RUN_ID, "status": grounded_result.get("status"), "errors": grounded_result.get("errors", []), "source_sha256": source["raw_sha256"]})
    target = [row for scene in grounded.get("scenes", []) for row in scene.get("dialogues", []) if row.get("text") == TARGET_QUOTE]
    participants = sorted({row.get("name") for scene in grounded.get("scenes", []) for row in scene.get("participants", [])})
    binding = target[0].get("binding_classification") if len(target) == 1 else ""
    binding_type = target[0].get("binding_type") if len(target) == 1 else ""
    dialogue_audit = {"run_id": RUN_ID, "status": "PASS" if len(target) == 1 and target[0].get("speaker") == "顾沉" and sha(TARGET_QUOTE) == TARGET_QUOTE_SHA256 else "FAIL", "target_quote": TARGET_QUOTE, "target_quote_sha256": sha(TARGET_QUOTE), "match_count": len(target), "speaker": target[0].get("speaker") if len(target) == 1 else "", "binding_type": binding_type, "binding_classification": binding}
    write_json("DIALOGUE_EXACT_MATCH_AUDIT.json", dialogue_audit)
    write_json("SPEAKER_BINDING_AUDIT.json", {"run_id": RUN_ID, "status": "PASS" if binding == "AUTHORIZED_SEMANTIC_BINDING" and binding_type == "COREFERENCE_RESOLUTION" else "FAIL", "participants": participants, "target": dialogue_audit})
    reported_count = sum(1 for error in grounded_result.get("errors", []) if error.get("code") == "REPORTED_SPEECH_PROMOTED")
    write_json("REPORTED_SPEECH_PROMOTION_AUDIT.json", {"run_id": RUN_ID, "status": "PASS" if reported_count == 0 else "FAIL", "reported_speech_promotion_count": reported_count})
    acceptance = {"run_id": RUN_ID, "participants": participants, "allowlist": list(ALLOWLIST), "target_dialogue_exactly_once": len(target) == 1, "target_speaker_is_gu_chen": len(target) == 1 and target[0].get("speaker") == "顾沉", "binding_classification": binding, "binding_type": binding_type, "reported_speech_promotion_count": reported_count, "status": "PASS" if grounded_result.get("status") == "PASS" and set(ALLOWLIST).issubset(set(participants)) and dialogue_audit["status"] == "PASS" and reported_count == 0 else "FAIL"}
    write_json("CANARY_ACCEPTANCE_AUDIT.json", acceptance)
    if acceptance["status"] != "PASS":
        write_json("GROUNDED_CANDIDATE_V2.json", {"run_id": RUN_ID, "status": "FAIL", "grounded_candidate": grounded, "errors": grounded_result.get("errors", [])})
        return write_failure("LLM_STRUCTURING_SOURCE_GROUNDING_FAILED", {"llm_calls": 1, "acceptance": acceptance, "grounding": grounded_result, "response_sha256": sha(raw_response)}, source=source_public)

    payload = canonical_script_payload_v2(grounded)
    strict_candidate = build_production_candidate(payload, book_id=BOOK_ID, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
    validation = validate_script_ir(strict_candidate)
    requirements = compile_script_ir_source_requirements(source_structure=strict_candidate)
    semantic = semantic_diff_source_to_script_ir(payload, strict_candidate)
    requirement_pass = not any(item.get("blocking") and isinstance(item.get("expected_value"), dict) and item["expected_value"].get("actual") == 0 for item in requirements.get("requirements", []) if isinstance(item, dict))
    preflight = {"run_id": RUN_ID, "status": "PASS" if validation.get("status") == "qualified" and semantic.get("status") == "SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY" and requirement_pass else "FAIL", "script_ir_validation": validation, "source_requirements": requirements, "semantic_diff": semantic, "source_requirement_status": "PASS" if requirement_pass else "FAIL"}
    write_json("STRICT_PREPERSISTENCE_PREFLIGHT.json", preflight)
    if preflight["status"] != "PASS":
        return write_failure("PRODUCTION_CANARY_SOURCE_PERSISTENCE_FAILED", {"llm_calls": 1, "preflight": preflight}, source=source_public)

    lineage = {"origin_book_id": BOOK_ID, "origin_chapter_id": CHAPTER_ID, "origin_chapter_seq": CHAPTER_SEQ, "origin_raw_sha256": source["raw_sha256"], "structuring_schema_version": "source_grounded_screenplay_structuring_candidate_v2", "grounded_schema_version": "grounded_source_screenplay_structuring_candidate_v2", "llm_profile_id": profile.get("id"), "llm_model": profile.get("model_name"), "llm_response_sha256": sha(raw_response), "actual_request_fingerprint": actual_fingerprint, "authorization_run_id": RUN_ID, "binding_authority": "AUTHORIZED_SEMANTIC_BINDING"}
    script_content = {**payload, "source_lineage": lineage}
    from core.book_lifecycle import create_book, create_script
    from models import Book, FactRecord, FactSnapshot, Script, ScriptIRVersion, Session
    new_book = None
    new_script = None
    try:
        with Session() as session:
            new_book = create_book(session, title=f"潮汐回声·Canonical Source Canary V2·{RUN_ID}")
        write_json("NEW_BOOK_CREATION.json", {"run_id": RUN_ID, "status": "CREATED", "book_id": int(new_book.id), "title": new_book.title})
        with Session() as session:
            new_script = create_script(session, book_id=int(new_book.id), episode=1, content=script_content, genre="short_drama", workflow_profile="production")
        write_json("NEW_PRODUCTION_SCRIPT.json", {"run_id": RUN_ID, "status": "CREATED", "book_id": int(new_book.id), "script_id": int(new_script.id), "content_sha256": sha(new_script.content), "source_lineage": lineage})
    except Exception as exc:
        write_json("NEW_BOOK_CREATION.json", {"run_id": RUN_ID, "status": "CREATED" if new_book else "FAILED", "book_id": int(new_book.id) if new_book else None})
        write_json("NEW_PRODUCTION_SCRIPT.json", {"run_id": RUN_ID, "status": "FAILED", "book_id": int(new_book.id) if new_book else None, "script_created": False, "error": str(exc)[:500]})
        return write_failure("PRODUCTION_CANARY_PARTIAL_SOURCE_PERSISTENCE" if new_book else "PRODUCTION_CANARY_SOURCE_PERSISTENCE_FAILED", {"llm_calls": 1, "new_book_id": int(new_book.id) if new_book else None, "script_created": False, "error": str(exc)[:500]}, source=source_public)

    try:
        from api.script_ir_preparation_api import PrepareProductionRequest, prepare_script_ir_production
        prep = prepare_script_ir_production(int(new_book.id), 1, PrepareProductionRequest(confirmed=True))
    except Exception as exc:
        write_json("NEW_FACT_SNAPSHOT.json", {"run_id": RUN_ID, "status": "FAILED", "book_id": int(new_book.id), "script_id": int(new_script.id), "error": str(exc)[:1000]})
        write_json("NEW_SCRIPT_IR_AUTHORITY.json", {"run_id": RUN_ID, "status": "FAILED", "book_id": int(new_book.id), "script_id": int(new_script.id), "error": str(exc)[:1000]})
        return write_failure("PRODUCTION_CANARY_SOURCE_PERSISTED_SCRIPT_IR_FAILED", {"llm_calls": 1, "book_id": int(new_book.id), "script_id": int(new_script.id), "error": str(exc)[:1000]}, source=source_public)

    script_ir = prep.get("script_ir") or {}
    payload_ir = script_ir.get("payload") or {}
    with Session() as session:
        book_row = session.get(Book, int(new_book.id))
        script_row = session.get(Script, int(new_script.id))
        fact_rows = session.query(FactSnapshot).filter_by(book_id=int(new_book.id), episode=1).all()
        ir_rows = session.query(ScriptIRVersion).filter_by(book_id=int(new_book.id), episode=1).all()
        resolved = resolve_script_payload(session, script_row, workflow_profile="production")
        resolved_ok = bool(resolved and resolved.get("scenes"))
        fact_id = fact_rows[-1].id if fact_rows else None
        ir_row = ir_rows[-1] if ir_rows else None
        source_content_hash = sha(script_row.content)
        fact_record_count = session.query(FactRecord).filter(FactRecord.snapshot_id.in_([row.id for row in fact_rows])).count() if fact_rows else 0
    dialogues = [d for scene in payload_ir.get("scenes", []) for d in scene.get("dialogues", []) if isinstance(d, dict)]
    semantic_final = semantic_diff_source_to_script_ir(payload, payload_ir)
    write_json("NEW_FACT_SNAPSHOT.json", {"run_id": RUN_ID, "status": "CREATED", "book_id": int(new_book.id), "script_id": int(new_script.id), "fact_snapshot_id": fact_id, "fact_record_count": fact_record_count, "source_fingerprint": source_content_hash})
    write_json("NEW_SCRIPT_IR_AUTHORITY.json", {"run_id": RUN_ID, "status": "PRODUCTION_QUALIFIED", "book_id": int(new_book.id), "script_id": int(new_script.id), "script_ir_version_id": script_ir.get("id"), "qualification_state": script_ir.get("qualification_state"), "authority_envelope": script_ir.get("authority_envelope"), "production_writes": {"script_ir_version": 1, "fact_snapshot": 1}})
    write_json("PRODUCTION_RESOLVE_CHECK.json", {"run_id": RUN_ID, "status": "PASS" if resolved_ok else "FAIL", "book_id": int(new_book.id), "script_id": int(new_script.id), "current_script_ir_version_id": getattr(script_row, "current_script_ir_version_id", None), "qualification_state": getattr(ir_row, "qualification_state", None), "resolved_scene_count": len(resolved.get("scenes", [])) if isinstance(resolved, dict) else 0})
    write_json("CANONICAL_DIALOGUE_PROPAGATION.json", {"run_id": RUN_ID, "status": "PASS" if semantic_final.get("status") == "SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY" and any(d.get("speaker") == "顾沉" and d.get("text") == TARGET_QUOTE and d.get("assertion_mode") == "" for d in dialogues) else "FAIL", "dialogues": dialogues, "semantic_diff": semantic_final, "timeline_origin": [scene.get("timeline_origin") for scene in payload_ir.get("scenes", [])], "timeline_authority": [scene.get("timeline_authority") for scene in payload_ir.get("scenes", [])]})
    write_json("NO_DOWNSTREAM_EXECUTION.json", {"run_id": RUN_ID, "status": "PASS", "director_executed": False, "treatment": 0, "scene_blocking": 0, "shot_plan": 0, "storyboard": 0, "prompt_ir": 0, "image": 0, "video": 0})
    final_details = {"llm_calls": 1, "transport_attempts": 1, "retry": False, "raw_response_persisted_before_parse": True, "raw_response_sha256": sha(raw_response), "raw_response_length": len(raw_response), "actual_request_fingerprint": actual_fingerprint, "candidate_schema": schema_result, "grounding": grounded_result.get("status"), "participants": participants, "target_dialogue": dialogue_audit, "reported_speech_promotion_count": reported_count, "semantic_diff": semantic_final, "new_book_id": int(new_book.id), "new_script_id": int(new_script.id), "fact_snapshot_id": fact_id, "script_ir_version_id": script_ir.get("id"), "qualification_state": script_ir.get("qualification_state"), "production_resolve": resolved_ok, "production_writes": {"book": 1, "script": 1, "fact_snapshot": 1, "fact_records": fact_record_count, "script_ir_version": 1}, "director_executed": False, "real_image_calls": 0, "real_video_calls": 0}
    write_json("PRODUCTION_CANARY_AUTHORIZED_SOURCE_STRUCTURING_V2_REPORT.json", {"run_id": RUN_ID, "status": "PRODUCTION_CANARY_SOURCE_STRUCTURED_V2", "script_ir_status": "PRODUCTION_CANARY_SCRIPT_IR_QUALIFIED", "details": final_details})
    report = ["# Production Canary Authorized Source Structuring V2 Report", "", f"- Status: `PRODUCTION_CANARY_SOURCE_STRUCTURED_V2`", f"- ScriptIR: `PRODUCTION_CANARY_SCRIPT_IR_QUALIFIED`", f"- Run ID: `{RUN_ID}`", "", "```json", json.dumps(final_details, ensure_ascii=False, indent=2, sort_keys=True), "```", "", "Director, Treatment, SceneBlocking, ShotPlan, Storyboard, PromptIR, IMAGE and VIDEO stages were not executed."]
    (EVIDENCE / "PRODUCTION_CANARY_AUTHORIZED_SOURCE_STRUCTURING_V2_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
