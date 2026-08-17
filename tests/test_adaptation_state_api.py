import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, KV, Session, init_db


class AdaptationStateApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 991101
        with Session() as session:
            session.query(KV).filter(KV.key == f"product_workspace:adaptation:{self.book_id}").delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Adaptation State Book",
                    filename="adaptation-state-book.txt",
                    chapter_count=1,
                    total_words=320,
                    status="bibeled",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(KV).filter(KV.key == f"product_workspace:adaptation:{self.book_id}").delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_get_adaptation_state_returns_default_payload_when_missing(self):
        response = self.client.get(f"/api/books/{self.book_id}/adaptation-state")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["book_id"], self.book_id)
        self.assertIsNone(payload["selected_id"])
        self.assertIsNone(payload["selected_name"])
        self.assertEqual(payload["custom_note"], "")
        self.assertIsNone(payload["locked_at"])

    def test_put_adaptation_state_persists_and_can_be_read_back(self):
        update_response = self.client.put(
            f"/api/books/{self.book_id}/adaptation-state",
            json={
                "selectedId": "hook-dark-reversal",
                "selectedName": "强反转悬疑向",
                "customNote": "保留误判感，首集前置悬念。",
                "lockedAt": "2026-07-25T08:00:00.000Z",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        saved = update_response.json()["adaptation_state"]
        self.assertEqual(saved["selected_id"], "hook-dark-reversal")
        self.assertEqual(saved["selected_name"], "强反转悬疑向")
        self.assertEqual(saved["custom_note"], "保留误判感，首集前置悬念。")
        self.assertEqual(saved["locked_at"], "2026-07-25T08:00:00.000Z")
        self.assertIsNotNone(saved["updated_at"])
        self.assertIsNotNone(saved["created_at"])

        get_response = self.client.get(f"/api/books/{self.book_id}/adaptation-state")
        self.assertEqual(get_response.status_code, 200)
        payload = get_response.json()
        self.assertEqual(payload["selected_id"], "hook-dark-reversal")
        self.assertEqual(payload["selected_name"], "强反转悬疑向")
        self.assertEqual(payload["custom_note"], "保留误判感，首集前置悬念。")
        self.assertEqual(payload["locked_at"], "2026-07-25T08:00:00.000Z")

    def test_put_adaptation_state_returns_404_for_missing_book(self):
        response = self.client.put(
            "/api/books/99999999/adaptation-state",
            json={"selectedId": "test-option"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
