import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, DirectorTreatment, SceneBlocking, Script, Session, init_db


class SceneBlockingShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="Blocking test", filename="blocking-test.txt", status="imported")
            session.add(book); session.flush()
            session.add(Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{
                "name": "门厅", "character_blocking": [{"name": "来客", "position": "screen_left", "facing": "screen_right"}],
            }]}, ensure_ascii=False)))
            session.add(DirectorTreatment(book_id=book.id, episode=1, scene_name="门厅", status="approved", revision=1,
                character_intents=json.dumps({"c1": {"name": "来客"}}), beat_map=json.dumps([{"beat_id": "B01", "event": "来客停下"}]),
                prompt_fingerprint="treatment-fp", source_script_hash="script-fp"))
            session.commit(); self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session.query(SceneBlocking).filter_by(book_id=self.book_id).delete()
            session.query(DirectorTreatment).filter_by(book_id=self.book_id).delete()
            session.query(Script).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_preview_requires_approved_treatment_and_preserves_missing_positions(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["llm_called"])
        self.assertTrue(payload["mutated"])
        self.assertEqual(payload["blocking"]["participants"][0]["position"], "screen_left")
        self.assertEqual(payload["blocking"]["unknowns"], [])

    def test_preview_marks_undeclared_position_as_unknown_without_inventing_it(self):
        with Session() as session:
            treatment = session.query(DirectorTreatment).filter_by(book_id=self.book_id).one()
            treatment.character_intents = json.dumps({"c1": {"name": "来客"}, "c2": {"name": "秘书"}})
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={})
        self.assertEqual(response.status_code, 200)
        participant = response.json()["blocking"]["participants"][1]
        self.assertIsNone(participant["position"])
        self.assertIn("秘书", response.json()["blocking"]["unknowns"][0])

    def test_preview_is_blocked_without_approved_treatment(self):
        with Session() as session:
            treatment = session.query(DirectorTreatment).filter_by(book_id=self.book_id).one()
            treatment.status = "draft"; session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={})
        self.assertEqual(response.status_code, 409)

    def test_confirm_creates_approved_revision_and_enables_shot_plan_gate(self):
        draft = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True}).json()
        blocking = draft["blocking"]
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={
            "blockingId": draft["persisted_draft_id"], "evidenceFingerprint": blocking["evidence_fingerprint"], "confirmed": True,
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["approved"])
        self.assertTrue(payload["shot_plan_allowed"])
        self.assertEqual(payload["scene_blocking"]["status"], "approved")
        self.assertIsNone(payload["rollback_anchor"]["previous_blocking_id"])

    def test_legacy_free_text_blocking_is_preserved_as_explicit_position(self):
        from core.scene_blocking import build_scene_blocking
        result = build_scene_blocking(
            scene={"name": "门厅", "character_blocking": [{"character": "甲", "blocking": "站在门边，面向室内"}]},
            treatment={"scene_name": "门厅", "character_intents": {"c1": {"name": "甲"}}, "beat_map": []},
        )
        self.assertEqual(result["unknowns"], [])
        self.assertEqual(result["participants"][0]["position"], "站在门边，面向室内")

    def test_confirm_rejects_stale_scene_evidence(self):
        draft = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True}).json()
        with Session() as session:
            script = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            script.content = script.content + " "
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={
            "blockingId": draft["persisted_draft_id"], "evidenceFingerprint": draft["blocking"]["evidence_fingerprint"], "confirmed": True,
        })
        self.assertEqual(response.status_code, 409)
        with Session() as session:
            row = session.query(SceneBlocking).filter_by(id=draft["persisted_draft_id"]).one()
            self.assertEqual(row.status, "superseded")

    def test_shot_plan_readiness_is_blocked_until_scene_blocking_is_approved(self):
        blocked = self.client.get(f"/api/books/{self.book_id}/episodes/1/shot-plan/readiness").json()
        self.assertFalse(blocked["allowed"])
        draft = self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/preview", json={"persist": True}).json()
        self.client.post(f"/api/books/{self.book_id}/episodes/1/scene-blocking/confirm", json={
            "blockingId": draft["persisted_draft_id"], "confirmed": True,
        })
        ready = self.client.get(f"/api/books/{self.book_id}/episodes/1/shot-plan/readiness").json()
        self.assertTrue(ready["allowed"])
