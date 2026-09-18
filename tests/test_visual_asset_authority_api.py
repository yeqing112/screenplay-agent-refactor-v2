import json

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Session, VisualAssetPointer, VisualAssetVersion, init_db


def test_visual_asset_authority_api_is_confirmed_and_provider_free():
    init_db()
    client = TestClient(app)
    with Session() as session:
        book = Book(title="authority api", filename="authority-api.txt", status="imported")
        session.add(book); session.commit(); book_id = book.id
    try:
        pending = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-requests", json={"missing_field": "baseline_hairstyle"})
        assert pending.status_code == 200
        request_id = pending.json()["request_id"]
        rejected = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-decisions", json={"request_id": request_id, "field": "baseline_hairstyle", "value": "short", "confirmed": False})
        assert rejected.status_code == 409
        decision = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-decisions", json={"request_id": request_id, "field": "baseline_hairstyle", "value": "short", "confirmed": True})
        assert decision.status_code == 200
        version = client.post(f"/api/books/{book_id}/visual-assets/authority/character/versions", json={"canonical_id": "C1", "canonical_identity": {"character_id": "C1"}, "authoring_decisions": [{"field": "baseline_hairstyle", "value": "short", "decision_id": decision.json()["decision_id"]}], "confirmed": True})
        assert version.status_code == 200, version.text
        assert version.json()["provider_calls"] == 0
        draft = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/reference-generation-drafts", json={"board_type": "six_view_board"})
        assert draft.status_code == 200, draft.text
        assert draft.json()["provider_not_called"] is True
        current = client.get(f"/api/books/{book_id}/visual-assets/authority/character/C1/current")
        assert current.status_code == 200
        assert current.json()["version"]["asset_key"] == f"book:{book_id}:character:C1"
    finally:
        with Session() as session:
            session.query(VisualAssetPointer).filter_by(book_id=book_id).delete(synchronize_session=False)
            session.query(VisualAssetVersion).filter_by(book_id=book_id).delete(synchronize_session=False)
            session.query(Book).filter_by(id=book_id).delete(synchronize_session=False)
            session.commit()
