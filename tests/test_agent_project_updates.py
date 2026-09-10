import unittest
import uuid

from fastapi.testclient import TestClient

from api.server import app
from core.agent_project_updates import derive_project_updates
from models import AgentProjectUpdate, Book, Session


class AgentProjectUpdatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_derivation_is_fact_based_and_deduplicable(self):
        evidence = {
            "scope": {"book_id": 1},
            "project": {"id": 1, "title": "测试项目"},
            "scripts": [{"episode": 1, "status": "ready"}],
            "shots": [{"shot_id": 3, "asset_status": "asset_pending", "prompt_state": {"static": True, "motion": False}}],
            "assets": {"characters": [], "locations": [{"id": 8, "name": "便利店", "asset_status": "pending"}], "props": []},
            "qa": {"issues": [{"id": 9, "type": "continuity", "title": "衔接冲突", "severity": "high", "status": "pending"}]},
            "tasks": {"recent": []},
        }
        first = derive_project_updates(evidence)
        second = derive_project_updates(evidence)
        self.assertTrue(any(item["type"] == "progress" for item in first))
        self.assertTrue(any(item["type"] == "issue" and item["severity"] == "blocking" for item in first))
        self.assertEqual([item["dedupe_key"] for item in first], [item["dedupe_key"] for item in second])
        self.assertTrue(all(item["evidence_fingerprint"] for item in first))

    def test_reconcile_is_idempotent_for_same_snapshot(self):
        with Session() as session:
            book = Book(title="主动汇报测试", filename=f"updates-{uuid.uuid4().hex}.txt")
            session.add(book)
            session.commit()
            book_id = book.id
        try:
            first = self.client.post("/api/agent/updates/reconcile", json={"bookId": book_id, "scope": {}})
            self.assertEqual(first.status_code, 200)
            self.assertGreater(first.json()["created_count"], 0)
            second = self.client.post("/api/agent/updates/reconcile", json={"bookId": book_id, "scope": {}})
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["created_count"], 0)
            self.assertGreater(second.json()["reused_count"], 0)
            listing = self.client.get("/api/agent/updates", params={"bookId": book_id})
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(len(listing.json()["updates"]), first.json()["created_count"])
        finally:
            with Session() as session:
                session.query(AgentProjectUpdate).filter_by(book_id=book_id).delete()
                session.query(Book).filter_by(id=book_id).delete()
                session.commit()

    def test_update_stream_is_read_only_and_emits_sse_snapshot(self):
        with Session() as session:
            book = Book(title="SSE 测试", filename=f"sse-{uuid.uuid4().hex}.txt")
            session.add(book)
            session.flush()
            row = AgentProjectUpdate(
                book_id=book.id, type="progress", severity="info", title="进度", message="已更新",
                source_refs="[]", evidence_fingerprint="e1", action_proposal="{}", requires_confirmation=0,
                status="unread", dedupe_key=f"sse-{uuid.uuid4().hex}",
            )
            session.add(row)
            session.commit()
            book_id, update_id = book.id, row.id
        try:
            response = self.client.get(f"/api/agent/updates/stream?bookId={book_id}&sinceId=0&waitMs=0")
            self.assertEqual(response.status_code, 200)
            self.assertIn("event: project_update", response.text)
            self.assertIn(f"id: {update_id}", response.text)
        finally:
            with Session() as session:
                session.query(AgentProjectUpdate).filter_by(book_id=book_id).delete()
                session.query(Book).filter_by(id=book_id).delete()
                session.commit()
