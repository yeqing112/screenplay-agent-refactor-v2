import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.server import _resolve_storyboard_video_reference_payloads, app
from models import DecisionPacketRecord, Session, StoryboardPromptVersion, StoryboardShot, VisualLocation, VisualReferenceAsset, init_db


class StoryboardGenerationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990401
        self.episode = 1
        self.shot_id = 1
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(DecisionPacketRecord).filter(DecisionPacketRecord.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(
                book_id=self.book_id,
                name="暴雨中的出租屋",
                negative_prompt="不要汽车",
            )
            session.add(location)
            session.flush()
            self.scene_id = str(location.id)

            session.add(
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="scene",
                    asset_id=self.scene_id,
                    asset_name="暴雨中的出租屋",
                    image_url="https://example.com/ref-scene-locked.png",
                    reference_token="@出租屋",
                    status="locked",
                    prompt="scene locked",
                    model="mock-image",
                )
            )

            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="暴雨中的出租屋",
                    shot_id=self.shot_id,
                    action_process="姐姐回头看向门外，雨声压住对白。",
                    start_state="姐姐站在门边，潮湿雨夜压进屋内。",
                    end_state="镜头停在她压低视线的瞬间。",
                    visual_prompt_static="暴雨中的出租屋内景，中景构图，姐姐站在门边，冷色雨光照进狭窄房间，外观严格参考 @出租屋。",
                    visual_prompt_motion="镜头缓慢推进，先保持首帧里的出租屋空间与人物位置一致，随后姐姐轻轻回头，雨声压住呼吸，最后停在她压低视线的瞬间，场景与服装保持一致。",
                    visual_prompt_final="低质量，不要汽车",
                    asset_links=json.dumps({
                        "images": [
                            {
                                "id": "image-existing",
                                "kind": "image",
                                "title": "已有首帧",
                                "label": "v1",
                                "uri": "https://example.com/frame-existing.png",
                                "previewUrl": "https://example.com/frame-existing.png",
                                "adopted": True,
                            }
                        ],
                        "references": {},
                    }, ensure_ascii=False),
                    meta_info=json.dumps({
                        "structured_shot": {
                            "scene_asset_id": self.scene_id,
                            "character_asset_ids": [],
                            "prop_asset_ids": [],
                            "style_key": "default",
                            "character_blocking": [],
                            "action_beats": [
                                {"start": 0.0, "end": 4.0, "action": "姐姐站在门边，随后轻轻回头看向门外。"},
                            ],
                        },
                        "prompt_compiler": {
                            "latest_version": 1,
                            "negative_prompt": "低质量，不要汽车",
                            "prompt_compile_context": {
                                "executability": {
                                    "status": "pass",
                                    "duration": 4,
                                    "action_count": 1,
                                    "recommended_max_actions": 2,
                                    "findings": [],
                                    "suggestions": [],
                                }
                            },
                            "reference_asset_ids": ["ref-1"],
                            "reference_images": [
                                {
                                    "asset_type": "scene",
                                    "asset_id": self.scene_id,
                                    "asset_name": "暴雨中的出租屋",
                                    "reference_asset_id": "ref-1",
                                    "reference_token": "@出租屋",
                                    "image_url": "https://example.com/ref-scene-locked.png",
                                    "reference_status": "locked",
                                    "role": "scene",
                                    "weight": 1.0,
                                }
                            ],
                        },
                    }, ensure_ascii=False),
                    asset_status="pending",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(DecisionPacketRecord).filter(DecisionPacketRecord.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.commit()

    def _create_prompt_draft_packet(self):
        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-drafts",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["packet"]

    def test_prompt_draft_rejects_missing_locked_asset_before_persisting_candidate(self):
        packet = self._create_prompt_draft_packet()
        invalid_candidate = {
            "visual_prompt_static": "暴雨中的出租屋内景，中景构图，冷色雨光照进狭窄房间。",
            "visual_prompt_motion": "固定机位，人物轻微回头后保持首帧一致性，最后停在压低视线的瞬间。",
            "negative_prompt": "低质量，水印，logo",
            "used_assets": [],
        }
        with patch("api.server._call_storyboard_prompt_compiler", return_value=invalid_candidate):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-drafts/{packet['id']}/llm",
                json={"packetFingerprint": packet["packet_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(response.status_code, 422)
        self.assertIn("遗漏锁定资产", response.json()["detail"])
        with Session() as session:
            saved = session.query(DecisionPacketRecord).filter_by(id=packet["id"]).first()
            self.assertFalse(json.loads(saved.model_info).get("llm_generated"))

    def test_prompt_draft_confirm_rejects_changed_evidence(self):
        packet = self._create_prompt_draft_packet()
        valid_candidate = {
            "visual_prompt_static": "暴雨中的出租屋内景，中景构图，姐姐站在门边，冷色雨光照进狭窄房间，外观严格参考暴雨中的出租屋。",
            "visual_prompt_motion": "固定机位，姐姐先保持门边站位，再轻轻回头，雨声压住呼吸，最后停在她压低视线的瞬间，场景与服装保持首帧一致。",
            "negative_prompt": "低质量，水印，logo",
            "used_assets": [{"asset_type": "scene", "asset_id": self.scene_id, "asset_name": "暴雨中的出租屋"}],
        }
        with patch("api.server._call_storyboard_prompt_compiler", return_value=valid_candidate):
            generated = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-drafts/{packet['id']}/llm",
                json={"packetFingerprint": packet["packet_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(generated.status_code, 200)
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=self.episode, shot_id=self.shot_id).first()
            shot.action_process = "姐姐忽然关上门，雨声戛然而止。"
            session.commit()
        confirmation = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-drafts/{packet['id']}/confirm",
            json={"packetFingerprint": packet["packet_fingerprint"], "action": "confirmed", "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(confirmation.status_code, 409)
        self.assertIn("事实已变化", confirmation.json()["detail"])

    def test_prompt_draft_confirm_persists_complete_runtime_contract(self):
        packet = self._create_prompt_draft_packet()
        valid_candidate = {
            "visual_prompt_static": "暴雨中的出租屋内景，中景构图，姐姐站在门边，冷色雨光照进狭窄房间，外观严格参考 @出租屋。",
            "visual_prompt_motion": "固定机位，姐姐先保持门边站位，再轻轻回头，雨声压住呼吸，最后停在她压低视线的瞬间，场景与服装保持首帧一致。",
            "negative_prompt": "低质量，水印，logo",
            "used_assets": [{"asset_type": "scene", "asset_id": self.scene_id, "asset_name": "暴雨中的出租屋"}],
        }
        with patch("api.server._call_storyboard_prompt_compiler", return_value=valid_candidate):
            generated = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-drafts/{packet['id']}/llm",
                json={"packetFingerprint": packet["packet_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(generated.status_code, 200)
        confirmation = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-drafts/{packet['id']}/confirm",
            json={"packetFingerprint": packet["packet_fingerprint"], "action": "confirmed", "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(confirmation.status_code, 200)
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(book_id=self.book_id, episode=self.episode, shot_id=self.shot_id).first()
            meta = json.loads(shot.meta_info)
            compiler = meta["prompt_compiler"]
            self.assertEqual(compiler["latest_version"], confirmation.json()["prompt_version"])
            self.assertEqual(compiler["prompt_compile_context"]["model_adapter"]["static_prompt_sections"]["schema_version"], "storyboard_image_prompt_sections_v1")
            self.assertTrue(compiler["compiler_diagnostics"]["context_fingerprint"])
            self.assertTrue(compiler["prompt_compile_context"]["executability"]["status"])
            self.assertEqual(
                compiler["prompt_compile_context"]["shot_ir"]["action_beats"],
                [{"start": 0.0, "end": 4.0, "action": "姐姐站在门边，随后轻轻回头看向门外。"}],
            )

    def test_generate_frame_and_video_use_final_prompts_and_reference_images(self):
        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.resolve_generation_profile",
            side_effect=lambda capability, model_profile_id=None: {
                "id": f"mock-{capability}",
                "provider": "prototype-task-adapter",
                "model_name": f"mock-{capability}",
                "enabled": True,
            },
        ):
            frame_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-frame",
                json={},
            )
            self.assertEqual(frame_response.status_code, 200)
            frame_payload = frame_response.json()
            self.assertEqual(frame_payload["status"], "queued")
            self.assertEqual(frame_payload["prompt"], "暴雨中的出租屋内景，中景构图，姐姐站在门边，冷色雨光照进狭窄房间，外观严格参考 @出租屋。")
            self.assertEqual(frame_payload["reference_asset_ids"], ["ref-1"])
            self.assertEqual(frame_payload["reference_images"][0]["reference_token"], "@出租屋")
            self.assertEqual(frame_payload["negative_prompt"], "低质量，不要汽车")

            task_payload = self.client.get(f"/api/prototyping/tasks/{frame_payload['task_id']}").json()
            self.assertEqual(task_payload["status"], "done")

            with Session() as session:
                shot = session.query(StoryboardShot).filter(
                    StoryboardShot.book_id == self.book_id,
                    StoryboardShot.episode == self.episode,
                    StoryboardShot.shot_id == self.shot_id,
                ).first()
                image_links = json.loads(shot.asset_links)["images"]
                self.assertEqual(len(image_links), 2)
                latest = image_links[-1]
                self.assertEqual(latest["metadata"]["referenceAssetIds"], ["ref-1"])
                self.assertEqual(latest["metadata"]["referenceImages"][0]["reference_token"], "@出租屋")
                self.assertEqual(latest["metadata"]["negativePrompt"], "低质量，不要汽车")

            video_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-video",
                json={},
            )
            self.assertEqual(video_response.status_code, 200)
            video_payload = video_response.json()
            self.assertEqual(video_payload["first_frame_asset_id"], latest["id"])
            self.assertEqual(video_payload["first_frame_url"], latest["previewUrl"])
            self.assertEqual(video_payload["status"], "queued")
            self.assertEqual(video_payload["prompt"], "镜头缓慢推进，先保持首帧里的出租屋空间与人物位置一致，随后姐姐轻轻回头，雨声压住呼吸，最后停在她压低视线的瞬间，场景与服装保持一致。")
            self.assertEqual(video_payload["reference_images"][0]["image_url"], "https://example.com/ref-scene-locked.png")

            task_payload = self.client.get(f"/api/prototyping/tasks/{video_payload['task_id']}").json()
            self.assertEqual(task_payload["status"], "done")

            with Session() as session:
                shot = session.query(StoryboardShot).filter(
                    StoryboardShot.book_id == self.book_id,
                    StoryboardShot.episode == self.episode,
                    StoryboardShot.shot_id == self.shot_id,
                ).first()
                payload = json.loads(shot.asset_links)
                self.assertEqual(len(payload["videos"]), 1)
                self.assertEqual(payload["videos"][0]["sourceAssetId"], payload["images"][-1]["id"])
                self.assertEqual(payload["videos"][0]["metadata"]["firstFrameAssetId"], payload["images"][-1]["id"])
                self.assertEqual(payload["videos"][0]["metadata"]["firstFrameUrl"], payload["images"][-1]["previewUrl"])
                self.assertEqual(payload["videos"][0]["metadata"]["providerTaskMode"], "reference_to_video")
                self.assertEqual(payload["videos"][0]["metadata"]["referenceImages"][0]["reference_token"], "@出租屋")
                self.assertEqual(shot.asset_status, "done")

    def test_video_references_prioritize_adopted_storyboard_composition_and_all_characters(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
            ).first()
            meta = json.loads(shot.meta_info)
            meta["prompt_compiler"]["reference_images"] = [
                {
                    "asset_type": "scene",
                    "asset_id": self.scene_id,
                    "asset_name": "暴雨中的出租屋",
                    "reference_asset_id": "ref-scene",
                    "image_url": "https://example.com/ref-scene-locked.png",
                    "role": "scene",
                },
                *[
                    {
                        "asset_type": "character",
                        "asset_id": str(index),
                        "asset_name": f"角色{index}",
                        "reference_asset_id": f"ref-character-{index}",
                        "image_url": f"https://example.com/ref-character-{index}.png",
                        "role": "character",
                    }
                    for index in range(1, 4)
                ],
            ]
            shot.meta_info = json.dumps(meta, ensure_ascii=False)
            session.commit()

            reference_ids, reference_images = _resolve_storyboard_video_reference_payloads(
                shot,
                requested_reference_asset_ids=None,
                max_reference_images=4,
            )

        self.assertEqual(
            reference_ids,
            ["composition-image-existing", "ref-character-1", "ref-character-2", "ref-character-3"],
        )
        self.assertEqual([item["role"] for item in reference_images], ["composition", "character", "character", "character"])
        self.assertEqual(reference_images[0]["image_url"], "https://example.com/frame-existing.png")

        # A larger provider limit must not re-introduce the scene turnaround:
        # the composition reference already owns shot layout and lighting.
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
            ).first()
            wide_ids, wide_images = _resolve_storyboard_video_reference_payloads(
                shot,
                requested_reference_asset_ids=None,
                max_reference_images=9,
            )
        self.assertEqual(wide_ids, reference_ids)
        self.assertEqual([item["role"] for item in wide_images], ["composition", "character", "character", "character"])


if __name__ == "__main__":
    unittest.main()
