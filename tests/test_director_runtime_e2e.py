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
    SceneBlocking,
    Script,
    Session,
    ShotPlan,
    StoryboardShot,
    init_db,
)


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
                    "beats": [
                        {"id": "B01", "type": "setup", "event": "林晚推开铁门进入门厅"},
                        {"id": "B02", "type": "reveal", "event": "林晚回望门缝确认无人"},
                    ],
                    "character_blocking": [{"name": "林晚", "position": "screen_right", "facing": "screen_left"}],
                }]}, ensure_ascii=False),
            ))
            session.commit()
            self.book_id = int(book.id)

    def tearDown(self):
        with Session() as session:
            for model in (StoryboardShot, ShotPlan, SceneBlocking, DirectorTreatment, DecisionPacketRecord, Script):
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
        with patch("api.director_treatment_api.llm_client.call_llm_json", return_value=candidate):
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

        benchmark = self.client.post(
            f"{base}/director-benchmark/runs",
            json={"sampleLabel": "director-runtime-e2e", "modelId": "deterministic"},
        )
        self.assertEqual(benchmark.status_code, 200)
        self.assertEqual(benchmark.json()["report"]["status"], "pass")
        self.assertEqual(benchmark.json()["report"]["score"], 100)


if __name__ == "__main__":
    unittest.main()
