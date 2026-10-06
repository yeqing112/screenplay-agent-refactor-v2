"""V7.1 source-grounded Director contract tests.

All persistence coverage in this module uses the hermetic pytest database.
The real V7 database is inspected by the evidence runner, never mutated here.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.director_source_grounded import (
    DIRECTOR_CREATIVE_AUTHORITY,
    build_source_grounded_director_preview,
    project_source_authoring_units,
    validate_director_contract_v2,
)
from core.director_semantics import validate_director_contract, validate_director_contract_v2 as validate_v2_export
from core.director_treatment import build_shadow_treatment
from core.director_treatment_authority import (
    AUTHORITY_POLICY_VERSION_V2,
    CONTRACT_SCHEMA_VERSION_V2,
    SCHEMA_VERSION_V2,
    build_treatment_authority_envelope_v2,
    contract_fingerprint_v2,
    resolve_current_authoritative_treatment,
    treatment_contract,
    treatment_contract_v2,
    treatment_payload_from_row,
    payload_hash,
)
from core.llm import call_llm_json
from models import Book, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, FactSnapshot, Script, ScriptIRVersion, Session, init_db


def _scene() -> dict:
    return {
        "scene_id": "E01_SC001",
        "name": "",
        "timeline_origin": "SOURCE_GROUNDED",
        "source_grounded_schema_version": "source_grounded_script_payload_v3_1",
        "source_identity_evidence": [{"evidence_id": "S1I001", "text": "source scene"}],
        "participants": [{"id": "P1", "name": "Speaker"}],
        "actions": [
            {"action_id": "E01_SC001_A001", "text": "first action", "source_evidence": {"evidence_id": "S1A001"}},
            {"action_id": "E01_SC001_A002", "text": "second action", "source_evidence": {"evidence_id": "S1A002"}},
            {"action_id": "E01_SC001_A003", "text": "third action", "source_evidence": {"evidence_id": "S1A003"}},
        ],
        "dialogues": [
            {"dialogue_id": "E01_SC001_D001", "speaker": "Speaker", "text": "source dialogue", "speaker_binding": {"classification": "AUTHORIZED_SEMANTIC_BINDING", "binding_type": "COREFERENCE_RESOLUTION"}, "source_evidence": {"evidence_id": "S1D001"}},
            {"dialogue_id": "E01_SC001_D002", "speaker": "Speaker", "text": "second dialogue", "speaker_binding": {"classification": "SOURCE_LITERAL_BINDING", "binding_type": "SOURCE_LITERAL"}, "source_evidence": {"evidence_id": "S1D002"}},
        ],
        "script_blocks": [
            {"order": 10, "type": "ACTION", "ref": "E01_SC001_A001"},
            {"order": 20, "type": "DIALOGUE", "ref": "E01_SC001_D001"},
            {"order": 30, "type": "ACTION", "ref": "E01_SC001_A002"},
            {"order": 40, "type": "DIALOGUE", "ref": "E01_SC001_D002"},
            {"order": 50, "type": "ACTION", "ref": "E01_SC001_A003"},
        ],
        "beats": [],
        "dramatic_beats": [],
    }


def _preview() -> dict:
    return build_source_grounded_director_preview(scene=_scene())


def _creative_candidate() -> dict:
    preview = _preview()
    units = preview["source_constraints"]["source_authoring_units"]
    return {
        "schema_version": "director_treatment_v3",
        "scene_id": "E01_SC001",
        "scene_name": "",
        "source_constraints": copy.deepcopy(preview["source_constraints"]),
        "creative_projection": {
            **copy.deepcopy(preview["creative_projection"]),
            "status": "CONFIRMED",
            "scene_objective": "Hold the uncertainty until the second action.",
            "dramatic_question": "What will the speaker reveal?",
            "creative_beats": [
                {"creative_beat_id": "DCB_E01_SC001_001", "authority": DIRECTOR_CREATIVE_AUTHORITY, "derived_from_source_unit_refs": [units[0]["unit_id"], units[1]["unit_id"]], "dramatic_purpose": "RAISE_SUSPICION", "director_objective": "Test the other person's certainty.", "information_change": "The audience notices a contradiction.", "audience_effect": "Suspicion increases.", "character_effects": [], "performance_intent": "Hold the answer back.", "transition_intent": "", "hook_intent": False},
                {"creative_beat_id": "DCB_E01_SC001_002", "authority": DIRECTOR_CREATIVE_AUTHORITY, "derived_from_source_unit_refs": [units[2]["unit_id"], units[3]["unit_id"], units[4]["unit_id"]], "dramatic_purpose": "TRIGGER_DECISION", "director_objective": "Force a choice.", "information_change": "The source dialogue lands as a decision point.", "audience_effect": "The next move becomes urgent.", "character_effects": [], "performance_intent": "Change tactics after the line.", "transition_intent": "creative_transition_intent", "hook_intent": True},
            ],
            "character_directions": [{"character_ref": "Speaker", "objective": "Test the room", "obstacle": "Missing information", "strategy": "Withhold", "performance_notes": "Use a pause."}],
            "explicit_passthrough_unit_refs": [],
        },
        "unknowns": [],
    }


def test_current_legacy_contract_conflict_is_reproducible_without_mutating_source():
    contract = treatment_contract()
    required = {item["field"] for item in contract["fields"] if item.get("required") and item.get("authority_class") == "SOURCE_CONSTRAINT"}
    assert {"scene_name", "source_beats"}.issubset(required)
    legacy_projection = build_shadow_treatment(scene={"name": "", "beats": []})
    assert legacy_projection["scene_name"] == "未命名场景"
    assert legacy_projection["dramatic_objective"] == "围绕“建立场景关系”建立冲突，并通过“完成当前节拍”推进本场戏。"
    assert validate_director_contract({"director_contract_version": "director_semantic_contract_v1", "director_beat_decisions": []}, scene={"name": "", "beats": []}, production=True)["status"] == "qualified"


def test_v2_contract_makes_scene_name_and_source_beats_optional():
    contract = treatment_contract_v2()
    assert contract["schema_version"] == CONTRACT_SCHEMA_VERSION_V2
    assert "scene_name" not in contract["source_constraint_fields"]
    assert "source_beats" not in contract["source_constraint_fields"]
    assert "source_authoring_units" in contract["source_constraint_fields"]
    assert contract_fingerprint_v2()


def test_source_units_follow_script_block_order_and_generic_ids():
    units = project_source_authoring_units(_scene())
    assert len(units) == 5
    assert [u["source_type"] for u in units] == ["SOURCE_ACTION", "SOURCE_DIALOGUE", "SOURCE_ACTION", "SOURCE_DIALOGUE", "SOURCE_ACTION"]
    assert [u["source_order"] for u in units] == [1, 2, 3, 4, 5]
    assert [u["unit_id"] for u in units] == ["SAU_E01_SC001_001", "SAU_E01_SC001_002", "SAU_E01_SC001_003", "SAU_E01_SC001_004", "SAU_E01_SC001_005"]
    assert all("Speaker" not in u["unit_id"] for u in units)


def test_zero_beat_preview_passes_with_no_synthetic_source_semantics():
    preview = _preview()
    report = validate_director_contract_v2(preview, scene=_scene())
    assert preview["scene_name"] == ""
    assert preview["creative_projection"]["creative_beats"] == []
    assert preview["creative_projection"]["status"] == "AUTHORING_REQUIRED"
    assert report["status"] == "AUTHORING_REQUIRED"
    assert report["synthetic_source_beat_count"] == 0
    assert report["synthetic_source_scene_name_count"] == 0


def test_all_story_units_have_explicit_passthrough_coverage():
    preview = _preview()
    report = validate_director_contract_v2(preview, scene=_scene())
    assert report["source_unit_count"] == 5
    assert report["source_action_count"] == 3
    assert report["source_dialogue_count"] == 2
    assert report["covered_story_unit_count"] == 5
    assert report["story_unit_count"] == 5


def test_creative_beats_are_independent_and_can_reference_units():
    candidate = _creative_candidate()
    report = validate_director_contract_v2(candidate, scene=_scene(), production=True)
    assert report["status"] == "qualified"
    assert all(beat["authority"] == DIRECTOR_CREATIVE_AUTHORITY for beat in candidate["creative_projection"]["creative_beats"])
    assert all(beat["derived_from_source_unit_refs"] for beat in candidate["creative_projection"]["creative_beats"])


def test_hook_and_transition_intents_do_not_mutate_script_ir():
    candidate = _creative_candidate()
    before = copy.deepcopy(_scene())
    assert validate_director_contract_v2(candidate, scene=_scene(), production=True)["status"] == "qualified"
    assert _scene() == before
    assert candidate["creative_projection"]["creative_beats"][1]["hook_intent"] is True
    assert candidate["creative_projection"]["creative_beats"][1]["transition_intent"]


@pytest.mark.parametrize("mutation,code", [
    (lambda c: c["creative_projection"]["creative_beats"][0].update({"derived_from_source_unit_refs": ["UNKNOWN"]}), "DIRECTOR_SOURCE_UNIT_REF_INVALID"),
    (lambda c: c["creative_projection"]["creative_beats"][0].update({"authority": "SOURCE_TEXT"}), "DIRECTOR_CREATIVE_AUTHORITY_INVALID"),
    (lambda c: c["source_constraints"]["source_authoring_units"][1].update({"text": "changed"}), "DIRECTOR_SOURCE_DIALOGUE_MUTATION"),
    (lambda c: c["source_constraints"]["source_authoring_units"][1].update({"speaker": "Other"}), "DIRECTOR_SOURCE_SPEAKER_MUTATION"),
    (lambda c: c["creative_projection"].update({"character_directions": [{"character_ref": "Unknown"}]}), "DIRECTOR_PARTICIPANT_REF_INVALID"),
    (lambda c: c["creative_projection"]["creative_beats"][0].update({"derived_from_source_unit_refs": []}), "DIRECTOR_CREATIVE_BEAT_SOURCE_REF_REQUIRED"),
])
def test_v2_invalid_candidates_fail_closed(mutation, code):
    candidate = _creative_candidate()
    mutation(candidate)
    report = validate_director_contract_v2(candidate, scene=_scene(), production=True)
    assert code in {item["code"] for item in report["errors"]}


def test_dialogue_protection_preserves_speaker_text_and_binding():
    candidate = _creative_candidate()
    report = validate_director_contract_v2(candidate, scene=_scene(), production=True)
    assert report["status"] == "qualified"
    candidate["creative_projection"]["creative_beats"][0]["source_dialogue"] = {"speaker": "Other", "text": "changed"}
    report = validate_director_contract_v2(candidate, scene=_scene(), production=True)
    assert {item["code"] for item in report["errors"]} & {"DIRECTOR_SOURCE_SPEAKER_MUTATION", "DIRECTOR_SOURCE_DIALOGUE_MUTATION"}


def test_authored_beat_fixture_stays_on_legacy_contract():
    scene = {"name": "Authored", "beats": [{"beat_id": "B1", "type": "action", "event": "turn"}]}
    treatment = {"director_contract_version": "director_semantic_contract_v1", "director_beat_decisions": [{"beat_ref": "B1", "dramatic_purpose": "SETUP_RELATIONSHIP", "audience_state_delta": {"knowledge_added": [], "knowledge_confirmed": [], "knowledge_invalidated": [], "belief_shift": [], "open_question_added": [], "open_question_resolved": []}, "character_state_deltas": [], "performance_objectives": [], "reaction_contracts": [], "information_policy": {"audience_knows_truth": True, "characters_with_truth": [], "characters_uncertain": [], "withheld_from": []}, "tempo_function": "PROGRESS_BEAT", "source_refs": ["ScriptIR:B1"], "decision_origin": "HUMAN_AUTHORED"}]}
    assert validate_director_contract(treatment, scene=scene, production=True)["status"] == "qualified"


def test_v2_authority_envelope_preserves_full_v7_lineage():
    candidate = _creative_candidate()
    script_env = {"schema_version": "script_ir_authority_envelope_v2", "envelope_fingerprint": "ir-envelope", "authority_profile": "SOURCE_GROUNDED_V3_1", "origin_source_kind": "BOOK_CHAPTER", "origin_source_package_id": "book:990402", "origin_source_version_id": "chapter:16:sha256:raw", "origin_source_raw_hash": "raw", "origin_source_evidence_index_fingerprint": "index", "canonical_script_content_hash": "script-content", "canonical_script_payload_fingerprint": "payload", "structuring_response_fingerprint": "llm", "reconciliation_fingerprint": "recon", "migration_fingerprint": "migration", "origin_source_locator": {"book_id": 990402, "chapter_id": 16, "chapter_seq": 3}, "fact_snapshot_id": 49, "fact_snapshot_revision": 1, "fact_snapshot_payload_hash": "fact"}
    version = SimpleNamespace(id=52, revision=1, payload_hash="ir-payload")
    envelope = build_treatment_authority_envelope_v2(treatment=candidate, evidence={"book_id": 990453, "episode": 1, "scene": _scene(), "scene_id": "E01_SC001"}, script_ir={"source_grounded_schema_version": "source_grounded_script_payload_v3_1"}, script_ir_version=version, script_ir_envelope=script_env, treatment_id=1, treatment_revision=1)
    assert envelope["schema_version"] == SCHEMA_VERSION_V2
    assert envelope["authority_policy_version"] == AUTHORITY_POLICY_VERSION_V2
    for key in ("origin_source_kind", "origin_source_package_id", "origin_source_version_id", "origin_source_raw_hash", "origin_source_evidence_index_fingerprint", "canonical_script_content_hash", "canonical_script_payload_fingerprint", "structuring_response_fingerprint", "reconciliation_fingerprint", "migration_fingerprint"):
        assert envelope[key] == script_env[key]


def test_v2_authority_resolver_rechecks_current_script_ir_and_can_stale():
    init_db()
    with Session() as session:
        book = Book(title="v7.1 resolver", filename="v71-resolver", status="imported")
        session.add(book); session.flush()
        script = Script(book_id=book.id, episode=1, content="{}", current_script_ir_version_id=None, workflow_profile="production")
        session.add(script); session.flush()
        payload = _creative_candidate()
        ir_env = {"schema_version": "script_ir_authority_envelope_v2", "envelope_fingerprint": "ir-envelope", "authority_profile": "SOURCE_GROUNDED_V3_1", "origin_source_kind": "BOOK_CHAPTER", "origin_source_package_id": "book:990402", "origin_source_version_id": "chapter:16:sha256:raw", "origin_source_raw_hash": "raw", "origin_source_evidence_index_fingerprint": "index", "canonical_script_content_hash": "script-content", "canonical_script_payload_fingerprint": "payload", "structuring_response_fingerprint": "llm", "reconciliation_fingerprint": "recon", "migration_fingerprint": "migration", "origin_source_locator": {}, "fact_snapshot_id": 1, "fact_snapshot_revision": 1, "fact_snapshot_payload_hash": "fact"}
        ir = ScriptIRVersion(book_id=book.id, episode=1, revision=1, status="production_qualified", qualification_state="PRODUCTION_QUALIFIED", payload_hash="ir-payload", payload_json=json.dumps({"scenes": [_scene()]}, ensure_ascii=False), authority_envelope_json=json.dumps(ir_env), stale_status="FRESH")
        session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        fact = FactSnapshot(id=1, book_id=book.id, episode=1, revision=1, status="confirmed", payload_hash="fact", source_fingerprint="raw")
        session.add(fact); session.flush()
        evidence = {"book_id": book.id, "episode": 1, "scene": _scene(), "scene_id": "E01_SC001"}
        auth_env = build_treatment_authority_envelope_v2(treatment=payload, evidence=evidence, script_ir={}, script_ir_version=ir, script_ir_envelope=ir_env, treatment_id=1, treatment_revision=1)
        row = DirectorTreatment(id=1, book_id=book.id, episode=1, scene_id="E01_SC001", scene_name="", status="approved", qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", revision=1, source_constraints=json.dumps({**payload["source_constraints"], "schema_version": "director_treatment_v3"}), director_decisions=json.dumps({"schema_version": "director_treatment_v3", "creative_projection": payload["creative_projection"]}), unknowns="[]", payload_hash=payload_hash(payload))
        session.add(row); session.flush()
        auth_env["treatment_id"] = row.id; auth_env["treatment_payload_hash"] = row.payload_hash; auth_env["envelope_fingerprint"] = ""  # recompute after row identity is bound
        from core.director_treatment_authority import _envelope_fingerprint
        auth_env["envelope_fingerprint"] = _envelope_fingerprint(auth_env)
        authority = DirectorTreatmentAuthority(book_id=book.id, episode=1, scene_id="E01_SC001", treatment_id=row.id, treatment_revision=1, payload_hash=row.payload_hash, envelope_fingerprint=auth_env["envelope_fingerprint"], envelope_json=json.dumps(auth_env), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH")
        pointer = DirectorTreatmentPointer(book_id=book.id, episode=1, scene_id="E01_SC001", treatment_id=row.id, treatment_revision=1, authority_envelope_fingerprint=auth_env["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED")
        session.add_all([authority, pointer]); session.commit()
        with patch("core.script_ir.resolve_script_payload", return_value={"scenes": [_scene()]}):
            resolved, resolved_env = resolve_current_authoritative_treatment(session, book_id=book.id, episode=1, scene_id="E01_SC001")
        assert resolved.id == row.id
        assert resolved_env["schema_version"] == SCHEMA_VERSION_V2
        session.query(DirectorTreatmentPointer).filter_by(book_id=book.id).delete(); session.query(DirectorTreatmentAuthority).filter_by(book_id=book.id).delete(); session.query(DirectorTreatment).filter_by(book_id=book.id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book.id).delete(); session.query(FactSnapshot).filter_by(book_id=book.id).delete(); session.query(Script).filter_by(book_id=book.id).delete(); session.query(Book).filter_by(id=book.id).delete(); session.commit()


def test_llm_raw_forensic_callback_runs_before_json_parser(monkeypatch):
    events = []
    monkeypatch.setattr("core.llm.call_llm", lambda *args, **kwargs: '{"creative_projection": {}}')
    monkeypatch.setattr("core.llm.parse_json_object", lambda text, **kwargs: events.append(("parse", text)) or {"creative_projection": {}})
    result = call_llm_json("prompt", required_keys={"creative_projection"}, raw_response_callback=lambda record: events.append(("raw", record["raw_response"])))
    assert result == {"creative_projection": {}}
    assert [event[0] for event in events] == ["raw", "parse"]
