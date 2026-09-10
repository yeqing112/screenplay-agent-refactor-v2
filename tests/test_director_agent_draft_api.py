import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core.agent_model_config import AGENT_MODEL_PROFILE_ID_KEY
from core.director_plan import build_director_plan
from models import Book, Session
from models.kv import KV


class DirectorAgentDraftApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            row = session.get(KV, AGENT_MODEL_PROFILE_ID_KEY)
            self.previous = row.value if row else None
            if row:
                row.value = "builtin-llm-env"
            else:
                session.add(KV(key=AGENT_MODEL_PROFILE_ID_KEY, value="builtin-llm-env"))
            book = Book(title="Agent draft API test", filename="agent-draft-api-test.txt")
            session.add(book)
            session.commit()
            self.book_id = book.id
        self.plan = build_director_plan(
            "检查项目状态", {"book_id": self.book_id, "section": f"storyboard-test-{uuid.uuid4().hex}"},
            {"items": ["只读测试证据"]}, [{"operation": "diagnose"}, {"operation": "draft_prompt"}],
        )

    def tearDown(self):
        with Session() as session:
            session.query(Book).filter_by(id=self.book_id).delete()
            row = session.get(KV, AGENT_MODEL_PROFILE_ID_KEY)
            if self.previous is None:
                session.delete(row)
            else:
                row.value = self.previous
            session.commit()

    def _preview(self):
        response = self.client.post("/api/agent/llm-drafts/preview", json={"objective": "检查项目状态", "plan": self.plan})
        self.assertEqual(response.status_code, 200)
        return response.json()["preview"]

    def test_preview_never_calls_llm_or_writes(self):
        with patch("api.director_agent_draft_api.llm_client.call_llm_json") as call:
            preview = self._preview()
        call.assert_not_called()
        self.assertIn("冻结证据包", preview["user_prompt"])
        self.assertNotIn("api_key", preview["model"])
        self.assertEqual(preview["evidence"]["evidence_snapshot"]["source"], "server_project_snapshot_v1")
        self.assertEqual(preview["evidence"]["evidence_snapshot"]["project"]["id"], self.book_id)

    def test_invoke_requires_two_explicit_consents(self):
        preview = self._preview()
        with patch("api.director_agent_draft_api.llm_client.call_llm_json") as call:
            response = self.client.post("/api/agent/llm-drafts/invoke", json={"plan": self.plan, "draftFingerprint": preview["draft_fingerprint"], "confirmed": True})
        self.assertEqual(response.status_code, 400)
        call.assert_not_called()

    def test_invoke_creates_candidate_only_and_deduplicates(self):
        preview = self._preview()
        response_payload = {"summary": "候选建议", "analysis": "只读分析", "recommended_steps": [], "risks": [], "requires_confirmation": False}
        request = {"plan": self.plan, "draftFingerprint": preview["draft_fingerprint"], "confirmed": True, "allowExternalCall": True}
        with patch("api.director_agent_draft_api.llm_client.call_llm_json", return_value=response_payload) as call:
            response = self.client.post("/api/agent/llm-drafts/invoke", json=request)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["llm_called"])
            deduped = self.client.post("/api/agent/llm-drafts/invoke", json=request)
        self.assertEqual(deduped.status_code, 200)
        self.assertTrue(deduped.json()["deduplicated"])
        self.assertEqual(call.call_count, 1)
        audit = self.client.get("/api/agent/audit", params={"bookId": self.book_id})
        self.assertEqual(audit.status_code, 200)
        entry = next(entry for entry in audit.json()["entries"] if entry["operation"] == "generate_llm_draft")
        handoff = self.client.get(f"/api/agent/audit/{entry['id']}/handoff-preview")
        self.assertEqual(handoff.status_code, 200)
        self.assertFalse(handoff.json()["mutated"])
        timeline = self.client.get("/api/agent/timeline", params={"bookId": self.book_id})
        self.assertEqual(timeline.status_code, 200)
        self.assertTrue(any(event["kind"] == "audit" for event in timeline.json()["events"]))
        session_id = entry["session_id"]
        state = self.client.get(f"/api/agent/sessions/{session_id}/state")
        self.assertEqual(state.status_code, 200)
        restored = state.json()
        self.assertEqual(restored["session"]["id"], session_id)
        self.assertTrue(any(message["role"] == "user" for message in restored["messages"]))
        self.assertTrue(any(message["role"] == "assistant" for message in restored["messages"]))
        self.assertIsNotNone(restored["plan"])
        self.assertEqual(restored["plan"]["plan_fingerprint"], preview["plan_fingerprint"])
        paused = self.client.post(f"/api/agent/sessions/{session_id}/pause")
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["status"], "paused")
        resumed = self.client.post(f"/api/agent/sessions/{session_id}/resume")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["status"], "awaiting_confirmation")

    def test_invoke_rejects_stale_preview(self):
        self._preview()
        with patch("api.director_agent_draft_api.llm_client.call_llm_json") as call:
            response = self.client.post("/api/agent/llm-drafts/invoke", json={"plan": self.plan, "draftFingerprint": "stale", "confirmed": True, "allowExternalCall": True})
        self.assertEqual(response.status_code, 409)
        call.assert_not_called()

    def test_failed_call_is_audited_and_never_retried_automatically(self):
        preview = self._preview()
        request = {"plan": self.plan, "draftFingerprint": preview["draft_fingerprint"], "confirmed": True, "allowExternalCall": True}
        with patch("api.director_agent_draft_api.llm_client.call_llm_json", side_effect=RuntimeError("provider unavailable")) as call:
            response = self.client.post("/api/agent/llm-drafts/invoke", json=request)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(call.call_count, 1)
        timeline = self.client.get("/api/agent/timeline", params={"bookId": self.book_id}).json()["events"]
        self.assertTrue(any(event.get("status") == "failed" for event in timeline))
