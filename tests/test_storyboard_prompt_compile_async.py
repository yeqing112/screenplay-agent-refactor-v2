import json
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import (
    Session,
    StoryboardPromptVersion,
    StoryboardShot,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    VisualReferenceAsset,
    init_db,
)


class StoryboardPromptCompileAsyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990302
        self.episode = 1
        self.shot_id = 1
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()

            location = VisualLocation(book_id=self.book_id, name="寺庙后院", negative_prompt="不要现代建筑")
            monk = VisualMakeup(book_id=self.book_id, episode=self.episode, character_name="阿宁", negative_prompt="不要多余人物")
            prop = VisualProp(book_id=self.book_id, name="木桶", negative_prompt="不要金属反光")
            session.add_all([location, monk, prop])
            session.flush()

            session.add_all(
                [
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=self.episode,
                        asset_type="scene",
                        asset_id=str(location.id),
                        asset_name="寺庙后院",
                        image_url="https://example.com/scene-locked.png",
                        reference_token="@寺庙后院",
                        status="locked",
                        prompt="scene locked",
                        model="mock-image",
                    ),
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=self.episode,
                        asset_type="character",
                        asset_id=str(monk.id),
                        asset_name="阿宁",
                        image_url="https://example.com/aning-locked.png",
                        reference_token="@阿宁",
                        status="locked",
                        prompt="character locked",
                        model="mock-image",
                    ),
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=self.episode,
                        asset_type="prop",
                        asset_id=str(prop.id),
                        asset_name="木桶",
                        image_url="https://example.com/prop-selected.png",
                        reference_token="@木桶",
                        status="selected",
                        prompt="prop selected",
                        model="mock-image",
                    ),
                ]
            )

            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="寺庙后院",
                    shot_id=self.shot_id,
                    action_process="阿宁抱着木桶在后院停步。",
                    start_state="阿宁站在回廊边，神情紧张。",
                    end_state="阿宁回头看向院门方向。",
                    dialogue="师兄来了。",
                    lighting="cool",
                    camera_angle="MS",
                    camera_movement="push-in",
                    duration=4,
                    meta_info=json.dumps(
                        {
                            "structured_shot": {
                                "scene_asset_id": str(location.id),
                                "character_asset_ids": [str(monk.id)],
                                "prop_asset_ids": [str(prop.id)],
                                "style_key": "default",
                            }
                        },
                        ensure_ascii=False,
                    ),
                    asset_links=json.dumps({"references": {}}, ensure_ascii=False),
                    asset_status="pending",
                )
            )
            session.commit()

        with Session() as session:
            self.scene_id = str(session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).first().id)
            self.character_id = str(session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).first().id)
            self.prop_id = str(session.query(VisualProp).filter(VisualProp.book_id == self.book_id).first().id)

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.commit()

    def _valid_llm_payload(self):
        return {
            "visual_prompt_static": "寺庙后院冷色调中景，人物严格参考 @阿宁，场景保持 @寺庙后院，木桶参考 @木桶。",
            "visual_prompt_motion": "镜头缓慢推进，阿宁抱紧木桶后退半步，人物与环境连续一致。",
            "negative_prompt": "低质量，多余人物，现代建筑",
            "used_assets": [
                {"asset_type": "scene", "asset_id": self.scene_id, "asset_name": "寺庙后院", "reference_token": "@寺庙后院", "reference_status": "locked"},
                {"asset_type": "character", "asset_id": self.character_id, "asset_name": "阿宁", "reference_token": "@阿宁", "reference_status": "locked"},
                {"asset_type": "prop", "asset_id": self.prop_id, "asset_name": "木桶", "reference_token": "@木桶", "reference_status": "selected"},
            ],
            "warnings": [],
        }

    def _poll_task_until_terminal(self, task_id: str, timeout_seconds: float = 20.0):
        deadline = time.time() + timeout_seconds
        last_payload = None
        while time.time() < deadline:
            response = self.client.get(f"/api/storyboard-prompt-compile-tasks/{task_id}")
            self.assertEqual(response.status_code, 200)
            last_payload = response.json()
            if last_payload["status"] in {"done", "error"}:
                return last_payload
            time.sleep(0.05)
        self.fail(f"Task {task_id} did not settle in time. Last payload: {last_payload}")

    def test_async_compile_queues_task_and_settles_with_new_version(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts/async",
                json={"compileReason": "async-test"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["task_id"])

        settled = self._poll_task_until_terminal(payload["task_id"])
        self.assertEqual(settled["status"], "done")
        self.assertEqual(settled["version"], 1)
        self.assertEqual(settled["prompt_version"], 1)
        self.assertEqual(settled["compile_reason"], "async-test")
        self.assertIn("@阿宁", settled["result"]["prompt_static"])

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            self.assertEqual(shot.visual_prompt_static, settled["result"]["prompt_static"])
            self.assertEqual(shot.visual_prompt_motion, settled["result"]["prompt_motion"])

    def test_async_compile_returns_409_for_locked_prompt_when_not_forced(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            meta = json.loads(shot.meta_info or "{}")
            meta["prompt_compiler"] = {"locked": True, "locked_version": 3}
            shot.meta_info = json.dumps(meta, ensure_ascii=False)
            session.commit()

        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts/async",
                json={"compileReason": "async-test"},
            )

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
