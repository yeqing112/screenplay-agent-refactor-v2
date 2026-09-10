import json
import unittest
from unittest.mock import patch

from core.alias_resolver import resolve_aliases
from core.constraint_engine import (
    Constraint,
    ConstraintCategory,
    ConstraintRegistry,
    ConstraintSeverity,
    ConstraintTarget,
    ConstraintValidator,
    RepairStrategy,
)
from core.portrait_qa import merge_characters, run_portrait_qa
from models import Book, Chapter, CharacterProfile, Session, VisualMakeup, VisualReferenceAsset, init_db


class P0GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991221
        with Session() as session:
            self._cleanup(session)
            session.add(
                Book(
                    id=self.book_id,
                    title="P0 Guardrail Tests",
                    filename="p0-guardrails.txt",
                    chapter_count=2,
                    total_words=200,
                    status="read",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            self._cleanup(session)
            session.commit()

    def _cleanup(self, session):
        session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
        session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
        session.query(Chapter).filter(Chapter.book_id == self.book_id).delete()
        session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).delete()
        session.query(Book).filter(Book.id == self.book_id).delete()

    def _add_profile(self, session, name, gender="", identity="", aliases=None):
        session.add(
            CharacterProfile(
                book_id=self.book_id,
                name=name,
                gender=gender,
                identity=identity,
                aliases=json.dumps(aliases or [], ensure_ascii=False),
            )
        )

    def test_alias_resolver_does_not_auto_merge_pending_confirm(self):
        with Session() as session:
            session.add_all(
                [
                    Chapter(
                        book_id=self.book_id,
                        seq=1,
                        title="第一章",
                        status="analyzed",
                        character_table=json.dumps([{"name": "甲"}], ensure_ascii=False),
                    ),
                    Chapter(
                        book_id=self.book_id,
                        seq=2,
                        title="第二章",
                        status="analyzed",
                        character_table=json.dumps([{"name": "乙"}], ensure_ascii=False),
                    ),
                ]
            )
            self._add_profile(session, "甲", gender="男性")
            self._add_profile(session, "乙", gender="男性")
            session.commit()

            with patch("core.alias_resolver.call_llm_json", return_value={
                "merged": [],
                "pending_confirm": [{"names": ["甲", "乙"], "confidence": "medium", "reason": "仅中置信"}],
                "gender_conflicts": [],
            }):
                result = resolve_aliases(self.book_id, session)

            self.assertEqual(result["甲"], ["甲"])
            self.assertEqual(result["乙"], ["乙"])
            names = {
                p.name
                for p in session.query(CharacterProfile).filter(CharacterProfile.book_id == self.book_id).all()
            }
            self.assertEqual(names, {"甲", "乙"})

    def test_portrait_qa_requires_identity_evidence_before_conflict_or_merge_candidate(self):
        with Session() as session:
            session.add_all(
                [
                    Chapter(
                        book_id=self.book_id,
                        seq=1,
                        title="第一章",
                        status="analyzed",
                        character_table=json.dumps([{"name": "阿强"}], ensure_ascii=False),
                    ),
                    Chapter(
                        book_id=self.book_id,
                        seq=2,
                        title="第二章",
                        status="analyzed",
                        character_table=json.dumps([{"name": "阿宁"}], ensure_ascii=False),
                    ),
                ]
            )
            self._add_profile(session, "阿强", gender="男性", identity="村民")
            self._add_profile(session, "阿宁", gender="女性", identity="医师")
            session.commit()

            report = run_portrait_qa(self.book_id, session)

            self.assertEqual(report.gender_conflicts, [])
            self.assertEqual(report.merge_candidates, [])

    def test_merge_characters_rejects_gender_conflict(self):
        with Session() as session:
            self._add_profile(session, "阿强", gender="男性")
            self._add_profile(session, "阿宁", gender="女性")
            session.commit()

            result = merge_characters(self.book_id, "阿强", "阿宁", session)

            self.assertIn("性别冲突", result["error"])
            self.assertIsNotNone(
                session.query(CharacterProfile).filter(
                    CharacterProfile.book_id == self.book_id,
                    CharacterProfile.name == "阿宁",
                ).first()
            )

    def test_portrait_qa_detects_locked_makeup_gender_drift(self):
        with Session() as session:
            self._add_profile(session, "阿强", gender="男性")
            session.flush()
            profile = session.query(CharacterProfile).filter_by(book_id=self.book_id, name="阿强").first()
            makeup = VisualMakeup(
                book_id=self.book_id,
                episode=1,
                character_name="阿强",
                meta_info=json.dumps({"character_profile_id": profile.id, "gender": "女性"}, ensure_ascii=False),
            )
            session.add(makeup); session.flush()
            session.add(VisualReferenceAsset(
                book_id=self.book_id, episode=1, asset_type="character", asset_id=str(makeup.id),
                asset_name="阿强", status="locked", image_url="https://example.com/aqiang.png",
            ))
            session.commit()

            report = run_portrait_qa(self.book_id, session)

        issue = next(issue for issue in report.issues if issue.issue_type == "makeup_gender_conflict")
        self.assertEqual(issue.severity, "high")
        self.assertEqual(issue.evidence["expected_gender"], "男性")
        self.assertEqual(issue.evidence["actual_gender"], "女性")

    def test_constraint_validator_handles_empty_and_positional_scene_rules(self):
        registry = ConstraintRegistry()
        registry._constraints = {
            "SHOT_PURPOSE_ENUM": Constraint(
                id="SHOT_PURPOSE_ENUM",
                category=ConstraintCategory.HARD,
                target=ConstraintTarget.SHOT,
                field="shot_purpose",
                rule="enum_match",
                rule_params={"valid_keys": {"hook", "action", "cliffhanger"}, "valid_values": set()},
                severity=ConstraintSeverity.BLOCK,
            ),
            "OPENING_MUST_BE_HOOK": Constraint(
                id="OPENING_MUST_BE_HOOK",
                category=ConstraintCategory.FORBIDDEN,
                target=ConstraintTarget.SCENE,
                field="shot_purpose",
                rule="forbidden",
                rule_params={"forbidden_values": {"establish"}},
                severity=ConstraintSeverity.BLOCK,
            ),
            "ENDING_MUST_HAVE_SUSPENSE": Constraint(
                id="ENDING_MUST_HAVE_SUSPENSE",
                category=ConstraintCategory.HARD,
                target=ConstraintTarget.SCENE,
                field="shot_purpose",
                rule="enum_match",
                rule_params={"valid_keys": {"cliffhanger"}, "valid_values": set()},
                severity=ConstraintSeverity.BLOCK,
                repair_strategy=RepairStrategy.HYBRID,
            ),
        }
        validator = ConstraintValidator(registry)

        empty_result = validator.validate_shot({})
        self.assertFalse(empty_result.passed)
        self.assertEqual(empty_result.violations[0].constraint_id, "SHOT_PURPOSE_ENUM")

        scene_result = validator.validate_scene(
            [
                {"shot_purpose": "hook"},
                {"shot_purpose": "action"},
                {"shot_purpose": "cliffhanger"},
            ]
        )
        self.assertTrue(scene_result.passed)
        self.assertNotIn("ENDING_MUST_HAVE_SUSPENSE", scene_result.stats)


if __name__ == "__main__":
    unittest.main()
