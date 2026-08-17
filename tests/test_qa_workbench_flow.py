import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import Book, EpisodeOutline, QAResult, QAIssue, Script, ScriptVersion, Session, init_db


class QAWorkbenchFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 991001
        self.episode = 3
        self.original_script = "\n".join([
            "场1：夜，破庙内。",
            "姜儿盯着莲花，迟迟不语。",
            "莲花只是低头，说自己没有证据。",
            "姜儿忽然点头：我信你。",
            "两人转身离开。",
        ])
        self.fixed_excerpt = "\n".join([
            "莲花忽然掏出染血账册，双手递到姜儿面前。",
            "姜儿盯着那本账册，呼吸一滞，终于点头：我信你。",
        ])

        with Session() as session:
            session.query(ScriptVersion).filter(ScriptVersion.book_id == self.book_id).delete()
            session.query(QAIssue).filter(QAIssue.book_id == self.book_id).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(EpisodeOutline).filter(EpisodeOutline.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()

            session.add(
                Book(
                    id=self.book_id,
                    title="QA Workbench Demo",
                    filename="qa-workbench-demo.txt",
                    chapter_count=1,
                    total_words=len(self.original_script),
                )
            )
            session.add(
                Script(
                    book_id=self.book_id,
                    episode=self.episode,
                    content=self.original_script,
                    word_count=len(self.original_script),
                    status="draft",
                )
            )
            session.add(
                EpisodeOutline(
                    book_id=self.book_id,
                    episode=self.episode,
                    title="?3?",
                    core_event="????????",
                    opening_hook="????",
                    core_conflict="??????",
                    climax="??????",
                    ending_hook="??????",
                    characters="??, ??",
                    scenes="???",
                )
            )
            session.add(
                QAResult(
                    book_id=self.book_id,
                    episode=self.episode,
                    result=json.dumps(
                        {
                            "errors": [
                                {
                                    "type": "logic_gap",
                                    "severity": "high",
                                    "title": "人物动机跳跃",
                                    "description": "姜儿突然决定信任莲花，缺少铺垫。",
                                    "location": {
                                        "script_section": "第3场",
                                        "line_range": [3, 4],
                                    },
                                    "suggestion": "增加莲花交出关键证据的动作，使信任转变成立。",
                                }
                            ],
                            "overall_score": 6,
                            "suggestions": ["补强关键证据和情绪递进。"],
                        },
                        ensure_ascii=False,
                    ),
                    error_count=1,
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(ScriptVersion).filter(ScriptVersion.book_id == self.book_id).delete()
            session.query(QAIssue).filter(QAIssue.book_id == self.book_id).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(EpisodeOutline).filter(EpisodeOutline.book_id == self.book_id).delete()
            session.query(Script).filter(Script.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_sync_structures_qa_issues_with_location_excerpt(self):
        response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["issues"]), 1)
        issue = payload["issues"][0]
        self.assertEqual(issue["type"], "logic_gap")
        self.assertEqual(issue["fix_status"], "pending")
        self.assertEqual(issue["rule_family"], "generic_skill_gap")
        self.assertTrue(issue["repair_goal"])
        self.assertEqual(issue["location"]["line_range"], [3, 4])
        self.assertIn("莲花只是低头", issue["source_excerpt"])

    def test_sync_prefers_structured_issues_fields_from_new_qa_protocol(self):
        with Session() as session:
            qa_result = session.query(QAResult).filter(
                QAResult.book_id == self.book_id,
                QAResult.episode == self.episode,
            ).first()
            qa_result.result = json.dumps(
                {
                    "issues": [
                        {
                            "type": "dialogue_style",
                            "severity": "medium",
                            "title": "dialogue-title",
                            "description": "dialogue-description",
                            "location": {
                                "script_section": "section-3",
                                "line_range": [2, 4],
                            },
                            "suggestion": "dialogue-suggestion",
                            "fix_mode": "auto",
                        }
                    ],
                    "errors": [],
                    "overall_score": 7,
                    "suggestions": ["summary-suggestion"],
                },
                ensure_ascii=False,
            )
            qa_result.error_count = 1
            session.commit()

        response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        self.assertEqual(response.status_code, 200)
        issue = response.json()["issues"][0]
        self.assertEqual(issue["type"], "dialogue_style")
        self.assertEqual(issue["title"], "dialogue-title")
        self.assertEqual(issue["suggestion"], "dialogue-suggestion")
        self.assertEqual(issue["fix_mode"], "auto")
        self.assertEqual(issue["rule_family"], "character_consistency")
        self.assertTrue(issue["repair_goal"])
        self.assertEqual(issue["location"]["line_range"], [2, 4])

    def test_workbench_auto_syncs_legacy_qa_result(self):
        response = self.client.get(f"/api/books/{self.book_id}/qa/workbench")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["episodes"]), 1)
        self.assertEqual(len(payload["episodes"][0]["issues"]), 1)
        self.assertEqual(payload["episodes"][0]["issues"][0]["type"], "logic_gap")
        self.assertEqual(payload["episodes"][0]["issues"][0]["rule_family"], "generic_skill_gap")
        self.assertTrue(payload["episodes"][0]["issues"][0]["repair_goal"])

    def test_preview_fix_returns_diff_without_mutating_script(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]
        response = self.client.post(
            f"/api/books/{self.book_id}/qa/issues/{issue_id}/preview-fix",
            json={
                "mode": "semi_auto",
                "patchedText": self.fixed_excerpt,
                "optionId": "A",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("--- episode-3-before", payload["diff_text"])
        self.assertIn("染血账册", payload["patched_text"])

        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()
        self.assertEqual(script.content, self.original_script)

    def test_workbench_backfills_excerpt_from_scene_location_when_line_range_missing(self):
        scene_script = "\n".join([
            "**场景一：[破庙内]**",
            "和尚甲打着哈欠，不愿意动。",
            "---",
            "**场景六：[后山夜色]**",
            "和尚甲说完最后一句，转身消失在夜色里。",
            "铜铃声还在远处回荡。",
        ])
        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()
            qa_result = session.query(QAResult).filter(QAResult.book_id == self.book_id, QAResult.episode == self.episode).first()
            script.content = scene_script
            script.word_count = len(scene_script)
            qa_result.result = json.dumps(
                {
                    "errors": [
                        {
                            "type": "format",
                            "severity": "medium",
                            "title": "场景六尾部被截断",
                            "description": "场景六末尾被截断，最后一句之后缺少收束。",
                            "location": "场景六末尾",
                        }
                    ],
                    "overall_score": 6,
                    "suggestions": ["补全结尾。"],
                },
                ensure_ascii=False,
            )
            qa_result.error_count = 1
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/qa/workbench")
        self.assertEqual(response.status_code, 200)
        issue = response.json()["episodes"][0]["issues"][0]
        self.assertIn("和尚甲说完最后一句", issue["source_excerpt"])

    def test_apply_fix_creates_version_and_recheck_pass(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        def fake_recheck_run(_self, episode):
            with Session() as session:
                session.add(
                    QAResult(
                        book_id=self.book_id,
                        episode=episode,
                        result=json.dumps(
                            {
                                "errors": [],
                                "overall_score": 9,
                                "suggestions": [],
                            },
                            ensure_ascii=False,
                        ),
                        error_count=0,
                    )
                )
                session.commit()
            return {"errors": [], "overall_score": 9}

        with patch("agents.qa.QAAgent.run", new=fake_recheck_run):
            response = self.client.post(
                f"/api/books/{self.book_id}/qa/issues/{issue_id}/apply-fix",
                json={
                    "mode": "auto",
                    "patchedText": self.fixed_excerpt,
                    "changeReason": "补强人物动机",
                    "rerunQa": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("--- episode-3-before", payload["diff_text"])
        self.assertEqual(payload["version"]["recheck_status"], "running")
        self.assertEqual(payload["recheck"]["status"], "running")

        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()
            issue = session.query(QAIssue).filter(QAIssue.issue_key == issue_id).first()
            versions = session.query(ScriptVersion).filter(
                ScriptVersion.book_id == self.book_id,
                ScriptVersion.episode == self.episode,
            ).order_by(ScriptVersion.version_no.asc()).all()

        self.assertIn("染血账册", script.content)
        self.assertEqual(issue.fix_status, "recheck_passed")
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].change_type, "baseline")
        self.assertEqual(versions[1].change_type, "auto_fix")
        self.assertEqual(versions[1].recheck_status, "passed")

    def test_auto_fix_issue_generates_and_applies_first_option(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        with patch("api.server.llm_client.call_llm_json", return_value={
            "options": [
                {
                    "id": "A",
                    "title": "auto-plan",
                    "strategy": "auto-strategy",
                    "patched_text": self.fixed_excerpt,
                }
            ]
        }):
            def fake_recheck_run(_self, episode):
                with Session() as session:
                    session.add(
                        QAResult(
                            book_id=self.book_id,
                            episode=episode,
                            result=json.dumps(
                                {"errors": [], "overall_score": 9, "suggestions": []},
                                ensure_ascii=False,
                            ),
                            error_count=0,
                        )
                    )
                    session.commit()
                return {"errors": [], "overall_score": 9}

            with patch("agents.qa.QAAgent.run", new=fake_recheck_run):
                response = self.client.post(
                    f"/api/books/{self.book_id}/qa/issues/{issue_id}/auto-fix",
                    json={"mode": "auto", "rerunQa": True},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected_option"]["id"], "A")
        self.assertEqual(payload["version"]["recheck_status"], "running")

        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()
            issue = session.query(QAIssue).filter(QAIssue.issue_key == issue_id).first()

        self.assertIn("染血账册", script.content)
        self.assertEqual(issue.fix_status, "recheck_passed")

    def test_generate_fix_options_includes_rule_family_repair_context(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        def fake_call(prompt, system=None, **kwargs):
            self.assertIn("## Script Repair Focus", prompt)
            self.assertIn("rule_family", prompt)
            self.assertIn("character_state_transition", prompt)
            self.assertIn("repair_goal", prompt)
            self.assertIn("## Script Skill Foundation", prompt)
            self.assertIn("## Script Skill Execution Plan", prompt)
            self.assertIn("## Script Skill Repair Packet", prompt)
            return {
                "options": [
                    {
                        "id": "A",
                        "title": "auto-plan",
                        "strategy": "auto-strategy",
                        "patched_text": self.fixed_excerpt,
                    }
                ]
            }

        with patch("api.server.llm_client.call_llm_json", side_effect=fake_call):
            response = self.client.post(
                f"/api/books/{self.book_id}/qa/issues/{issue_id}/generate-fix-options",
                json={"mode": "auto", "optionCount": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["options"][0]["id"], "A")
        self.assertEqual(payload["options"][0]["rule_family"], "character_state_transition")
        self.assertTrue(payload["options"][0]["repair_goal"])

    def test_auto_fix_issue_prefers_more_conservative_option(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        with patch("api.server.llm_client.call_llm_json", return_value={
            "options": [
                {
                    "id": "A",
                    "title": "larger rewrite",
                    "strategy": "大幅重写并扩展多个段落",
                    "patched_text": self.fixed_excerpt + "\n额外增加很多解释。\n额外增加很多解释。\n额外增加很多解释。",
                },
                {
                    "id": "B",
                    "title": "conservative",
                    "strategy": "保守局部修复，补足关键证据动作",
                    "patched_text": self.fixed_excerpt,
                },
            ]
        }):
            response = self.client.post(
                f"/api/books/{self.book_id}/qa/issues/{issue_id}/auto-fix",
                json={"mode": "auto", "rerunQa": False},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected_option"]["id"], "B")
        self.assertEqual(payload["selection_reason"], "best-scored-option")

    def test_auto_fix_episode_applies_multiple_open_issues(self):
        scene_script = "\n".join([
            "场景一：夜，破庙内。",
            "姜儿盯着莲花，迟迟不语。",
            "莲花只是低头，说自己没有证据。",
            "姜儿忽然点头：我信你。",
            "两人转身离开。",
            "下一场切到寺门外，却没有过渡。",
        ])
        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()
            qa_result = session.query(QAResult).filter(QAResult.book_id == self.book_id, QAResult.episode == self.episode).first()
            script.content = scene_script
            script.word_count = len(scene_script)
            qa_result.result = json.dumps(
                {
                    "issues": [
                        {
                            "type": "logic_gap",
                            "severity": "high",
                            "title": "人物动机跳跃",
                            "description": "姜儿突然决定信任莲花，缺少铺垫。",
                            "location": {"script_section": "场景一", "line_range": [3, 4]},
                            "suggestion": "补足关键证据动作。",
                            "fix_mode": "auto",
                        },
                        {
                            "type": "pace",
                            "severity": "medium",
                            "title": "转场生硬",
                            "description": "寺门外转场缺少过渡句。",
                            "location": {"script_section": "场景一", "line_range": [5, 6]},
                            "suggestion": "补一句转场过渡。",
                            "fix_mode": "auto",
                        }
                    ],
                    "overall_score": 5,
                    "suggestions": [],
                },
                ensure_ascii=False,
            )
            qa_result.error_count = 2
            session.commit()

        self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")

        with patch("api.server.llm_client.call_llm_json", side_effect=[
            {"options": [{"id": "A", "title": "fix1", "strategy": "s1", "patched_text": "莲花忽然掏出染血账册，双手递到姜儿面前。\n姜儿盯着那本账册，终于点头：我信你。"}]},
            {"options": [{"id": "A", "title": "fix2", "strategy": "s2", "patched_text": "两人转身离开，钟声把画面缓缓带到寺门外。\n下一场切到寺门外，风更冷了。"}]},
        ]):
            response = self.client.post(
                f"/api/books/{self.book_id}/qa/episodes/{self.episode}/auto-fix",
                json={"mode": "auto", "rerunQa": False, "maxIssues": 10},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["applied_count"], 2)
        self.assertEqual(payload["failed_count"], 0)
        self.assertEqual(payload["report"]["applied_count"], 2)
        self.assertEqual(len(payload["report"]["applied"]), 2)

        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()

        self.assertIn("染血账册", script.content)
        self.assertIn("钟声把画面缓缓带到寺门外", script.content)

    def test_auto_fix_issue_blocks_large_diff_by_safety_guard(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        with patch("api.server.llm_client.call_llm_json", return_value={
            "options": [
                {
                    "id": "A",
                    "title": "huge rewrite",
                    "strategy": "大幅重写",
                    "patched_text": "\n".join([f"重写段落 {i}" for i in range(1, 30)]),
                }
            ]
        }):
            response = self.client.post(
                f"/api/books/{self.book_id}/qa/issues/{issue_id}/auto-fix",
                json={"mode": "auto", "rerunQa": False, "maxDiffLines": 6, "maxLengthDeltaRatio": 0.4},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("safety guard", response.text)

    def test_auto_fix_issue_stops_after_recheck_failed_threshold(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        with Session() as session:
            issue = session.query(QAIssue).filter(QAIssue.issue_key == issue_id).first()
            issue.meta_info = json.dumps({"auto_fix_recheck_fail_count": 2}, ensure_ascii=False)
            session.commit()

        with patch("api.server.llm_client.call_llm_json", return_value={
            "options": [{"id": "A", "title": "ignored", "strategy": "ignored", "patched_text": self.fixed_excerpt}]
        }):
            response = self.client.post(
                f"/api/books/{self.book_id}/qa/issues/{issue_id}/auto-fix",
                json={"mode": "auto", "rerunQa": False, "stopAfterFailedRechecks": 2},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("failed recheck 2 times", response.text)

    def test_workflow_patch_persists_status_version_and_note(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]

        response = self.client.patch(
            f"/api/books/{self.book_id}/qa/issues/{issue_id}/workflow",
            json={
                "workflowStatus": "in_progress",
                "repairVersion": "script v2",
                "note": "manual follow-up in progress",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["issue"]["workflow_status"], "in_progress")
        self.assertEqual(payload["issue"]["repair_version"], "script v2")
        self.assertEqual(payload["issue"]["note"], "manual follow-up in progress")

        workbench = self.client.get(f"/api/books/{self.book_id}/qa/workbench")
        self.assertEqual(workbench.status_code, 200)
        issue = workbench.json()["episodes"][0]["issues"][0]
        self.assertEqual(issue["workflow_status"], "in_progress")
        self.assertEqual(issue["repair_version"], "script v2")
        self.assertEqual(issue["note"], "manual follow-up in progress")

    def test_rollback_restores_previous_script(self):
        sync_response = self.client.post(f"/api/books/{self.book_id}/qa/episodes/{self.episode}/sync")
        issue_id = sync_response.json()["issues"][0]["issue_id"]
        apply_response = self.client.post(
            f"/api/books/{self.book_id}/qa/issues/{issue_id}/apply-fix",
            json={
                "mode": "manual",
                "patchedText": self.fixed_excerpt,
                "changeReason": "manual patch",
                "rerunQa": False,
            },
        )
        fix_version_id = apply_response.json()["version"]["id"]

        rollback_response = self.client.post(
            f"/api/books/{self.book_id}/scripts/{self.episode}/versions/{fix_version_id}/rollback",
            json={"rerunQa": False},
        )
        self.assertEqual(rollback_response.status_code, 200)
        payload = rollback_response.json()
        self.assertEqual(payload["version"]["change_type"], "rollback")

        with Session() as session:
            script = session.query(Script).filter(Script.book_id == self.book_id, Script.episode == self.episode).first()

        self.assertEqual(script.content, self.original_script)


if __name__ == "__main__":
    unittest.main()
