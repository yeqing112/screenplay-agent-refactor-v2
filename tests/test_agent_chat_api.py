import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import AgentAuditLog, AgentMessage, AgentPlan, AgentSession, Book, Session


class AgentChatApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="自由对话测试", filename=f"chat-{uuid.uuid4().hex}.txt")
            session.add(book)
            session.commit()
            self.book_id = book.id

    def tearDown(self):
        with Session() as session:
            session_ids = session.query(AgentSession.id).filter_by(book_id=self.book_id)
            session.query(AgentAuditLog).filter(AgentAuditLog.session_id.in_(session_ids)).delete(synchronize_session=False)
            session.query(AgentMessage).filter(AgentMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            session.query(AgentPlan).filter(AgentPlan.session_id.in_(session_ids)).delete(synchronize_session=False)
            session.query(AgentSession).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete()
            session.commit()

    def test_read_only_chat_replies_without_preview_or_confirmation(self):
        with patch("api.director_agent_draft_api.get_agent_model_profile_for_invocation", return_value=None), patch("api.director_agent_draft_api.llm_client.call_llm_json") as call:
            response = self.client.post("/api/agent/chat", json={"bookId": self.book_id, "message": "请告诉我当前项目下一步做什么"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["requires_confirmation"])
        self.assertFalse(payload["llm_called"])
        self.assertIn("当前最值得关注", payload["message"]["content"])
        call.assert_not_called()

    def test_model_action_is_returned_as_proposal_only(self):
        profile = {"id": "agent-test", "provider": "test", "model_name": "chat"}
        model_result = {
            "reply": "我已经准备好提交视频，但需要你确认。",
            "intent": "action_proposal",
            "requires_confirmation": True,
            "action_proposal": {"operation": "video_generation", "summary": "提交当前镜头视频", "impact": "会产生外部费用"},
        }
        with patch("api.director_agent_draft_api.get_agent_model_profile_for_invocation", return_value=profile), patch("api.director_agent_draft_api.llm_client.call_llm_json", return_value=model_result):
            response = self.client.post("/api/agent/chat", json={"bookId": self.book_id, "message": "帮我提交视频"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["requires_confirmation"])
        self.assertEqual(payload["action_proposal"]["operation"], "video_generation")
        self.assertTrue(payload["mutated"])
        with Session() as session:
            current = session.get(AgentSession, payload["session_id"])
            self.assertIsNotNone(current)
            self.assertEqual(current.book_id, self.book_id)
            self.assertEqual(current.status, "awaiting_confirmation")

    def test_action_confirmation_records_handoff_without_executing_tool(self):
        profile = {"id": "agent-test", "provider": "test", "model_name": "chat"}
        model_result = {
            "reply": "可以提交视频，但需要你确认。",
            "intent": "action_proposal",
            "requires_confirmation": True,
            "action_proposal": {"operation": "video_generation", "summary": "提交当前镜头视频", "impact": "会产生外部费用"},
        }
        with patch("api.director_agent_draft_api.get_agent_model_profile_for_invocation", return_value=profile), patch("api.director_agent_draft_api.llm_client.call_llm_json", return_value=model_result):
            response = self.client.post("/api/agent/chat", json={"bookId": self.book_id, "message": "帮我提交视频", "scope": {"section": "storyboard", "shot_id": 3}})
        self.assertEqual(response.status_code, 200)
        audit_id = response.json()["audit_id"]
        confirmed = self.client.post(f"/api/agent/audit/{audit_id}/handoff-confirm")
        self.assertEqual(confirmed.status_code, 200)
        payload = confirmed.json()
        self.assertEqual(payload["handoff"]["section"], "storyboard")
        self.assertEqual(payload["handoff"]["shot_id"], 3)
        self.assertTrue(payload["mutated"])
        with Session() as session:
            audit = session.get(AgentAuditLog, audit_id)
            self.assertEqual(audit.result_status, "handoff_confirmed")
            self.assertEqual(audit.confirmation_user, "local-user")
            current = session.get(AgentSession, response.json()["session_id"])
            self.assertEqual(current.status, "accepted")
        repeated = self.client.post(f"/api/agent/audit/{audit_id}/handoff-confirm")
        self.assertEqual(repeated.status_code, 200)

    def test_non_action_chat_cannot_be_confirmed(self):
        with patch("api.director_agent_draft_api.get_agent_model_profile_for_invocation", return_value=None):
            response = self.client.post("/api/agent/chat", json={"bookId": self.book_id, "message": "当前进度如何"})
        self.assertEqual(response.status_code, 200)
        rejected = self.client.post(f"/api/agent/audit/{response.json()['audit_id']}/handoff-confirm")
        self.assertEqual(rejected.status_code, 409)

    def test_action_confirmation_rejects_changed_evidence(self):
        profile = {"id": "agent-test", "provider": "test", "model_name": "chat"}
        model_result = {
            "reply": "可以提交视频，但需要你确认。",
            "intent": "action_proposal",
            "requires_confirmation": True,
            "action_proposal": {"operation": "video_generation", "summary": "提交当前镜头视频"},
        }
        with patch("api.director_agent_draft_api.get_agent_model_profile_for_invocation", return_value=profile), patch("api.director_agent_draft_api.llm_client.call_llm_json", return_value=model_result):
            response = self.client.post("/api/agent/chat", json={"bookId": self.book_id, "message": "提交视频"})
        audit_id = response.json()["audit_id"]
        with patch("api.director_agent_draft_api.build_project_evidence", return_value={"scope": {"book_id": self.book_id}, "changed": True}):
            rejected = self.client.post(f"/api/agent/audit/{audit_id}/handoff-confirm")
        self.assertEqual(rejected.status_code, 409)
        with Session() as session:
            self.assertEqual(session.get(AgentAuditLog, audit_id).result_status, "expired")
