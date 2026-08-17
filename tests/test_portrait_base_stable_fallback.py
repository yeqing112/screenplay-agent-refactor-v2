import unittest
from unittest.mock import patch

from agents.portrait_base import generate_base_profile
from models import Book, Chapter, CharacterProfile, Session, init_db


class PortraitBaseStableFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991102
        with Session() as session:
            session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
            session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Portrait Base Stable Fallback",
                    filename="portrait-base-stable-fallback.txt",
                    chapter_count=1,
                    total_words=500,
                    status="read",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
            session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_generate_base_profile_uses_stable_template_when_llm_fails(self):
        char_info = {
            "identity": "和尚（寺庙僧侣）",
            "personality": "懒惰、推诿、随意、爱欺负新人，略显粗鄙",
            "aliases": [],
            "relationships": {"阿宁": "欺负新人"},
            "first_chapter": 1,
            "chapters": [1],
        }
        fragments = [
            "和尚甲剃着光头，灰旧僧袍松松垮垮地挂在身上，手里捻着一串磨旧的念珠，神情懒散又带着几分欺人的轻慢。",
            "他说话散漫，站姿懒散，像个混日子的僧人。",
        ]

        with Session() as session, patch(
            "agents.portrait_base.call_llm_json",
            side_effect=TimeoutError("llm timeout"),
        ):
            result = generate_base_profile(
                self.book_id,
                session,
                "和尚甲",
                fragments,
                char_info,
            )

        self.assertIn("人物定妆设定板", result["visual_prompt_zh"])
        self.assertIn("上排为脸部特写：正面、侧面、45度", result["visual_prompt_zh"])
        self.assertIn("下排为全身展示：正面、侧面、背面", result["visual_prompt_zh"])
        self.assertIn("身份是【和尚（寺庙僧侣）】", result["visual_prompt_zh"])
        self.assertIn("【中国】【男性】", result["visual_prompt_zh"])
        self.assertIn("剃着光头", result["visual_prompt_zh"])
        self.assertIn("灰旧僧袍", result["visual_prompt_zh"])
        self.assertIn("念珠", result["visual_prompt_zh"])
        self.assertNotIn("阿宁", result["visual_prompt_zh"])
        self.assertNotIn("剃着光头，光头", result["visual_prompt_zh"])
        self.assertIn("服装：【", result["outfit_prompt_zh"])
        self.assertIn("六宫格排版", result["scene_prompt_zh"])

        with Session() as session:
            profile = (
                session.query(CharacterProfile)
                .filter(CharacterProfile.book_id == self.book_id, CharacterProfile.name == "和尚甲")
                .first()
            )
            self.assertIsNotNone(profile)
            self.assertIn("人物定妆设定板", profile.visual_prompt_zh)
            self.assertIn("剃着光头", profile.visual_prompt_zh)
            self.assertIn("灰旧僧袍", profile.visual_prompt_zh)
            self.assertEqual(profile.gender, "男性")

    def test_generate_base_profile_infers_male_for_temple_disciple_context(self):
        char_info = {
            "identity": "寺中新入门的弟子（推测）",
            "personality": "隐忍克制，内心不服输，有骨气",
            "aliases": [],
            "relationships": {"和尚甲": "被刁难的新弟子"},
            "first_chapter": 1,
            "chapters": [1],
        }
        fragments = [
            "阿宁在雨夜赶回寺门，肩上背着湿透的包袱，脸色发白，脚步却很稳。守门的和尚甲剃着光头，灰旧僧袍松松垮垮地挂在身上。",
            "和尚甲斜眼打量阿宁，故意把门挡住，慢吞吞地说新人就该先去厨房烧水。阿宁低头应下，袖口滴着雨水，神情克制，眼里却压着不服。",
            "阿宁提着旧铁壶穿过廊下，看见灶间火光昏黄，湿衣贴在身上。和尚甲倚着门框，站姿散漫，像个混日子的僧人，却总爱欺负新来的弟子。",
        ]

        with Session() as session, patch(
            "agents.portrait_base.call_llm_json",
            side_effect=TimeoutError("llm timeout"),
        ):
            result = generate_base_profile(
                self.book_id,
                session,
                "阿宁",
                fragments,
                char_info,
            )

        self.assertIn("【男性】", result["visual_prompt_zh"])
        self.assertNotIn("【人物】", result["visual_prompt_zh"])
        self.assertNotIn("[第2章]", result["visual_prompt_zh"])
        self.assertIn("面色偏白，雨夜奔波后的疲态轻压在眼下", result["visual_prompt_zh"])
        self.assertIn("情绪克制，目光里仍压着不服气", result["visual_prompt_zh"])
        self.assertIn("黑色短发或束发", result["visual_prompt_zh"])
        self.assertIn("朴素弟子衣装因雨夜受潮贴身，整体简洁克制", result["visual_prompt_zh"])
        self.assertIn("旧包袱", result["visual_prompt_zh"])
        self.assertIn("中等偏瘦体型", result["visual_prompt_zh"])
        self.assertNotIn("剃着光头", result["visual_prompt_zh"])
        self.assertNotIn("灰旧僧袍", result["visual_prompt_zh"])

        with Session() as session:
            profile = (
                session.query(CharacterProfile)
                .filter(CharacterProfile.book_id == self.book_id, CharacterProfile.name == "阿宁")
                .first()
            )
            self.assertIsNotNone(profile)
            self.assertEqual(profile.gender, "男性")


if __name__ == "__main__":
    unittest.main()
