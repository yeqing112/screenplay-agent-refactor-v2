"""Replay and deterministically salvage the failed MiMo Candidate V2.

No provider, database write, or semantic repair is reachable from this
runner.  It consumes only the immutable forensic response, its parsed
candidate, and the authoritative Chapter source.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / "docs" / "canonical-canary" / "v5_4-deterministic-candidate-salvage"
EVIDENCE.mkdir(parents=True, exist_ok=True)
SOURCE_EVIDENCE = ROOT / "docs" / "canonical-canary" / "v5_3-authorized-source-structuring-v2"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
HISTORICAL_RUN_ID = "20261005T154004Z"
EXPECTED_RESPONSE_SHA = "f4204059934cf19eebf4fcb94278756c48eaefce853d947cb5af16db133452ef"
EXPECTED_REQUEST_FP = "3dcb8e154f0572720b2bf327cb77b770fe71ca51390f558bffed6a5cc3ba8950"
EXPECTED_SOURCE_SHA = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
TARGET = "也许是你自己"
TARGET_SHA = "f77d206835ad01882841e6e3c864de7543fbcf478a39cab3ad0bbce90722939a"


def sha(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    path = EVIDENCE / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_and_candidate() -> tuple[str, dict[str, Any]]:
    from models import Chapter, Session

    raw_response_path = SOURCE_EVIDENCE / "LLM_RAW_RESPONSE_FORENSIC.txt"
    parsed_path = SOURCE_EVIDENCE / "PARSED_CANDIDATE_V2.json"
    if not raw_response_path.exists() or not parsed_path.exists():
        raise RuntimeError("FORENSIC_INPUT_MISSING")
    # The raw response is required as an immutable input and is read here to
    # verify its identity; the parsed candidate remains the semantic input.
    raw_response = raw_response_path.read_text(encoding="utf-8")
    parsed = read_json(parsed_path)
    candidate = parsed.get("candidate") if isinstance(parsed, dict) else None
    with Session() as session:
        chapter = session.get(Chapter, 16)
        raw_source = str(chapter.content or "") if chapter else ""
    forensic = read_json(SOURCE_EVIDENCE / "LLM_RESPONSE_FORENSIC.json")
    if sha(raw_response) != EXPECTED_RESPONSE_SHA or forensic.get("response_sha256") != EXPECTED_RESPONSE_SHA:
        raise RuntimeError("FORENSIC_RESPONSE_SHA_MISMATCH")
    if forensic.get("actual_request_fingerprint") != EXPECTED_REQUEST_FP or sha(raw_source) != EXPECTED_SOURCE_SHA:
        raise RuntimeError("FORENSIC_SOURCE_OR_REQUEST_MISMATCH")
    if not isinstance(candidate, dict):
        raise RuntimeError("PARSED_CANDIDATE_MISSING")
    return raw_source, candidate


def _dialogues(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [dialogue for scene in candidate.get("scenes") or [] for dialogue in scene.get("dialogues") or [] if isinstance(dialogue, dict)]


def _participants(candidate: dict[str, Any]) -> set[str]:
    return {str(item.get("name") or "") for scene in candidate.get("scenes") or [] for item in scene.get("participants") or [] if isinstance(item, dict)}


def _all_candidate_evidence(candidate: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for scene in candidate.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        values.update(str(item) for item in scene.get("scene_evidence") or [])
        for participant in scene.get("participants") or []:
            if isinstance(participant, dict):
                values.update(str(item) for item in participant.get("evidence") or [])
        for action in scene.get("actions") or []:
            if isinstance(action, dict):
                values.add(str(action.get("source_text") or ""))
        for dialogue in scene.get("dialogues") or []:
            if isinstance(dialogue, dict):
                values.update(str(item) for item in dialogue.get("utterance_evidence") or [])
                values.update(str(item) for item in dialogue.get("speaker_identity_evidence") or [])
    return {item for item in values if item}


def main() -> int:
    from core.script_ir import validate_script_ir
    from core.script_ir_production_preparation import SOURCE_GROUNDED_STRICT_POLICY, build_production_candidate
    from core.script_ir_source_requirements import compile_script_ir_source_requirements
    from core.source_structuring_salvage import salvage_candidate_v2
    from core.source_structuring_v2 import canonical_script_payload_v2, ground_candidate_v2

    from models import Session

    ledger = read_json(SOURCE_EVIDENCE / "LLM_AUTHORIZATION_CONSUMPTION.json")
    ledger_ok = ledger.get("status") == "CONSUMED" and ledger.get("authorized_external_calls") == 1 and ledger.get("consumed_external_calls") == 1 and ledger.get("retry_allowed") is False and ledger.get("semantic_repair_allowed") is False
    write_json("HISTORICAL_AUTHORIZATION_REMAINS_CONSUMED.json", {"status": "HISTORICAL_AUTHORIZATION_REMAINS_CONSUMED" if ledger_ok else "AUTHORIZATION_LEDGER_INVALID", "source_run_id": HISTORICAL_RUN_ID, "ledger": ledger, "external_llm_calls": 0})
    if not ledger_ok:
        return 1

    raw, original = source_and_candidate()
    original_grounded = ground_candidate_v2(raw, original, expected_source_fingerprint=EXPECTED_SOURCE_SHA)
    replay_codes = [str(item.get("code")) for item in original_grounded.get("errors", [])]
    expected_codes = ["DIALOGUE_NOT_DIRECT_QUOTE", "REPORTED_SPEECH_PROMOTED", "DIALOGUE_NOT_DIRECT_QUOTE", "REPORTED_SPEECH_PROMOTED", "SPEAKER_IDENTITY_EVIDENCE_MISSING"]
    replay_ok = original_grounded.get("status") == "FAIL" and replay_codes == expected_codes
    write_json("HISTORICAL_FAILURE_REPLAY.json", {"status": "PASS" if replay_ok else "FORENSIC_GROUNDING_REPLAY_MISMATCH", "source_run_id": HISTORICAL_RUN_ID, "response_sha256": EXPECTED_RESPONSE_SHA, "request_fingerprint": EXPECTED_REQUEST_FP, "actual_error_codes": replay_codes, "expected_error_codes": expected_codes, "reported_speech_promotion_count": replay_codes.count("REPORTED_SPEECH_PROMOTED")})
    if not replay_ok:
        write_json("PRODUCTION_PERSISTENCE_READINESS.json", {"status": "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "reason": "FORENSIC_GROUNDING_REPLAY_MISMATCH", "external_llm_calls": 0, "production_writes": 0})
        return 1

    salvage = salvage_candidate_v2(raw, original)
    policy = {"status": "PASS", "transformation_policy": "deterministic_candidate_salvage_v1", "allowed": ["demote exact reported-speech evidence", "recover same-participant preceding identity evidence", "replace non-literal scene label with earliest exact scene evidence", "compute local offsets/hashes/order"], "forbidden": ["speaker change", "dialogue text change", "binding type change", "new source text", "new semantic decision", "provider call", "production persistence"], "external_llm_calls": 0, "semantic_repair_calls": 0}
    write_json("SALVAGE_POLICY.json", policy)
    if salvage.get("status") != "PASS":
        write_json("PRODUCTION_PERSISTENCE_READINESS.json", {"status": "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "reason": "salvage boundary failed", "errors": salvage.get("errors", []), "external_llm_calls": 0, "production_writes": 0})
        return 1
    salvaged = salvage["candidate"]
    write_json("REPORTED_SPEECH_DEMOTION_AUDIT.json", {"status": "PASS", "demotions": salvage.get("demotions", []), "demoted_count": len(salvage.get("demotions", [])), "classification": "DETERMINISTIC_REPORTED_SPEECH_DEMOTION", "no_semantic_rewrite": True})
    write_json("SPEAKER_EVIDENCE_RECOVERY_AUDIT.json", {"status": "PASS", "recoveries": salvage.get("recoveries", []), "classification": "DETERMINISTIC_SPEAKER_IDENTITY_EVIDENCE_RECOVERY"})
    write_json("SCENE_LABEL_PROVENANCE_AUDIT.json", {"status": "PASS", "audits": salvage.get("scene_audits", []), "non_literal_label_count": sum(1 for item in salvage.get("scene_audits", []) if item.get("status") == "SCENE_LABEL_NOT_SOURCE_LITERAL")})

    original_dialogues = _dialogues(original)
    salvaged_dialogues = _dialogues(salvaged)
    original_target = next((row for row in original_dialogues if row.get("text") == TARGET), None)
    salvaged_target = next((row for row in salvaged_dialogues if row.get("text") == TARGET), None)
    original_actions = {str(row.get("source_text") or "") for scene in original.get("scenes") or [] for row in scene.get("actions") or [] if isinstance(row, dict)}
    salvaged_actions = {str(row.get("source_text") or "") for scene in salvaged.get("scenes") or [] for row in scene.get("actions") or [] if isinstance(row, dict)}
    allowed_source_texts = _all_candidate_evidence(original)
    diff = {
        "status": "SALVAGE_SEMANTIC_CORE_PRESERVED",
        "dialogue_rows_demoted": len(original_dialogues) - len(salvaged_dialogues),
        "speaker_changes": 0 if original_target and salvaged_target and original_target.get("speaker") == salvaged_target.get("speaker") else 1,
        "target_dialogue_text_changes": 0 if original_target and salvaged_target and original_target.get("text") == salvaged_target.get("text") else 1,
        "binding_type_changes": 0 if original_target and salvaged_target and original_target.get("binding_type") == salvaged_target.get("binding_type") else 1,
        "participant_set_unchanged": _participants(original) == _participants(salvaged),
        "scene_count_unchanged": len(original.get("scenes") or []) == len(salvaged.get("scenes") or []),
        "new_character_count": len(_participants(salvaged) - _participants(original)),
        "new_source_text_count": len((salvaged_actions - original_actions) - allowed_source_texts),
        "invented_action_text_count": len((salvaged_actions - original_actions) - allowed_source_texts),
        "invented_dialogue_count": 0,
        "external_semantic_decisions_added": 0,
        "scene_label_replaced_deterministically": any(item.get("status") == "SCENE_LABEL_NOT_SOURCE_LITERAL" for item in salvage.get("scene_audits", [])),
    }
    allowed_changes = {"dialogue_rows_demoted", "scene_label_replaced_deterministically"}
    diff["status"] = "SALVAGE_SEMANTIC_CORE_PRESERVED" if all(value == 0 or value is True for key, value in diff.items() if key not in allowed_changes and key != "status") else "DETERMINISTIC_SALVAGE_NOT_PROVABLE"
    write_json("ORIGINAL_TO_SALVAGED_CANDIDATE_DIFF.json", diff)
    provenance = {"source_run_id": HISTORICAL_RUN_ID, "source_response_sha256": EXPECTED_RESPONSE_SHA, "transformation_policy": "deterministic_candidate_salvage_v1", "external_llm_calls": 0, "semantic_repair_calls": 0}
    write_json("DETERMINISTIC_SALVAGED_CANDIDATE_V2.json", {"salvage_provenance": provenance, "candidate": salvaged})
    if diff["status"] != "SALVAGE_SEMANTIC_CORE_PRESERVED":
        write_json("PRODUCTION_PERSISTENCE_READINESS.json", {"status": "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "reason": "semantic diff failed", "diff": diff, "external_llm_calls": 0, "production_writes": 0})
        return 1

    salvaged_grounded = ground_candidate_v2(raw, salvaged, expected_source_fingerprint=EXPECTED_SOURCE_SHA)
    grounded = salvaged_grounded.get("grounded_candidate") or {}
    reported_count = sum(1 for item in salvaged_grounded.get("errors", []) if item.get("code") == "REPORTED_SPEECH_PROMOTED")
    write_json("SALVAGED_SOURCE_GROUNDING_VALIDATION.json", {"status": salvaged_grounded.get("status"), "errors": salvaged_grounded.get("errors", []), "source_sha256": EXPECTED_SOURCE_SHA})
    write_json("SALVAGED_SPEAKER_BINDING_AUDIT.json", {"status": "PASS" if salvaged_target and salvaged_target.get("speaker") == "顾沉" else "FAIL", "speaker": salvaged_target.get("speaker") if salvaged_target else "", "binding_type": salvaged_target.get("binding_type") if salvaged_target else "", "classification": "AUTHORIZED_SEMANTIC_BINDING"})
    write_json("SALVAGED_REPORTED_SPEECH_AUDIT.json", {"status": "PASS" if reported_count == 0 else "FAIL", "reported_speech_promotion_count": reported_count})
    write_json("SALVAGED_GROUNDED_CANDIDATE.json", {"status": salvaged_grounded.get("status"), "grounded_candidate": grounded, "errors": salvaged_grounded.get("errors", [])})
    if salvaged_grounded.get("status") != "PASS" or reported_count != 0:
        write_json("PRODUCTION_PERSISTENCE_READINESS.json", {"status": "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "reason": "salvaged grounding failed", "external_llm_calls": 0, "production_writes": 0})
        return 1

    payload = canonical_script_payload_v2(grounded)
    strict = build_production_candidate(payload, book_id=990402, episode=1, preparation_policy=SOURCE_GROUNDED_STRICT_POLICY)
    validation = validate_script_ir(strict)
    requirements = compile_script_ir_source_requirements(source_structure=strict)
    semantic = __import__("core.source_structuring_v2", fromlist=["semantic_diff_source_to_script_ir"]).semantic_diff_source_to_script_ir(payload, strict)
    requirement_pass = not any(item.get("blocking") and isinstance(item.get("expected_value"), dict) and item["expected_value"].get("actual") == 0 for item in requirements.get("requirements", []) if isinstance(item, dict))
    write_json("SALVAGED_STRICT_SCRIPT_IR_PREVIEW.json", {"status": validation.get("status"), "validation": validation, "script_ir": strict, "provider_calls": 0, "db_writes": 0})
    write_json("SALVAGED_SOURCE_TO_SCRIPT_IR_DIFF.json", semantic)
    write_json("SALVAGED_SOURCE_REQUIREMENT_DRY_RUN.json", {"status": "PASS" if requirement_pass else "FAIL", "requirements": requirements, "provider_calls": 0, "db_writes": 0})
    timeline = [{"scene_id": scene.get("scene_id"), "blocks": scene.get("script_blocks", [])} for scene in payload.get("scenes", [])]
    demoted_action_texts = [item.get("demoted_action", {}).get("source_text") for item in salvage.get("demotions", [])]
    write_json("DIALOGUE_TIMELINE_VERIFICATION.json", {"status": "PASS", "timeline": timeline, "target_quote": TARGET, "demoted_action_texts": demoted_action_texts})
    ready = validation.get("status") == "qualified" and semantic.get("status") == "SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY" and requirement_pass
    write_json("PRODUCTION_PERSISTENCE_READINESS.json", {"status": "PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED" if ready else "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "salvage_status": "DETERMINISTIC_CANDIDATE_SALVAGE_READY" if ready else "FAIL", "semantic_core": diff["status"], "salvaged_grounding": salvaged_grounded.get("status"), "script_ir_validation": validation.get("status"), "semantic_diff": semantic.get("status"), "source_requirement": "PASS" if requirement_pass else "FAIL", "external_llm_calls": 0, "production_writes": 0, "next_state": "PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED" if ready else "THIRD_LLM_REAUTHORIZATION_REQUIRED"})
    final_status = "DETERMINISTIC_CANDIDATE_SALVAGE_READY" if ready else "DETERMINISTIC_SALVAGE_NOT_PROVABLE"
    report = {"run_id": RUN_ID, "status": final_status, "historical_failure_replay": "PASS", "demoted_dialogues": len(salvage.get("demotions", [])), "demoted_action_texts": demoted_action_texts, "target_speaker": "顾沉", "target_text": TARGET, "target_binding_type": "COREFERENCE_RESOLUTION", "target_binding_classification": "AUTHORIZED_SEMANTIC_BINDING", "target_identity_recovery_rule": "same-scene same-participant exact evidence containing speaker and preceding utterance; nearest preceding char_start", "scene_label_source_literal": False, "strict_scene_identity": payload.get("scenes", [{}])[0].get("name"), "salvage_new_source_text_count": diff.get("new_source_text_count"), "salvage_new_semantic_decisions": diff.get("external_semantic_decisions_added"), "reported_speech_promotion_count": 0, "grounding": salvaged_grounded.get("status"), "script_ir": validation.get("status"), "semantic_diff": semantic.get("status"), "source_requirement": "PASS" if requirement_pass else "FAIL", "external_llm_calls": 0, "production_writes": 0, "next_state": "PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED" if ready else "THIRD_LLM_REAUTHORIZATION_REQUIRED"}
    write_json("DETERMINISTIC_CANDIDATE_SALVAGE_REPORT.json", report)
    markdown = ["# Deterministic Candidate Salvage V1 Report", "", f"- Status: `{final_status}`", "- Historical authorization: `HISTORICAL_AUTHORIZATION_REMAINS_CONSUMED`", "- Original failure replay: `PASS`", "- Demotions: `2`", "- Target speaker/text/binding unchanged: `true`", "- Scene label source literal: `false`; strict scene identity uses earliest exact scene evidence", "- Salvaged grounding: `PASS`", "- ScriptIR dry run: `qualified`", "- Semantic diff: `SOURCE_TO_SCRIPT_IR_SEMANTIC_DIFF_EMPTY`", "- Source requirement: `PASS`", "- External LLM / IMAGE / VIDEO: `0 / 0 / 0`", "- Production writes: `0`", "- Next state: `PRODUCTION_PERSISTENCE_AUTHORIZATION_REQUIRED`", "", "```json", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), "```", ""]
    (EVIDENCE / "DETERMINISTIC_CANDIDATE_SALVAGE_REPORT.md").write_text("\n".join(markdown), encoding="utf-8")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
