import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, DirectorTreatment, SceneBlocking, Script, ScriptIRVersion, Session, ShotPlan, StoryboardShot, init_db
from unittest.mock import patch


def test_materialize_endpoint_requires_confirmation_and_is_deterministic():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer", filename="materializer.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="门厅", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="门厅", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="fp", shots=json.dumps([{"plan_shot_id": "S01", "event": "进入", "duration_hint_seconds": 4, "camera": {"movement": "static"}, "entry_state": {}, "exit_state": {}}])); session.add(plan); session.commit()
    blocked = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={})
    assert blocked.status_code == 409
    ok = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert ok.status_code == 200
    assert ok.json()["materialized_count"] == 1
    with Session() as session:
        assert session.query(StoryboardShot).filter_by(book_id=book_id).count() == 1
        session.query(StoryboardShot).filter_by(book_id=book_id).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_production_materializer_never_calls_storyboard_agent():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-no-agent", filename="materializer-no-agent.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "走廊"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "走廊"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="走廊", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="走廊", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="走廊", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, evidence_fingerprint="fp", shots=json.dumps([
            {"plan_shot_id": "S01", "event": "停步", "action_beats": [{"at": 0.5, "action": "停步"}], "duration_hint_seconds": 3, "camera": {"movement": "static"}, "entry_state": {"position": "门口"}, "exit_state": {"position": "走廊"}, "asset_bindings": {"character": ["C1"]}, "continuity_contract": {"screen_direction": "left_to_right"}},
            {"plan_shot_id": "S02", "event": "回望", "action_beats": [{"at": 1.0, "action": "回望"}], "duration_hint_seconds": 4, "camera": {"movement": "push-in"}, "entry_state": {"position": "走廊"}, "exit_state": {"position": "走廊"}, "asset_bindings": {"character": ["C1"]}, "continuity_contract": {"screen_direction": "left_to_right"}},
        ])); session.add(plan); session.commit()
    with patch("agents.storyboard.StoryboardAgent.run", side_effect=AssertionError("production must not call StoryboardAgent")) as run:
        response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 200
    assert response.json()["materialized_count"] == 2
    assert run.call_count == 0
    with Session() as session:
        rows = session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).order_by(StoryboardShot.shot_id).all()
        assert len(rows) == 2
        meta = [json.loads(row.meta_info) for row in rows]
        assert {item["plan_shot_id"] for item in meta} == {"S01", "S02"}
        assert all(item["workflow_profile"] == "production" for item in meta)
        assert meta[0]["action_beats"] == [{"at": 0.5, "action": "停步"}]
        assert meta[0]["asset_bindings"] == {"character": ["C1"]}
        assert meta[0]["continuity_contract"] == {"screen_direction": "left_to_right"}
        session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_production_materializer_fails_closed_when_upstream_evidence_is_missing():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-blocked", filename="materializer-blocked.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        session.add(Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "仓库"}]}), workflow_profile="production"))
        session.add(ShotPlan(book_id=book_id, episode=1, scene_name="仓库", status="approved", shots=json.dumps([{ "plan_shot_id": "S01", "event": "等待"}]))); session.commit()
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 409
    assert "qualified ScriptIR" in str(response.json()["detail"])
    with Session() as session:
        session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()


def test_qualification_blocker_never_promotes_materialized_shot_to_ready():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer-qualification", filename="materializer-qualification.txt", status="imported"); session.add(book); session.flush(); book_id = book.id
        script = Script(book_id=book_id, episode=1, content=json.dumps({"scenes": [{"name": "车站"}]}), workflow_profile="production"); session.add(script); session.flush()
        ir = ScriptIRVersion(book_id=book_id, episode=1, status="qualified", validation_status="qualified", payload_json=json.dumps({"scenes": [{"name": "车站"}]})); session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
        treatment = DirectorTreatment(book_id=book_id, episode=1, scene_name="车站", status="approved"); session.add(treatment); session.flush()
        blocking = SceneBlocking(book_id=book_id, episode=1, scene_name="车站", status="approved", treatment_id=treatment.id); session.add(blocking); session.flush()
        plan = ShotPlan(book_id=book_id, episode=1, scene_name="车站", status="approved", treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps([{ "plan_shot_id": "S01", "event": "", "duration_hint_seconds": 3, "camera": {"movement": "static"}}])); session.add(plan); session.commit()
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 200
    with Session() as session:
        row = session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).one()
        assert row.quality_status == "needs_review"
        assert row.production_status == "blocked"
        meta = json.loads(row.meta_info)
        assert meta["qualification"]["status"] == "needs_review"
        session.query(StoryboardShot).filter_by(book_id=book_id, episode=1).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(SceneBlocking).filter_by(book_id=book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=book_id).delete(); session.query(ScriptIRVersion).filter_by(book_id=book_id).delete(); session.query(Script).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()
