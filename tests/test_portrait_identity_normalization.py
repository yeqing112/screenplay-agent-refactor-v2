import unittest
from unittest.mock import patch

from agents.portrait_base import generate_base_profile
from models import Book, CharacterProfile, Session, init_db


class PortraitIdentityNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991104
        with Session() as session:
            session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Portrait Identity Normalization",
                    filename="portrait-identity-normalization.txt",
                    chapter_count=1,
                    total_words=200,
                    status="read",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_monk_identity_is_normalized_to_canonical_label(self):
        with Session() as session, patch("agents.portrait_base.call_llm_json", side_effect=TimeoutError("llm timeout")):
            result = generate_base_profile(
                self.book_id,
                session,
                "和尚甲",
                ["和尚甲剃着光头，灰旧僧袍松松垮垮地挂在身上。"],
                {
                    "identity": "寺庙守门僧人（推测）",
                    "personality": "懒散、轻慢",
                    "aliases": [],
                    "relationships": {},
                    "chapters": [1],
                    "first_chapter": 1,
                },
            )

        self.assertIn("身份是【和尚（寺庙僧侣）】", result["visual_prompt_zh"])
        with Session() as session:
            profile = session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id, CharacterProfile.name == "和尚甲").first()
            self.assertEqual(profile.identity, "和尚（寺庙僧侣）")

    def test_disciple_identity_is_normalized_to_canonical_label(self):
        with Session() as session, patch("agents.portrait_base.call_llm_json", side_effect=TimeoutError("llm timeout")):
            result = generate_base_profile(
                self.book_id,
                session,
                "阿宁",
                ["阿宁在雨夜赶回寺门，肩上背着湿透的包袱，脸色发白。"],
                {
                    "identity": "寺庙新入弟子（推测）",
                    "personality": "克制、隐忍",
                    "aliases": [],
                    "relationships": {},
                    "chapters": [1],
                    "first_chapter": 1,
                },
            )

        self.assertIn("身份是【寺中新入门的弟子（推测）】", result["visual_prompt_zh"])
        with Session() as session:
            profile = session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id, CharacterProfile.name == "阿宁").first()
            self.assertEqual(profile.identity, "寺中新入门的弟子（推测）")


if __name__ == "__main__":
    unittest.main()
