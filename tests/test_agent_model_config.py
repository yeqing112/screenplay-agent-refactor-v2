import unittest

from fastapi.testclient import TestClient

from api.server import app
from core.agent_model_config import AGENT_MODEL_PROFILE_ID_KEY, AGENT_THINKING_MODE_KEY, AGENT_VISION_ENABLED_KEY
from models import Session
from models.kv import KV


class AgentModelConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            row = session.get(KV, AGENT_MODEL_PROFILE_ID_KEY)
            self.previous = row.value if row else None
            self.previous_thinking = session.get(KV, AGENT_THINKING_MODE_KEY).value if session.get(KV, AGENT_THINKING_MODE_KEY) else None
            self.previous_vision = session.get(KV, AGENT_VISION_ENABLED_KEY).value if session.get(KV, AGENT_VISION_ENABLED_KEY) else None
            if row:
                session.delete(row)
                session.commit()

    def tearDown(self):
        with Session() as session:
            row = session.get(KV, AGENT_MODEL_PROFILE_ID_KEY)
            if row:
                session.delete(row)
            for key in (AGENT_THINKING_MODE_KEY, AGENT_VISION_ENABLED_KEY):
                policy_row = session.get(KV, key)
                if policy_row:
                    session.delete(policy_row)
            if self.previous is not None:
                session.add(KV(key=AGENT_MODEL_PROFILE_ID_KEY, value=self.previous))
            if self.previous_thinking is not None:
                session.add(KV(key=AGENT_THINKING_MODE_KEY, value=self.previous_thinking))
            if self.previous_vision is not None:
                session.add(KV(key=AGENT_VISION_ENABLED_KEY, value=self.previous_vision))
            session.commit()

    def test_empty_config_does_not_use_production_default(self):
        response = self.client.get("/api/agent/model-config")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["configured"])
        self.assertEqual(body["profile_id"], "")
        self.assertFalse(body["uses_production_default"])

    def test_agent_can_select_existing_llm_profile_without_changing_defaults(self):
        before = self.client.get("/api/model-registry/defaults").json()["defaults"]
        response = self.client.put(
            "/api/agent/model-config",
            json={"profileId": "builtin-llm-env"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["profile_id"], "builtin-llm-env")
        self.assertEqual(body["profile"]["capability"], "llm")
        after = self.client.get("/api/model-registry/defaults").json()["defaults"]
        self.assertEqual(before, after)

    def test_agent_config_never_returns_provider_key(self):
        response = self.client.put(
            "/api/agent/model-config",
            json={"profileId": "builtin-llm-env"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("api_key", response.json()["profile"])

    def test_agent_rejects_non_llm_profile(self):
        response = self.client.put(
            "/api/agent/model-config",
            json={"profile_id": "builtin-mock-image"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("LLM", response.json()["detail"])

    def test_agent_config_can_be_cleared(self):
        self.client.put("/api/agent/model-config", json={"profile_id": "builtin-llm-env"})
        response = self.client.put("/api/agent/model-config", json={"profile_id": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["configured"])

    def test_runtime_policy_is_independent_and_returned(self):
        response = self.client.put("/api/agent/model-config", json={
            "profile_id": "builtin-llm-env", "thinking": "enabled", "visionEnabled": True,
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["runtime_policy"], {"thinking": "enabled", "vision_enabled": True})
        registry = self.client.get("/api/model-registry/defaults").json()["defaults"]
        self.assertEqual(registry, self.client.get("/api/model-registry/defaults").json()["defaults"])
