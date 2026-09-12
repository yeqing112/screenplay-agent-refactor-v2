import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Session, ShotPlan, StoryboardShot, init_db


def test_materialize_endpoint_requires_confirmation_and_is_deterministic():
    init_db(); client = TestClient(app)
    with Session() as session:
        book = Book(title="materializer", filename="materializer.txt", status="imported"); session.add(book); session.flush()
        plan = ShotPlan(book_id=book.id, episode=1, scene_name="门厅", status="approved", evidence_fingerprint="fp", shots=json.dumps([{"plan_shot_id": "S01", "event": "进入", "duration_hint_seconds": 4, "camera": {"movement": "static"}, "entry_state": {}, "exit_state": {}}])); session.add(plan); session.commit(); book_id = book.id
    blocked = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={})
    assert blocked.status_code == 409
    ok = client.post(f"/api/books/{book_id}/episodes/1/storyboard/materialize", json={"confirmed": True})
    assert ok.status_code == 200
    assert ok.json()["materialized_count"] == 1
    with Session() as session:
        assert session.query(StoryboardShot).filter_by(book_id=book_id).count() == 1
        session.query(StoryboardShot).filter_by(book_id=book_id).delete(); session.query(ShotPlan).filter_by(book_id=book_id).delete(); session.query(Book).filter_by(id=book_id).delete(); session.commit()

