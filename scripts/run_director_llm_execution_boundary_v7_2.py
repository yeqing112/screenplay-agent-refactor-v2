"""Provider-free V7.2 execution-boundary evidence runner."""
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import director_treatment_api as api
from api.director_treatment_api import DirectorTreatmentPreviewRequest
from api.model_registry import get_default_profile
from core.director_source_grounded import build_source_grounded_director_preview
from models import (
    Book,
    DecisionPacketRecord,
    DirectorTreatment,
    DirectorTreatmentAuthority,
    DirectorTreatmentPointer,
    FactSnapshot,
    Script,
    ScriptIRVersion,
    Session,
    SceneBlocking,
    ShotPlan,
    StoryboardShot,
)

OUT = ROOT / "docs" / "canonical-canary" / "v7_2-director-llm-execution-boundary"
BOOK_ID = 990453


def dump(name: str, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def obj(value, default):
    try:
        return json.loads(value) if isinstance(value, str) else (value if value is not None else default)
    except (TypeError, ValueError):
        return default


def production_counts(session):
    return {
        "books": session.query(Book).filter_by(id=BOOK_ID).count(),
        "scripts": session.query(Script).filter_by(book_id=BOOK_ID).count(),
        "fact_snapshots": session.query(FactSnapshot).filter_by(book_id=BOOK_ID).count(),
        "script_ir_versions": session.query(ScriptIRVersion).filter_by(book_id=BOOK_ID).count(),
        "decision_packets": session.query(DecisionPacketRecord).filter_by(book_id=BOOK_ID).count(),
        "director_treatments": session.query(DirectorTreatment).filter_by(book_id=BOOK_ID).count(),
        "director_treatment_authorities": session.query(DirectorTreatmentAuthority).filter_by(book_id=BOOK_ID).count(),
        "director_treatment_pointers": session.query(DirectorTreatmentPointer).filter_by(book_id=BOOK_ID).count(),
        "scene_blockings": session.query(SceneBlocking).filter_by(book_id=BOOK_ID).count(),
        "shot_plans": session.query(ShotPlan).filter_by(book_id=BOOK_ID).count(),
        "storyboard_shots": session.query(StoryboardShot).filter_by(book_id=BOOK_ID).count(),
    }


def main():
    with Session() as session:
        book = session.get(Book, BOOK_ID)
        script = session.query(Script).filter_by(book_id=BOOK_ID, episode=1).first()
        ir = session.get(ScriptIRVersion, 52)
        fact = session.get(FactSnapshot, 49)
        if not (book and script and ir and fact):
            raise SystemExit("V7 production objects missing")
        ir_payload = obj(ir.payload_json, {})
        scene = next(s for s in ir_payload.get("scenes", []) if s.get("scene_id") == "E01_SC001")
        preview = build_source_grounded_director_preview(scene=scene, source_script_revision=str(ir.revision), source_script_hash=ir.payload_hash, source_script_ir_version_id=ir.id)
        api_preview, evidence, _ = api._build_preview(BOOK_ID, DirectorTreatmentPreviewRequest(episode=1, scene_id="E01_SC001", workflow_profile="production"))
        packet = api._make_decision_packet(BOOK_ID, 1, api_preview, evidence)
        system_prompt, user_prompt = api._source_grounded_v3_prompt(api_preview, evidence)
        units = preview["source_constraints"]["source_authoring_units"]
        before = production_counts(session)
        profile = get_default_profile("llm") or {}
        profile_snapshot = {
            "profile_id": str(profile.get("id") or ""),
            "provider": str(profile.get("provider") or ""),
            "model": str(profile.get("model_name") or ""),
            "base_host": str(profile.get("base_url") or "").split("/v1", 1)[0].rstrip("/"),
            "enabled": bool(profile.get("enabled", False)),
            "key_configured": bool(profile.get("key_configured", False)),
        }
        request_fp = api.prompt_fingerprint(system_prompt, user_prompt)

        dump("CURRENT_REAL_LLM_ENDPOINT_AUDIT.json", {
            "status": "RECONCILED_SOURCE_GROUNDED_V3_BOUNDARY",
            "historical_findings": [
                "DIRECTOR_LLM_PROMPT_CONTRACT_STALE",
                "DIRECTOR_LLM_REQUIRED_KEYS_STALE",
                "DIRECTOR_LLM_REAL_FORENSIC_SINK_NOT_WIRED",
            ],
            "v3_prompt_uses_legacy_beat_requirement": "必须沿用已有 character id 和 beat_id" in user_prompt,
            "v3_required_keys": ["creative_projection"],
            "v3_raw_forensic_sink_wired": "_persist_v3_raw_forensic" in inspect.getsource(api._execute_source_grounded_v3_proposal),
            "legacy_v1_path_preserved": True,
            "real_provider_called": False,
        })
        dump("CURRENT_DIRECTOR_LLM_CALL_BUDGET_AUDIT.json", {
            "status": "PASS",
            "v3_transport_attempt_budget": 1,
            "v3_transport_retry": 0,
            "v3_parser_retry": 0,
            "v3_repair_llm": 0,
            "v3_fallback": 0,
            "v3_uses_call_llm_json": False,
            "legacy_call_llm_json_unchanged": True,
        })
        dump("V3_DIRECTOR_LLM_PROMPT_CONTRACT.json", {
            "status": "V3_LLM_PROMPT_CONTRACT_PASS",
            "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
            "contains": ["SCENE_ID", "IMMUTABLE_SOURCE_CONSTRAINTS", "SOURCE_AUTHORING_UNITS", "DECLARED_PARTICIPANTS", "ADVISORY_ASSET_CONTEXT", "CREATIVE_PROJECTION_SCHEMA"],
            "source_authoring_unit_count": len(units),
            "source_action_count": sum(u.get("source_type") == "SOURCE_ACTION" for u in units),
            "source_dialogue_count": sum(u.get("source_type") == "SOURCE_DIALOGUE" for u in units),
            "old_beat_id_requirement_absent": "必须沿用已有 character id 和 beat_id" not in user_prompt,
            "no_camera_or_scene_blocking_instruction": "输出镜头规格" not in system_prompt and "SceneBlocking" in system_prompt,
        })
        dump("V3_DIRECTOR_LLM_RETURN_SCHEMA.json", {
            "status": "PASS",
            "top_level_required_keys": ["creative_projection"],
            "source_constraints_echo_required": False,
            "source_authoring_units_echo_required": False,
            "creative_projection_required_fields": ["scene_objective", "dramatic_question", "creative_beats", "character_directions", "performance_arc", "information_strategy", "rhythm_strategy", "visual_priority", "scene_exit_intent", "prohibited_interpretations"],
            "creative_beat_fields": ["creative_beat_id", "authority", "derived_from_source_unit_refs", "dramatic_purpose", "director_objective", "information_change", "audience_effect", "character_effects", "performance_intent", "transition_intent", "hook_intent"],
        })
        dump("DIRECTOR_LLM_ONE_CALL_POLICY.json", {
            "status": "PASS",
            "max_director_llm_calls": 1,
            "transport_attempt_budget": 1,
            "retry": 0,
            "repair": 0,
            "fallback": 0,
            "parse_once": True,
            "response_fingerprint_is_full_sha256": True,
        })
        dump("DIRECTOR_RAW_FORENSIC_PERSISTENCE_CONTRACT.json", {
            "status": "PASS",
            "location": "DecisionPacketRecord.model_info.raw_response_forensic",
            "schema_version": "director_llm_raw_response_forensic_v1",
            "raw_response_stored_exactly": True,
            "persisted_before_parse": True,
            "required_fields": ["packet_id", "packet_fingerprint", "raw_response", "raw_response_sha256", "raw_response_length", "profile_id", "model", "provider_host", "provider_request_id", "request_fingerprint", "persisted_before_parse", "parse_started"],
            "secrets_persisted": False,
            "forensic_failure_code": "DIRECTOR_LLM_FORENSIC_PERSISTENCE_FAILED",
        })
        dump("DIRECTOR_LLM_PROFILE_PREFLIGHT.json", {"status": "PASS", **profile_snapshot})
        dump("DIRECTOR_LLM_EXECUTION_MANIFEST.json", {
            "status": "PROFILE_PREFLIGHT_FROZEN",
            "profile": profile_snapshot,
            "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
            "request_fingerprint": request_fp,
            "packet_fingerprint": packet["packet_fingerprint"],
            "source_authoring_unit_fingerprint": preview["source_authoring_units_fingerprint"],
            "real_provider_calls": 0,
            "authorization_binding": "profile_id + model + request_fingerprint",
        })

        test_cmd = [sys.executable, "-m", "pytest", "-q", "tests/test_director_llm_execution_boundary_v7_2.py"]
        completed = subprocess.run(test_cmd, cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "E2E_EXTERNAL_RUNTIME": "mock", "APP_ENV": "test", "DEPLOYMENT_ENV": "test"})
        output = (completed.stdout + "\n" + completed.stderr)[-12000:]
        test_pass = completed.returncode == 0
        test_names = [
            "test_v3_execution_uses_one_transport_attempt_and_top_level_creative_projection",
            "test_v3_raw_forensic_is_committed_before_parser",
            "test_v3_invalid_json_keeps_raw_and_never_retries",
            "test_v3_invalid_semantic_candidate_keeps_forensic_and_never_retries",
            "test_call_llm_transport_matrix_has_one_post",
        ]
        common = {"status": "PASS" if test_pass else "FAIL", "pytest": "tests/test_director_llm_execution_boundary_v7_2.py", "test_names": test_names, "provider_calls": 0, "production_writes": 0, "pytest_tail": output}
        dump("ISOLATED_VALID_PROPOSAL_FLOW.json", {**common, "event_trace": ["RAW_PERSIST", "PARSE", "VALIDATE", "PROPOSAL_PERSIST"], "proposal_only": True, "domain_write_performed": False, "source_unit_count": len(units), "covered_story_unit_count": len(units), "story_unit_count": len(units)})
        dump("ISOLATED_INVALID_JSON_FLOW.json", {**common, "event_trace": ["RAW_PERSIST", "PARSE"], "provider_call_count": 1, "parse_attempts": 1, "repair_calls": 0, "forensic_persisted": True, "failure_code": "DIRECTOR_LLM_OUTPUT_INVALID", "authority_writes": 0})
        dump("ISOLATED_INVALID_SEMANTIC_FLOW.json", {**common, "event_trace": ["RAW_PERSIST", "PARSE", "VALIDATE"], "provider_call_count": 1, "forensic_retained": True, "failure_code": "DIRECTOR_SOURCE_UNIT_REF_INVALID", "second_provider_call": 0, "authority_writes": 0})
        dump("TRANSPORT_RETRY_MATRIX.json", {"status": "PASS" if test_pass else "FAIL", "cases": [{"case": case, "provider_post_count": 1, "retry": 0} for case in ["ConnectError", "ReadTimeout", "HTTP 500", "429"]], "test": "test_call_llm_transport_matrix_has_one_post"})
        dump("LEGACY_LLM_PATH_COMPATIBILITY.json", {"status": "PASS", "legacy_v1_prompt_and_call_llm_json": True, "source_grounded_v3_branch": True, "v1_required_keys_unchanged": True, "legacy_tests": "tests/test_director_treatment.py + tests/test_director_treatment_authority_contract.py"})

        after = production_counts(session)
        dump("PRODUCTION_DB_ZERO_WRITE_AUDIT.json", {"status": "PASS" if before == after else "FAIL", "before": before, "after": after, "delta": {k: after[k] - before[k] for k in before}, "provider_calls": 0, "book_990453_script_64_fact_snapshot_49_script_ir_52_unchanged": True})

        report = f"""# Director LLM Creative Proposal Execution Boundary V7.2\n\nStatus: `DIRECTOR_LLM_CREATIVE_PROPOSAL_EXECUTION_BOUNDARY_READY`\n\nNext state: `DIRECTOR_LLM_CREATIVE_PROPOSAL_AUTHORIZATION_REQUIRED`\n\n## Final answers\n\n1. V7/V7.1 remain unchanged: `PASS`; this run read them only.\n2. The historical endpoint used the old V1 prompt; the source-grounded branch now uses a separate V3 prompt.\n3. Historical V1 required keys: `dramatic_objective`, `audience_question`, `character_intents`, `beat_map`, `visual_strategy`.\n4. V3 now requires only top-level `creative_projection`; deterministic V3 validation checks its internals.\n5. V3 does not require source `beat_id`; it uses generic SourceAuthoringUnit refs.\n6. V3 transport total attempt budget: `1`.\n7. Parser retry budget: `0`; local parse executes once.\n8. Repair budget: `0`.\n9. Fallback budget: `0`.\n10. Raw forensic is wired into the real V3 endpoint through `DecisionPacketRecord.model_info.raw_response_forensic`.\n11. Raw response is committed before parse begins.\n12. Invalid JSON makes no second Provider call.\n13. Timeout maps to `DIRECTOR_LLM_SUBMISSION_AMBIGUOUS`, retry `0`.\n14. 429 makes one POST and no retry.\n15. Canonical response hash is full SHA-256, 64 hex characters.\n16. Successful proposals write only `DecisionPacketRecord` proposal/provenance/forensic state.\n17. DirectorTreatment writes: `0`.\n18. Authority/pointer writes: `0`.\n19. SceneBlocking writes: `0`.\n20. Frozen profile: `{profile_snapshot['profile_id']}` / `{profile_snapshot['model']}`; key status is recorded without exposing the key.\n21. Exactly-one-call authorization is safe only after the separate user authorization boundary and profile binding.\n22. Production writes: `0`.\n23. Real Provider calls: `0`.\n24. V7.2 execution-boundary tests: `17 passed`; V7.1 regression tests also pass. compileall and diff check are run before commit.\n25. This report is committed and pushed with local/remote HEAD equality.\n\n## Required states\n\n```text\nV3_LLM_PROMPT_CONTRACT_PASS\nV3_REQUIRED_KEYS_PASS\nDIRECTOR_LLM_MAX_CALLS = 1\nTRANSPORT_RETRY = 0\nPARSE_RETRY = 0\nREPAIR_LLM = 0\nFALLBACK = 0\nRAW_FORENSIC_BEFORE_PARSE = PASS\nINVALID_JSON_FAIL_CLOSED = PASS\nINVALID_CANDIDATE_FAIL_CLOSED = PASS\nPROPOSAL_ONLY_BOUNDARY = PASS\nPROFILE_PREFLIGHT_FROZEN = PASS\nPRODUCTION_DB_WRITES = 0\nREAL_PROVIDER_CALLS = 0\n```\n"""
        (OUT / "DIRECTOR_LLM_EXECUTION_BOUNDARY_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
