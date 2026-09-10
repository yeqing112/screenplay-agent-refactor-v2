import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import _qa_location_line_range_matches_scene_section, app
from core.decision_draft import build_decision_draft_prompt, validate_decision_draft
from models import DecisionPacketRecord, QAIssue, QAResult, Script, Session, init_db


class DecisionPacketLlmDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 991119
        with Session() as session:
            session.query(DecisionPacketRecord).filter_by(book_id=self.book_id).delete()
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/decision-packets/draft", json={
            "domain": "storyboard",
            "scope": {"episode": 1, "shot_id": 7},
            "evidence": [{"id": "shot:7", "tier": "source_text", "summary": "角色停在门口。", "version": "v1"}],
            "allowedOperations": ["propose_duration_change", "request_missing_information"],
        })
        self.assertEqual(response.status_code, 200)
        self.packet = response.json()["packet"]

    def test_preview_does_not_call_llm(self):
        with patch("api.server.llm_client.call_llm_json") as mock_call:
            response = self.client.get(
                f"/api/books/{self.book_id}/decision-packets/{self.packet['id']}/llm-draft-preview",
                params={"packetFingerprint": self.packet["packet_fingerprint"]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["llm_called"])
        self.assertIn("证据包", response.json()["prompt"])
        mock_call.assert_not_called()

    def test_real_call_requires_explicit_external_consent(self):
        with patch("api.server.llm_client.call_llm_json") as mock_call:
            response = self.client.post(
                f"/api/books/{self.book_id}/decision-packets/{self.packet['id']}/llm-draft",
                json={"packetFingerprint": self.packet["packet_fingerprint"], "confirmed": True},
            )
        self.assertEqual(response.status_code, 409)
        mock_call.assert_not_called()

    def test_real_call_rejects_a_second_request_while_first_is_in_progress(self):
        with Session() as session:
            row = session.query(DecisionPacketRecord).filter_by(id=self.packet["id"]).first()
            row.model_info = json.dumps({
                "mode": "explicit_llm_draft",
                "llm_generated": False,
                "llm_draft_in_progress": True,
                "llm_draft_attempt_id": "existing-attempt",
            })
            row.status = "llm_draft_in_progress"
            session.commit()

        with patch("api.server.llm_client.call_llm_json") as mock_call:
            response = self.client.post(
                f"/api/books/{self.book_id}/decision-packets/{self.packet['id']}/llm-draft",
                json={"packetFingerprint": self.packet["packet_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("in progress", response.json()["detail"])
        mock_call.assert_not_called()

    def test_real_call_persists_only_a_reviewable_proposal(self):
        model_result = {
            "decision": "ready_for_review", "confidence": 0.72,
            "evidence": [{"id": "shot:7", "reason": "动作单一且明确"}],
            "unknowns": [], "conflicts": [],
            "proposals": [{"operation": "propose_duration_change", "summary": "建议人工复核时长", "affected_fields": ["duration"], "proposed_content": "不应在非剧本操作中保存", "requires_human_review": False}],
            "human_confirmation_required": False,
        }
        with patch("api.server.llm_client.call_llm_json", return_value=model_result) as mock_call:
            response = self.client.post(
                f"/api/books/{self.book_id}/decision-packets/{self.packet['id']}/llm-draft",
                json={"packetFingerprint": self.packet["packet_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["llm_called"])
        self.assertTrue(response.json()["packet"]["proposal"]["human_confirmation_required"])
        self.assertEqual(response.json()["packet"]["proposal"]["proposals"][0]["proposed_content"], "")
        self.assertFalse(response.json()["domain_write_performed"])
        mock_call.assert_called_once()

    def test_script_qa_packet_contains_script_and_qa_evidence(self):
        issue_key = "decision-packet-qa-issue"
        with Session() as session:
            session.query(QAIssue).filter_by(book_id=self.book_id, issue_key=issue_key).delete()
            session.query(QAResult).filter_by(book_id=self.book_id, episode=2).delete()
            session.query(Script).filter_by(book_id=self.book_id, episode=2).delete()
            session.add(Script(book_id=self.book_id, episode=2, content="雨夜里，她将账本藏进抽屉。"))
            session.add(QAResult(book_id=self.book_id, episode=2, result="线索动机需要补充。"))
            session.add(QAIssue(book_id=self.book_id, episode=2, issue_key=issue_key, issue_type="motivation", title="动机不足", description="账本来源未交代", source_excerpt="将账本藏进抽屉"))
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/qa/issues/{issue_key}/decision-packet/draft")
        self.assertEqual(response.status_code, 200)
        packet = response.json()["packet"]
        self.assertEqual(packet["domain"], "script")
        self.assertEqual(packet["scope"]["issue_key"], issue_key)
        self.assertTrue(any(item["tier"] == "source_text" for item in packet["evidence"]))
        self.assertTrue(any(item["id"].startswith("qa-issue:") for item in packet["evidence"]))
        self.assertEqual(packet["scope"]["proposal_contract"]["kind"], "script_qa_single_issue_local_revision_v1")
        self.assertTrue(any(item["id"] == "production-skill:script" for item in packet["evidence"]))

    def test_script_local_contract_strips_unsafe_whole_episode_candidate(self):
        packet = {
            "domain": "script",
            "scope": {
                "proposal_contract": {
                    "kind": "script_qa_single_issue_local_revision_v1",
                    "target_excerpt_is_precise_span": False,
                    "max_replacement_chars": 0,
                }
            },
            "evidence": [{"id": "script:1", "tier": "source_text", "summary": "原剧本", "version": "v1"}],
            "allowed_operations": ["propose_script_revision", "request_missing_information"],
        }
        value = {
            "decision": "ready_for_review", "confidence": 0.8,
            "evidence": [], "unknowns": [], "conflicts": [],
            "proposals": [{
                "operation": "propose_script_revision",
                "summary": "错误地尝试整集重写",
                "affected_fields": ["content"],
                "proposed_content": "这是不应被接受的整集替换文本。",
            }],
            "human_confirmation_required": True,
        }

        prompt = build_decision_draft_prompt(packet)
        draft = validate_decision_draft(value, packet)

        self.assertIn("proposed_content 必须为空", prompt)
        self.assertEqual(draft["proposals"][0]["proposed_content"], "")
        self.assertTrue(any("精确替换区间" in item for item in draft["conflicts"]))

    def test_propose_edits_validates_anchored_operation_batch(self):
        packet = {
            "domain": "script",
            "scope": {"beat_ids": ["ep1-s2-b11", "ep1-s2-b12"], "proposal_contract": {"kind": "script_qa_single_issue_local_revision_v1", "target_excerpt_is_precise_span": True, "target_line_range": [1, 2], "max_replacement_chars": 1000}},
            "evidence": [{"id": "script:1", "tier": "source_text", "summary": "剧本", "version": "v1"}],
            "allowed_operations": ["propose_edits", "propose_script_revision", "request_missing_information"],
        }
        value = {
            "decision": "ready_for_review", "confidence": 0.8, "evidence": [], "unknowns": [], "conflicts": [],
            "proposals": [{
                "operation": "propose_edits", "summary": "锚定两处编辑", "affected_fields": ["content"],
                "edits": [
                    {"op": "replace", "beat_id": "ep1-s2-b11", "new_text": "新文本"},
                    {"op": "insert_after", "beat_id": "ep1-s2-b12", "new_text": "插入行"},
                    {"op": "replace", "beat_id": "ep1-s9-b01", "new_text": "未授权beat"},
                    {"op": "replace", "beat_id": "ep1-s2-b11", "new_text": ""},
                ],
                "proposed_content": "",
            }],
            "human_confirmation_required": True,
        }
        draft = validate_decision_draft(value, packet)
        edits = draft["proposals"][0]["edits"]
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0]["beat_id"], "ep1-s2-b11")
        self.assertEqual(edits[1]["op"], "insert_after")
        self.assertTrue(any("未授权 beat" in item for item in draft["conflicts"]))
        self.assertTrue(any("缺 new_text" in item for item in draft["conflicts"]))

    def test_target_resolution_contract_accepts_only_frozen_candidate_span(self):
        packet = {
            "domain": "script",
            "scope": {"proposal_contract": {
                "kind": "script_qa_target_resolution_v1",
                "candidate_spans": [{"line_start": 80, "line_end": 120, "source_fingerprint": "scene-2-v1"}],
            }},
            "evidence": [{"id": "script:1", "tier": "source_text", "summary": "剧本", "version": "v1"}],
            "allowed_operations": ["propose_repair_target", "request_missing_information"],
        }
        value = {
            "decision": "ready_for_review", "confidence": 0.8, "evidence": [], "unknowns": [], "conflicts": [],
            "proposals": [{
                "operation": "propose_repair_target", "summary": "选择场景二末尾", "affected_fields": [],
                "proposed_content": "", "target_span": {"line_start": 101, "line_end": 118, "source_fingerprint": "scene-2-v1"},
            }], "human_confirmation_required": True,
        }
        draft = validate_decision_draft(value, packet)
        self.assertEqual(draft["proposals"][0]["target_span"]["line_start"], 101)

        value["proposals"][0]["target_span"]["line_start"] = 79
        unsafe = validate_decision_draft(value, packet)
        self.assertEqual(unsafe["proposals"][0]["target_span"], {})
        self.assertTrue(any("候选定位" in item for item in unsafe["conflicts"]))

    def test_qa_line_range_must_match_declared_scene_section(self):
        script = "\n".join([
            "## 场景1：门外", "林晚推门。",
            "## 场景2：大厅", "三人进入大厅。",
            "## 场景3：阁楼", "三人登上阁楼。",
        ])

        self.assertFalse(_qa_location_line_range_matches_scene_section(script, "场景2末尾至场景3开头", 1, 2))
        self.assertTrue(_qa_location_line_range_matches_scene_section(script, "场景2", 3, 4))

    def test_qa_line_range_must_honour_scene_start_and_end_qualifiers(self):
        script = "\n".join([
            "## 场景1：门外", "林晚推门。", "她停在门口。", "风吹动信封。",
            "## 场景2：大厅", "老周整理工具箱。", "林远避开视线。", "林晚发现新刮痕。", "她查看遗产清单。",
            "老周挡住楼梯。", "林远催促离开。", "林晚回望钟面。", "三人离开钟楼。",
        ])

        # Same scene is insufficient: the first two body lines are not the
        # declared end beat of scene 2.
        self.assertFalse(_qa_location_line_range_matches_scene_section(script, "场景2末尾", 6, 7))
        self.assertTrue(_qa_location_line_range_matches_scene_section(script, "场景2末尾", 11, 12))

    def test_target_resolution_forward_creates_local_revision_packet_only_for_strict_subrange(self):
        issue_key = "forward-local-revision-qa"
        script = "\n".join([
            "## 场景1：门外", "林晚推门。", "她停下。",
            "## 场景2：大厅", "老周整理工具箱。", "林远避开视线。", "林晚发现新刮痕。", "她查看清单。", "老周挡住楼梯。", "林远催促离开。", "林晚回望钟面。", "三人离开钟楼。",
        ])
        with Session() as session:
            session.query(DecisionPacketRecord).filter_by(book_id=self.book_id, domain="script").delete()
            session.query(QAIssue).filter_by(book_id=self.book_id, issue_key=issue_key).delete()
            session.query(QAResult).filter_by(book_id=self.book_id, episode=1).delete()
            session.query(Script).filter_by(book_id=self.book_id, episode=1).delete()
            session.add(Script(book_id=self.book_id, episode=1, content=script))
            session.add(QAResult(book_id=self.book_id, episode=1, result="{}"))
            session.add(QAIssue(book_id=self.book_id, episode=1, issue_key=issue_key, issue_type="hook", title="结尾钩子", description="增强钩子", script_section="场景2末尾"))
            session.commit()

        target = self.client.post(f"/api/books/{self.book_id}/qa/issues/{issue_key}/decision-packet/draft").json()["packet"]
        self.assertEqual(target["scope"]["proposal_contract"]["kind"], "script_qa_target_resolution_v1")
        candidate = target["scope"]["proposal_contract"]["candidate_spans"][0]
        sub = {"line_start": candidate["line_start"] + 1, "line_end": candidate["line_end"] - 1, "source_fingerprint": candidate["source_fingerprint"]}

        ok_response = self.client.post(
            f"/api/books/{self.book_id}/qa/issues/{issue_key}/target-resolution/{target['id']}/revision-draft",
            json={"packetFingerprint": target["packet_fingerprint"], "targetSpan": sub},
        )
        self.assertEqual(ok_response.status_code, 200)
        local = ok_response.json()["packet"]
        self.assertEqual(local["scope"]["proposal_contract"]["kind"], "script_qa_single_issue_local_revision_v1")
        self.assertTrue(local["scope"]["proposal_contract"]["target_excerpt_is_precise_span"])
        self.assertEqual(local["scope"]["proposal_contract"]["target_line_range"], [sub["line_start"], sub["line_end"]])
        self.assertTrue(local["scope"]["proposal_contract"]["target_span_fingerprint"])
        self.assertIn("propose_script_revision", local["allowed_operations"])

        whole = {"line_start": candidate["line_start"], "line_end": candidate["line_end"], "source_fingerprint": candidate["source_fingerprint"]}
        reject_response = self.client.post(
            f"/api/books/{self.book_id}/qa/issues/{issue_key}/target-resolution/{target['id']}/revision-draft",
            json={"packetFingerprint": target["packet_fingerprint"], "targetSpan": whole},
        )
        self.assertEqual(reject_response.status_code, 409)

    def test_prompt_guides_anchored_edits_when_packet_has_beat_ids(self):
        packet = {
            "domain": "script",
            "scope": {"beat_ids": ["ep1-s2-b11"], "proposal_contract": {"kind": "script_qa_single_issue_local_revision_v1", "target_excerpt_is_precise_span": True, "target_line_range": [1, 1], "max_replacement_chars": 1000}},
            "evidence": [{"id": "script:1", "tier": "source_text", "summary": "剧本", "version": "v1"}],
            "allowed_operations": ["propose_edits", "propose_script_revision", "request_missing_information"],
        }
        prompt = build_decision_draft_prompt(packet)
        self.assertIn("propose_edits", prompt)
        self.assertIn("beat_id", prompt)


if __name__ == "__main__":
    unittest.main()
