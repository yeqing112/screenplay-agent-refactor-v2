import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Script, Session, FactSnapshot, FactRecord, ScriptIRVersion, init_db


def test_targeted_missing_fact_api_is_provider_free_and_fail_closed():
    init_db()
    client = TestClient(app)
    with Session() as session:
        book = Book(title="targeted coverage api", filename="targeted.txt", status="imported")
        session.add(book)
        session.flush()
        session.add(Script(book_id=book.id, episode=1, content="FACT: subject_type=character; subject_id=林晚; predicate=gender; value=female\n"))
        session.commit()
        book_id = book.id
    try:
        requirements = [{"subject_type": "character", "subject_id": "林晚", "predicate": "gender", "scope": "global", "required": True}]
        missing = client.post(f"/api/books/{book_id}/episodes/1/fact-coverage/missing-manifest", json={"requirements": requirements})
        assert missing.status_code == 200
        assert missing.json()["status"] == "FACT_COVERAGE_INSUFFICIENT"
        assert missing.json()["missing_fact_manifest"]["count"] == 1
        extracted = client.post(f"/api/books/{book_id}/episodes/1/fact-coverage/targeted-extract", json={"requirements": requirements})
        assert extracted.status_code == 200
        body = extracted.json()
        assert body["llm_called"] is False
        assert body["provider_calls"] == 0
        assert len(body["extraction"]["candidates"]) == 1
        assert body["merge"]["changed"] is True
        # Read-only extraction must not create a snapshot row.
        with Session() as session:
            assert session.query(FactSnapshot).filter_by(book_id=book_id).count() == 0
    finally:
        with Session() as session:
            ids = [row.id for row in session.query(FactSnapshot).filter_by(book_id=book_id).all()]
            if ids:
                session.query(FactRecord).filter(FactRecord.snapshot_id.in_(ids)).delete(synchronize_session=False)
            session.query(FactSnapshot).filter_by(book_id=book_id).delete()
            session.query(Script).filter_by(book_id=book_id).delete()
            session.query(Book).filter_by(id=book_id).delete()
            session.commit()


def test_script_ir_confirm_is_blocked_when_bound_snapshot_reports_insufficient_coverage():
    init_db()
    client = TestClient(app)
    with Session() as session:
        book = Book(title="script gate coverage", filename="gate.txt", status="imported")
        session.add(book); session.flush()
        script = Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{"name": "门厅", "beats": [{"event": "进入"}]}]}, ensure_ascii=False))
        session.add(script)
        snapshot = FactSnapshot(book_id=book.id, episode=1, revision=1, status="confirmed", source_fingerprint="", payload_hash="", records_json="[]", validation_report=json.dumps({"fact_coverage": {"status": "FACT_COVERAGE_INSUFFICIENT", "missing_fact_manifest": {"count": 1}}}, ensure_ascii=False))
        session.add(snapshot); session.commit(); book_id, snapshot_id = book.id, snapshot.id
    try:
        built = client.post(f"/api/books/{book_id}/episodes/1/script-ir/build", json={"persist": True, "sourceFactSnapshotId": str(snapshot_id)})
        assert built.status_code == 200
        response = client.post(f"/api/books/{book_id}/episodes/1/script-ir/confirm", json={"versionId": built.json()["persisted_draft_id"], "confirmed": True})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "FACT_COVERAGE_INSUFFICIENT"
    finally:
        with Session() as session:
            session.query(ScriptIRVersion).filter_by(book_id=book_id).delete()
            session.query(FactSnapshot).filter_by(book_id=book_id).delete()
            session.query(Script).filter_by(book_id=book_id).delete()
            session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_semantic_resolution_api_is_read_only_and_returns_anchor_diagnostics():
    init_db()
    client = TestClient(app)
    with Session() as session:
        book = Book(title="semantic resolution api", filename="semantic.txt", status="imported")
        session.add(book); session.flush()
        session.add(Script(book_id=book.id, episode=1, content="Alice is red.\n"))
        session.commit(); book_id = book.id
    try:
        manifest = {"items": [{"fact_key": "character|Alice|is|global", "semantic_type": "character", "subject_type": "character", "entity": "Alice", "subject_id": "Alice", "predicate": "is", "scope": "global", "expected_value": "red", "required": True}]}
        response = client.post(f"/api/books/{book_id}/episodes/1/fact-coverage/semantic-resolve", json={"missing_manifest": manifest})
        assert response.status_code == 200
        body = response.json()
        assert body["llm_called"] is False and body["provider_calls"] == 0
        assert body["mutated"] is False
        assert body["results"][0]["resolution"]["support_status"] == "SUPPORTED"
        with Session() as session:
            assert session.query(FactSnapshot).filter_by(book_id=book_id).count() == 0
    finally:
        with Session() as session:
            session.query(FactSnapshot).filter_by(book_id=book_id).delete()
            session.query(Script).filter_by(book_id=book_id).delete()
            session.query(Book).filter_by(id=book_id).delete(); session.commit()
