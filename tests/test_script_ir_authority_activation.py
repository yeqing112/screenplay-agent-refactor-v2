import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from api.server import app
from core.script_ir import resolve_script_payload
from core.fact_snapshot import snapshot_hash
from core.script_ir_authority import validate_authority_envelope
from core.source_evidence_index import build_source_evidence_index
from models import Book, FactSnapshot, Script, ScriptIRVersion, Session, init_db
from tests.script_fixtures import build_explicit_production_script_payload


def _create_ready_fixture():
    init_db()
    source = build_explicit_production_script_payload({"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]})
    content = json.dumps(source, ensure_ascii=False)
    raw_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with Session() as session:
        book = Book(title="authority-test", filename="authority.txt", status="imported")
        session.add(book); session.flush()
        script = Script(book_id=book.id, episode=1, content=content)
        session.add(script); session.flush()
        records = [
            {"fact_key": "episode|scenes|scene_existence|episode", "predicate": "scene_existence", "subject_id": "1", "value": {"minimum": 1, "actual": 1}, "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]},
            {"fact_key": "scene|门厅|scene_identity|scene", "predicate": "scene_identity", "subject_id": "门厅", "value": "门厅", "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]},
        ]
        snapshot = FactSnapshot(book_id=book.id, episode=1, revision=1, status="confirmed", source_fingerprint=raw_hash, payload_hash=snapshot_hash(records), records_json=json.dumps(records, ensure_ascii=False), validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}))
        session.add(snapshot); session.commit()
        return book.id, snapshot.id, raw_hash


def _cleanup(book_id):
    with Session() as session:
        session.query(ScriptIRVersion).filter_by(book_id=book_id).delete()
        session.query(FactSnapshot).filter_by(book_id=book_id).delete()
        session.query(Script).filter_by(book_id=book_id).delete()
        session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_activation_binds_source_fact_contract_and_pointer_atomically():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)}).json()
        version_id = draft["persisted_draft_id"]
        source = build_explicit_production_script_payload({"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]})
        source_index = build_source_evidence_index(json.dumps(source, ensure_ascii=False).encode("utf-8"), source_package_id="SRC_TEST", source_version_id="SRC_TEST:V01:abc", source_raw_hash=raw_hash)
        body = {
            "versionId": version_id, "confirmed": True, "factSnapshotId": snapshot_id,
            "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01:abc", "immutableSourceRawHash": raw_hash,
            "sourceEvidenceIndex": source_index,
            "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]},
            "sourceStructure": source,
        }
        activated = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json=body)
        assert activated.status_code == 200, activated.text
        payload = activated.json()
        assert payload["status"] == "SCRIPT_IR_AUTHORITY_ACTIVATED"
        assert payload["qualification_state"] == "PRODUCTION_QUALIFIED"
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            row = session.query(ScriptIRVersion).filter_by(id=version_id).one()
            assert script.current_script_ir_version_id == version_id
            assert row.status == "production_qualified"
            assert json.loads(row.authority_envelope_json)["source_requirement_contract_version"] == "script_ir_source_requirement_contract_v1"
            assert resolve_script_payload(session, script, workflow_profile="production")["scenes"][0]["name"] == "门厅"
    finally:
        _cleanup(book_id)


def test_activation_requires_real_anchor_binding_and_rejects_placeholder():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)}).json()
        source = build_explicit_production_script_payload({"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]})
        source_index = build_source_evidence_index(json.dumps(source, ensure_ascii=False).encode("utf-8"), source_package_id="SRC_TEST", source_version_id="SRC_TEST:V01:abc", source_raw_hash=raw_hash)
        common = {"versionId": draft["persisted_draft_id"], "confirmed": True, "factSnapshotId": snapshot_id, "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01:abc", "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": source_index, "sourceStructure": source}
        blocked = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={**common, "sourceAnchorBindings": {}})
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "SOURCE_EVIDENCE_BINDING_REQUIRED"
    finally:
        _cleanup(book_id)


def test_production_resolver_does_not_fallback_to_latest_qualified_version():
    init_db()
    with Session() as session:
        book = Book(title="pointer-test", filename="pointer.txt", status="imported"); session.add(book); session.flush()
        script = Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(script); session.flush()
        session.add(ScriptIRVersion(book_id=book.id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]}))); session.commit()
        with pytest.raises(Exception, match="current ScriptIR authority pointer"):
            resolve_script_payload(session, script, workflow_profile="production")
        session.query(ScriptIRVersion).filter_by(book_id=book.id).delete(); session.query(Script).filter_by(book_id=book.id).delete(); session.query(Book).filter_by(id=book.id).delete(); session.commit()


def test_authority_validation_detects_payload_tamper_and_freshness_changes():
    envelope = {"schema_version": "script_ir_authority_envelope_v1", "qualification_state": "PRODUCTION_QUALIFIED", "qualified": True, "stale": False, "stale_status": "FRESH", "stale_reasons": [], "script_ir_payload_hash": "wrong", "envelope_fingerprint": "wrong"}
    result = validate_authority_envelope(envelope, payload={"schema_version": "script_ir_v1", "scenes": []}, expected={"source_requirement_contract_fingerprint": "new-contract"})
    codes = {row["code"] for row in result["errors"]}
    assert "SCRIPT_IR_AUTHORITY_ENVELOPE_TAMPERED" in codes
    assert "SCRIPT_IR_AUTHORITY_TAMPERED" in codes


def _activate_ready_fixture(client, book_id, snapshot_id, raw_hash):
    source = build_explicit_production_script_payload({"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]})
    draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)}).json()
    index = build_source_evidence_index(json.dumps(source, ensure_ascii=False).encode("utf-8"), source_package_id="SRC_TEST", source_version_id="SRC_TEST:V01:abc", source_raw_hash=raw_hash)
    response = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={
        "versionId": draft["persisted_draft_id"], "confirmed": True, "factSnapshotId": snapshot_id,
        "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01:abc", "immutableSourceRawHash": raw_hash,
        "sourceEvidenceIndex": index,
        "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]},
        "sourceStructure": source,
    })
    assert response.status_code == 200, response.text
    return draft["persisted_draft_id"]


def test_fact_snapshot_revision_change_blocks_production_resolver():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        _activate_ready_fixture(client, book_id, snapshot_id, raw_hash)
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            snapshot = session.query(FactSnapshot).filter_by(id=snapshot_id).one()
            snapshot.revision += 1
            session.commit()
            with pytest.raises(Exception) as exc:
                resolve_script_payload(session, script, workflow_profile="production")
            assert "FACT_SNAPSHOT" in str(exc.value) or "STALE" in str(exc.value)
    finally:
        _cleanup(book_id)


def test_fact_snapshot_payload_change_blocks_production_resolver():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        _activate_ready_fixture(client, book_id, snapshot_id, raw_hash)
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            snapshot = session.query(FactSnapshot).filter_by(id=snapshot_id).one()
            records = json.loads(snapshot.records_json)
            records.append({"fact_key": "optional|x", "predicate": "note", "subject_id": "x", "value": "changed", "status": "confirmed", "evidence": [{"anchor_ref": "E0001"}]})
            snapshot.records_json = json.dumps(records, ensure_ascii=False)
            snapshot.payload_hash = snapshot_hash(records)
            session.commit()
            with pytest.raises(Exception) as exc:
                resolve_script_payload(session, script, workflow_profile="production")
            assert "STALE" in str(exc.value)
    finally:
        _cleanup(book_id)


def test_source_change_and_payload_tamper_block_production_resolver():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        _activate_ready_fixture(client, book_id, snapshot_id, raw_hash)
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            script.content = script.content + "\nchanged"
            session.commit()
            with pytest.raises(Exception) as exc:
                resolve_script_payload(session, script, workflow_profile="production")
            assert "SOURCE" in str(exc.value) or "STALE" in str(exc.value)
    finally:
        _cleanup(book_id)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        version_id = _activate_ready_fixture(client, book_id, snapshot_id, raw_hash)
        with Session() as session:
            row = session.query(ScriptIRVersion).filter_by(id=version_id).one()
            row.payload_json = json.dumps({"schema_version": "script_ir_v1", "book_id": book_id, "episode": 1, "scenes": []}, ensure_ascii=False)
            session.commit()
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            with pytest.raises(Exception) as exc:
                resolve_script_payload(session, script, workflow_profile="production")
            assert "TAMPERED" in str(exc.value) or "PAYLOAD" in str(exc.value)
    finally:
        _cleanup(book_id)


def test_contract_and_requirement_set_changes_are_stale(monkeypatch):
    import core.script_ir_source_requirements as requirements_module

    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        _activate_ready_fixture(client, book_id, snapshot_id, raw_hash)
        original_contract = requirements_module.script_ir_source_requirement_contract
        monkeypatch.setattr(requirements_module, "script_ir_source_requirement_contract", lambda: {**original_contract(), "fingerprint": "contract-changed"})
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            with pytest.raises(Exception) as exc:
                resolve_script_payload(session, script, workflow_profile="production")
            assert "STALE" in str(exc.value)
    finally:
        _cleanup(book_id)

    monkeypatch.undo()
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        _activate_ready_fixture(client, book_id, snapshot_id, raw_hash)
        original_requirements = requirements_module.compile_script_ir_source_requirements
        monkeypatch.setattr(requirements_module, "compile_script_ir_source_requirements", lambda **kwargs: {**original_requirements(**kwargs), "fingerprint": "requirement-set-changed"})
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            with pytest.raises(Exception) as exc:
                resolve_script_payload(session, script, workflow_profile="production")
            assert "STALE" in str(exc.value)
    finally:
        _cleanup(book_id)


def test_activation_failure_does_not_update_current_pointer_and_wrong_snapshot_is_blocked():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    wrong_book_id = book_id + 999
    try:
        draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)}).json()
        source = build_explicit_production_script_payload({"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]})
        index = build_source_evidence_index(json.dumps(source, ensure_ascii=False).encode("utf-8"), source_package_id="SRC_TEST", source_version_id="SRC_TEST:V01:abc", source_raw_hash=raw_hash)
        blocked = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={"versionId": draft["persisted_draft_id"], "confirmed": True, "factSnapshotId": snapshot_id, "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01:abc", "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": index, "sourceAnchorBindings": {}})
        assert blocked.status_code == 409
        with Session() as session:
            script = session.query(Script).filter_by(book_id=book_id, episode=1).one()
            assert script.current_script_ir_version_id is None
            wrong = FactSnapshot(book_id=wrong_book_id, episode=1, revision=1, status="confirmed", source_fingerprint=raw_hash, payload_hash="wrong", records_json="[]", validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}))
            session.add(wrong); session.commit(); wrong_id = wrong.id
        blocked_wrong = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={"versionId": draft["persisted_draft_id"], "confirmed": True, "factSnapshotId": wrong_id, "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01:abc", "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": index, "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]}, "sourceStructure": source})
        assert blocked_wrong.status_code == 409
        assert blocked_wrong.json()["detail"]["code"] == "FACT_SNAPSHOT_BINDING_INVALID"
    finally:
        _cleanup(book_id)
        # The deliberately mismatched snapshot belongs to a synthetic book
        # identity; remove it explicitly so a later SQLite id reuse cannot
        # make this test depend on execution order.
        with Session() as session:
            session.query(FactSnapshot).filter_by(book_id=wrong_book_id).delete()
            session.commit()


def test_placeholder_and_stale_draft_cannot_become_authority():
    client = TestClient(app)
    book_id, snapshot_id, raw_hash = _create_ready_fixture()
    try:
        draft = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)}).json()
        with Session() as session:
            row = session.query(ScriptIRVersion).filter_by(id=draft["persisted_draft_id"]).one()
            payload = json.loads(row.payload_json)
            payload["scenes"][0]["name"] = "未命名场景1"
            row.payload_json = json.dumps(payload, ensure_ascii=False)
            row.payload_hash = "tampered-draft"
            session.commit()
        source = build_explicit_production_script_payload({"episode": 1, "scenes": [{"name": "门厅", "beats": [{"id": "B1", "event": "进入"}]}]})
        index = build_source_evidence_index(json.dumps(source, ensure_ascii=False).encode("utf-8"), source_package_id="SRC_TEST", source_version_id="SRC_TEST:V01:abc", source_raw_hash=raw_hash)
        blocked = client.post(f"/api/books/{book_id}/episodes/1/script-ir/activate", json={"versionId": draft["persisted_draft_id"], "confirmed": True, "factSnapshotId": snapshot_id, "sourcePackageId": "SRC_TEST", "sourceVersionId": "SRC_TEST:V01:abc", "immutableSourceRawHash": raw_hash, "sourceEvidenceIndex": index, "sourceAnchorBindings": {"episode|scenes|scene_existence|episode": ["E0001"], "scene|门厅|scene_identity|scene": ["E0001"]}, "sourceStructure": source})
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "SCENE_NAME_SOURCE_AUTHORITY_REQUIRED"
    finally:
        _cleanup(book_id)
