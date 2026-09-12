import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, DirectorTreatment, SceneBlocking, Script, ScriptIRVersion, Session, ShotPlan, StoryboardShot, init_db


def test_materialized_production_shot_has_phase_a_state():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="compiler invariant", filename="compiler.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="门厅", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        session.add(ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="fp", shots=json.dumps([{"plan_shot_id": "S01", "event": "进入", "duration_hint_seconds": 4, "camera": {"movement": "static"}, "entry_state": {}, "exit_state": {}}]))); session.commit()
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 200
    with Session() as session:
        shot = session.query(StoryboardShot).filter_by(book_id=book_id).one()
        meta = json.loads(shot.meta_info)
        assert meta["prompt_compiler"]["phase_a_status"] == "pass"
        assert meta["prompt_compiler"]["compiler_fingerprint"]
        session.query(StoryboardShot).filter_by(book_id=book_id).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()
