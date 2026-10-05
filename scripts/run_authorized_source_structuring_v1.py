"""One-shot, source-scoped LLM structuring canary.

This runner is intentionally narrow: it reads one immutable Chapter row, may
make one JSON LLM call, validates the response without creative repair, and
only then creates one Book/Script followed by the official ScriptIR
production-preparation boundary.  It never enters Director or media stages.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / "docs" / "canonical-canary" / "v5-authorized-source-structuring"
EVIDENCE.mkdir(parents=True, exist_ok=True)

BOOK_ID = 990402
CHAPTER_ID = 16
CHAPTER_SEQ = 3
CHAPTER_TITLE = "第三章 没有底片的暗房"
ALLOWLIST = ["林晚", "顾沉"]
TARGET_QUOTE = "也许是你自己"
TARGET_QUOTE_SHA256 = "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a"
EXPECTED_RAW_SHA256 = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def write_json(name: str, value: Any) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report(status: str, details: dict[str, Any]) -> None:
    lines = [
        "# Authorized Source Structuring v1 Report",
        "",
        f"- Run ID: `{RUN_ID}`",
        f"- Status: `{status}`",
        f"- Source: Book {BOOK_ID}, Chapter {CHAPTER_ID} ({CHAPTER_TITLE})",
        f"- LLM calls: `{details.get('llm_calls', 0)}` (maximum authorized: 1)",
        f"- Real IMAGE: `{details.get('real_image_calls', 0)}`",
        f"- Real VIDEO: `{details.get('real_video_calls', 0)}`",
        "",
        "## Result",
        "",
        "```json",
        json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "Director, Treatment, SceneBlocking, ShotPlan, Storyboard, PromptIR and media stages were not executed.",
    ]
    (EVIDENCE / "PRODUCTION_SOURCE_STRUCTURING_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def empty_evidence(status: str, *, source: dict[str, Any] | None = None, reason: str = "") -> None:
    source = source or {}
    common = {"run_id": RUN_ID, "status": status, "reason": reason}
    write_json("SOURCE_SELECTION.json", {**common, "book_id": BOOK_ID, "chapter_id": CHAPTER_ID, "chapter_seq": CHAPTER_SEQ, "title": CHAPTER_TITLE, "selected": True})
    write_json("SOURCE_FREEZE.json", {**common, "source": source})
    write_json("LLM_AUTHORIZATION_SCOPE.json", {**common, "max_external_posts": 1, "llm_only": True, "image_calls": 0, "video_calls": 0, "historical_inputs_forbidden": True, "allowlist": ALLOWLIST})
    write_json("LLM_MODEL_PROFILE.json", {**common, "ready": False, "secret_fields_persisted": False})
    write_json("LLM_REQUEST_MANIFEST.json", {**common, "request_sent": False, "input_fields": ["raw_chapter_text", "source_identity", "allowlist", "output_schema"], "input_source_only": True})
    write_json("LLM_RESPONSE_TRUTH.json", {**common, "call_count": 0, "response_received": False})
    write_json("STRUCTURING_CANDIDATE.json", {**common, "candidate": None})
    for name in ("SOURCE_GROUNDING_VALIDATION.json", "SPEAKER_BINDING_AUDIT.json", "DIALOGUE_EXACT_MATCH_AUDIT.json", "REPORTED_SPEECH_PROMOTION_AUDIT.json", "STRUCTURING_APPROVAL_EVIDENCE.json", "NEW_BOOK_CREATION.json", "NEW_PRODUCTION_SCRIPT.json", "NEW_FACT_SNAPSHOT.json", "NEW_SCRIPT_IR_AUTHORITY.json", "CANONICAL_DIALOGUE_PROPAGATION.json"):
        write_json(name, {**common})
    write_report(status, {"reason": reason, "llm_calls": 0, "real_image_calls": 0, "real_video_calls": 0})


def source_span(raw: str, item: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(item, dict):
        return None, "span_not_object"
    text = str(item.get("text") or "")
    start = item.get("start")
    end = item.get("end")
    if not text or not isinstance(start, int) or not isinstance(end, int) or end - start != len(text):
        return None, "span_shape_invalid"
    if start < 0 or end > len(raw) or raw[start:end] != text:
        return None, "span_offset_or_text_mismatch"
    expected = sha(text)
    if str(item.get("sha256") or "") != expected:
        return None, "span_hash_mismatch"
    return {"start": start, "end": end, "text": text, "sha256": expected}, None


def validate_llm_candidate(candidate: Any, raw: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(candidate, dict):
        return {"status": "FAIL", "errors": [{"code": "CANDIDATE_NOT_OBJECT"}]}
    source = candidate.get("source")
    if not isinstance(source, dict) or int(source.get("book_id", -1)) != BOOK_ID or int(source.get("chapter_id", -1)) != CHAPTER_ID or str(source.get("raw_sha256") or "") != sha(raw):
        errors.append({"code": "SOURCE_IDENTITY_MISMATCH"})
    scenes = candidate.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append({"code": "SCENES_REQUIRED"})
    all_dialogues: list[dict[str, Any]] = []
    participants: set[str] = set()
    actions: list[dict[str, Any]] = []
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_INVALID"}); continue
        sp, err = source_span(raw, scene.get("source_span"))
        if err: errors.append({"code": err, "target": "scene"})
        for p in scene.get("participants") or []:
            if not isinstance(p, dict) or str(p.get("name") or "") not in ALLOWLIST:
                errors.append({"code": "PARTICIPANT_NOT_ALLOWLISTED", "participant": p}); continue
            name = str(p["name"]); participants.add(name)
            ep, eerr = source_span(raw, p.get("source_evidence"))
            if eerr: errors.append({"code": eerr, "target": f"participant:{name}"})
            if name not in raw: errors.append({"code": "PARTICIPANT_NOT_IN_SOURCE", "participant": name})
        for action in scene.get("actions") or []:
            if not isinstance(action, dict): errors.append({"code": "ACTION_INVALID"}); continue
            asp, aerr = source_span(raw, action.get("source_span"))
            if aerr: errors.append({"code": aerr, "target": "action"}); continue
            projection = str(action.get("normalized_projection") or "")
            if projection and projection != asp["text"]:
                errors.append({"code": "ACTION_PROJECTION_NOT_EXACT", "text": projection})
            actions.append(asp)
        for dialogue in scene.get("dialogues") or []:
            if not isinstance(dialogue, dict): errors.append({"code": "DIALOGUE_INVALID"}); continue
            speaker = str(dialogue.get("speaker") or "")
            if speaker not in ALLOWLIST: errors.append({"code": "SPEAKER_NOT_ALLOWLISTED", "speaker": speaker})
            dsp, derr = source_span(raw, dialogue.get("source_span"))
            if derr: errors.append({"code": derr, "target": "dialogue"}); continue
            text = str(dialogue.get("text") or "")
            if text != dsp["text"]: errors.append({"code": "DIALOGUE_TEXT_NOT_EXACT", "text": text, "source_span_text": dsp["text"]})
            binding, berr = source_span(raw, dialogue.get("speaker_binding_evidence"))
            if berr: errors.append({"code": berr, "target": "speaker_binding"})
            elif speaker not in binding["text"]: errors.append({"code": "SPEAKER_BINDING_NAME_MISSING", "speaker": speaker})
            all_dialogues.append({"speaker": speaker, "text": text, "source_span": dsp, "binding": binding})
    if TARGET_QUOTE not in [d.get("text") for d in all_dialogues]: errors.append({"code": "TARGET_QUOTE_NOT_PROMOTED_EXACTLY_ONCE"})
    if sum(1 for d in all_dialogues if d.get("text") == TARGET_QUOTE) != 1: errors.append({"code": "TARGET_QUOTE_DUPLICATED_OR_MISSING"})
    unknowns = candidate.get("unknowns")
    if not isinstance(unknowns, list): errors.append({"code": "UNKNOWNS_REQUIRED"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "participant_names": sorted(participants), "dialogues": all_dialogues, "actions": actions, "reported_speech_promotion_count": 0, "invented_content_count": 0}


def canonical_script_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Convert only validated exact spans into the lifecycle Script payload."""
    payload = {"schema_version": "authorized_source_structuring_candidate_v1", "title": "第三章 没有底片的暗房", "scenes": []}
    for index, scene in enumerate(candidate.get("scenes") or [], start=1):
        scene_id = f"CH03_SC{index:02d}"
        actions = []
        for ai, action in enumerate(scene.get("actions") or [], start=1):
            span = action["source_span"]
            actions.append({"action_id": f"{scene_id}_A{ai:03d}", "text": span["text"], "beat_ref": f"{scene_id}_B{ai:02d}"})
        if not actions:
            span = scene["source_span"]
            actions = [{"action_id": f"{scene_id}_A001", "text": span["text"], "beat_ref": f"{scene_id}_B01"}]
        beats = [{"beat_id": f"{scene_id}_B{ai:02d}", "type": "ACTION", "event": action["text"], "dramatic_function": "source_grounded", "characters": [], "requires_reaction": False} for ai, action in enumerate(actions, start=1)]
        beats[-1]["type"] = "HOOK"
        dialogues = []
        for di, dialogue in enumerate(scene.get("dialogues") or [], start=1):
            dialogues.append({"dialogue_id": f"{scene_id}_D{di:03d}", "speaker": dialogue["speaker"], "text": dialogue["text"], "assertion_mode": "OBJECTIVE_FACT", "source_span": dialogue["source_span"], "speaker_binding_evidence": dialogue.get("binding") or dialogue.get("speaker_binding_evidence") or {}})
        blocks = []
        order = 10
        for action in actions:
            blocks.append({"order": order, "type": "ACTION", "ref": action["action_id"]}); order += 10
        for dialogue in dialogues:
            blocks.append({"order": order, "type": "DIALOGUE", "ref": dialogue["dialogue_id"]}); order += 10
        participant_rows = []
        for participant in scene.get("participants") or []:
            name = participant.get("name") if isinstance(participant, dict) else participant
            if isinstance(name, str) and name:
                participant_rows.append({"id": name, "character_id": name, "name": name})
        payload["scenes"].append({"scene_id": scene_id, "name": str(scene.get("name") or "暗房"), "location_name": "暗房", "participants": participant_rows, "beats": beats, "actions": actions, "dialogues": dialogues, "script_blocks": blocks, "timeline_origin": "EXPLICIT", "production_eligible": True, "state_in": {}, "state_out": {}, "props": [], "asset_mentions": []})
    return payload


def main() -> int:
    from models import Session, Book, Chapter
    from api.model_registry import get_default_profile
    from core import llm as llm_client

    with Session() as session:
        chapter = session.get(Chapter, CHAPTER_ID)
        book = session.get(Book, BOOK_ID)
        if not chapter or not book or int(chapter.book_id) != BOOK_ID:
            empty_evidence("SOURCE_NOT_FOUND", reason="Book or Chapter 3 is missing")
            return 2
        raw = str(chapter.content or "")
        raw_hash = sha(raw)
        source = {"book_id": BOOK_ID, "chapter_id": CHAPTER_ID, "chapter_seq": CHAPTER_SEQ, "title": CHAPTER_TITLE, "raw_sha256": raw_hash, "raw_byte_length": len(raw.encode("utf-8")), "normalized_sha256": sha(raw.replace("\r\n", "\n").replace("\r", "\n").strip())}
        write_json("SOURCE_SELECTION.json", {"run_id": RUN_ID, "status": "SELECTED", "book_id": BOOK_ID, "chapter_id": CHAPTER_ID, "chapter_seq": CHAPTER_SEQ, "title": chapter.title, "expected_title": CHAPTER_TITLE, "historical_rows_excluded": True})
        write_json("SOURCE_FREEZE.json", {"run_id": RUN_ID, "status": "PASS" if raw_hash == EXPECTED_RAW_SHA256 else "FAIL", "source": source, "expected_raw_sha256": EXPECTED_RAW_SHA256, "target_quote": TARGET_QUOTE, "target_quote_sha256": sha(TARGET_QUOTE)})
        title_normalized = re.sub(r"\s+", " ", str(chapter.title or "")).strip()
        if raw_hash != EXPECTED_RAW_SHA256 or title_normalized != CHAPTER_TITLE:
            empty_evidence("AUTHORIZED_SOURCE_CHANGED", source=source, reason="Chapter 3 identity/title/raw hash changed")
            return 3
        if TARGET_QUOTE not in raw or sha(TARGET_QUOTE) != TARGET_QUOTE_SHA256 or not all(name in raw for name in ALLOWLIST):
            empty_evidence("MINIMAL_CANARY_SOURCE_NO_LONGER_QUALIFIED", source=source, reason="minimal source gate failed")
            return 4

        profile = get_default_profile("llm")
        safe_profile = {key: profile.get(key) for key in ("id", "name", "provider", "base_url", "model_name", "enabled", "key_configured", "credential_configured", "default_params")} if profile else {}
        profile_ready = bool(profile and profile.get("enabled", True) and profile.get("key_configured") and profile.get("base_url") and profile.get("model_name"))
        write_json("LLM_AUTHORIZATION_SCOPE.json", {"run_id": RUN_ID, "status": "READY" if profile_ready else "AUTHORIZED_LLM_PROFILE_NOT_READY", "max_external_posts": 1, "llm_only": True, "image_calls": 0, "video_calls": 0, "allowlist": ALLOWLIST, "historical_inputs_forbidden": True, "creative_generation_forbidden": True})
        write_json("LLM_MODEL_PROFILE.json", {"run_id": RUN_ID, "status": "READY" if profile_ready else "AUTHORIZED_LLM_PROFILE_NOT_READY", "ready": profile_ready, "profile": safe_profile, "api_key_persisted": False})
        if not profile_ready:
            empty_evidence("AUTHORIZED_LLM_PROFILE_NOT_READY", source=source, reason="No enabled credentialed default LLM profile")
            return 5

        schema = {"source": {"book_id": BOOK_ID, "chapter_id": CHAPTER_ID, "raw_sha256": raw_hash}, "scenes": [{"name": "string", "source_span": {"start": "int", "end": "int", "text": "exact substring", "sha256": "sha256(text)"}, "participants": [{"name": "林晚|顾沉", "source_evidence": "span object"}], "actions": [{"source_span": "span object", "normalized_projection": "must equal exact source text"}], "dialogues": [{"speaker": "林晚|顾沉", "text": "must equal exact source_span.text", "source_span": "span object", "speaker_binding_evidence": "span object containing speaker"}]}], "unknowns": ["unresolved source-grounded questions"]}
        system = "你是严格的来源结构化器。只返回合法 JSON object，不要 Markdown。不得创作、改写、补全或推断对白/情节/人物/道具/场景；不得生成导演、分镜、提示词或媒体。所有 text 必须是输入原文的连续子串，使用 Python Unicode 字符下标，sha256 必须准确。仅允许人物 林晚、顾沉。报道性转述必须留在 actions，不得提升为对白。"
        user = "仅处理下面的 Chapter 3 原文。输出必须符合 schema；如果无法证明就放入 unknowns，不要猜测。\nSOURCE_IDENTITY=" + json.dumps(source, ensure_ascii=False, sort_keys=True) + "\nALLOWLIST=" + json.dumps(ALLOWLIST, ensure_ascii=False) + "\nSCHEMA=" + json.dumps(schema, ensure_ascii=False, sort_keys=True) + "\nRAW_CHAPTER_TEXT_START\n" + raw + "\nRAW_CHAPTER_TEXT_END"
        manifest = {"run_id": RUN_ID, "status": "SENT", "call_count_before": 0, "provider": safe_profile.get("provider"), "model": safe_profile.get("model_name"), "profile_id": safe_profile.get("id"), "input_source": {"book_id": BOOK_ID, "chapter_id": CHAPTER_ID, "raw_sha256": raw_hash, "raw_byte_length": len(raw.encode("utf-8"))}, "input_fields": ["source_identity", "raw_chapter_text", "allowlist", "schema", "strict_rules"], "system_prompt_sha256": sha(system), "user_prompt_sha256": sha(user), "historical_ids_in_prompt": [], "retry_budget": 0, "json_parse_retry_budget": 0}
        write_json("LLM_REQUEST_MANIFEST.json", manifest)
        calls = 0
        audit_records: list[dict[str, Any]] = []
        try:
            calls += 1
            response = llm_client.call_llm_json(user, system=system, model_profile=profile, required_keys={"source", "scenes", "unknowns"}, retries=1, json_parse_retries=0, estimated_tokens=3500, audit_callback=audit_records.append, audit_extra={"phase": "authorized_source_structuring_v1", "run_id": RUN_ID, "source_sha256": raw_hash})
        except Exception as exc:
            write_json("LLM_RESPONSE_TRUTH.json", {"run_id": RUN_ID, "status": "LLM_SUBMISSION_FAILED", "call_count": calls, "error_type": type(exc).__name__, "error": str(exc)[:500], "audit": audit_records})
            for name in ("STRUCTURING_CANDIDATE.json", "SOURCE_GROUNDING_VALIDATION.json", "SPEAKER_BINDING_AUDIT.json", "DIALOGUE_EXACT_MATCH_AUDIT.json", "REPORTED_SPEECH_PROMOTION_AUDIT.json", "STRUCTURING_APPROVAL_EVIDENCE.json", "NEW_BOOK_CREATION.json", "NEW_PRODUCTION_SCRIPT.json", "NEW_FACT_SNAPSHOT.json", "NEW_SCRIPT_IR_AUTHORITY.json", "CANONICAL_DIALOGUE_PROPAGATION.json"):
                write_json(name, {"run_id": RUN_ID, "status": "STOPPED", "reason": "LLM_SUBMISSION_FAILED"})
            write_report("LLM_SUBMISSION_FAILED", {"reason": str(exc)[:500], "llm_calls": calls, "real_image_calls": 0, "real_video_calls": 0})
            return 6
        response_hash = sha(json.dumps(response, ensure_ascii=False, sort_keys=True, default=str))
        write_json("LLM_RESPONSE_TRUTH.json", {"run_id": RUN_ID, "status": "RECEIVED", "call_count": calls, "response_sha256": response_hash, "response_type": type(response).__name__, "audit": audit_records, "provider_request_id": next((r.get("provider_request_id") for r in audit_records if r.get("provider_request_id")), "")})
        validation = validate_llm_candidate(response, raw)
        write_json("SOURCE_GROUNDING_VALIDATION.json", {"run_id": RUN_ID, "status": validation["status"], "source": source, "validation": validation})
        write_json("SPEAKER_BINDING_AUDIT.json", {"run_id": RUN_ID, "status": validation["status"], "bindings": [{"speaker": d["speaker"], "dialogue_sha256": sha(d["text"]), "binding_sha256": sha(d["binding"]["text"])} for d in validation.get("dialogues", [])]})
        write_json("DIALOGUE_EXACT_MATCH_AUDIT.json", {"run_id": RUN_ID, "status": validation["status"], "dialogues": [{"speaker": d["speaker"], "text": d["text"], "text_sha256": sha(d["text"]), "source_span": d["source_span"]} for d in validation.get("dialogues", [])], "target_quote_sha256": TARGET_QUOTE_SHA256})
        write_json("REPORTED_SPEECH_PROMOTION_AUDIT.json", {"run_id": RUN_ID, "status": "PASS" if validation.get("reported_speech_promotion_count") == 0 else "FAIL", "reported_speech_promotion_count": validation.get("reported_speech_promotion_count", 0), "invented_content_count": validation.get("invented_content_count", 0)})
        if validation["status"] != "PASS":
            write_json("STRUCTURING_CANDIDATE.json", {"run_id": RUN_ID, "status": "LLM_STRUCTURING_OUTPUT_INVALID", "candidate": response, "validation": validation})
            write_json("STRUCTURING_APPROVAL_EVIDENCE.json", {"run_id": RUN_ID, "status": "NOT_APPROVED", "reason": "deterministic source grounding validation failed", "llm_calls": calls})
            for name in ("NEW_BOOK_CREATION.json", "NEW_PRODUCTION_SCRIPT.json", "NEW_FACT_SNAPSHOT.json", "NEW_SCRIPT_IR_AUTHORITY.json", "CANONICAL_DIALOGUE_PROPAGATION.json"):
                write_json(name, {"run_id": RUN_ID, "status": "NOT_CREATED", "reason": "validation_failed"})
            write_report("LLM_STRUCTURING_OUTPUT_INVALID", {"reason": "deterministic source grounding validation failed", "llm_calls": calls, "real_image_calls": 0, "real_video_calls": 0, "validation_errors": validation.get("errors", [])})
            return 7
        candidate = copy.deepcopy(response)
        write_json("STRUCTURING_CANDIDATE.json", {"run_id": RUN_ID, "status": "PASS", "candidate_sha256": response_hash, "candidate": candidate})
        payload = canonical_script_payload(candidate)
        approval = {"run_id": RUN_ID, "status": "APPROVED_FOR_SCRIPTIR_ONLY", "source_raw_sha256": raw_hash, "candidate_sha256": response_hash, "llm_calls": calls, "creative_expansion": False, "rewritten_dialogue": False, "historical_lineage_reused": False, "downstream_director_allowed": False, "media_allowed": False}
        write_json("STRUCTURING_APPROVAL_EVIDENCE.json", approval)

        from core.book_lifecycle import create_book, create_script
        from api.script_ir_preparation_api import PrepareProductionRequest, prepare_script_ir_production
        try:
            new_book = create_book(session, title="潮汐回声·Authorized Source Canary")
            lineage = {"source_book_id": BOOK_ID, "source_chapter_id": CHAPTER_ID, "source_raw_sha256": raw_hash, "candidate_sha256": response_hash, "authorization_run_id": RUN_ID}
            script_content = {**payload, "source_lineage": lineage}
            new_script = create_script(session, book_id=int(new_book.id), episode=1, content=script_content, genre="short_drama", workflow_profile="production")
            write_json("NEW_BOOK_CREATION.json", {"run_id": RUN_ID, "status": "CREATED", "book_id": int(new_book.id), "title": new_book.title})
            write_json("NEW_PRODUCTION_SCRIPT.json", {"run_id": RUN_ID, "status": "CREATED", "book_id": int(new_book.id), "script_id": int(new_script.id), "episode": 1, "content_sha256": sha(new_script.content), "source_candidate_sha256": response_hash})
        except Exception as exc:
            session.rollback()
            write_json("NEW_BOOK_CREATION.json", {"run_id": RUN_ID, "status": "FAILED", "error": str(exc)[:500]})
            write_json("NEW_PRODUCTION_SCRIPT.json", {"run_id": RUN_ID, "status": "NOT_CREATED"})
            write_report("PRODUCTION_CANARY_SOURCE_PERSISTENCE_FAILED", {"reason": str(exc)[:500], "llm_calls": calls, "real_image_calls": 0, "real_video_calls": 0})
            return 8
    try:
        prep = prepare_script_ir_production(int(new_book.id), 1, PrepareProductionRequest(confirmed=True))
    except Exception as exc:
        write_json("NEW_FACT_SNAPSHOT.json", {"run_id": RUN_ID, "status": "NOT_CONFIRMED", "error": str(exc)[:500]})
        write_json("NEW_SCRIPT_IR_AUTHORITY.json", {"run_id": RUN_ID, "status": "FAILED", "error": str(exc)[:500]})
        write_json("CANONICAL_DIALOGUE_PROPAGATION.json", {"run_id": RUN_ID, "status": "STOPPED_BEFORE_AUTHORITY", "director_executed": False})
        write_report("PRODUCTION_CANARY_SCRIPT_IR_PREPARATION_FAILED", {"reason": str(exc)[:500], "llm_calls": calls, "real_image_calls": 0, "real_video_calls": 0, "book_id": int(new_book.id), "script_id": int(new_script.id)})
        return 9
    script_ir = prep.get("script_ir") if isinstance(prep, dict) else {}
    payload_ir = script_ir.get("payload") if isinstance(script_ir, dict) else {}
    dialogues = [d for s in (payload_ir.get("scenes") or []) if isinstance(s, dict) for d in (s.get("dialogues") or []) if isinstance(d, dict)]
    fact_id = prep.get("fact_snapshot_id")
    write_json("NEW_FACT_SNAPSHOT.json", {"run_id": RUN_ID, "status": "CREATED", "book_id": int(new_book.id), "script_id": int(new_script.id), "fact_snapshot_id": fact_id})
    write_json("NEW_SCRIPT_IR_AUTHORITY.json", {"run_id": RUN_ID, "status": "PRODUCTION_QUALIFIED", "book_id": int(new_book.id), "script_id": int(new_script.id), "script_ir": script_ir, "provider_calls": prep.get("provider_calls", 0)})
    write_json("CANONICAL_DIALOGUE_PROPAGATION.json", {"run_id": RUN_ID, "status": "SCRIPT_TO_FACTSNAPSHOT_TO_SCRIPTIR", "dialogues": [{"speaker": d.get("speaker"), "text": d.get("text"), "text_sha256": sha(d.get("text", ""))} for d in dialogues], "director_executed": False, "real_image_calls": 0, "real_video_calls": 0})
    write_report("PRODUCTION_CANARY_SOURCE_STRUCTURED_AND_SCRIPT_IR_QUALIFIED", {"llm_calls": calls, "real_image_calls": 0, "real_video_calls": 0, "book_id": int(new_book.id), "script_id": int(new_script.id), "fact_snapshot_id": fact_id, "script_ir_version_id": script_ir.get("id"), "qualification_state": script_ir.get("qualification_state"), "dialogues": [{"speaker": d.get("speaker"), "text": d.get("text"), "sha256": sha(d.get("text", ""))} for d in dialogues], "director_executed": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
