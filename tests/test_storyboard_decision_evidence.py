import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import init_db


class StoryboardDecisionPacketEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_storyboard_decision_packet_includes_executability_evidence(self):
        response = self.client.post("/api/books/990309/storyboard/1/16/decision-packet/draft")
        self.assertEqual(response.status_code, 200)
        packet = response.json()["packet"]
        evidence = packet.get("evidence") or []
        exec_entries = [item for item in evidence if str(item.get("id") or "").startswith("executability:")]
        self.assertEqual(len(exec_entries), 1, "executability evidence must be present")
        summary = json.loads(exec_entries[0].get("summary") or "{}")
        self.assertIn("status", summary)
        self.assertIn("action_count", summary)
        self.assertIn("recommended_max_actions", summary)
        self.assertIn("findings", summary)
        self.assertIn("suggestions", summary)


if __name__ == "__main__":
    unittest.main()
