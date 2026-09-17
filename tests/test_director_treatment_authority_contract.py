import json
import hashlib
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.director_treatment_authority import (
    contract_fingerprint,
    treatment_contract,
    treatment_payload_from_row,
    validate_treatment_candidate,
    build_treatment_authority_envelope,
    classify_asset_authority,
    mark_treatment_stale,
    resolve_scene_for_treatment,
    payload_hash as treatment_payload_hash,
)
from core.director_treatment_authority import resolve_current_authoritative_treatment
from models import Book, DirectorTreatmentPointer, Session, init_db
from api.server import app
from fastapi.testclient import TestClient
from core.fact_snapshot import snapshot_hash
from core.source_evidence_index import build_source_evidence_index
from models import FactSnapshot, Script, ScriptIRVersion, DirectorTreatment, DirectorTreatmentAuthority


class Row:
    scene_id = "E01_SC001"
    scene_name = "门厅"
    dramatic_objective = "建立冲突"
    audience_question = "谁会先让步？"
    character_intents = json.dumps({"c1": {"name": "林默", "goal": "进入"}})
    beat_map = json.dumps([{"beat_id": "E01_SC001_B01", "type": "action", "event": "林默停下"}])
    relationship_power_shift = ""
    audience_emotion = "紧张"
    information_strategy = "延迟揭示"
    performance_direction = "克制"
    visual_strategy = "门框压迫"
    coverage_strategy = "先建立空间"
    sound_strategy = "雨声"
    edit_rhythm = "缓慢"
    constraints = json.dumps(["不得新增人物"])
    unknowns = json.dumps(["门锁状态未知"])


def baseline():
    row = Row()
    payload = treatment_payload_from_row(row)
    return payload


def test_contract_is_scene_blocking_consumer_derived_and_stable():
    contract = treatment_contract()
    assert contract["schema_version"] == "director_treatment_authority_contract_v1"
    assert "scene_id" in contract["source_constraint_fields"]
    assert "visual_strategy" in contract["director_decision_fields"]
    assert "scene_geometry" in contract["downstream_authoring_fields"]
    assert contract_fingerprint() == contract_fingerprint()


def test_source_beats_and_identity_cannot_be_modified():
    base = baseline()
    candidate = {**base, "beat_map": [{"beat_id": "E01_SC001_B01", "type": "action", "event": "改写事实"}]}
    with pytest.raises(ValueError, match="immutable"):
        validate_treatment_candidate(candidate, base)
    with pytest.raises(ValueError, match="scene_id"):
        validate_treatment_candidate({**base, "scene_id": "E01_SC009"}, base)


def test_director_decision_can_change_but_unknowns_are_preserved():
    base = baseline()
    updated = validate_treatment_candidate({**base, "dramatic_objective": "新的导演目标", "character_intents": {"c1": {"goal": "后退"}}}, base)
    assert updated["dramatic_objective"] == "新的导演目标"
    assert updated["character_intents"]["c1"]["name"] == "林默"
    assert updated["unknowns"] == ["门锁状态未知"]
    with pytest.raises(ValueError, match="unknowns"):
        validate_treatment_candidate({**base, "unknowns": []}, base)


def test_non_whitelisted_downstream_authoring_is_rejected():
    base = baseline()
    with pytest.raises(ValueError, match="non-whitelisted"):
        validate_treatment_candidate({**base, "scene_geometry": {"door": "wood"}}, base)


def test_production_resolver_has_no_latest_approved_fallback():
    init_db()
    with Session() as session:
        book = Book(title="authority-pointer-test", filename="authority-pointer-test.txt", status="imported")
        session.add(book); session.commit(); book_id = book.id
        with pytest.raises(HTTPException) as exc:
            resolve_current_authoritative_treatment(session, book_id=book_id, episode=1, scene_id="E01_SC001")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "DIRECTOR_TREATMENT_POINTER_MISSING"
        session.query(DirectorTreatmentPointer).filter_by(book_id=book_id).delete()
        session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_production_candidate_activation_binds_pointer_without_provider_by_default():
    init_db(); client = TestClient(app)
    source = {"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]}
    content = json.dumps(source, ensure_ascii=False); raw_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with Session() as session:
        book = Book(title="treatment-production-test", filename="treatment-production-test.txt", status="imported"); session.add(book); session.flush()
        script = Script(book_id=book.id, episode=1, content=content); session.add(script)
        records = [{"fact_key": "episode|scenes|scene_existence|episode", "predicate": "scene_existence", "subject_id": "1", "value": {"minimum": 1, "actual": 1}, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]}, {"fact_key": "scene|门厅|scene_identity|scene", "predicate": "scene_identity", "subject_id": "门厅", "value": "门厅", "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]}]
        snapshot = FactSnapshot(book_id=book.id, episode=1, revision=1, status="confirmed", source_fingerprint=raw_hash, payload_hash=snapshot_hash(records), records_json=json.dumps(records, ensure_ascii=False), validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}})); session.add(snapshot); session.commit(); book_id, snapshot_id = book.id, snapshot.id
    try:
        draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)}).json(); version_id = draft["persisted_draft_id"]
        idx = build_source_evidence_index(content.encode("utf-8"), source_package_id="SRC_TEST", source_version_id="SRC_TEST:V01", source_raw_hash=raw_hash)
        activation = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={"versionId": version_id, "confirmed": True, "factSnapshotId": snapshot_id, "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01", "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": idx, "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]}, "sourceStructure": source}); assert activation.status_code == 200, activation.text
        preview = client.post(f"/api/books/{book_id}/episodes/1/director-treatment/preview", json={"workflowProfile": "production", "sceneId": "E01_SC001"}); assert preview.status_code == 200, preview.text
        base = preview.json()["treatment"]
        candidate = {"scene_id": base["scene_id"], "scene_name": base["scene_name"], "dramatic_objective": "重新组织冲突", "audience_question": base["audience_question"], "character_intents": base["character_intents"], "beat_map": base["beat_map"], "visual_strategy": base["visual_strategy"]}
        with patch("api.director_treatment_api.llm_client.call_llm_json", return_value=candidate):
            generated = client.post(f"/api/books/{book_id}/episodes/1/director-treatment/llm-draft", json={"workflowProfile": "production", "sceneId": "E01_SC001", "packetFingerprint": preview.json()["packet_fingerprint"], "confirmed": True, "allowExternalCall": True})
        assert generated.status_code == 200, generated.text
        approved = client.post(f"/api/books/{book_id}/episodes/1/director-treatment/confirm", json={"workflowProfile": "production", "packetId": generated.json()["packet_id"], "packetFingerprint": generated.json()["packet_fingerprint"], "confirmed": True})
        assert approved.status_code == 200, approved.text
        body = approved.json(); assert body["authority_bound"] is True; assert body["qualification_state"] == "PRODUCTION_QUALIFIED"; assert body["provider_calls"] == 0
        blocking = client.post(f"/api/books/{book_id}/episodes/1/scene-blocking/preview", json={"workflowProfile": "production", "sceneId": "E01_SC001"})
        assert blocking.status_code == 200, blocking.text
        with Session() as session:
            assert session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, scene_id="E01_SC001", treatment_id=body["treatment"]["id"]).count() == 1
            assert session.query(DirectorTreatmentAuthority).filter_by(treatment_id=body["treatment"]["id"]).count() == 1
    finally:
        with Session() as session:
            session.query(DirectorTreatmentPointer).filter_by(book_id=book_id).delete(); session.query(DirectorTreatmentAuthority).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(FactSnapshot).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_locked_reference_requires_a_resolvable_reference_before_becoming_authority():
    locked = classify_asset_authority({"locked_references": [{"id": 1, "status": "locked", "asset_type": "location", "asset_name": "门厅", "image_url": "https://example.invalid/door.png"}]})
    assert len(locked["locked_constraints"]) == 1
    assert locked["locked_constraints"][0]["authority_class"] == "LOCKED_PRODUCTION_CONSTRAINT"
    pending = classify_asset_authority({"locked_references": [{"id": 2, "status": "locked", "asset_type": "location", "asset_name": "无图场景"}]})
    assert pending["locked_constraints"] == []
    assert pending["authoring_pending"][0]["authority_class"] == "AUTHORING_PENDING"


def test_unlocked_asset_is_advisory_context_only():
    result = classify_asset_authority({"characters": [{"id": "c1", "name": "林默", "asset_status": "draft"}]})
    assert result["locked_constraints"] == []
    assert result["advisory_context"][0]["authority_class"] == "ADVISORY_ASSET_CONTEXT"


def test_authority_envelope_binds_script_fact_contract_and_asset_lineage():
    treatment = {**baseline(), "scene_id": "E01_SC001"}
    scene = {"scene_id": "E01_SC001", "name": "门厅", "participants": []}
    version = SimpleNamespace(id=11, revision=3, payload_hash="ir-hash")
    script_envelope = {"envelope_fingerprint": "script-envelope", "source_package_id": "SRC", "source_version_id": "SRC:V3", "immutable_source_raw_hash": "raw", "source_evidence_index_fingerprint": "idx", "fact_snapshot_id": 7, "fact_snapshot_revision": 2, "fact_snapshot_payload_hash": "fact"}
    result = build_treatment_authority_envelope(treatment=treatment, evidence={"book_id": 9, "episode": 1, "scene": scene, "scene_id": "E01_SC001", "scene_name": "门厅", "characters": [], "locked_references": []}, script_ir={"scenes": [scene]}, script_ir_version=version, script_ir_envelope=script_envelope, treatment_id=4, treatment_revision=2)
    assert result["scene_id"] == "E01_SC001"
    assert result["script_ir"]["id"] == 11
    assert result["fact_snapshot"]["id"] == 7
    assert result["contract"]["schema_version"] == "director_treatment_authority_contract_v1"
    assert result["treatment_payload_hash"] == treatment_payload_hash(treatment)
    assert result["envelope_fingerprint"]


def test_candidate_cannot_add_or_drop_declared_participants():
    base = baseline()
    with pytest.raises(ValueError, match="character_intents"):
        validate_treatment_candidate({**base, "character_intents": {"c2": {"goal": "进入"}}}, base)


def test_candidate_unknowns_can_only_be_preserved_or_explicitly_appended():
    base = baseline()
    candidate = validate_treatment_candidate({**base, "unknowns": ["门锁状态未知", "灯光色温未知"]}, base)
    assert candidate["unknowns"] == ["门锁状态未知", "灯光色温未知"]


def test_production_scene_resolution_requires_scene_id_even_when_name_exists():
    script_row = SimpleNamespace(book_id=1, episode=1, content=json.dumps({"scenes": [{"scene_id": "E01_SC001", "name": "门厅"}]}))
    with pytest.raises(HTTPException) as exc:
        resolve_scene_for_treatment(None, script_row, scene_name="门厅", workflow_profile="production")
    assert exc.value.detail["code"] == "SCENE_ID_REQUIRED"


def test_mark_treatment_stale_sets_explicit_state_and_removes_pointer():
    init_db()
    with Session() as session:
        book = Book(title="stale-state-test", filename="stale-state-test.txt", status="imported")
        session.add(book); session.flush()
        treatment = DirectorTreatment(book_id=book.id, episode=1, scene_id="E01_SC001", scene_name="门厅", status="approved", qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", payload_hash="p")
        session.add(treatment); session.flush()
        pointer = DirectorTreatmentPointer(book_id=book.id, episode=1, scene_id="E01_SC001", treatment_id=treatment.id, treatment_revision=1, authority_envelope_fingerprint="fp", qualification_state="PRODUCTION_QUALIFIED")
        session.add(pointer); session.commit()
        mark_treatment_stale(session, treatment, ["SOURCE_CHANGED"]); session.commit(); session.refresh(treatment)
        assert treatment.status == "stale"
        assert treatment.qualification_state == "STALE"
        assert session.query(DirectorTreatmentPointer).filter_by(treatment_id=treatment.id).count() == 0
        session.query(DirectorTreatment).filter_by(id=treatment.id).delete(); session.query(Book).filter_by(id=book.id).delete(); session.commit()


def test_llm_call_boundary_rejects_missing_explicit_confirmation_without_provider_call():
    client = TestClient(app)
    with patch("api.director_treatment_api.llm_client.call_llm_json") as call:
        response = client.post("/api/books/999999/episodes/1/director-treatment/llm-draft", json={"workflowProfile": "production", "sceneId": "E01_SC001"})
    assert response.status_code == 409
    call.assert_not_called()
