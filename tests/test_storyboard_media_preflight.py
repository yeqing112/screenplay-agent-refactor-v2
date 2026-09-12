import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardShot, init_db


class StoryboardMediaPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990777
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="预检场景",
                    shot_id=1,
                    meta_info=json.dumps({"structured_shot": {"shot_id": "1", "scene_asset_id": "scene-1"}}, ensure_ascii=False),
                    asset_links=json.dumps({"images": []}, ensure_ascii=False),
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.commit()

    @staticmethod
    def _h3_profile():
        return {
            "id": "test-h3",
            "name": "Test H3",
            "provider": "minimax-h3-async",
            "model_name": "MiniMax-H3",
            "default_params": {"max_reference_images": 9},
            "enabled": True,
        }

    def test_preflight_is_read_only_and_reports_missing_references(self):
        with patch("api.server.resolve_generation_profile", return_value=self._h3_profile()):
            response = self.client.get(f"/api/books/{self.book_id}/storyboard/1/1/media-preflight")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ready_for_real_submit"])
        self.assertIn("prompt_compiler_references_missing", payload["blockers"])
        self.assertFalse(payload["mutated"])
        self.assertFalse(payload["provider_call"])

    def test_preflight_marks_inaccessible_compiled_reference_without_uploading(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1, shot_id=1).one()
            shot.meta_info = json.dumps(
                {
                    "prompt_compiler": {
                        "reference_images": [
                            {
                                "reference_asset_id": "ref-scene",
                                "asset_type": "scene",
                                "asset_name": "预检场景",
                                "image_url": "https://assets.invalid/scene.png",
                                "reference_status": "locked",
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            )
            session.commit()

        with patch("api.server.resolve_generation_profile", return_value=self._h3_profile()), patch(
            "api.server.check_public_url_accessible", return_value=(False, "http_404")
        ) as check_url:
            response = self.client.get(f"/api/books/{self.book_id}/storyboard/1/1/media-preflight")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ready_for_real_submit"])
        self.assertIn("compiled_reference_images_not_provider_accessible", payload["blockers"])
        self.assertEqual(payload["references"][0]["error"], "http_404")
        self.assertTrue(payload["references"][0]["requires_publish"])
        check_url.assert_called_once()

    def test_preflight_allows_local_reference_when_gray_storage_override_is_explicit(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=1, shot_id=1).one()
            shot.meta_info = json.dumps(
                {
                    "prompt_compiler": {
                        "reference_images": [
                            {
                                "reference_asset_id": "ref-local",
                                "asset_type": "scene",
                                "asset_name": "预检场景",
                                "image_url": "/api/prototyping/manual-media/local.png",
                                "reference_status": "locked",
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            )
            session.commit()

        with patch("api.server.resolve_generation_profile", return_value=self._h3_profile()), patch(
            "api.server.load_public_asset_storage_config",
            return_value=SimpleNamespace(
                enabled=True,
                provider="qiniu",
                qiniu_public_base_url="http://temporary.clouddn.com",
            ),
        ), patch("api.server.public_asset_storage_is_production_safe", return_value=False):
            response = self.client.get(
                f"/api/books/{self.book_id}/storyboard/1/1/media-preflight"
                "?allow_unstable_public_assets=true"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ready_for_real_submit"])
        self.assertEqual(payload["blockers"], [])
        self.assertIn("reference_will_be_published_before_submit", payload["warnings"])
        self.assertTrue(payload["references"][0]["publishable_via_storage"])
        self.assertFalse(payload["mutated"])
        self.assertFalse(payload["provider_call"])


if __name__ == "__main__":
    unittest.main()
