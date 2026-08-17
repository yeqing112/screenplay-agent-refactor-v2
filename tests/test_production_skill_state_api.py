import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, KV, Session, init_db


class ProductionSkillStateApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 991201
        self.kv_key = f"product_workspace:production_skill:{self.book_id}"
        with Session() as session:
            session.query(KV).filter(KV.key == self.kv_key).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Production Skill Book",
                    filename="production-skill-book.txt",
                    chapter_count=1,
                    total_words=520,
                    status="draft",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(KV).filter(KV.key == self.kv_key).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_list_production_skills_returns_builtin_registry(self):
        response = self.client.get("/api/production-skills")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("skills", payload)
        self.assertGreaterEqual(len(payload["skills"]), 3)
        first_meta = payload["skills"][0]["skill_meta"]
        self.assertIn("id", first_meta)
        self.assertIn("name", first_meta)

    def test_get_production_skill_state_returns_default_when_missing(self):
        response = self.client.get(f"/api/books/{self.book_id}/production-skill-state")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["skill_id"], "rebirth_suspense")
        self.assertEqual(payload["platform"], "douyin")
        self.assertEqual(payload["track"], "重生悬疑")
        self.assertEqual(payload["enforcement"], "strict")
        self.assertIsNone(payload["locked_at"])
        self.assertEqual(payload["runtime_summary"]["skill_name"], "重生悬疑 Production Skill")

    def test_put_production_skill_state_persists_and_returns_runtime_summary(self):
        response = self.client.put(
            f"/api/books/{self.book_id}/production-skill-state",
            json={
                "skillId": "romance_abuse",
                "platform": "kuaishou",
                "track": "情感虐恋",
                "emotionGoal": "强情绪反噬",
                "rhythmStrength": "fast_conflict",
                "visualStyle": "close_pressure",
                "priorities": ["emotion", "assets"],
                "enforcement": "strict",
                "customNote": "优先保留误会升级与关系压迫。",
                "lockedAt": "2026-08-14T09:30:00+08:00",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["skill_id"], "romance_abuse")
        self.assertEqual(payload["platform"], "kuaishou")
        self.assertEqual(payload["track"], "情感虐恋")
        self.assertEqual(payload["priorities"], ["emotion", "assets"])
        self.assertEqual(payload["locked_at"], "2026-08-14T09:30:00+08:00")
        self.assertEqual(payload["runtime_summary"]["skill_name"], "情感虐恋 Production Skill")

        get_response = self.client.get(f"/api/books/{self.book_id}/production-skill-state")
        self.assertEqual(get_response.status_code, 200)
        saved = get_response.json()
        self.assertEqual(saved["skill_id"], "romance_abuse")
        self.assertEqual(saved["custom_note"], "优先保留误会升级与关系压迫。")
        self.assertEqual(saved["runtime_summary"]["track"], "情感虐恋")


if __name__ == "__main__":
    unittest.main()
