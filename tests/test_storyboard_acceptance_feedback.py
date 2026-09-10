import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardAcceptanceRecord, StoryboardPromptVersion, StoryboardShot, VisualLocation, init_db


class StoryboardAcceptanceFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990501
        self.episode = 1
        self.shot_id = 1
        with Session() as session:
            session.query(StoryboardAcceptanceRecord).filter(StoryboardAcceptanceRecord.book_id == self.book_id).delete()
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(book_id=self.book_id, name="Tea House", negative_prompt="no modern signs")
            session.add(location)
            session.flush()
            self.scene_id = str(location.id)
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="Tea House",
                    shot_id=self.shot_id,
                    action_process="Two rivals stare at each other across the table.",
                    asset_links="{}",
                    meta_info=json.dumps({
                        "structured_shot": {
                            "scene_asset_id": str(location.id),
                            "character_asset_ids": [],
                            "prop_asset_ids": [],
                            "style_key": "default",
                            "character_blocking": [],
                            "action_beats": [],
                        }
                    }, ensure_ascii=False),
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardAcceptanceRecord).filter(StoryboardAcceptanceRecord.book_id == self.book_id).delete()
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.commit()

    def test_acceptance_record_persists_and_recompile_absorbs_failure_feedback(self):
        acceptance_response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/acceptance-records",
            json={
                "assetKind": "image",
                "assetId": "image-1",
                "status": "failed",
                "failureTags": ["prop_missing", "character_blocking_error"],
                "notes": "桌上的茶杯必须完整可见，主角站位不要互换",
            },
        )
        self.assertEqual(acceptance_response.status_code, 200)
        acceptance_payload = acceptance_response.json()
        self.assertEqual(acceptance_payload["status"], "failed")
        self.assertIn("prop_missing", acceptance_payload["failure_tags"])

        with patch("core.llm.call_llm_json", return_value={
            "visual_prompt_static": "茶馆内景，中景构图，两名对手隔桌对视，桌上茶杯完整可见，暖色室内光压住紧张气氛。",
            "visual_prompt_motion": "镜头缓慢推进，先保持首帧里的茶馆桌椅与两人站位一致，随后两名对手隔桌僵持，视线持续对撞，最后停在桌上茶杯与人物对峙的紧张瞬间，场景与站位保持一致。",
            "negative_prompt": "模糊, 变形, 字幕, 水印",
            "used_assets": [
                {"asset_type": "scene", "asset_id": self.scene_id, "asset_name": "Tea House", "reference_token": None, "reference_status": "missing"}
            ],
            "warnings": [],
        }):
            compile_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "after-feedback", "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(compile_response.status_code, 200)
        compile_payload = compile_response.json()
        feedback = compile_payload["acceptance_feedback"]
        self.assertIn("prop_missing", feedback["failure_tags"])
        self.assertIn("桌上的茶杯必须完整可见", " ".join(feedback["notes"]))
        self.assertIn("ensure all key props are fully visible", compile_payload["negative_prompt"])

        history_response = self.client.get(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/acceptance-records"
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(len(history_response.json()["records"]), 1)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(outputs_response.status_code, 200)
        shot_payload = outputs_response.json()["storyboard"][0]
        self.assertEqual(shot_payload["acceptance"]["status"], "failed")
        self.assertIn("character_blocking_error", shot_payload["acceptance"]["failure_tags"])


if __name__ == "__main__":
    unittest.main()
