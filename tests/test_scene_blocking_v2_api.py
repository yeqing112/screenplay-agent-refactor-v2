import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, DirectorTreatment, SceneBlocking, Script, ScriptIRVersion, Session, init_db


class SceneBlockingV2ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="V2 API test", filename="v2-api.txt", status="imported")
            session.add(book); session.flush()
            script = Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{"name": "门厅"}]}, ensure_ascii=False))
            session.add(script); session.flush()
            ir = ScriptIRVersion(book_id=book.id, episode=1, revision=1, status="qualified", payload_json=json.dumps({"scenes": [{"name": "门厅"}]}, ensure_ascii=False), payload_hash="ir-hash", validation_status="qualified")
            session.add(ir); session.flush(); script.current_script_ir_version_id = ir.id
            session.add(DirectorTreatment(book_id=book.id, episode=1, scene_name="门厅", status="approved", revision=1, character_intents=json.dumps({"c1": {"name": "林默"}, "c2": {"name": "苏晴"}}), beat_map=json.dumps([{"beat_id": "B01", "event": "两人对视"}]), prompt_fingerprint="tp"))
            session.commit(); self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session.query(SceneBlocking).filter_by(book_id=self.book_id).delete()
            session.query(DirectorTreatment).filter_by(book_id=self.book_id).delete()
            session.query(Script).filter_by(book_id=self.book_id).delete()
            session.query(ScriptIRVersion).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_production_preview_uses_v2_and_does_not_block_silent_position(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True, "workflow_profile": "production"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["llm_called"])
        self.assertEqual(body["blocking"]["schema_version"], "scene_blocking_v2")
        self.assertEqual(body["blocking"]["unknowns"], [])
        self.assertEqual(body["blocking"]["status"], "ready_for_review")
        draft_id = body["persisted_draft_id"]
        confirm = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={"blockingId": draft_id, "evidenceFingerprint": body["blocking"]["evidence_fingerprint"], "confirmed": True, "workflow_profile": "production", "schema_version": "scene_blocking_v2"})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        self.assertEqual(confirm.json()["scene_blocking"]["schema_version"], "scene_blocking_v2")

    def test_production_preview_keeps_fact_conflict_blocked(self):
        with Session() as session:
            script = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            payload = {"scenes": [{"name": "门厅", "character_blocking": [{"character": "林默", "position": "门口"}], "spatial_facts": [{"subject_id": "c1", "predicate": "position", "value": "窗边"}]}]}
            script.content = json.dumps(payload, ensure_ascii=False)
            ir = session.query(ScriptIRVersion).filter_by(book_id=self.book_id, episode=1).one()
            ir.payload_json = json.dumps(payload, ensure_ascii=False)
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"workflow_profile": "production"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["blocking"]["status"], "needs_information")
        self.assertTrue(body["blocking"]["unknowns"])


if __name__ == "__main__":
    unittest.main()
