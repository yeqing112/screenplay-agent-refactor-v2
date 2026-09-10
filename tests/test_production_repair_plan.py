import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardPromptVersion, StoryboardShot, Book, init_db


class ProductionRepairPlanApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990307
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(Book(id=self.book_id, title="修复计划测试", filename="repair-plan.txt", chapter_count=1, total_words=1, status="imported"))
            # Keep the fixture repairable: diagnostics and executability are
            # current, while the absent structured sections require a safe
            # prompt recompile and therefore exercise the repair-plan path.
            session.add(StoryboardShot(book_id=self.book_id, episode=1, shot_id=1, scene_name="场景", duration=3, meta_info='{"prompt_compiler":{"compiler_diagnostics":{"status":"pass"},"prompt_compile_context":{"executability":{"status":"pass"}}}}'))
            session.commit()

    def test_plan_is_read_only_and_classifies_recompile_shot(self):
        response = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "readonly-repair-plan")
        self.assertFalse(payload["real_data_mutated"])
        self.assertEqual(len(payload["confirmation_token"]), 16)
        self.assertEqual(payload["confirmation_token"], payload["plan_fingerprint"])
        self.assertEqual(payload["summary"]["warning_shots"], 1)
        self.assertEqual(payload["shot_actions"][0]["action"], "prepare_prompt_draft")
        self.assertTrue(payload["shot_actions"][0]["confirmation_required"])

    def test_execute_rejects_nonrepairable_shot_even_with_current_token(self):
        plan = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan").json()
        response = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-plan/execute",
            json={"confirmationToken": plan["confirmation_token"], "shotIds": ["1"], "confirmed": False, "allowWrite": False},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No repairable shots selected", response.json()["detail"])

        invalid = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-plan/execute",
            json={"confirmationToken": "stale-token", "shotIds": ["1"]},
        )
        self.assertEqual(invalid.status_code, 409)

    def test_retry_plan_is_read_only_for_failed_task_results(self):
        from api.server import _creative_tasks
        task_id = "repair-test-task"
        _creative_tasks[task_id] = {
            "task_id": task_id,
            "kind": "production-readiness-repair",
            "book_id": self.book_id,
            "status": "completed_with_errors",
            "results": [{"episode": 1, "shot_id": 1, "status": "failed", "error": "compile failed"}],
        }
        response = self.client.post(f"/api/books/{self.book_id}/production-readiness/repair-tasks/{task_id}/retry-plan")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "readonly-retry-plan")
        self.assertFalse(payload["real_data_mutated"])
        self.assertEqual(len(payload["retryable_shots"]), 1)

    def test_rollback_requires_confirmation_and_defaults_to_preview(self):
        from api.server import _creative_tasks
        task_id = "repair-rollback-task"
        _creative_tasks[task_id] = {
            "task_id": task_id,
            "kind": "production-readiness-repair",
            "book_id": self.book_id,
            "confirmation_token": "token-123",
            "status": "done",
            "results": [],
        }
        response = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-tasks/{task_id}/rollback",
            json={"confirmationToken": "token-123", "episode": 1, "shotId": "1", "baselineVersion": 1, "confirmed": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "rollback-preview")
        self.assertFalse(response.json()["real_data_mutated"])

    def test_execute_rejects_selected_shot_without_repairable_action(self):
        from api.server import _creative_tasks
        plan = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan").json()
        response = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-plan/execute",
            json={"confirmationToken": plan["confirmation_token"], "shotIds": ["1"], "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No repairable shots selected", response.json()["detail"])

    def test_declared_structural_transform_can_get_a_state_anchor_after_confirmation(self):
        transformed_meta = {
            "prompt_compiler": {"latest_version": None, "recompile_required": True, "compiler_diagnostics": {"status": "warning"}},
            "executability_split_draft": {"status": "applied", "sequence": 2, "source_shot_id": 1, "applied_at": "2026-08-30T00:00:00"},
        }
        with Session() as session:
            session.add(StoryboardShot(
                book_id=self.book_id, episode=1, shot_id=2, scene_name="场景", duration=3,
                action_process="人物转身", meta_info=json.dumps(transformed_meta, ensure_ascii=False),
            ))
            session.commit()

        plan = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan").json()
        action = next(item for item in plan["shot_actions"] if item["shot_id"] == 2)
        self.assertIsNone(action["rollback_anchor"])
        preview = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-plan/rollback-anchors",
            json={"confirmationToken": plan["confirmation_token"], "shotIds": ["2"]},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["mode"], "rollback-anchor-preview")
        self.assertEqual(len(preview.json()["eligible_shots"]), 1)

        created = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-plan/rollback-anchors",
            json={"confirmationToken": plan["confirmation_token"], "shotIds": ["2"], "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["real_data_mutated"])
        refreshed = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan").json()
        anchored = next(item for item in refreshed["shot_actions"] if item["shot_id"] == 2)
        self.assertEqual(anchored["rollback_anchor"]["kind"], "state_snapshot")

    def test_state_snapshot_rollback_restores_storyboard_fields_not_only_prompts(self):
        from api.server import _create_storyboard_state_snapshot_anchor, _creative_tasks

        transformed_meta = {
            "prompt_compiler": {"latest_version": None, "recompile_required": True},
            "executability_split_draft": {"status": "applied", "sequence": 1, "source_shot_id": 1},
        }
        with Session() as session:
            shot = session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id, StoryboardShot.shot_id == 1).first()
            shot.action_process = "拆分后的动作"
            shot.start_state = "起始状态"
            shot.asset_links = '{"references":{"character":[]}}'
            shot.meta_info = json.dumps(transformed_meta, ensure_ascii=False)
            anchor = _create_storyboard_state_snapshot_anchor(
                session, shot, {"type": "storyboard-transform", "operation": "test-transform"}, "test"
            )
            shot.action_process = "后续编译改写"
            shot.start_state = "错误状态"
            session.commit()

        task_id = "repair-state-snapshot-task"
        _creative_tasks[task_id] = {
            "task_id": task_id, "kind": "production-readiness-repair", "book_id": self.book_id,
            "confirmation_token": "snapshot-token", "status": "done", "results": [],
        }
        response = self.client.post(
            f"/api/books/{self.book_id}/production-readiness/repair-tasks/{task_id}/rollback",
            json={"confirmationToken": "snapshot-token", "episode": 1, "shotId": "1", "baselineVersion": anchor["version"], "confirmed": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["restored_anchor_kind"], "state_snapshot")
        with Session() as session:
            restored = session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id, StoryboardShot.shot_id == 1).first()
            self.assertEqual(restored.action_process, "拆分后的动作")
            self.assertEqual(restored.start_state, "起始状态")
