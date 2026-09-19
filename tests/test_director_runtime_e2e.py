"""End-to-end deterministic acceptance for the Director Runtime path."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import (
    Book,
    DecisionPacketRecord,
    DirectorTreatment,
    FactSnapshot,
    SceneBlocking,
    Script,
    Session,
    ShotPlan,
    StoryboardShot,
    VisualLocation,
    init_db,
)


def _provider_call(candidate):
    def call(*args, **kwargs):
        callback = kwargs.get("audit_callback")
        if callback:
            callback({"profile_id": "test-profile", "vendor_model": "test-model", "request_fingerprint": "test-request", "response_sha256": "test-response"})
        return candidate
    return call


class DirectorRuntimeE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            book = Book(title="Director Runtime E2E", filename="director-runtime-e2e.txt", status="imported")
            session.add(book)
            session.flush()
            session.add(Script(
                book_id=book.id,
                episode=1,
                content=json.dumps({"scenes": [{
                    "name": "雨夜门厅",
                    "location_id": "LOC_HALL",
                    "participants": [{"character_id": "C1", "name": "林晚"}],
                    "props": [{"id": "PROP_PHOTO", "name": "照片"}],
                    "beats": [
                        {"id": "B01", "type": "setup", "event": "林晚推开铁门进入门厅"},
                        {"id": "B02", "type": "reveal", "event": "林晚回望门缝确认无人"},
                    ],
                    "character_blocking": [{"name": "林晚", "position": "screen_right", "facing": "screen_left"}],
                }]}, ensure_ascii=False),
            ))
            session.add(VisualLocation(
                book_id=book.id,
                name="雨夜门厅",
                canonical_facts=json.dumps({"fixed_set": "铁门、门厅长椅"}, ensure_ascii=False),
                state_variants=json.dumps({"weather": "雨夜"}, ensure_ascii=False),
                look_profile=json.dumps({"palette": "冷青灰"}, ensure_ascii=False),
                board_spec=json.dumps({"layout": "2x2"}, ensure_ascii=False),
                key_props=json.dumps(["PROP_PHOTO"], ensure_ascii=False),
            ))
            session.add(FactSnapshot(
                book_id=book.id,
                episode=1,
                revision=1,
                status="confirmed",
                source_fingerprint="script-source-1",
                payload_hash="facts-1",
                records_json=json.dumps([{
                    "fact_id": "F1",
                    "subject_type": "location",
                    "subject_id": "LOC_HALL",
                    "predicate": "fixed_set",
                    "value": "铁门、门厅长椅",
                    "authority": "approved_fact",
                    "status": "confirmed",
                }], ensure_ascii=False),
            ))
            session.commit()
            self.book_id = int(book.id)

    def tearDown(self):
        with Session() as session:
            for model in (StoryboardShot, ShotPlan, SceneBlocking, DirectorTreatment, DecisionPacketRecord, FactSnapshot, VisualLocation, Script):
                session.query(model).filter(model.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_treatment_to_shot_plan_and_benchmark(self):
        base = f"/api/books/{self.book_id}/episodes/1"

        treatment_preview = self.client.post(f"{base}/director-treatment/preview", json={"persist": True})
        self.assertEqual(treatment_preview.status_code, 200)
        treatment_payload = treatment_preview.json()
        self.assertFalse(treatment_payload["llm_called"])
        self.assertTrue(treatment_payload["mutated"])

        treatment = treatment_payload["treatment"]
        candidate = {
            "dramatic_objective": treatment["dramatic_objective"],
            "audience_question": treatment["audience_question"],
            "character_intents": treatment["character_intents"],
            "beat_map": treatment["beat_map"],
            "visual_strategy": treatment["visual_strategy"],
        }
        with patch("api.director_treatment_api.llm_client.call_llm_json", side_effect=_provider_call(candidate)):
            treatment_draft = self.client.post(
                f"{base}/director-treatment/llm-draft",
                json={
                    "packetFingerprint": treatment_payload["packet_fingerprint"],
                    "confirmed": True,
                    "allowExternalCall": True,
                },
            )
        self.assertEqual(treatment_draft.status_code, 200)
        treatment_confirm = self.client.post(
            f"{base}/director-treatment/confirm",
            json={
                "packetId": treatment_draft.json()["packet_id"],
                "packetFingerprint": treatment_draft.json()["packet_fingerprint"],
                "confirmed": True,
            },
        )
        self.assertEqual(treatment_confirm.status_code, 200)
        self.assertTrue(treatment_confirm.json()["approved"])

        blocking_preview = self.client.post(f"{base}/scene-blocking/preview", json={"persist": True})
        self.assertEqual(blocking_preview.status_code, 200)
        blocking_payload = blocking_preview.json()
        blocking_confirm = self.client.post(
            f"{base}/scene-blocking/confirm",
            json={
                "blockingId": blocking_payload["persisted_draft_id"],
                "evidenceFingerprint": blocking_payload["blocking"]["evidence_fingerprint"],
                "confirmed": True,
            },
        )
        self.assertEqual(blocking_confirm.status_code, 200)
        self.assertTrue(blocking_confirm.json()["approved"])

        shot_plan_preview = self.client.post(f"{base}/shot-plan/preview", json={"persist": True})
        self.assertEqual(shot_plan_preview.status_code, 200)
        shot_plan_payload = shot_plan_preview.json()
        reviewed_shots = json.loads(json.dumps(shot_plan_payload["plan"]["shots"], ensure_ascii=False))
        for index, shot in enumerate(reviewed_shots, start=1):
            shot["camera"] = {"shot_size": "MS", "movement": "static"}
            shot["duration_hint_seconds"] = 4
            shot["shot_id"] = index
        shot_plan_confirm = self.client.post(
            f"{base}/shot-plan/confirm",
            json={
                "planId": shot_plan_payload["persisted_draft_id"],
                "evidenceFingerprint": shot_plan_payload["plan"]["evidence_fingerprint"],
                "confirmed": True,
                "plan": {"scene_name": "雨夜门厅", "shots": reviewed_shots, "unknowns": []},
            },
        )
        self.assertEqual(shot_plan_confirm.status_code, 200)
        self.assertTrue(shot_plan_confirm.json()["storyboard_generation_allowed"])

        readiness = self.client.get(f"{base}/storyboard/readiness")
        self.assertEqual(readiness.status_code, 200)
        self.assertTrue(readiness.json()["allowed"])

        patch_preview = self.client.post(
            f"{base}/shot-plan/creative-patch-preview",
            json={
                "sceneName": "雨夜门厅",
                "patchDocument": {
                    "schema_version": "director_creative_patch_v1",
                    "patches": [{"plan_shot_id": reviewed_shots[0]["plan_shot_id"], "changes": {"camera.shot_size": "CU"}}],
                    "auxiliary_shot_proposals": [],
                },
            },
        )
        self.assertEqual(patch_preview.status_code, 200)
        self.assertFalse(patch_preview.json()["llm_called"])
        self.assertTrue(patch_preview.json()["requires_approval"])
        self.assertEqual(patch_preview.json()["candidate"]["patch_document"]["patches"][0]["plan_shot_id"], reviewed_shots[0]["plan_shot_id"])
        self.assertEqual(patch_preview.json()["partial_acceptance"]["accepted_patch_count"], 1)
        self.assertEqual(patch_preview.json()["partial_acceptance"]["rejected_patch_count"], 0)
        self.assertTrue(patch_preview.json()["contract_reliability"]["schema_pass"])
        contract = patch_preview.json()["contract"]
        self.assertEqual(contract["scene"]["scene_name"], "雨夜门厅")
        self.assertEqual(contract["immutable_projection"]["facts"]["fact_snapshot_records"][0]["fact_id"], "F1")
        self.assertEqual(contract["immutable_projection"]["assets"]["scene"], ["LOC_HALL"])
        self.assertEqual(contract["immutable_projection"]["assets"]["characters"], ["C1"])
        self.assertEqual(contract["immutable_projection"]["assets"]["props"], ["PROP_PHOTO"])

        persisted_patch_preview = self.client.post(
            f"{base}/shot-plan/creative-patch-preview",
            json={
                "sceneName": "雨夜门厅",
                "persist": True,
                "patchDocument": patch_preview.json()["candidate"]["patch_document"],
            },
        )
        self.assertEqual(persisted_patch_preview.status_code, 200)
        self.assertTrue(persisted_patch_preview.json()["mutated"])
        self.assertIsNotNone(persisted_patch_preview.json()["persisted_draft_id"])

        partial_schema_preview = self.client.post(
            f"{base}/shot-plan/creative-patch-preview",
            json={
                "sceneName": "雨夜门厅",
                "patchDocument": {
                    "schema_version": "director_creative_patch_v1",
                    "patches": [
                        {"plan_shot_id": reviewed_shots[0]["plan_shot_id"], "changes": {"camera.angle": "low_angle"}},
                        {"plan_shot_id": reviewed_shots[1]["plan_shot_id"], "changes": {"scene_name": "不得改事实"}},
                    ],
                    "auxiliary_shot_proposals": [],
                },
            },
        )
        self.assertEqual(partial_schema_preview.status_code, 200)
        partial_payload = partial_schema_preview.json()
        self.assertEqual(partial_payload["partial_acceptance"]["accepted_patch_count"], 1)
        self.assertEqual(partial_payload["partial_acceptance"]["rejected_patch_count"], 1)
        self.assertEqual(partial_payload["contract_reliability"]["schema_rejection_count"], 1)
        self.assertEqual(partial_payload["contract_reliability"]["fact_override_attempt_count"], 1)
        self.assertTrue(partial_payload["contract_reliability"]["forbidden_field_attempt"])
        self.assertEqual(partial_payload["candidate"]["patch_document"]["patches"][0]["plan_shot_id"], reviewed_shots[0]["plan_shot_id"])

        blocked_patch_llm = self.client.post(
            f"{base}/shot-plan/creative-patch-llm-draft",
            json={"sceneName": "雨夜门厅"},
        )
        self.assertEqual(blocked_patch_llm.status_code, 409)

        with patch("api.shot_plan_api.llm_client.call_llm_json", return_value={
            "schema_version": "director_creative_patch_v1",
            "patches": [{"plan_shot_id": reviewed_shots[0]["plan_shot_id"], "changes": {"camera.angle": "low_angle"}}],
            "auxiliary_shot_proposals": [],
        }) as patch_llm:
            patch_llm_response = self.client.post(
                f"{base}/shot-plan/creative-patch-llm-draft",
                json={"sceneName": "雨夜门厅", "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(patch_llm_response.status_code, 200)
        self.assertEqual(patch_llm.call_count, 1)
        self.assertTrue(patch_llm_response.json()["llm_called"])
        self.assertTrue(patch_llm_response.json()["requires_approval"])
        self.assertEqual(patch_llm_response.json()["candidate"]["patch_document"]["patches"][0]["changes"]["camera.angle"], "low_angle")
        self.assertRegex(patch_llm_response.json()["system_prompt_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(patch_llm_response.json()["user_prompt_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(patch_llm_response.json()["prompt_prefix_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertNotIn("api_key", patch_llm_response.json()["model_snapshot"])
        self.assertNotIn("base_url", patch_llm_response.json()["model_snapshot"])
        self.assertEqual(
            patch_llm_response.json()["candidate"]["model_info"]["prompt_prefix_fingerprint"],
            patch_llm_response.json()["prompt_prefix_fingerprint"],
        )

        benchmark = self.client.post(
            f"{base}/director-benchmark/runs",
            json={"sampleLabel": "director-runtime-e2e", "modelId": "deterministic"},
        )
        self.assertEqual(benchmark.status_code, 200)
        self.assertEqual(benchmark.json()["report"]["status"], "pass")
        self.assertEqual(benchmark.json()["report"]["score"], 100)


if __name__ == "__main__":
    unittest.main()
