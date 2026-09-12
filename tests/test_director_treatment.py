import unittest
import json

from fastapi.testclient import TestClient
from unittest.mock import patch

from core.director_treatment import build_shadow_treatment
from api.server import app
from models import Book, DecisionPacketRecord, DirectorTreatment, Script, Session, VisualMakeup, init_db


class DirectorTreatmentShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            self.book = Book(title="Treatment test", filename="treatment-test.txt", status="imported")
            session.add(self.book)
            session.flush()
            session.add(Script(book_id=self.book.id, episode=1, content=json.dumps({
                "scenes": [{"name": "办公室门口", "beats": [
                    {"id": "B01", "type": "obstacle", "event": "秘书挡住去路"},
                    {"id": "B02", "type": "decision", "event": "来客继续前行"},
                ]}],
            }, ensure_ascii=False)))
            session.add(VisualMakeup(book_id=self.book.id, episode=1, character_name="来客"))
            session.commit()
            self.book_id = self.book.id

    def tearDown(self):
        with Session() as session:
            session.query(DecisionPacketRecord).filter_by(book_id=self.book_id, domain="director_treatment").delete()
            session.query(DirectorTreatment).filter_by(book_id=self.book_id).delete()
            session.query(VisualMakeup).filter_by(book_id=self.book_id).delete()
            session.query(Script).filter_by(book_id=self.book_id).delete()
            session.query(Book).filter_by(id=self.book_id).delete()
            session.commit()

    def test_builds_independent_treatment_from_scene_beats(self):
        treatment = build_shadow_treatment(
            scene={
                "name": "办公室门口",
                "beats": [
                    {"id": "B01", "type": "obstacle", "event": "秘书挡住去路"},
                    {"id": "B02", "type": "decision", "event": "来客无视阻拦继续前行"},
                ],
            },
            characters=[
                {"id": "CHAR_A", "name": "来客", "goal": "见到董事长"},
                {"id": "CHAR_B", "name": "秘书", "goal": "维持门禁"},
            ],
            source_script_revision="script-v1",
        )

        self.assertEqual(treatment["status"], "draft")
        self.assertEqual(treatment["model_info"]["llm_called"], False)
        self.assertEqual([beat["beat_id"] for beat in treatment["beat_map"]], ["B01", "B02"])
        self.assertEqual(treatment["character_intents"]["CHAR_A"]["goal"], "见到董事长")
        self.assertTrue(treatment["prompt_fingerprint"])

    def test_treatment_preserves_canonical_script_ir_beat_ids(self):
        treatment = build_shadow_treatment(
            scene={"name": "门厅", "beats": [{"beat_id": "E02_SC001_B07", "type": "action", "event": "停下"}]},
        )
        self.assertEqual(treatment["beat_map"][0]["beat_id"], "E02_SC001_B07")

    def test_llm_candidate_merges_intents_without_overwriting_identity(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={}).json()
        character_id = next(iter(preview["treatment"]["character_intents"]))
        baseline_name = preview["treatment"]["character_intents"][character_id]["name"]
        candidate = {
            "character_intents": {character_id: {"goal": "新目标"}},
            "beat_map": preview["treatment"]["beat_map"],
            "dramatic_objective": "目标",
            "audience_question": "问题",
            "visual_strategy": "空间",
        }
        from api.director_treatment_api import _validate_llm_candidate
        normalized = _validate_llm_candidate(candidate, preview["treatment"])
        self.assertEqual(normalized["character_intents"][character_id]["name"], baseline_name)
        self.assertEqual(normalized["character_intents"][character_id]["goal"], "新目标")

    def test_same_evidence_is_stable_and_does_not_invent_assets(self):
        scene = {"name": "空房间", "beats": [{"id": "B01", "type": "setup", "event": "人物停在门边"}]}
        first = build_shadow_treatment(scene=scene)
        second = build_shadow_treatment(scene=scene)
        self.assertEqual(first["prompt_fingerprint"], second["prompt_fingerprint"])
        self.assertEqual(first["character_intents"], {})
        self.assertEqual(first["unknowns"], [])

    def test_preview_is_read_only_by_default_and_persist_is_idempotent(self):
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={
            "sceneName": "办公室门口",
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["llm_called"])
        self.assertFalse(payload["mutated"])
        self.assertIsNone(payload["persisted_draft_id"])
        self.assertEqual(payload["treatment"]["status"], "draft")

        first = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={
            "sceneName": "办公室门口", "persist": True,
        }).json()
        second = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={
            "sceneName": "办公室门口", "persist": True,
        }).json()
        self.assertTrue(first["mutated"])
        self.assertEqual(first["persisted_draft_id"], second["persisted_draft_id"])
        self.assertFalse(second["llm_called"])

    def test_preview_scopes_character_evidence_to_declared_scene_participants(self):
        with Session() as session:
            session.add(VisualMakeup(book_id=self.book_id, episode=1, character_name="旁观者"))
            row = session.query(Script).filter_by(book_id=self.book_id, episode=1).one()
            payload = json.loads(row.content)
            payload["scenes"][0]["participants"] = ["来客"]
            row.content = json.dumps(payload, ensure_ascii=False)
            session.commit()
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={})
        self.assertEqual(preview.status_code, 200)
        names = [item["name"] for item in preview.json()["evidence"]["characters"]]
        self.assertEqual(names, ["来客"])

    def test_llm_draft_requires_confirmation_and_only_writes_packet_proposal(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={}).json()
        fingerprint = preview["packet_fingerprint"]
        blocked = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/llm-draft", json={
            "packetFingerprint": fingerprint,
        })
        self.assertEqual(blocked.status_code, 409)

        character_id = next(iter(preview["treatment"]["character_intents"]))
        candidate = {
            "scene_name": "办公室门口",
            "dramatic_objective": "来客突破阻碍并改变关系预期",
            "audience_question": "来客为何不受阻拦影响？",
            "character_intents": {character_id: {"goal": "见到董事长", "tactic": "继续前行"}},
            "beat_map": [
                {"beat_id": "B01", "type": "obstacle", "event": "秘书挡住去路"},
                {"beat_id": "B02", "type": "decision", "event": "来客继续前行"},
            ],
            "visual_strategy": "用空间阻挡与行动反差呈现权力变化",
        }
        with patch("api.director_treatment_api.llm_client.call_llm_json", return_value=candidate) as call:
            response = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/llm-draft", json={
                "packetFingerprint": fingerprint,
                "confirmed": True,
                "allowExternalCall": True,
            })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["llm_called"])
        self.assertFalse(payload["domain_write_performed"])
        call.assert_called_once()
        with Session() as session:
            self.assertEqual(session.query(DirectorTreatment).filter_by(book_id=self.book_id).count(), 0)
            packet = session.query(DecisionPacketRecord).filter_by(id=payload["packet_id"]).one()
            self.assertEqual(packet.domain, "director_treatment")
            self.assertEqual(json.loads(packet.proposal)["dramatic_objective"], candidate["dramatic_objective"])

    def test_confirm_candidate_creates_approved_revision_and_rollback_anchor(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={}).json()
        character_id = next(iter(preview["treatment"]["character_intents"]))
        candidate = {
            "dramatic_objective": "确认后的导演目标",
            "audience_question": "来客会不会突破阻碍？",
            "character_intents": {character_id: {"goal": "见到董事长", "tactic": "继续前行"}},
            "beat_map": preview["treatment"]["beat_map"],
            "visual_strategy": "用门口阻挡和行动方向呈现关系变化",
        }
        with patch("api.director_treatment_api.llm_client.call_llm_json", return_value=candidate):
            draft = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/llm-draft", json={
                "packetFingerprint": preview["packet_fingerprint"], "confirmed": True, "allowExternalCall": True,
            }).json()
        approved = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/confirm", json={
            "packetId": draft["packet_id"], "packetFingerprint": draft["packet_fingerprint"], "confirmed": True,
        })
        self.assertEqual(approved.status_code, 200)
        payload = approved.json()
        self.assertTrue(payload["approved"])
        self.assertEqual(payload["treatment"]["status"], "approved")
        self.assertEqual(payload["treatment"]["revision"], 1)
        self.assertEqual(payload["rollback_anchor"]["previous_treatment_id"], None)
        with Session() as session:
            packet = session.query(DecisionPacketRecord).filter_by(id=draft["packet_id"]).one()
            self.assertEqual(packet.status, "confirmed")
            self.assertEqual(session.query(DirectorTreatment).filter_by(book_id=self.book_id, status="approved").count(), 1)

    def test_confirm_rejects_stale_evidence_and_preserves_existing_data(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={}).json()
        character_id = next(iter(preview["treatment"]["character_intents"]))
        candidate = {
            "dramatic_objective": "候选目标", "audience_question": "问题", "character_intents": {character_id: {}},
            "beat_map": preview["treatment"]["beat_map"], "visual_strategy": "空间关系",
        }
        with patch("api.director_treatment_api.llm_client.call_llm_json", return_value=candidate):
            draft = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/llm-draft", json={
                "packetFingerprint": preview["packet_fingerprint"], "confirmed": True, "allowExternalCall": True,
            }).json()
        with Session() as session:
            row = session.query(Script).filter_by(book_id=self.book_id, episode=1).first()
            row.content = row.content + " "
            session.commit()
        response = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/confirm", json={
            "packetId": draft["packet_id"], "packetFingerprint": draft["packet_fingerprint"], "confirmed": True,
        })
        self.assertEqual(response.status_code, 409)
        with Session() as session:
            packet = session.query(DecisionPacketRecord).filter_by(id=draft["packet_id"]).one()
            self.assertEqual(packet.status, "superseded")
            self.assertEqual(session.query(DirectorTreatment).filter_by(book_id=self.book_id).count(), 0)

    def test_candidate_history_is_replayable_without_exposing_secrets(self):
        preview = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/preview", json={}).json()
        with patch("api.director_treatment_api.llm_client.call_llm_json", return_value={
            "dramatic_objective": "候选目标", "audience_question": "问题", "character_intents": {},
            "beat_map": preview["treatment"]["beat_map"], "visual_strategy": "空间策略",
        }):
            response = self.client.post(f"/api/books/{self.book_id}/episodes/1/director-treatment/llm-draft", json={
                "packetFingerprint": preview["packet_fingerprint"], "confirmed": True, "allowExternalCall": True,
            })
        self.assertEqual(response.status_code, 200)
        history = self.client.get(f"/api/books/{self.book_id}/episodes/1/director-treatment/candidates")
        self.assertEqual(history.status_code, 200)
        item = history.json()["items"][0]
        self.assertEqual(item["packet_id"], response.json()["packet_id"])
        self.assertEqual(item["status"], "draft")
        self.assertEqual(item["candidate"]["dramatic_objective"], "候选目标")
        self.assertNotIn("api_key", item["model_info"])
