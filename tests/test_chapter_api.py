import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Chapter, Session, init_db


class ChapterApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 991224
        with Session() as session:
            self._cleanup(session)
            session.add(
                Book(
                    id=self.book_id,
                    title="Chapter API",
                    filename="chapter-api.txt",
                    chapter_count=1,
                    total_words=12,
                    status="read",
                )
            )
            session.add(
                Chapter(
                    book_id=self.book_id,
                    seq=1,
                    title="第一章",
                    content="这是一段很长的正文，不应出现在章节列表里。",
                    word_count=21,
                    status="analyzed",
                    summary="雨夜叩门。",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            self._cleanup(session)
            session.commit()

    def _cleanup(self, session):
        session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
        session.query(Book).filter(Book.id == self.book_id).delete()

    def test_chapter_list_omits_content_and_detail_loads_it(self):
        list_response = self.client.get(f"/api/books/{self.book_id}/chapters")
        self.assertEqual(list_response.status_code, 200)
        chapter_summary = list_response.json()[0]
        self.assertNotIn("content", chapter_summary)

        detail_response = self.client.get(f"/api/books/{self.book_id}/chapters/{chapter_summary['id']}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("很长的正文", detail_response.json()["content"])

    def test_missing_chapter_returns_404(self):
        response = self.client.get(f"/api/books/{self.book_id}/chapters/999999")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
