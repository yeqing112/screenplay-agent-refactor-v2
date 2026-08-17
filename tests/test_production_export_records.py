import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, ProductionExportRecord, Script, Session, StoryboardShot, init_db


class ProductionExportRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990701
        with Session() as session:
            session.query(ProductionExportRecord).filter(ProductionExportRecord.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Export Acceptance Book",
                    filename="export-acceptance-book.txt",
                    chapter_count=1,
                    total_words=1000,
                    status="storyboarded",
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=1,
                    content="第1场 客厅 日\n主角走进房间。",
                    word_count=20,
                    status="done",
                )
            )
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="客厅",
                    shot_id=1,
                    dialogue="你回来了。",
                    action_process="主角推门进入，停在门口。",
                    duration=3,
                    camera_angle="MS",
                    camera_movement="static",
                    transition="cut",
                    meta_info="{}",
                    asset_links="{}",
                    asset_status="pending",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(ProductionExportRecord).filter(ProductionExportRecord.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_export_record_persists_and_lists_history(self):
        create_response = self.client.post(
            f"/api/books/{self.book_id}/export-records",
            json={
                "exportFormat": "json",
                "status": "completed",
                "totalShots": 12,
                "deliverableShots": 10,
                "pendingReviewShots": 2,
                "blockedShots": 1,
                "summary": "已导出第 1 版交付包",
                "metaInfo": {
                    "issues": ["镜头 1-3 待验收"],
                    "blockedShotIds": ["1-3"],
                },
            },
        )
        self.assertEqual(create_response.status_code, 200)
        payload = create_response.json()
        self.assertEqual(payload["export_format"], "json")
        self.assertEqual(payload["deliverable_shots"], 10)
        self.assertEqual(payload["meta_info"]["blockedShotIds"], ["1-3"])

        list_response = self.client.get(f"/api/books/{self.book_id}/export-records")
        self.assertEqual(list_response.status_code, 200)
        records = list_response.json()["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["summary"], "已导出第 1 版交付包")
        self.assertEqual(records[0]["pending_review_shots"], 2)

    def test_export_pdf_endpoint_returns_pdf_bytes(self):
        response = self.client.get(f"/api/books/{self.book_id}/export-pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn(".pdf", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_export_pdf_endpoint_accepts_episode_scope(self):
        with Session() as session:
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=2,
                    content="第二集剧本",
                    word_count=10,
                    status="done",
                )
            )
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=2,
                    scene_name="后院",
                    shot_id=2,
                    dialogue="第二集对白",
                    action_process="角色走向后院",
                    duration=4,
                    camera_angle="CU",
                    camera_movement="push-in",
                    transition="cut",
                    meta_info="{}",
                    asset_links="{}",
                    asset_status="pending",
                )
            )
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/export-pdf?episode=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("episode-2", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
