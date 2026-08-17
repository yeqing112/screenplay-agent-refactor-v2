import unittest
from unittest.mock import patch

from agents.portrait import PortraitAgent
from models import Book, Chapter, CharacterProfile, CharacterStage, Session, VisualMakeup, init_db


class PortraitFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991101
        with Session() as session:
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(CharacterStage).filter(CharacterStage.book_id == self.book_id).delete()
            session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
            session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()

            session.add(
                Book(
                    id=self.book_id,
                    title="Portrait Fallback Book",
                    filename="portrait-fallback-book.txt",
                    chapter_count=1,
                    total_words=800,
                    status="read",
                )
            )
            session.add(
                Chapter(
                    book_id=self.book_id,
                    seq=1,
                    title="第一章",
                    content="阿宁回到寺门前。",
                    status="analyzed",
                    character_table='[{"name":"阿宁","identity":"归寺少年","personality":"谨慎、沉默","aliases":[],"relationships":{"和尚甲":"对立"}}]',
                    appearance_fragments="{}",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(CharacterStage).filter(CharacterStage.book_id == self.book_id).delete()
            session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
            session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_portrait_agent_generates_base_profile_without_appearance_fragments(self):
        captured = {}

        def fake_generate_base_profile(book_id, session, name, fragments, char_info):
            captured["name"] = name
            captured["fragments"] = fragments
            captured["char_info"] = char_info
            session.add(
                CharacterProfile(
                    book_id=book_id,
                    name=name,
                    gender="未知",
                    age_range="青年(18-35)",
                    role="minor",
                    identity=char_info.get("identity", ""),
                    face_shape="",
                    facial_features="",
                    body_type="",
                    skin_tone="",
                    distinguishing_marks="",
                    signature_outfit="僧人便装",
                    accessories="",
                    hairstyle="短发",
                    temperament=char_info.get("personality", ""),
                    vibe="",
                    color_palette="",
                    personality=char_info.get("personality", ""),
                    speech_style="",
                    body_language="",
                    visual_prompt_en="base prompt",
                    visual_prompt_zh="基础画像提示词",
                    core_prompt_en="base prompt",
                    core_prompt_zh="基础画像提示词",
                    outfit_prompt_en="",
                    outfit_prompt_zh="",
                    scene_prompt_en="",
                    scene_prompt_zh="",
                    chapter_range="第1章",
                    importance="low",
                )
            )
            session.commit()
            return {"visual_prompt_zh": "基础画像提示词"}

        with patch("agents.portrait.generate_base_profile", side_effect=fake_generate_base_profile), patch(
            "agents.portrait.generate_stages", return_value=None
        ):
            output = PortraitAgent(self.book_id).run()

        self.assertIn("角色画像.md", output)
        self.assertEqual(captured["name"], "阿宁")
        self.assertTrue(any("身份是" in item or "性格是" in item for item in captured["fragments"]))

        with Session() as session:
            book = session.get(Book, self.book_id)
            profile = (
                session.query(CharacterProfile)
                .filter(CharacterProfile.book_id == self.book_id, CharacterProfile.name == "阿宁")
                .first()
            )
            makeup = (
                session.query(VisualMakeup)
                .filter(
                    VisualMakeup.book_id == self.book_id,
                    VisualMakeup.character_name == "阿宁",
                    VisualMakeup.stage_name == "base_identity",
                )
                .first()
            )

            self.assertIsNotNone(profile)
            self.assertIsNotNone(makeup)
            self.assertIn("base_identity", makeup.meta_info)
            self.assertEqual(book.status, "portraited")


if __name__ == "__main__":
    unittest.main()
