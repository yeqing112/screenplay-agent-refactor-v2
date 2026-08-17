import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, EpisodeOutline, Session, init_db


class OutlineCharacterListParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990501
        with Session() as session:
            session.query(EpisodeOutline).filter(EpisodeOutline.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Outline Character Parsing Demo",
                    filename="outline-character-demo.txt",
                    chapter_count=1,
                    total_words=1200,
                    status="imported",
                )
            )
            session.add(
                EpisodeOutline(
                    book_id=self.book_id,
                    episode=1,
                    title="Episode 1",
                    core_event="Three monks argue by the water room.",
                    characters="和尚甲, 和尚乙, 和尚丙",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(EpisodeOutline).filter(EpisodeOutline.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_outputs_parse_outline_characters_without_json_warning(self):
        with self.assertNoLogs("core", level="WARNING"):
            response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")

        self.assertEqual(response.status_code, 200)
        outlines = response.json()["outlines"]
        self.assertEqual(len(outlines), 1)
        self.assertEqual(outlines[0]["characters"], ["和尚甲", "和尚乙", "和尚丙"])


if __name__ == "__main__":
    unittest.main()
