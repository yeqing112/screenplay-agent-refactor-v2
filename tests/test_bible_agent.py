import json
import unittest
from unittest.mock import patch

from agents.bible import BibleAgent
from models import Book, BookBible, Chapter, Session, init_db


class BibleAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991229
        with Session() as session:
            self._cleanup(session)
            session.add(
                Book(
                    id=self.book_id,
                    title="Bible Agent Tests",
                    filename="bible-agent-tests.txt",
                    chapter_count=1,
                    total_words=100,
                    status="read",
                )
            )
            session.add(
                Chapter(
                    book_id=self.book_id,
                    seq=1,
                    title="第一章",
                    status="analyzed",
                    character_table=json.dumps(
                        [
                            {
                                "name": "新角色",
                                "identity": "医生",
                                "personality": "冷静",
                                "relationships": {},
                            }
                        ],
                        ensure_ascii=False,
                    ),
                    events=json.dumps(
                        [{"importance": "high", "description": "新事件"}],
                        ensure_ascii=False,
                    ),
                    scenes=json.dumps([{"location": "新地点"}], ensure_ascii=False),
                    foreshadowing=json.dumps(["新伏笔"], ensure_ascii=False),
                )
            )
            session.add(BookBible(book_id=self.book_id, content="OLD_BIBLE_CONTENT"))
            session.commit()

    def tearDown(self):
        with Session() as session:
            self._cleanup(session)
            session.commit()

    def _cleanup(self, session):
        session.query(BookBible).filter(BookBible.book_id == self.book_id).delete()
        session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
        session.query(Book).filter(Book.id == self.book_id).delete()

    def test_run_validates_fresh_bible_document_instead_of_old_db_content(self):
        seen = {}

        def fake_qa_run(_checker, bible_content=None):
            seen["bible_content"] = bible_content
            return {"overall_score": 9, "auto_fixes": []}

        with patch("agents.bible_qa.BibleQAChecker.run", new=fake_qa_run):
            BibleAgent(self.book_id).run()

        self.assertIn("新角色", seen["bible_content"])
        self.assertIn("新事件", seen["bible_content"])
        self.assertNotIn("OLD_BIBLE_CONTENT", seen["bible_content"])

    def test_bible_qa_auto_fix_is_scoped_to_target_character_section(self):
        doc = "\n".join(
            [
                "# 小说圣经 - 测试",
                "",
                "## 一、人物数据库",
                "",
                "### 甲",
                "**身份/职业：** 医生",
                "- 性别: 男性 | 年龄: 20-30岁 | 定位: 主角",
                "",
                "### 乙",
                "**身份/职业：** 老师",
                "- 性别: 女性 | 年龄: 20-30岁 | 定位: 配角",
            ]
        )

        fixed = BibleAgent(self.book_id)._apply_bible_qa_fixes(
            doc,
            [
                {
                    "character": "乙",
                    "field": "age_range",
                    "old_value": "20-30岁",
                    "new_value": "30-40岁",
                }
            ],
        )

        self.assertIn("- 性别: 男性 | 年龄: 20-30岁 | 定位: 主角", fixed)
        self.assertIn("- 性别: 女性 | 年龄: 30-40岁 | 定位: 配角", fixed)

    def test_bible_qa_auto_fix_matches_exact_character_heading(self):
        doc = "\n".join(
            [
                "# 小说圣经 - 测试",
                "",
                "### 甲方",
                "- 性别: 男性 | 年龄: 20-30岁 | 定位: 反派",
                "",
                "### 甲",
                "- 性别: 女性 | 年龄: 20-30岁 | 定位: 主角",
            ]
        )

        fixed = BibleAgent(self.book_id)._apply_bible_qa_fixes(
            doc,
            [
                {
                    "character": "甲",
                    "field": "age_range",
                    "old_value": "20-30岁",
                    "new_value": "30-40岁",
                }
            ],
        )

        self.assertIn("### 甲方\n- 性别: 男性 | 年龄: 20-30岁 | 定位: 反派", fixed)
        self.assertIn("### 甲\n- 性别: 女性 | 年龄: 30-40岁 | 定位: 主角", fixed)


if __name__ == "__main__":
    unittest.main()
