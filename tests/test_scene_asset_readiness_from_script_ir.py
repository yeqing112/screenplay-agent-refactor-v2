import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Script, ScriptIRVersion, Session, VisualLocation, VisualMakeup, VisualProp, init_db


def test_registry_endpoint_requires_confirmed_and_qualified_ir():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="registry api", filename="registry-api.txt", status="imported"); session.add(book); session.flush()
        script = Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(script); session.flush()
        ir = {"schema_version": "script_ir_v1", "book_id": book.id, "episode": 1, "scenes": [{"scene_id": "E01_SC001", "name": "门厅", "location_name": "门厅", "beats": [{"beat_id": "B1", "event": "进入"}]}], "characters": []}
        session.add(ScriptIRVersion(book_id=book.id, episode=1, status="qualified", payload_json=json.dumps(ir, ensure_ascii=False), payload_hash="ir-hash", source_fingerprint="src", validation_status="qualified", validation_report=json.dumps({"status": "qualified"}))); session.commit(); book_id = book.id
    blocked = client.post(f"/api/books/{book_id}/episodes/1/asset-registry/sync", json={})
    assert blocked.status_code == 409
    ok = client.post(f"/api/books/{book_id}/episodes/1/asset-registry/sync", json={"confirmed": True})
    assert ok.status_code == 200
    assert ok.json()["created"]["scene"] == 1
    with Session() as session:
        session.query(VisualLocation).filter_by(book_id=book_id).delete(); session.query(VisualMakeup).filter_by(book_id=book_id).delete(); session.query(VisualProp).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()

