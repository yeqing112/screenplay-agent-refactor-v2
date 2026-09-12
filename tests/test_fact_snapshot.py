import unittest
import json

from fastapi.testclient import TestClient

from core.fact_snapshot import build_fact_snapshot, validate_fact_records
from api.server import app
from models import Book, Script, FactRecord, FactSnapshot, Session, init_db


class FactSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db(); cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="Fact snapshot test", filename="facts.txt", status="imported"); session.add(book); session.flush()
            session.add(Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]})))
            session.commit(); self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session.query(FactRecord).filter(FactRecord.snapshot_id.in_(session.query(FactSnapshot.id).filter_by(book_id=self.book_id))).delete(synchronize_session=False)
            session.query(FactSnapshot).filter_by(book_id=self.book_id).delete(); session.query(Script).filter_by(book_id=self.book_id).delete(); session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_build_is_deterministic_and_reports_hash(self):
        result = build_fact_snapshot([{"subject_type": "character", "subject_id": "c1", "predicate": "gender", "value": "female", "authority": "source_text", "status": "confirmed", "evidence": [{"source_id": "chapter-1"}]}], book_id=1, episode=1, source_fingerprint="src")
        self.assertEqual(result["schema_version"], "fact_snapshot_v1")
        self.assertEqual(result["validation"]["status"], "qualified")
        self.assertTrue(result["payload_hash"])

    def test_conflicting_values_are_not_qualified(self):
        report = validate_fact_records([
            {"fact_id": "a", "subject_type": "character", "subject_id": "c1", "predicate": "gender", "value": "female", "authority": "source_text", "status": "confirmed"},
            {"fact_id": "b", "subject_type": "character", "subject_id": "c1", "predicate": "gender", "value": "male", "authority": "model_observation", "status": "proposed"},
        ])
        self.assertEqual(report["status"], "needs_review")
        self.assertTrue(any(item["code"] == "FACT_CONFLICT" for item in report["errors"]))

    def test_api_build_and_confirm_persists_records_without_llm(self):
        record = {"fact_id": "f1", "subject_type": "character", "subject_id": "c1", "predicate": "gender", "value": "female", "authority": "source_text", "status": "confirmed", "evidence": [{"source_id": "chapter-1"}]}
        built = self.client.post(f"/api/books/{self.book_id}/episodes/1/fact-snapshots/build", json={"records": [record], "persist": True})
        self.assertEqual(built.status_code, 200); self.assertFalse(built.json()["llm_called"])
        confirmed = self.client.post(f"/api/books/{self.book_id}/episodes/1/fact-snapshots/confirm", json={"snapshotId": built.json()["persisted_draft_id"], "confirmed": True})
        self.assertEqual(confirmed.status_code, 200)
        with Session() as session:
            self.assertEqual(session.query(FactRecord).filter_by(snapshot_id=built.json()["persisted_draft_id"]).count(), 1)


if __name__ == "__main__":
    unittest.main()
