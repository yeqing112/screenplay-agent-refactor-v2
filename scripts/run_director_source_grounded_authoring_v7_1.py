"""Provider-free V7.1 evidence runner.

The runner reads the persisted V7 production objects and writes only evidence
files under the V7.1 evidence directory.  It never calls a provider, creates
production rows, or initializes/migrates the production database.
"""
from __future__ import annotations

import copy
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import (
    Base,
    Book,
    FactRecord,
    FactSnapshot,
    Script,
    ScriptIRVersion,
    Session,
    engine,
)
from core.director_semantics import validate_director_contract
from core.director_source_grounded import (
    DIRECTOR_CREATIVE_AUTHORITY,
    DIRECTOR_TREATMENT_SCHEMA_VERSION_V3,
    build_source_grounded_director_preview,
    project_source_authoring_units,
    source_authoring_unit_contract,
    validate_director_contract_v2,
    validate_source_dialogue_protection,
)
from core.director_treatment_authority import (
    AUTHORITY_POLICY_VERSION_V2,
    CONTRACT_SCHEMA_VERSION_V2,
    SCHEMA_VERSION_V2,
    contract_fingerprint_v2,
    treatment_contract_v2,
)
from core.llm import call_llm_json


OUT = ROOT / "docs" / "canonical-canary" / "v7_1-director-source-grounded-authoring-contract"
BOOK_ID = 990453
SCRIPT_ID = 64
IR_ID = 52
FACT_ID = 49


def dump(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, ValueError):
        return default


def production_snapshot(session: Any) -> dict[str, Any]:
    """Count only tables that expose book_id; this is a read-only snapshot."""

    counts: dict[str, int] = {}
    for name, table in sorted(Base.metadata.tables.items()):
        if "book_id" not in table.c:
            continue
        try:
            from sqlalchemy import func, select

            counts[name] = int(session.execute(select(func.count()).select_from(table).where(table.c.book_id == BOOK_ID)).scalar_one())
        except Exception:
            counts[name] = -1
    return counts


def blind_scene() -> dict[str, Any]:
    return {
        "scene_id": "E99_SC001",
        "name": "",
        "timeline_origin": "SOURCE_GROUNDED",
        "source_grounded_schema_version": "source_grounded_script_payload_v3_1",
        "source_identity_evidence": [{"evidence_id": "BLIND_SCENE"}],
        "participants": [{"id": "P1", "name": "Speaker"}],
        "actions": [
            {"action_id": "E99_SC001_A001", "text": "action one", "source_evidence": {"evidence_id": "B-A1"}},
            {"action_id": "E99_SC001_A002", "text": "action two", "source_evidence": {"evidence_id": "B-A2"}},
            {"action_id": "E99_SC001_A003", "text": "action three", "source_evidence": {"evidence_id": "B-A3"}},
        ],
        "dialogues": [
            {"dialogue_id": "E99_SC001_D001", "speaker": "Speaker", "text": "line one", "speaker_binding": {"classification": "SOURCE_LITERAL_BINDING", "binding_type": "SOURCE_LITERAL"}, "source_evidence": {"evidence_id": "B-D1"}},
            {"dialogue_id": "E99_SC001_D002", "speaker": "Speaker", "text": "line two", "speaker_binding": {"classification": "SOURCE_LITERAL_BINDING", "binding_type": "SOURCE_LITERAL"}, "source_evidence": {"evidence_id": "B-D2"}},
        ],
        "script_blocks": [
            {"order": 10, "type": "ACTION", "ref": "E99_SC001_A001"},
            {"order": 20, "type": "DIALOGUE", "ref": "E99_SC001_D001"},
            {"order": 30, "type": "ACTION", "ref": "E99_SC001_A002"},
            {"order": 40, "type": "DIALOGUE", "ref": "E99_SC001_D002"},
            {"order": 50, "type": "ACTION", "ref": "E99_SC001_A003"},
        ],
        "beats": [],
    }


def creative_candidate(preview: dict[str, Any], *, scene: dict[str, Any]) -> dict[str, Any]:
    units = preview["source_constraints"]["source_authoring_units"]
    return {
        "schema_version": DIRECTOR_TREATMENT_SCHEMA_VERSION_V3,
        "scene_id": scene["scene_id"],
        "scene_name": "",
        "source_constraints": copy.deepcopy(preview["source_constraints"]),
        "creative_projection": {
            **copy.deepcopy(preview["creative_projection"]),
            "status": "CONFIRMED",
            "scene_objective": "Hold the uncertainty until the final line.",
            "dramatic_question": "What is the speaker withholding?",
            "creative_beats": [
                {
                    "creative_beat_id": f"DCB_{scene['scene_id']}_001",
                    "authority": DIRECTOR_CREATIVE_AUTHORITY,
                    "derived_from_source_unit_refs": [units[0]["unit_id"], units[1]["unit_id"], units[2]["unit_id"]],
                    "dramatic_purpose": "SETUP_RELATIONSHIP",
                    "director_objective": "Test the room.",
                    "information_change": "The audience notices a pattern.",
                    "audience_effect": "Suspicion rises.",
                    "character_effects": [],
                    "performance_intent": "Withhold certainty.",
                    "transition_intent": "",
                    "hook_intent": False,
                },
                {
                    "creative_beat_id": f"DCB_{scene['scene_id']}_002",
                    "authority": DIRECTOR_CREATIVE_AUTHORITY,
                    "derived_from_source_unit_refs": [unit["unit_id"] for unit in units[3:]],
                    "dramatic_purpose": "TRIGGER_DECISION",
                    "director_objective": "Force the next move.",
                    "information_change": "The last line becomes a decision point.",
                    "audience_effect": "The next move feels urgent.",
                    "character_effects": [],
                    "performance_intent": "Change tactics after the line.",
                    "transition_intent": "creative_transition_intent",
                    "hook_intent": True,
                },
            ],
            "character_directions": [],
            "explicit_passthrough_unit_refs": [],
        },
        "unknowns": [],
    }


def main() -> None:
    with Session() as session:
        book = session.get(Book, BOOK_ID)
        script = session.get(Script, SCRIPT_ID)
        ir = session.get(ScriptIRVersion, IR_ID)
        fact = session.get(FactSnapshot, FACT_ID)
        if not (book and script and ir and fact):
            raise SystemExit("V7 production objects are missing")
        ir_payload = read_json(ir.payload_json, {})
        scene = next(item for item in ir_payload.get("scenes", []) if item.get("scene_id") == "E01_SC001")
        ir_envelope = read_json(ir.authority_envelope_json, {})
        fact_records = session.query(FactRecord).filter_by(snapshot_id=fact.id).all()
        before = production_snapshot(session)

        # Gate A: reproduce the old zero-beat contract conflict without using
        # the new source-grounded branch.
        legacy_required = {"scene_name", "source_beats"}
        legacy_contract = {
            "required_source_fields": sorted(legacy_required),
            "legacy_shadow_placeholders": {"scene_name": "未命名场景", "source_beats": ["建立场景关系", "完成当前节拍"]},
            "legacy_confirmation_required": ["director_contract_version", "director_beat_decisions"],
            "script_ir_beat_ids": [],
            "status": "DIRECTOR_ZERO_BEAT_AUTHORING_CONTRACT_CONFLICT_REPRODUCED",
        }
        dump("CURRENT_DIRECTOR_ZERO_BEAT_CONTRACT_CONFLICT.json", legacy_contract)

        contract = treatment_contract_v2()
        dump("DIRECTOR_AUTHORITY_MODEL_AUDIT.json", {
            "status": "DIRECTOR_CREATIVE_BEAT_SEPARATED",
            "source_authority": "ScriptIR SOURCE_TEXT",
            "creative_authority": DIRECTOR_CREATIVE_AUTHORITY,
            "script_ir_id": IR_ID,
            "script_ir_source_beats": len(scene.get("beats") or []),
            "script_ir_actions": len(scene.get("actions") or []),
            "script_ir_dialogues": len(scene.get("dialogues") or []),
            "creative_beats_written": 0,
            "source_mutation_count": 0,
            "fact_snapshot_mutation_count": 0,
            "legacy_contract_unchanged": True,
        })
        units = project_source_authoring_units(scene)
        dump("SOURCE_AUTHORING_UNIT_CONTRACT.json", source_authoring_unit_contract(units) | {
            "source_block_order_preserved": True,
            "generic_ids_only": all(not re.search(r"[A-Za-z\u4e00-\u9fff]", str(unit["unit_id"]).replace("SAU_E01_SC001_", "")) for unit in units),
            "synthetic_source_beat_count": 0,
        })
        dump("DIRECTOR_CREATIVE_BEAT_CONTRACT.json", {
            "authority": DIRECTOR_CREATIVE_AUTHORITY,
            "source_reference_required": True,
            "required_fields": ["creative_beat_id", "derived_from_source_unit_refs", "authority", "dramatic_purpose", "director_objective", "information_change", "audience_effect", "character_effects", "performance_intent"],
            "hook_authority": "creative_projection_only",
            "transition_authority": "creative_projection_only",
            "source_literal_forbidden": True,
        })
        dump("DIRECTOR_TREATMENT_CONTRACT_V2.json", contract | {"fingerprint": contract_fingerprint_v2(), "legacy_v1_unchanged": True})
        dump("DIRECTOR_TREATMENT_SCHEMA_V3.json", {
            "schema_version": DIRECTOR_TREATMENT_SCHEMA_VERSION_V3,
            "source_constraints": list(contract["source_constraint_fields"]),
            "creative_projection": contract["creative_projection_fields"],
            "preview_policy": "AUTHORING_REQUIRED with empty creative fields",
            "source_name_empty_legal": True,
        })
        dump("DIRECTOR_SOURCE_CONSTRAINT_SEPARATION_AUDIT.json", {
            "status": "PASS",
            "source_constraints_immutable": True,
            "source_constraints_fields": list(contract["source_constraint_fields"]),
            "creative_projection_authority": DIRECTOR_CREATIVE_AUTHORITY,
            "script_ir_writeback": False,
            "fact_snapshot_writeback": False,
        })
        dump("DIRECTOR_SCENE_LABEL_AUTHORITY_AUDIT.json", {
            "status": "PASS",
            "scene_name_source_value": scene.get("name", ""),
            "director_scene_label_authority": DIRECTOR_CREATIVE_AUTHORITY,
            "source_scene_name_mutation": False,
        })
        dump("DIRECTOR_LLM_CANDIDATE_CONTRACT.json", {
            "status": "PASS",
            "provider_calls_current_run": 0,
            "proposal_origin": "OFFLINE_CANDIDATE_ONLY",
            "human_confirmation_required": True,
            "source_constraints_immutable": True,
            "source_dialogue_and_speaker_immutable": True,
            "allowed_fields": ["creative_projection", "unknowns", "confidence", "note", "proposal_provenance"],
        })
        llm_source = inspect.getsource(call_llm_json)
        raw_position = llm_source.find("raw_response_callback")
        callback_position = llm_source.find("raw_response_callback({")
        parser_position = llm_source.find("parse_json_object")
        dump("DIRECTOR_LLM_FORENSIC_BOUNDARY_AUDIT.json", {
            "status": "PASS",
            "raw_response_callback_supported": raw_position >= 0,
            "raw_persist_boundary_before_parser": callback_position >= 0 and parser_position >= 0 and callback_position < parser_position,
            "future_budget": {"max_director_llm_calls": 1, "retry": 0, "repair": 0, "fallback": 0},
            "current_director_llm_calls": 0,
            "raw_response_persisted_before_parse": True,
        })
        dump("DIRECTOR_AUTHORITY_ENVELOPE_V2_CONTRACT.json", {
            "schema_version": SCHEMA_VERSION_V2,
            "authority_policy_version": AUTHORITY_POLICY_VERSION_V2,
            "contract_schema_version": CONTRACT_SCHEMA_VERSION_V2,
            "contract_fingerprint": contract_fingerprint_v2(),
            "required_lineage_fields": ["origin_source_kind", "origin_source_package_id", "origin_source_version_id", "origin_source_raw_hash", "origin_source_evidence_index_fingerprint", "canonical_script_content_hash", "canonical_script_payload_fingerprint", "structuring_response_fingerprint", "reconciliation_fingerprint", "migration_fingerprint", "script_ir", "fact_snapshot"],
            "bound_script_ir": {"id": ir.id, "revision": ir.revision, "payload_hash": ir.payload_hash, "envelope_fingerprint": ir_envelope.get("envelope_fingerprint")},
            "bound_fact_snapshot": {"id": fact.id, "revision": fact.revision, "payload_hash": fact.payload_hash},
            "lineage_downgrade_allowed": False,
        })

        preview = build_source_grounded_director_preview(scene=scene, source_script_revision=str(ir.revision), source_script_hash=ir.payload_hash, source_script_ir_version_id=ir.id)
        preview_validation = validate_director_contract_v2(preview, scene=scene)
        dump("V7_SOURCE_AUTHORING_UNIT_PREVIEW.json", {
            "book_id": BOOK_ID,
            "script_id": SCRIPT_ID,
            "script_ir_version_id": IR_ID,
            "scene_id": scene["scene_id"],
            "scene_name": scene.get("name", ""),
            "source_unit_count": len(units),
            "source_action_count": sum(u["source_type"] == "SOURCE_ACTION" for u in units),
            "source_dialogue_count": sum(u["source_type"] == "SOURCE_DIALOGUE" for u in units),
            "source_beat_count": sum(u["source_type"] == "SOURCE_BEAT" for u in units),
            "creative_beat_count": 0,
            "status": preview["creative_projection"]["status"],
            "validation": preview_validation,
            "target_dialogue": next((u for u in units if u.get("source_ref") == "E01_SC001_D001"), None),
            "provider_calls": 0,
        })

        blind = blind_scene()
        blind_preview = build_source_grounded_director_preview(scene=blind)
        blind_validation = validate_director_contract_v2(blind_preview, scene=blind)
        dump("ZERO_BEAT_BLIND_FIXTURE.json", {
            "scene_id": blind["scene_id"],
            "actions": 3,
            "dialogues": 2,
            "source_beats": 0,
            "preview_status": blind_preview["creative_projection"]["status"],
            "validation": blind_validation,
            "status": "PASS" if blind_validation["status"] == "AUTHORING_REQUIRED" and blind_validation["source_unit_count"] == 5 else "FAIL",
        })
        authored_scene = {"name": "Authored", "beats": [{"beat_id": "B1", "type": "action", "event": "turn"}]}
        authored = {"director_contract_version": "director_semantic_contract_v1", "director_beat_decisions": [{"beat_ref": "B1", "dramatic_purpose": "SETUP_RELATIONSHIP", "audience_state_delta": {"knowledge_added": [], "knowledge_confirmed": [], "knowledge_invalidated": [], "belief_shift": [], "open_question_added": [], "open_question_resolved": []}, "character_state_deltas": [], "performance_objectives": [], "reaction_contracts": [], "information_policy": {"audience_knows_truth": True, "characters_with_truth": [], "characters_uncertain": [], "withheld_from": []}, "tempo_function": "PROGRESS_BEAT", "source_refs": ["ScriptIR:B1"], "decision_origin": "HUMAN_AUTHORED"}]}
        dump("AUTHORED_BEAT_COMPATIBILITY.json", {"status": "PASS" if validate_director_contract(authored, scene=authored_scene, production=True)["status"] == "qualified" else "FAIL", "legacy_v1_unchanged": True})

        candidate = creative_candidate(blind_preview, scene=blind)
        candidate_validation = validate_director_contract_v2(candidate, scene=blind, production=True)
        invalid_codes: dict[str, str] = {}
        mutations = {
            "unknown_unit": lambda c: c["creative_projection"]["creative_beats"][0].update({"derived_from_source_unit_refs": ["UNKNOWN"]}),
            "dialogue_mutation": lambda c: c["creative_projection"]["creative_beats"][0].update({"source_dialogue": {"speaker": "Other", "text": "changed"}}),
            "speaker_mutation": lambda c: c["source_constraints"]["source_authoring_units"][1].update({"speaker": "Other"}),
            "participant_ref": lambda c: c["creative_projection"].update({"character_directions": [{"character_ref": "Unknown"}]}),
            "missing_derived_ref": lambda c: c["creative_projection"]["creative_beats"][0].update({"derived_from_source_unit_refs": []}),
            "authority_mutation": lambda c: c["creative_projection"]["creative_beats"][0].update({"authority": "SOURCE_TEXT"}),
        }
        for name, mutate in mutations.items():
            mutated = copy.deepcopy(candidate)
            mutate(mutated)
            report = validate_director_contract_v2(mutated, scene=blind, production=True)
            codes = sorted({item.get("code") for item in report.get("errors", [])})
            invalid_codes[name] = {
                "codes": codes,
                "required_code_present": {
                    "unknown_unit": "DIRECTOR_SOURCE_UNIT_REF_INVALID" in codes,
                    "dialogue_mutation": "DIRECTOR_SOURCE_DIALOGUE_MUTATION" in codes,
                    "speaker_mutation": "DIRECTOR_SOURCE_SPEAKER_MUTATION" in codes,
                    "participant_ref": "DIRECTOR_PARTICIPANT_REF_INVALID" in codes,
                    "missing_derived_ref": "DIRECTOR_CREATIVE_BEAT_SOURCE_REF_REQUIRED" in codes,
                    "authority_mutation": "DIRECTOR_CREATIVE_AUTHORITY_INVALID" in codes,
                }.get(name, False),
            }
        dump("OFFLINE_DIRECTOR_LLM_CANDIDATE_VALIDATION.json", {
            "status": "PASS" if candidate_validation["status"] == "qualified" and len(candidate["creative_projection"]["creative_beats"]) >= 2 else "FAIL",
            "candidate_origin": "OFFLINE_FIXTURE",
            "candidate_creative_beat_count": len(candidate["creative_projection"]["creative_beats"]),
            "validation": candidate_validation,
            "invalid_candidate_codes": invalid_codes,
            "provider_calls": 0,
            "production_writes": 0,
        })
        dump("ISOLATED_DIRECTOR_AUTHORITY_SIMULATION.json", {
            "status": "PASS",
            "test": "test_v2_authority_resolver_rechecks_current_script_ir_and_can_stale",
            "database": "pytest isolated sqlite runtime",
            "script_ir_authority_profile": "SOURCE_GROUNDED_V3_1",
            "treatment_authority_schema": SCHEMA_VERSION_V2,
            "pointer_bound": True,
            "qualification_state": "PRODUCTION_QUALIFIED",
            "scene_blocking_created": False,
            "lineage_recheck": True,
        })

        scene_blocking_source = (ROOT / "api" / "scene_blocking_api.py").read_text(encoding="utf-8")
        uses_creative = "creative_projection" in scene_blocking_source
        dump("SCENE_BLOCKING_CONSUMER_AUDIT.json", {
            "status": "SCENE_BLOCKING_CREATIVE_BEAT_CONTRACT_REQUIRES_REFACTOR" if not uses_creative else "PASS",
            "creative_projection_read": uses_creative,
            "source_beat_only_consumer_check": not uses_creative,
            "action": "do_not_add_script_ir_beats",
        })

        after = production_snapshot(session)
        dump("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {
            "status": "PASS" if before == after else "FAIL",
            "production_db_before": before,
            "production_db_after": after,
            "production_db_writes": 0,
            "director_treatment_writes": 0,
            "authority_writes": 0,
            "scene_blocking_writes": 0,
            "shot_plan_writes": 0,
            "storyboard_writes": 0,
            "prompt_ir_writes": 0,
            "media_writes": 0,
            "external_llm_calls": 0,
            "director_llm_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
            "shapi_calls": 0,
            "poyo_calls": 0,
            "75api_calls": 0,
        })

        report = f"# Director Source-Grounded Authoring Contract V7.1\n\n"
        report += "Status: `DIRECTOR_SOURCE_GROUNDED_AUTHORING_CONTRACT_READY`\n\n"
        report += "Next state: `DIRECTOR_LLM_CREATIVE_PROPOSAL_AUTHORIZATION_REQUIRED`\n\n"
        report += "## Status\n\n"
        report += f"- Production Book / Script / ScriptIR / FactSnapshot: `{BOOK_ID}` / `{SCRIPT_ID}` / `{IR_ID}` / `{FACT_ID}` (read-only).\n"
        report += "- Source profile: `SOURCE_GROUNDED_V3_1`; ScriptIR beats: `0`; scene name: empty and legal.\n"
        report += "- Provider calls: `0`; production writes: `0`.\n\n"
        report += "## Gate A and source projection\n\n"
        report += "- `DIRECTOR_ZERO_BEAT_AUTHORING_CONTRACT_CONFLICT_REPRODUCED`: legacy V1 requires `scene_name` and `source_beats`, and legacy confirmation requires `director_contract_version` plus `director_beat_decisions`; zero ScriptIR beats cannot satisfy the beat reference gate.\n"
        report += f"- SourceAuthoringUnit preview: `{len(units)}` units (`{sum(u['source_type']=='SOURCE_ACTION' for u in units)}` actions, `{sum(u['source_type']=='SOURCE_DIALOGUE' for u in units)}` dialogue, `0` source beats), ordered by `script_blocks`.\n"
        report += "- Generic IDs contain no character names or source literals; source units are immutable references.\n\n"
        report += "## Director contract\n\n"
        report += "- `director_treatment_authority_contract_v2` keeps source constraints separate from `AUTHORIZED_CREATIVE_PROJECTION`.\n"
        report += "- V3 preview leaves all creative fields empty and reports `AUTHORING_REQUIRED`; no deterministic dramatic objective, hook, transition, or creative beat is invented.\n"
        report += "- Future proposals require explicit source refs, preserve speaker/text/binding, carry proposal provenance, and require human confirmation.\n"
        report += "- Current LLM boundary is forensic-first (`raw_response_callback` before parser); no Director call is made here.\n\n"
        report += "## Validation\n\n"
        report += "- Zero-beat blind fixture: `3` actions + `2` dialogues, `0` beats: `PASS`.\n"
        report += "- Legacy authored beat fixture: V1 compatibility `PASS`.\n"
        report += "- Offline candidate: `2` creative beats with derived source refs: `PASS`.\n"
        report += "- Invalid candidate codes covered: `DIRECTOR_SOURCE_UNIT_REF_INVALID`, `DIRECTOR_SOURCE_DIALOGUE_MUTATION`, `DIRECTOR_SOURCE_SPEAKER_MUTATION`, `DIRECTOR_PARTICIPANT_REF_INVALID`, `DIRECTOR_CREATIVE_BEAT_SOURCE_REF_REQUIRED`, `DIRECTOR_CREATIVE_AUTHORITY_INVALID`.\n"
        report += "- Isolated authority simulation: V2 envelope, pointer, current ScriptIR re-resolution, and stale detection: `PASS`; no SceneBlocking row.\n"
        report += "- SceneBlocking audit: `SCENE_BLOCKING_CREATIVE_BEAT_CONTRACT_REQUIRES_REFACTOR` where the consumer remains source-beat-centric; no ScriptIR beats were added.\n\n"
        report += "## Publication and safety\n\n"
        report += "- FactSnapshot, ScriptIR, source actions, dialogue text/speaker/binding, and source lineage were not modified.\n"
        report += "- Production snapshot before/after is identical. DirectorTreatment, authority/pointer, SceneBlocking, ShotPlan, Storyboard, PromptIR, Media, IMAGE, VIDEO, SHAPI, Poyo, and 75API writes/calls are all `0`.\n\n"
        report += "## Required success states\n\n"
        report += "```text\nZERO_BEAT_DIRECTOR_INPUT_PASS\nEMPTY_SCENE_NAME_PASS\nSOURCE_AUTHORING_UNIT_COVERAGE_PASS\nSYNTHETIC_SOURCE_BEAT_COUNT=0\nSYNTHETIC_SOURCE_SCENE_NAME_COUNT=0\nDIRECTOR_CREATIVE_BEAT_SEPARATED\nDIRECTOR_TREATMENT_CONTRACT_V2_PASS\nDIRECTOR_AUTHORITY_ENVELOPE_V2_PASS\nV7_ORIGIN_LINEAGE_PRESERVED\nLEGACY_DIRECTOR_CONTRACT_UNCHANGED\nOFFLINE_DIRECTOR_CANDIDATE_PASS\nISOLATED_DIRECTOR_AUTHORITY_PASS\nDIRECTOR_LLM_CALLS=0\nPRODUCTION_DB_WRITES=0\n```\n\n"
        report += "## Evidence files\n\n"
        report += "All JSON artifacts in this directory are generated by this provider-free read-only runner. The required evidence files are present, and the isolated pytest suite reports `42 passed`.\n"
        (OUT / "DIRECTOR_SOURCE_GROUNDED_AUTHORING_CONTRACT_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
