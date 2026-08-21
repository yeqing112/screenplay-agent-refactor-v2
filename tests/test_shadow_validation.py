import json
import unittest

from core.validators.shadow_validation import shadow_validate_storyboard_shots
from models import AgentViolationLog, Book, Session, init_db


class ShadowValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991222
        with Session() as session:
            self._cleanup(session)
            session.add(
                Book(
                    id=self.book_id,
                    title="Shadow Validation Tests",
                    filename="shadow-validation.txt",
                    chapter_count=1,
                    total_words=100,
                    status="storyboarded",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            self._cleanup(session)
            session.commit()

    def _cleanup(self, session):
        session.query(AgentViolationLog).filter(AgentViolationLog.book_id == self.book_id).delete()
        session.query(Book).filter(Book.id == self.book_id).delete()

    def test_shadow_storyboard_validation_logs_without_mutating_shots(self):
        shots = [
            {
                "scene_name": "雨夜门口",
                "shot_id": 1,
                "duration": 9,
                "camera_angle": "MS",
                "camera_movement": "static",
                "transition": "cut",
                "shot_purpose": "",
            },
            {
                "scene_name": "雨夜门口",
                "shot_id": 2,
                "duration": 3,
                "camera_angle": "MS",
                "camera_movement": "static",
                "transition": "cut",
                "shot_purpose": "action",
            },
        ]
        original = json.dumps(shots, ensure_ascii=False, sort_keys=True)

        with Session() as session:
            logged = shadow_validate_storyboard_shots(self.book_id, 1, shots, session)
            session.commit()

        self.assertGreater(logged, 0)
        self.assertEqual(json.dumps(shots, ensure_ascii=False, sort_keys=True), original)

        with Session() as session:
            logs = session.query(AgentViolationLog).filter(
                AgentViolationLog.book_id == self.book_id,
                AgentViolationLog.repair_result == "shadow_logged",
            ).all()

        self.assertEqual(len(logs), logged)
        self.assertTrue(any(log.violation_id == "DURATION_RANGE" for log in logs))
        self.assertTrue(any(log.violation_id == "SHOT_PURPOSE_ENUM" for log in logs))


if __name__ == "__main__":
    unittest.main()
