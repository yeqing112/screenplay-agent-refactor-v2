import json
import unittest

from fastapi.testclient import TestClient

from api.server import _attach_approved_shot_plan_refs, app
from models import Book, DirectorTreatment, SceneBlocking, Script, Session, ShotPlan, StoryboardShot, init_db


class ShotPlanShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db(); cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="Shot plan test", filename="shot-plan-test.txt", status="imported"); session.add(book); session.flush()
            session.add(Script(book_id=book.id, episode=1, content=json.dumps({"scenes": [{"name": "门厅", "beats": [{"id": "B01", "type": "setup", "event": "来客进入"}, {"id": "B02", "type": "reveal", "event": "发现异常"}]}]}, ensure_ascii=False)))
            treatment = DirectorTreatment(book_id=book.id, episode=1, scene_name="门厅", status="approved", revision=1, character_intents=json.dumps({"c1": {"name": "来客"}}), beat_map=json.dumps([{"beat_id": "B01", "type": "setup", "event": "来客进入"}, {"beat_id": "B02", "type": "reveal", "event": "发现异常"}]), prompt_fingerprint="treatment-fp")
            session.add(treatment); session.flush()
            session.add(SceneBlocking(book_id=book.id, episode=1, scene_name="门厅", status="approved", revision=1, treatment_id=treatment.id, participants=json.dumps([{"character_id": "c1", "name": "来客", "position": "screen_left"}]), unknowns="[]", evidence_fingerprint="blocking-fp"))
            session.commit(); self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session.query(ShotPlan).filter_by(book_id=self.book_id).delete(); session.query(SceneBlocking).filter_by(book_id=self.book_id).delete(); session.query(DirectorTreatment).filter_by(book_id=self.book_id).delete(); session.query(Script).filter_by(book_id=self.book_id).delete(); session.query(Book).filter_by(id=self.book_id).delete(); session.commit()

    def test_preview_uses_only_approved_upstream_and_is_idempotent(self):
        first = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True})
        self.assertEqual(first.status_code, 200); payload = first.json(); self.assertFalse(payload["llm_called"]); self.assertEqual(len(payload["plan"]["shots"]), 2)
        second = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True}).json(); self.assertEqual(payload["persisted_draft_id"], second["persisted_draft_id"])

    def test_preview_blocks_unresolved_spatial_unknowns(self):
        with Session() as session:
            row = session.query(SceneBlocking).filter_by(book_id=self.book_id).one(); row.unknowns = json.dumps(["未声明位置"]); session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={})
        self.assertEqual(response.status_code, 409)

    def test_confirm_requires_reviewed_camera_and_creates_approved_plan(self):
        draft = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"persist": True}).json()
        reviewed = json.loads(json.dumps(draft["plan"]["shots"]))
        for shot in reviewed:
            shot["camera"] = {"shot_size": "MS", "movement": "static"}
            shot["duration_hint_seconds"] = 3
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/confirm", json={
            "planId": draft["persisted_draft_id"], "evidenceFingerprint": draft["plan"]["evidence_fingerprint"], "confirmed": True,
            "plan": {"scene_name": "门厅", "shots": reviewed, "unknowns": []},
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["storyboard_generation_allowed"])
        self.assertEqual(payload["shot_plan"]["status"], "approved")

    def test_storyboard_readiness_is_blocked_before_shot_plan_approval(self):
        blocked = self.client.get(f"/api/books/{self.book_id}/episodes/1/storyboard/readiness").json()
        self.assertFalse(blocked["allowed"])

    def test_storyboard_readiness_handles_markdown_script_without_500(self):
        with Session() as session:
            script = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            script.content = "# 第1集\n\n## 门厅\n\n人物进入，发现异常。"
            session.commit()
        response = self.client.get(f"/api/books/{self.book_id}/episodes/1/storyboard/readiness")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["allowed"])
        self.assertTrue(any("结构化 scenes" in issue for issue in payload["blocking_issues"]))

    def test_multi_scene_preview_and_readiness_are_scene_scoped(self):
        with Session() as session:
            script = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            script.content = json.dumps({"scenes": [
                {"name": "门厅", "beats": [{"id": "B01", "type": "setup", "event": "来客进入"}]},
                {"name": "走廊", "beats": [{"id": "B09", "type": "reveal", "event": "灯光熄灭"}]},
            ]}, ensure_ascii=False)
            treatment = DirectorTreatment(book_id=self.book_id, episode=1, scene_name="走廊", status="approved", revision=1, character_intents=json.dumps({"c2": {"name": "来客"}}), beat_map=json.dumps([{"beat_id": "B09", "type": "reveal", "event": "灯光熄灭"}]), prompt_fingerprint="treatment-corridor")
            session.add(treatment); session.flush()
            session.add(SceneBlocking(book_id=self.book_id, episode=1, scene_name="走廊", status="approved", revision=1, treatment_id=treatment.id, participants=json.dumps([{"character_id": "c2", "name": "来客", "position": "screen_left"}]), unknowns="[]", evidence_fingerprint="blocking-corridor"))
            session.commit()

        corridor = self.client.post(f"/api/books/{self.book_id}/episodes/1/shot-plan/preview", json={"sceneName": "走廊", "persist": True})
        self.assertEqual(corridor.status_code, 200)
        self.assertEqual(corridor.json()["plan"]["scene_name"], "走廊")

        blocked = self.client.get(f"/api/books/{self.book_id}/episodes/1/storyboard/readiness").json()
        self.assertFalse(blocked["allowed"])
        self.assertTrue(any("门厅" in issue for issue in blocked["blocking_issues"]))
        self.assertTrue(any("走廊" in issue for issue in blocked["blocking_issues"]))

    def test_approved_plan_provenance_is_attached_without_overwriting_shot_content(self):
        with Session() as session:
            plan = session.query(ShotPlan).filter_by(book_id=self.book_id).first()
            if not plan:
                plan = ShotPlan(book_id=self.book_id, episode=1, scene_name="门厅", status="approved", shots=json.dumps([{"plan_shot_id": "S01", "beat_id": "B01", "purpose": "establish"}]))
                session.add(plan)
            session.add(StoryboardShot(book_id=self.book_id, episode=1, scene_name="门厅", shot_id=1, dialogue="原始对白", meta_info=json.dumps({"keep": True})))
            session.commit()
        result = _attach_approved_shot_plan_refs(self.book_id, 1)
        self.assertEqual(result["attached"], 1)
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1, shot_id=1).one()
            meta = json.loads(shot.meta_info)
            self.assertEqual(meta["keep"], True)
            self.assertEqual(meta["shot_plan_ref"]["plan_shot_id"], "S01")
            self.assertEqual(shot.dialogue, "原始对白")
            session.query(StoryboardShot).filter_by(book_id=self.book_id).delete(); session.commit()

    def test_shot_level_diff_replays_plan_against_generated_storyboard(self):
        with Session() as session:
            plan = ShotPlan(book_id=self.book_id, episode=1, scene_name="门厅", status="approved", revision=1, shots=json.dumps([
                {"plan_shot_id": "S01", "beat_id": "B01", "purpose": "establish"},
                {"plan_shot_id": "S02", "beat_id": "B02", "purpose": "reveal"},
            ]))
            session.add(plan); session.flush()
            session.add(StoryboardShot(book_id=self.book_id, episode=1, scene_name="门厅", shot_id=1, camera_angle="MS", meta_info=json.dumps({"shot_plan_ref": {"plan_shot_id": "S01"}})))
            session.commit(); plan_id = plan.id
        response = self.client.get(f"/api/books/{self.book_id}/episodes/1/shot-plans/{plan_id}/diff")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["mutated"])
        self.assertEqual(payload["items"][0]["status"], "matched")
        self.assertEqual(payload["items"][1]["status"], "missing_generated_shot")
        with Session() as session:
            session.query(StoryboardShot).filter_by(book_id=self.book_id).delete(); session.query(ShotPlan).filter_by(id=plan_id).delete(); session.commit()
