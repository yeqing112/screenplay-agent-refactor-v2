import unittest

from core.director_benchmark import score_runtime
from fastapi.testclient import TestClient
from api.server import app
from models import Book, DirectorTreatment, SceneBlocking, Script, Session, ShotPlan, init_db


class DirectorBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_api_is_read_only_and_returns_report(self):
        response = TestClient(app).get("/api/books/999999/episodes/1/director-benchmark")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["mutated"])
        self.assertEqual(response.json()["report"]["status"], "needs_work")

    def test_api_startup_applies_schema_before_serving_routes(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(
                client.get("/api/books/999999/episodes/1/director-benchmark/runs").status_code,
                200,
            )

    def test_complete_runtime_scores_pass(self):
        report = score_runtime(
            treatment={"status": "approved", "beat_map": [{"beat_id": "B01"}]},
            blocking={"status": "approved", "unknowns": []},
            shot_plan={"status": "approved", "shots": [{"camera": {"shot_size": "MS"}, "duration_hint_seconds": 3}]},
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["score"], 100)

    def test_api_scores_every_declared_scene_instead_of_latest_row_only(self):
        with Session() as session:
            book = Book(title="Benchmark multi-scene", filename="benchmark-multi-scene.txt")
            session.add(book); session.flush()
            session.add(Script(book_id=book.id, episode=1, content='{"scenes":[{"name":"门厅"},{"name":"走廊"}]}'))
            treatment = DirectorTreatment(book_id=book.id, episode=1, scene_name="门厅", status="approved", beat_map='[{"beat_id":"B01"}]')
            blocking = SceneBlocking(book_id=book.id, episode=1, scene_name="门厅", status="approved", unknowns="[]")
            plan = ShotPlan(book_id=book.id, episode=1, scene_name="门厅", status="approved", shots='[{"camera":{"shot_size":"MS"},"duration_hint_seconds":3}]', unknowns="[]")
            session.add_all([treatment, blocking, plan]); session.commit(); book_id = book.id
        try:
            response = TestClient(app).get(f"/api/books/{book_id}/episodes/1/director-benchmark")
            self.assertEqual(response.status_code, 200)
            report = response.json()["report"]
            self.assertEqual(report["scene_count"], 2)
            self.assertEqual(report["status"], "needs_work")
            self.assertTrue(any("走廊" in item["label"] and not item["passed"] for item in report["checks"]))
        finally:
            with Session() as session:
                for model in (ShotPlan, SceneBlocking, DirectorTreatment, Script):
                    session.query(model).filter_by(book_id=book_id).delete()
                session.query(Book).filter_by(id=book_id).delete(); session.commit()

    def test_incomplete_runtime_reports_actionable_checks(self):
        report = score_runtime(treatment={"status": "draft", "beat_map": []}, blocking={"status": "approved", "unknowns": ["位置"]}, shot_plan=None)
        self.assertEqual(report["status"], "needs_work")
        self.assertTrue(any(item["key"] == "shot_plan_approved" and not item["passed"] for item in report["checks"]))
        self.assertTrue(any(item["key"] == "blocking_unknowns" and not item["passed"] for item in report["checks"]))

    def test_run_can_be_saved_and_replayed(self):
        client = TestClient(app)
        book_id = 424242
        saved = client.post(
            f"/api/books/{book_id}/episodes/1/director-benchmark/runs",
            json={"sampleLabel": "golden-empty", "modelId": "deterministic"},
        )
        self.assertEqual(saved.status_code, 200)
        payload = saved.json()
        self.assertTrue(payload["mutated"])
        self.assertGreater(payload["run_id"], 0)
        self.assertEqual(payload["sample_label"], "golden-empty")
        self.assertEqual(payload["model_id"], "deterministic")
        self.assertEqual(payload["report"]["status"], "needs_work")

        history = client.get(f"/api/books/{book_id}/episodes/1/director-benchmark/runs")
        self.assertEqual(history.status_code, 200)
        items = history.json()["items"]
        self.assertTrue(any(item["run_id"] == payload["run_id"] for item in items))
        replayed = next(item for item in items if item["run_id"] == payload["run_id"])
        self.assertEqual(replayed["sample_label"], "golden-empty")
        self.assertEqual(replayed["report"]["status"], "needs_work")
        self.assertIsNotNone(replayed["created_at"])

        second = client.post(
            f"/api/books/{book_id}/episodes/1/director-benchmark/runs",
            json={"sample_label": "golden-empty-2", "model_id": "deterministic"},
        )
        self.assertEqual(second.status_code, 200)
        summary = client.get(f"/api/books/{book_id}/episodes/1/director-benchmark/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["run_count"], 2)
        self.assertEqual(summary.json()["models"][0]["model_id"], "deterministic")
        self.assertEqual(summary.json()["models"][0]["needs_work_count"], 2)
        self.assertEqual(summary.json()["models"][0]["pass_rate"], 0.0)
        self.assertIsNotNone(summary.json()["models"][0]["average_score"])
