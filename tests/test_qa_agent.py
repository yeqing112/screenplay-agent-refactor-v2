import json
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from agents.qa import QAAgent
from models import Book, BookBible, QAResult, Script, Session, init_db


class QAAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991304
        self.episode = 1
        self.book_title = "QA Agent Demo"
        self.script_text = "\n".join(
            [
                "**Scene 1:[courtyard-noon]**",
                "The monk freezes when the token briefly slips from his sleeve.",
                "**Scene 2:[hall-night]**",
                "He confesses too quickly and the others accept it without pressure.",
            ]
        )
        with Session() as session:
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(BookBible).filter(BookBible.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title=self.book_title,
                    filename="qa-agent-demo.txt",
                    chapter_count=1,
                    total_words=len(self.script_text),
                    status="draft",
                )
            )
            session.add(
                BookBible(
                    book_id=self.book_id,
                    content="\n".join(
                        [
                            "# Bible",
                            "## Character Bible",
                            "Monk A: restrained and careful.",
                            "Monk B: lazy and rude.",
                            "## World",
                            "Temple rules are strict.",
                        ]
                    ),
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=self.episode,
                    content=self.script_text,
                    word_count=len(self.script_text),
                    status="draft",
                )
            )
            session.commit()

    def tearDown(self):
        cleanup_paths = [
            Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa.json")),
            Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa_invalid_attempt_1.txt")),
            Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa_invalid_attempt_2.txt")),
            Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa_invalid_attempt_3.txt")),
            Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa_invalid_attempt_4.txt")),
        ]
        for path in cleanup_paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

        with Session() as session:
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(BookBible).filter(BookBible.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_qa_agent_persists_structured_result(self):
        captured = {}

        def fake_call(prompt, system=None, **kwargs):
            captured["prompt"] = prompt
            captured["system"] = system
            return json.dumps(
                {
                    "issues": [
                        {
                            "type": "logic_gap",
                            "severity": "high",
                            "title": "token payoff too easy",
                            "description": "The confession lands without enough resistance.",
                            "location": {"script_section": "Scene 2", "line_range": [4, 4]},
                            "suggestion": "Add resistance before acceptance.",
                            "fix_mode": "semi_auto",
                        }
                    ],
                    "errors": [],
                    "overall_score": 6,
                    "suggestions": ["Strengthen scene pressure before the reveal lands."],
                },
                ensure_ascii=False,
            )

        with patch("agents.qa.call_llm", side_effect=fake_call):
            result = QAAgent(self.book_id).run(self.episode)

        self.assertEqual(result["overall_score"], 6)
        self.assertIn("Production Skill", captured["prompt"])
        self.assertIn("## QA Structure Focus", captured["prompt"])
        self.assertIn("structure_layer must lean toward one of", captured["prompt"])
        self.assertIn("repair_stage must lean toward one of", captured["prompt"])
        self.assertIn("issues", captured["prompt"])

        qa_path = Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa.json"))
        self.assertTrue(qa_path.exists())
        payload = json.loads(qa_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["issues"][0]["title"], "token payoff too easy")

        with Session() as session:
            qa_rows = session.query(QAResult).filter(
                QAResult.book_id == self.book_id,
                QAResult.episode == self.episode,
            ).all()
        self.assertEqual(len(qa_rows), 1)
        self.assertEqual(qa_rows[0].error_count, 1)

    def test_qa_agent_retries_after_invalid_non_json_output(self):
        calls = {"count": 0}

        def fake_call(prompt, system=None, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return "analysis first\n{ not valid json"
            return json.dumps(
                {
                    "issues": [],
                    "errors": [],
                    "overall_score": 8,
                    "suggestions": ["Minor polish only."],
                },
                ensure_ascii=False,
            )

        with patch("agents.qa.call_llm", side_effect=fake_call):
            result = QAAgent(self.book_id).run(self.episode)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result["overall_score"], 8)
        debug_path = Path(config.output_path(self.book_title, "qa", f"episode_{self.episode:02d}_qa_invalid_attempt_1.txt"))
        self.assertTrue(debug_path.exists())
        self.assertIn("analysis first", debug_path.read_text(encoding="utf-8"))

    def test_qa_agent_salvages_truncated_compact_json(self):
        responses = [
            "not json at all",
            "still not json",
            """{
  "issues": [
    {
      "type": "continuity",
      "severity": "high",
      "title": "portrait drift",
      "description": "Character behavior no longer matches profile.",
      "location": {"script_section": "Scene 1", "line_range": []},
      "suggestion": "Restore the established persona.",
      "fix_mode": "manual"
    },
    {
      "type": "visual",
      "severity": "medium",
      "title": "missing evidence on screen",
      "description": "The clue is mentioned but never shown.",
      "location": {"script_section": "Scene 2", "line_range": []},
      "suggestion": "Add a close-up of the clue.",
      "fix_mode": "auto"
    },
    {
      "type": "logic_gap",
      "severity": "high",
      "title": "incomplete""",
        ]

        with patch("agents.qa.call_llm", side_effect=responses):
            result = QAAgent(self.book_id).run(self.episode)

        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual(result["issues"][0]["title"], "portrait drift")
        self.assertEqual(result["issues"][1]["type"], "visual")

    def test_detects_analysis_only_qa_output(self):
        raw = "\n".join(
            [
                "我们需要回答用户：作为短剧剧本质检编辑。",
                "需要仔细分析剧本，找出问题。",
                "Current episode script is in Chinese.",
            ]
        )

        self.assertTrue(QAAgent(self.book_id)._looks_like_analysis_only_output(raw))

    def test_qa_agent_retries_compact_json_when_analysis_only_output_appears(self):
        responses = [
            "not json at all",
            "still not json",
            "我们需要回答用户：作为短剧剧本质检编辑。\n需要仔细分析剧本，找出问题。\nCurrent episode script is in Chinese.",
            json.dumps(
                {
                    "issues": [],
                    "errors": [],
                    "overall_score": 8,
                    "suggestions": ["Minor polish only."],
                },
                ensure_ascii=False,
            ),
        ]

        with patch("agents.qa.call_llm", side_effect=responses) as mocked_call:
            result = QAAgent(self.book_id).run(self.episode)

        self.assertEqual(result["overall_score"], 8)
        self.assertEqual(mocked_call.call_count, 4)

    def test_parse_qa_payload_normalizes_missing_optional_fields(self):
        raw = json.dumps(
            {
                "issues": [
                    {
                        "type": "continuity",
                        "severity": "high",
                        "title": "portrait drift",
                        "description": "Character behavior no longer matches profile.",
                        "location": {"script_section": "Scene 1", "line_range": []},
                        "suggestion": "Restore the established persona.",
                        "fix_mode": "manual",
                    }
                ],
                "errors": [],
            },
            ensure_ascii=False,
        )

        result = QAAgent(self.book_id)._parse_qa_payload(raw)

        self.assertEqual(result["overall_score"], 7)
        self.assertTrue(result["word_count_ok"])
        self.assertEqual(result["suggestions"], [])
        self.assertEqual(result["issues"][0]["rule_family"], "character_consistency")
        self.assertEqual(result["issues"][0]["structure_layer"], "fact_layer")
        self.assertEqual(result["issues"][0]["repair_stage"], "fact_generation")
        self.assertEqual(result["structure_summary"]["dominant_layer"], "fact_layer")
        self.assertEqual(result["structure_summary"]["dominant_stage"], "fact_generation")

    def test_parse_qa_payload_builds_structure_summary_across_layers(self):
        raw = json.dumps(
            {
                "issues": [
                    {
                        "type": "continuity",
                        "severity": "high",
                        "title": "法牌物证去向未交代",
                        "description": "Prop custody chain is broken.",
                        "location": {"script_section": "Scene 1", "line_range": []},
                        "suggestion": "Show who takes custody.",
                        "fix_mode": "manual",
                    },
                    {
                        "type": "visual",
                        "severity": "medium",
                        "title": "线索没有入画",
                        "description": "The clue is only mentioned in dialogue.",
                        "location": {"script_section": "Scene 2", "line_range": []},
                        "suggestion": "Add a close-up.",
                        "fix_mode": "auto",
                    },
                ],
                "errors": [],
            },
            ensure_ascii=False,
        )

        result = QAAgent(self.book_id)._parse_qa_payload(raw)

        self.assertEqual(result["issues"][0]["structure_layer"], "fact_layer")
        self.assertEqual(result["issues"][1]["structure_layer"], "scene_execution_layer")
        self.assertEqual(result["structure_summary"]["layer_counts"]["fact_layer"], 1)
        self.assertEqual(result["structure_summary"]["layer_counts"]["scene_execution_layer"], 1)

    def test_qa_agent_uses_normalization_when_salvage_is_low_fidelity(self):
        responses = [
            "not json at all",
            "still not json",
            "We need respond JSON only, no analysis.\nNeed inspect script carefully.\n"
            '"issues": [{"type": "evidence", "severity": "high", "title": "single issue", '
            '"description": "Only one extracted issue.", "location": {"script_section": "Scene 1", "line_range": []}, '
            '"suggestion": "Add evidence.", "fix_mode": "manual"}], "errors": []',
            json.dumps(
                {
                    "issues": [
                        {
                            "type": "continuity",
                            "severity": "high",
                            "title": "portrait drift",
                            "description": "Character behavior no longer matches profile.",
                            "location": {"script_section": "Scene 1", "line_range": []},
                            "suggestion": "Restore the established persona.",
                            "fix_mode": "manual",
                        },
                        {
                            "type": "visual",
                            "severity": "medium",
                            "title": "missing evidence on screen",
                            "description": "The clue is mentioned but never shown.",
                            "location": {"script_section": "Scene 2", "line_range": []},
                            "suggestion": "Add a close-up of the clue.",
                            "fix_mode": "auto",
                        },
                    ],
                    "errors": [],
                    "overall_score": 7,
                    "suggestions": ["Normalize the evidence chain."],
                },
                ensure_ascii=False,
            ),
        ]

        with patch("agents.qa.call_llm", side_effect=responses) as mocked_call:
            result = QAAgent(self.book_id).run(self.episode)

        self.assertEqual(mocked_call.call_count, 4)
        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual(result["issues"][0]["title"], "portrait drift")
        self.assertEqual(result["overall_score"], 7)


if __name__ == "__main__":
    unittest.main()
