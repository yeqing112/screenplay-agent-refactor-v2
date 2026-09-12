import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Session, StoryboardShot, init_db


class StoryboardDecisionPacketEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        # Keep this regression hermetic: the project database is intentionally
        # empty after the legacy-data purge, so never depend on a historical
        # book id such as 990309.
        with Session() as session:
            book = Book(
                title="Decision packet evidence fixture",
                filename="decision-packet-evidence-fixture.txt",
            )
            session.add(book)
            session.flush()
            session.add(
                StoryboardShot(
                    book_id=book.id,
                    episode=1,
                    scene_name="Fixture scene",
                    shot_id=16,
                    action_process="A character crosses the room and stops at the desk.",
                    start_state="character at the door",
                    end_state="character at the desk",
                )
            )
            session.commit()
            self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id
            ).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_storyboard_decision_packet_includes_executability_evidence(self):
        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/1/16/decision-packet/draft"
        )
        self.assertEqual(response.status_code, 200)
        packet = response.json()["packet"]
        evidence = packet.get("evidence") or []
        exec_entries = [item for item in evidence if str(item.get("id") or "").startswith("executability:")]
        self.assertEqual(len(exec_entries), 1, "executability evidence must be present")
        summary = json.loads(exec_entries[0].get("summary") or "{}")
        self.assertIn("status", summary)
        self.assertIn("action_count", summary)
        self.assertIn("recommended_max_actions", summary)
        self.assertIn("findings", summary)
        self.assertIn("suggestions", summary)


if __name__ == "__main__":
    unittest.main()
