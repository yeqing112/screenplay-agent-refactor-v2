import unittest
from unittest.mock import patch

from agents.reader import ReaderAgent
from models import Book, Chapter, Session, init_db


class ReaderFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991103
        with Session() as session:
            session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Reader Fallback Book",
                    filename="reader-fallback-book.txt",
                    chapter_count=2,
                    total_words=260,
                    status="imported",
                )
            )
            session.add(
                Chapter(
                    book_id=self.book_id,
                    seq=1,
                    title="",
                    content="《寺门归客八》",
                    word_count=7,
                    status="imported",
                )
            )
            session.add(
                Chapter(
                    book_id=self.book_id,
                    seq=2,
                    title="第1章 雨夜归门",
                    content=(
                        "阿宁在雨夜赶回寺门，肩上背着湿透的包袱，脸色发白，脚步却很稳。"
                        "守门的和尚甲剃着光头，灰旧僧袍松松垮垮地挂在身上，手里捻着一串磨旧的念珠，神情懒散。"
                    ),
                    word_count=80,
                    status="imported",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_reader_handles_short_title_only_chapter_without_llm(self):
        agent = ReaderAgent(self.book_id, chapter_delay=0)
        with patch("agents.reader.call_llm_json", side_effect=AssertionError("llm should not be called")):
            result = agent._analyze_chapter({"id": self._chapter_id(1), "seq": 1, "title": "", "content": "《寺门归客八》"})

        self.assertIn("仅包含标题或极短文本", result["summary"])
        self.assertEqual(result["characters"], [])

        with Session() as session:
            chapter = session.query(Chapter).filter(Chapter.book_id == self.book_id, Chapter.seq == 1).first()
            self.assertEqual(chapter.status, "analyzed")
            self.assertIn("仅包含标题或极短文本", chapter.summary)

    def test_reader_falls_back_to_local_structured_extraction_when_llm_json_fails(self):
        agent = ReaderAgent(self.book_id, chapter_delay=0)
        with patch("agents.reader.call_llm_json", side_effect=ValueError("Failed to parse LLM JSON response")):
            result = agent._analyze_chapter(
                {
                    "id": self._chapter_id(2),
                    "seq": 2,
                    "title": "第1章 雨夜归门",
                    "content": (
                        "阿宁在雨夜赶回寺门，肩上背着湿透的包袱，脸色发白，脚步却很稳。"
                        "守门的和尚甲剃着光头，灰旧僧袍松松垮垮地挂在身上，手里捻着一串磨旧的念珠，神情懒散。"
                    ),
                }
            )

        character_names = [item["name"] for item in result["characters"]]
        self.assertIn("阿宁", character_names)
        self.assertIn("和尚甲", character_names)
        self.assertTrue(result["events"])
        self.assertTrue(result["scenes"])
        self.assertIn("阿宁", result["appearance_fragments"])

    def _chapter_id(self, seq: int) -> int:
        with Session() as session:
            chapter = session.query(Chapter).filter(Chapter.book_id == self.book_id, Chapter.seq == seq).first()
            return chapter.id


if __name__ == "__main__":
    unittest.main()
