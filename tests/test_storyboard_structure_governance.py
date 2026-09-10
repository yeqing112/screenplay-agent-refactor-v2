import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, DecisionPacketRecord, Session, StoryboardPromptVersion, StoryboardShot, init_db


class StoryboardStructureGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990307
        with Session() as session:
            for model in (DecisionPacketRecord, StoryboardPromptVersion, StoryboardShot, Book):
                session.query(model).filter(model.book_id == self.book_id if model is not Book else model.id == self.book_id).delete()
            session.add(Book(id=self.book_id, title="结构治理测试", filename="structure.txt", chapter_count=1, total_words=10, status="imported"))
            session.add(StoryboardShot(
                book_id=self.book_id,
                episode=1,
                shot_id=6,
                scene_name="便利店",
                duration=4,
                meta_info=json.dumps({
                    "structured_shot": {"shot_id": "2", "duration": 4, "executability": {"status": "pass"}},
                    "prompt_compiler": {"compiler_diagnostics": {"status": "warning"}, "prompt_compile_context": {"executability": {"status": "pass"}}},
                }, ensure_ascii=False),
            ))
            session.commit()

    def test_plan_is_read_only_and_backfill_is_confirmation_gated_and_auditable(self):
        before = self.client.get(f"/api/books/{self.book_id}/storyboard/structure-governance/plan")
        self.assertEqual(before.status_code, 200)
        plan = before.json()
        self.assertEqual(plan["summary"]["identity_repairs"], 1)
        self.assertTrue(plan["items"][0]["identity_stale"])

        preview = self.client.post(f"/api/books/{self.book_id}/storyboard/structure-governance/backfill", json={"planFingerprint": plan["plan_fingerprint"]})
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["real_data_mutated"])
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1, shot_id=6).one()
            self.assertEqual(json.loads(shot.meta_info)["structured_shot"]["shot_id"], "2")

        applied = self.client.post(f"/api/books/{self.book_id}/storyboard/structure-governance/backfill", json={
            "planFingerprint": plan["plan_fingerprint"],
            "confirmationToken": "CONFIRM_STRUCTURED_SHOT_IDENTITY_BACKFILL",
            "confirmed": True,
            "allowWrite": True,
        })
        self.assertEqual(applied.status_code, 200)
        self.assertTrue(applied.json()["real_data_mutated"])
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1, shot_id=6).one()
            meta = json.loads(shot.meta_info)
            self.assertEqual(meta["structured_shot"]["shot_id"], "6")
            self.assertTrue(meta["prompt_compiler"]["recompile_required"])
            self.assertEqual(meta["prompt_compiler"]["diagnostics_state"]["status"], "stale")
            self.assertEqual(session.query(StoryboardPromptVersion).filter_by(book_id=self.book_id, episode=1, shot_id=6).count(), 1)
            self.assertEqual(session.query(DecisionPacketRecord).filter_by(book_id=self.book_id, status="confirmed").count(), 1)
        self.assertEqual(
            self.client.get(f"/api/books/{self.book_id}/storyboard/structure-governance/plan").json()["summary"]["affected_shots"],
            0,
        )
        repair_plan = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan").json()
        self.assertEqual(repair_plan["shot_actions"][0]["action"], "prepare_prompt_draft")

    def test_readiness_never_treats_identity_mismatched_diagnostics_as_current(self):
        response = self.client.get(f"/api/books/{self.book_id}/production-readiness")
        self.assertEqual(response.status_code, 200)
        issues = {item["code"] for item in response.json()["shots"][0]["issues"]}
        self.assertIn("structured_shot_identity_stale", issues)
        self.assertIn("stale_prompt_diagnostics", issues)
