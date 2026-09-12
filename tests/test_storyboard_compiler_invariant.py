import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Session, ShotPlan, StoryboardShot, init_db


def test_materialized_production_shot_has_phase_a_state():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="compiler invariant", filename="compiler.txt", status="imported"); session.add(book); session.flush()
        session.add(ShotPlan(book_id=book.id, episode=1, scene_name="门厅", status="approved", evidence_fingerprint="fp", shots=json.dumps([{"plan_shot_id": "S01", "event": "进入", "duration_hint_seconds": 4, "camera": {"movement": "static"}, "entry_state": {}, "exit_state": {}}]))); session.commit(); book_id = book.id
    response = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert response.status_code == 200
    with Session() as session:
        shot = session.query(StoryboardShot).filter_by(book_id=book_id).one()
        meta = json.loads(shot.meta_info)
        assert meta["prompt_compiler"]["phase_a_status"] == "pass"
        assert meta["prompt_compiler"]["compiler_fingerprint"]
        session.query(StoryboardShot).filter_by(book_id=book_id).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()

