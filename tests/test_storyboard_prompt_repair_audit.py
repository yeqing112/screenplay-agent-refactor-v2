import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import server as server_module
from api.server import app
from models import AgentAuditLog, AgentPlan, AgentSession, Session
from tests import test_storyboard_prompt_compile as storyboard_prompt_compile_tests


class _StoryboardRepairAuditBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storyboard_prompt_compile_tests.StoryboardPromptCompileTests.setUpClass()
        cls.client = storyboard_prompt_compile_tests.ConfirmedMockCompileClient(app)

    def setUp(self):
        self.base = storyboard_prompt_compile_tests.StoryboardPromptCompileTests()
        self.base.setUp()

    def tearDown(self):
        self.base.tearDown()

    def _create_packet(self):
        response = self.client.post(
            f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/prompt-drafts"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["packet"]

    def _seed_agent_audit(self, episode, shot_id, summary, analysis):
        with Session() as s:
            sess = AgentSession(
                book_id=self.base.book_id,
                user_prompt="test",
                status="completed",
                skill_id="continuity",
                skill_version="v1",
            )
            s.add(sess)
            s.flush()
            plan = AgentPlan(
                session_id=sess.id,
                plan_fingerprint="plan-fp-test",
                objective="continuity",
                scope=json.dumps(
                    {
                        "book_id": self.base.book_id,
                        "episode": episode,
                        "shot_id": str(shot_id),
                    },
                    ensure_ascii=False,
                ),
                evidence_snapshot="{}",
                steps="[]",
                status="accepted",
            )
            s.add(plan)
            s.flush()
            audit = AgentAuditLog(
                session_id=sess.id,
                plan_id=plan.id,
                step_index=0,
                operation="generate_llm_draft",
                tool_tier="B",
                evidence_fingerprint="evidence-fp-test",
                plan_fingerprint="plan-fp-test",
                model_info="{}",
                request_payload="{}",
                response_payload=json.dumps(
                    {"summary": summary, "analysis": analysis}, ensure_ascii=False
                ),
                confirmation_user="test",
                confirmation_at=__import__("datetime").datetime.utcnow(),
                result_status="succeeded",
                result_message=summary,
            )
            s.add(audit)
            s.commit()
            s.refresh(audit)
            return audit.id


class StoryboardPromptRepairAuditTests(_StoryboardRepairAuditBase):
    def test_compiler_forwards_revision_evidence_to_llm_and_audit(self):
        captured = {}

        def fake_llm(prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return {}

        repair_request = {
            "goal": "rewrite the motion prompt to inherit the preceding end state",
            "continuity_advisory": {
                "audit_id": 31,
                "summary": "The preceding shot already contains the bell event.",
                "analysis": "The next shot must treat it as a starting state.",
            },
        }
        with patch.object(server_module.llm_client, "call_llm_json", side_effect=fake_llm):
            server_module._call_storyboard_prompt_compiler(
                {
                    "scene_name": "test scene",
                    "bound_assets": [],
                    "required_used_assets": [],
                    "motion_contract": {},
                    "repair_request": repair_request,
                },
                audit_callback=lambda _: None,
                audit_extra={"mode": "prompt_compile_revision"},
            )

        self.assertIn("REVISION MODE", captured["system"])
        self.assertIn("revision_disposition", captured["system"])
        self.assertEqual(captured["audit_repair_request"], repair_request)
        self.assertEqual(captured["audit_extra"]["mode"], "prompt_compile_revision")

    def test_revision_path_rejects_candidate_without_revision_disposition(self):
        packet = self._create_packet()
        audit_id = self._seed_agent_audit(
            self.base.episode,
            self.base.shot_id,
            "shot3 needs to inherit wind chime ring",
            "shot2 already ended with wind chime; shot3 should inherit it as start state.",
        )

        bad_candidate = dict(self.base._valid_llm_payload())

        def fake_compile(context, *, audit_callback=None, audit_extra=None):
            if audit_callback is not None:
                audit_callback(
                    {
                        "vendor_model": "fake-model",
                        "vendor_host": "fake-host",
                        "profile_id": "fake-profile",
                        "system_prompt_sha256": "a" * 32,
                        "system_prompt_length": 100,
                        "user_prompt_sha256": "b" * 32,
                        "user_prompt_length": 200,
                        "request_messages_sha256": "c" * 32,
                        "has_repair_request": True,
                        "repair_request_sha256": "d" * 32,
                        "repair_request_length": 50,
                        "response_sha256": "e" * 32,
                        "response_length": 512,
                        "http_status": 200,
                        "parse_ok": True,
                    }
                )
            return bad_candidate

        with patch.object(server_module, "_call_storyboard_prompt_compiler", side_effect=fake_compile):
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/prompt-drafts/{packet['id']}/llm",
                json={
                    "packetFingerprint": packet["packet_fingerprint"],
                    "confirmed": True,
                    "allowExternalCall": True,
                    "continuityRevision": True,
                    "agentAuditId": audit_id,
                },
            )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertIn("revision_disposition", body["detail"])
        packets = self.client.get(
            f"/api/books/{self.base.book_id}/decision-packets?domain=prompt"
        ).json()["items"]
        audited = next(item for item in packets if item["id"] == packet["id"])
        self.assertEqual(
            audited["model_info"]["last_llm_attempt"]["outcome"],
            "revision_disposition_missing",
        )
        self.assertIn("has_repair_request", audited["model_info"]["llm_request_audit"])

    def test_revision_path_rejects_candidate_that_kept_previous(self):
        packet = self._create_packet()
        audit_id = self._seed_agent_audit(
            self.base.episode,
            self.base.shot_id,
            "shot3 needs to inherit wind chime ring",
            "shot2 already ended with wind chime.",
        )

        candidate = dict(self.base._valid_llm_payload())
        candidate["revision_disposition"] = {
            "goal_ack": True,
            "advisory_audit_id": audit_id,
            "advisory_summary_reflected": True,
            "previous_candidate_kept": True,
        }
        with patch.object(server_module, "_call_storyboard_prompt_compiler", return_value=candidate):
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/prompt-drafts/{packet['id']}/llm",
                json={
                    "packetFingerprint": packet["packet_fingerprint"],
                    "confirmed": True,
                    "allowExternalCall": True,
                    "continuityRevision": True,
                    "agentAuditId": audit_id,
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("未改写", response.json()["detail"])

    def test_revision_path_persists_audit_summary_on_success(self):
        packet = self._create_packet()
        audit_id = self._seed_agent_audit(
            self.base.episode,
            self.base.shot_id,
            "shot3 needs to inherit wind chime ring",
            "shot2 already ended with wind chime.",
        )

        candidate = dict(self.base._valid_llm_payload())
        candidate["revision_disposition"] = {
            "goal_ack": True,
            "advisory_audit_id": audit_id,
            "advisory_summary_reflected": True,
            "previous_candidate_kept": False,
        }
        captured = {}

        def fake_compile(context, *, audit_callback=None, audit_extra=None):
            captured["revision_mode"] = bool(context.get("repair_request"))
            captured["audit_extra"] = audit_extra
            if audit_callback is not None:
                audit_callback(
                    {
                        "vendor_model": "fake-model",
                        "vendor_host": "fake-host",
                        "profile_id": "fake-profile",
                        "system_prompt_sha256": "a" * 32,
                        "system_prompt_length": 100,
                        "user_prompt_sha256": "b" * 32,
                        "user_prompt_length": 200,
                        "request_messages_sha256": "c" * 32,
                        "has_repair_request": True,
                        "repair_request_sha256": "d" * 32,
                        "repair_request_length": 50,
                        "response_sha256": "e" * 32,
                        "response_length": 1024,
                        "http_status": 200,
                        "parse_ok": True,
                        "extra": {"mode": "prompt_compile_revision"},
                    }
                )
            return candidate

        with patch.object(server_module, "_call_storyboard_prompt_compiler", side_effect=fake_compile):
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/prompt-drafts/{packet['id']}/llm",
                json={
                    "packetFingerprint": packet["packet_fingerprint"],
                    "confirmed": True,
                    "allowExternalCall": True,
                    "continuityRevision": True,
                    "agentAuditId": audit_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["llm_called"])
        self.assertTrue(captured["revision_mode"])
        self.assertEqual(captured["audit_extra"]["continuity_revision"], True)
        packets = self.client.get(
            f"/api/books/{self.base.book_id}/decision-packets?domain=prompt"
        ).json()["items"]
        audited = next(item for item in packets if item["id"] == packet["id"])
        audit_summary = audited["model_info"]["llm_request_audit"]
        self.assertTrue(audit_summary["has_repair_request"])
        self.assertEqual(audit_summary["last_http_status"], 200)
        self.assertEqual(audit_summary["vendor_models"], ["fake-model"])
        self.assertEqual(audit_summary["last_parse_ok"], True)
        self.assertEqual(audited["model_info"]["continuity_revision"], True)
        self.assertEqual(audited["model_info"]["source_agent_audit_id"], audit_id)


if __name__ == "__main__":
    unittest.main()
