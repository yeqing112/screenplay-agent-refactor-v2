import unittest

from fastapi.testclient import TestClient

from api import server
from api.server import app
from models import Session, TaskRun, init_db


class TaskPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def tearDown(self):
        with Session() as session:
            session.query(TaskRun).filter(TaskRun.task_id.like("persist-test-%")).delete()
            session.commit()
        server._pipeline_tasks.pop("persist-test-pipeline", None)
        server._storyboard_tasks.pop("persist-test-storyboard", None)
        server._creative_tasks.pop("persist-test-creative", None)

    def test_pipeline_task_can_be_loaded_after_memory_miss(self):
        task_id = "persist-test-pipeline"
        state = {
            "task_id": task_id,
            "status": "done",
            "progress": 100,
            "current_step": "content preparation complete",
            "book_id": 123,
            "finished_at": "2026-08-21T12:00:00",
        }

        server._persist_task_state(task_id, "pipeline", state)
        server._pipeline_tasks.pop(task_id, None)

        response = self.client.get(f"/api/pipeline/task/{task_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["current_step"], "content preparation complete")
        self.assertEqual(payload["book_id"], 123)
        self.assertIn(task_id, server._pipeline_tasks)

    def test_storyboard_task_can_be_loaded_after_memory_miss(self):
        task_id = "persist-test-storyboard"
        state = {
            "task_id": task_id,
            "status": "partial",
            "progress": 100,
            "current_step": "Storyboard partially completed: 1 succeeded, 1 failed",
            "book_id": 456,
            "requested_episodes": [1, 2],
            "episodes": [
                {"episode": 1, "status": "done", "progress": 100},
                {"episode": 2, "status": "error", "progress": 100},
            ],
            "finished_at": "2026-08-21T12:05:00",
        }

        server._persist_task_state(task_id, "storyboard", state)
        server._storyboard_tasks.pop(task_id, None)

        response = self.client.get(f"/api/pipeline/storyboard/task/{task_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["requested_episodes"], [1, 2])
        self.assertEqual(payload["episodes"][1]["status"], "error")
        self.assertIn(task_id, server._storyboard_tasks)

    def test_creative_task_can_be_loaded_and_listed_after_memory_miss(self):
        task_id = "persist-test-creative"
        state = {
            "task_id": task_id,
            "kind": "image",
            "status": "done",
            "progress": 100,
            "target_kind": "image",
            "book_id": 789,
            "episode": 1,
            "shot_id": "1",
            "asset": {"id": "asset-1", "title": "测试分镜图"},
        }

        server._creative_tasks[task_id] = state
        server._stamp_creative_task_state(server._creative_tasks[task_id], created=True)
        server._creative_tasks.pop(task_id, None)

        response = self.client.get(f"/api/prototyping/tasks/{task_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["asset"]["id"], "asset-1")
        self.assertIn(task_id, server._creative_tasks)

        server._creative_tasks.pop(task_id, None)
        list_response = self.client.get("/api/books/789/creative-tasks")
        self.assertEqual(list_response.status_code, 200)
        tasks = list_response.json()["tasks"]
        self.assertTrue(any(task["task_id"] == task_id for task in tasks))


if __name__ == "__main__":
    unittest.main()
