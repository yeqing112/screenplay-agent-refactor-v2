import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core.ingest import ingest
from models import Book, Session, init_db


class ContentPreparationPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 991001
        with Session() as session:
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Content Prep Book",
                    filename="content-prep-book.txt",
                    chapter_count=1,
                    total_words=600,
                    status="imported",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_stop_after_content_finishes_without_entering_adaptation(self):
        with patch("agents.reader.ReaderAgent.run", return_value=None), patch(
            "agents.bible.BibleAgent.run", return_value=None
        ), patch(
            "agents.portrait.PortraitAgent.run", side_effect=ValueError("portrait unavailable")
        ), patch(
            "agents.adapter.AdapterAgent.run", side_effect=AssertionError("adapt should not run")
        ):
            response = self.client.post(
                "/api/pipeline/script",
                json={
                    "book_id": self.book_id,
                    "genre": "short_drama",
                    "episode_count": 1,
                    "stop_after": "content",
                },
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        payload = self.client.get(f"/api/pipeline/task/{task_id}").json()

        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["current_step"], "content preparation complete")
        self.assertTrue(any("人物画像已跳过" in item for item in payload.get("warnings", [])))

        with Session() as session:
            book = session.get(Book, self.book_id)
            self.assertIsNotNone(book)
            self.assertEqual(book.status, "bibeled")

    def test_ingest_prefers_explicit_title_over_auto_extracted_title(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "20260716_220000_manual.txt"
            filepath.write_text("第一章\n雨夜借宿，寺门被敲响。", encoding="utf-8")

            with patch("core.ingest.vs.add_documents", return_value=None), patch(
                "core.llm.call_llm", side_effect=AssertionError("title extraction should not run")
            ):
                result = ingest(str(filepath), preferred_title="验收短篇标题")

        created_book_id = result["book_id"]
        try:
            with Session() as session:
                book = session.get(Book, created_book_id)
                self.assertIsNotNone(book)
                self.assertEqual(book.title, "验收短篇标题")
        finally:
            with Session() as session:
                session.query(Book).filter(Book.id == created_book_id).delete()
                session.commit()

    def test_ingest_rejects_failed_title_extraction_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "20260716_220100_text_input.txt"
            filepath.write_text("第一章\n寺门深夜，风声压得人喘不过气。", encoding="utf-8")

            with patch("core.ingest.vs.add_documents", return_value=None), patch(
                "core.llm.call_llm", return_value="请提供包含书籍/故事标题的文本。"
            ):
                result = ingest(str(filepath))

        created_book_id = result["book_id"]
        try:
            with Session() as session:
                book = session.get(Book, created_book_id)
                self.assertIsNotNone(book)
                self.assertEqual(book.title, "20260716_220100_text_input")
        finally:
            with Session() as session:
                session.query(Book).filter(Book.id == created_book_id).delete()
                session.commit()


if __name__ == "__main__":
    unittest.main()
