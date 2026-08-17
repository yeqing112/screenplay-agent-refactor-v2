import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Session, init_db


class BooksListTitleNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_ids = [992101, 992102, 992103]
        with Session() as session:
            session.query(Book).filter(Book.id.in_(self.book_ids)).delete(synchronize_session=False)
            session.add_all(
                [
                    Book(
                        id=self.book_ids[0],
                        title="????????-????",
                        filename="corrupted-question.txt",
                        chapter_count=1,
                        total_words=12,
                        status="bibled",
                    ),
                    Book(
                        id=self.book_ids[1],
                        title="请提供包含书籍/故事标题的文本。",
                        filename="corrupted-hint.txt",
                        chapter_count=1,
                        total_words=12,
                        status="bibled",
                    ),
                    Book(
                        id=self.book_ids[2],
                        title="雨夜借宿",
                        filename="valid-title.txt",
                        chapter_count=1,
                        total_words=12,
                        status="portraited",
                    ),
                ]
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(Book).filter(Book.id.in_(self.book_ids)).delete(synchronize_session=False)
            session.commit()

    def test_books_endpoint_returns_display_safe_titles(self):
        response = self.client.get("/api/books")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        by_id = {item["id"]: item for item in payload}

        self.assertEqual(by_id[self.book_ids[0]]["title"], "未命名项目 992101")
        self.assertEqual(by_id[self.book_ids[1]]["title"], "未命名项目 992102")
        self.assertEqual(by_id[self.book_ids[2]]["title"], "雨夜借宿")


if __name__ == "__main__":
    unittest.main()
