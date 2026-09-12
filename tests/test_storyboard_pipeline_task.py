import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app, StoryboardRequest
import config
from models import Book, Script, Session, StoryboardShot, ShotPlan, init_db


class StoryboardPipelineTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990801
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(ShotPlan).filter(ShotPlan.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Storyboard Task Book",
                    filename="storyboard-task-book.txt",
                    chapter_count=1,
                    total_words=1200,
                    status="scripted",
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=1,
                    genre="short_drama",
                    content="第1集剧本",
                    word_count=20,
                    status="done",
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=2,
                    genre="short_drama",
                    content="第2集剧本",
                    word_count=20,
                    status="done",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(ShotPlan).filter(ShotPlan.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_shot_plan_gate_default_is_configuration_driven(self):
        original = config.REQUIRE_SHOT_PLAN_BY_DEFAULT
        try:
            config.REQUIRE_SHOT_PLAN_BY_DEFAULT = False
            self.assertFalse(StoryboardRequest(book_id=self.book_id).require_shot_plan)
            config.REQUIRE_SHOT_PLAN_BY_DEFAULT = True
            self.assertTrue(StoryboardRequest(book_id=self.book_id).require_shot_plan)
        finally:
            config.REQUIRE_SHOT_PLAN_BY_DEFAULT = original

    def test_storyboard_task_reports_per_episode_partial_status(self):
        def fake_run(self, episode, resume_after_scene=None):
            if callable(getattr(self, "progress_callback", None)):
                self.progress_callback({"stage": "scene_list_loaded", "episode": episode, "total_scenes": 2})
                self.progress_callback({"stage": "scene_started", "episode": episode, "scene_name": f"Episode {episode} Scene A"})
                self.progress_callback({"stage": "scene_completed", "episode": episode, "scene_name": f"Episode {episode} Scene A"})
            if episode == 2:
                if callable(getattr(self, "progress_callback", None)):
                    self.progress_callback({"stage": "scene_started", "episode": episode, "scene_name": f"Episode {episode} Scene B"})
                raise ValueError("LLM output truncated")
            return [{"shot_id": 1}, {"shot_id": 2}]

        with patch("agents.storyboard.StoryboardAgent.run", new=fake_run):
            response = self.client.post(
                "/api/pipeline/storyboard",
                json={"book_id": self.book_id, "genre": "short_drama", "episodes": [1, 2]},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]

        task_response = self.client.get(f"/api/pipeline/storyboard/task/{task_id}")
        self.assertEqual(task_response.status_code, 200)
        payload = task_response.json()

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["completed_episodes"], 1)
        self.assertEqual(payload["failed_episodes"], 1)
        self.assertEqual(payload["queued_episodes"], 0)
        self.assertEqual(len(payload["episodes"]), 2)

        first = next(item for item in payload["episodes"] if item["episode"] == 1)
        second = next(item for item in payload["episodes"] if item["episode"] == 2)
        self.assertEqual(first["status"], "done")
        self.assertEqual(first["shot_count"], 2)
        self.assertEqual(second["status"], "error")
        self.assertIn("truncated", second["error"])
        self.assertEqual(second["failure_kind"], "llm_truncated")
        self.assertIn("只重试失败集", second["guidance"])
        self.assertEqual(second["completed_scenes"], 1)
        self.assertEqual(second["last_completed_scene_name"], "Episode 2 Scene A")
        self.assertEqual(second["failed_scene_name"], "Episode 2 Scene B")
        self.assertIn("已完成到", second["guidance"])

    def test_storyboard_request_can_enforce_approved_shot_plan_gate(self):
        response = self.client.post("/api/pipeline/storyboard", json={"book_id": self.book_id, "episodes": [1], "requireShotPlan": True})
        self.assertEqual(response.status_code, 409)
        self.assertIn("ShotPlan gate", response.json()["detail"])

    def test_storyboard_resume_passes_scene_anchor_to_agent(self):
        seen = {}

        def fake_run(self, episode, resume_after_scene=None):
            seen[episode] = resume_after_scene
            if callable(getattr(self, "progress_callback", None)):
                self.progress_callback({
                    "stage": "resume_initialized",
                    "episode": episode,
                    "completed_scenes": 1,
                    "resume_after_scene": resume_after_scene or "",
                })
            return [{"shot_id": 1}]

        with patch("agents.storyboard.StoryboardAgent.run", new=fake_run):
            response = self.client.post(
                "/api/pipeline/storyboard",
                json={
                    "book_id": self.book_id,
                    "genre": "short_drama",
                    "episodes": [2],
                    "resumeFromScene": {"2": "Episode 2 Scene A"},
                },
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        self.assertEqual(seen[2], "Episode 2 Scene A")
        task_payload = self.client.get(f"/api/pipeline/storyboard/task/{task_id}").json()
        resumed = next(item for item in task_payload["episodes"] if item["episode"] == 2)
        self.assertEqual(resumed["completed_scenes"], 1)
        self.assertIn("继续", resumed["resume_anchor"])

    def test_storyboard_task_reports_scene_retrying_progress(self):
        def fake_run(self, episode, resume_after_scene=None):
            if callable(getattr(self, "progress_callback", None)):
                self.progress_callback({"stage": "scene_list_loaded", "episode": episode, "total_scenes": 1})
                self.progress_callback({"stage": "scene_started", "episode": episode, "scene_name": "Episode 1 Scene A"})
                self.progress_callback({"stage": "scene_retrying", "episode": episode, "scene_name": "Episode 1 Scene A"})
                self.progress_callback({"stage": "scene_completed", "episode": episode, "scene_name": "Episode 1 Scene A"})
            return [{"shot_id": 1}]

        with patch("agents.storyboard.StoryboardAgent.run", new=fake_run):
            response = self.client.post(
                "/api/pipeline/storyboard",
                json={"book_id": self.book_id, "genre": "short_drama", "episodes": [1]},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/pipeline/storyboard/task/{task_id}").json()
        finished = next(item for item in task_payload["episodes"] if item["episode"] == 1)
        self.assertEqual(finished["status"], "done")
        self.assertEqual(finished.get("retry_count"), 1)
        self.assertEqual(finished.get("last_retry_reason"), "scene_retrying")

    def test_storyboard_task_keeps_warning_when_scene_fallback_is_used(self):
        def fake_run(self, episode, resume_after_scene=None):
            if callable(getattr(self, "progress_callback", None)):
                self.progress_callback({"stage": "scene_list_loaded", "episode": episode, "total_scenes": 1})
                self.progress_callback({"stage": "scene_started", "episode": episode, "scene_name": "Episode 1 Scene A"})
                self.progress_callback({"stage": "scene_retrying", "episode": episode, "scene_name": "Episode 1 Scene A"})
                self.progress_callback({"stage": "scene_fallback_used", "episode": episode, "scene_name": "Episode 1 Scene A"})
                self.progress_callback({"stage": "scene_completed", "episode": episode, "scene_name": "Episode 1 Scene A"})
            return [{"shot_id": 1}]

        with patch("agents.storyboard.StoryboardAgent.run", new=fake_run):
            response = self.client.post(
                "/api/pipeline/storyboard",
                json={"book_id": self.book_id, "genre": "short_drama", "episodes": [1]},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/pipeline/storyboard/task/{task_id}").json()
        finished = next(item for item in task_payload["episodes"] if item["episode"] == 1)
        self.assertEqual(finished["status"], "done")
        self.assertEqual(finished.get("warning_count"), 1)
        self.assertEqual(finished.get("fallback_scene_count"), 1)
        self.assertIn("fallback", finished.get("current_step") or "")
        self.assertIn("fallback", (finished.get("guidance") or "").lower())

    def test_storyboard_defaults_to_director_llm_mode(self):
        seen = {}

        def fake_init(agent, *args, **kwargs):
            seen["force_llm"] = kwargs.get("force_llm")
            agent.progress_callback = kwargs.get("progress_callback")

        def fake_run(agent, episode, resume_after_scene=None):
            return []

        with patch("agents.storyboard.StoryboardAgent.__init__", new=fake_init), patch(
            "agents.storyboard.StoryboardAgent.run", new=fake_run,
        ):
            response = self.client.post(
                "/api/pipeline/storyboard",
                json={"book_id": self.book_id, "genre": "short_drama", "episodes": [1]},
            )

        self.assertEqual(response.status_code, 200)
        task_payload = self.client.get(
            f"/api/pipeline/storyboard/task/{response.json()['task_id']}"
        ).json()
        self.assertEqual(task_payload["generation_mode"], "director_llm")
        self.assertTrue(seen["force_llm"])

    def test_deterministic_safe_mode_is_explicit(self):
        seen = {}

        def fake_init(agent, *args, **kwargs):
            seen["force_llm"] = kwargs.get("force_llm")
            agent.progress_callback = kwargs.get("progress_callback")

        with patch("agents.storyboard.StoryboardAgent.__init__", new=fake_init), patch(
            "agents.storyboard.StoryboardAgent.run", new=lambda agent, episode, resume_after_scene=None: [],
        ):
            response = self.client.post(
                "/api/pipeline/storyboard",
                json={
                    "book_id": self.book_id,
                    "genre": "short_drama",
                    "episodes": [1],
                    "generationMode": "deterministic_safe",
                },
            )

        self.assertEqual(response.status_code, 200)
        task_payload = self.client.get(
            f"/api/pipeline/storyboard/task/{response.json()['task_id']}"
        ).json()
        self.assertEqual(task_payload["generation_mode"], "deterministic_safe")
        self.assertFalse(seen["force_llm"])


if __name__ == "__main__":
    unittest.main()
