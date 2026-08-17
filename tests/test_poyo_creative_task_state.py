import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.generation_adapters import ModelProfileError
from api.model_registry import MODEL_REGISTRY_DEFAULTS_KEY, MODEL_REGISTRY_PROFILES_KEY, save_registry
from api.server import app, _creative_tasks
from models import Session, StoryboardShot, VisualMakeup, VisualReferenceAsset, VisualLocation, get_kv, init_db, set_kv


class PoyoCreativeTaskStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self._original_profiles = get_kv(MODEL_REGISTRY_PROFILES_KEY, "[]")
        self._original_defaults = get_kv(MODEL_REGISTRY_DEFAULTS_KEY, "{}")
        self.book_id = 990499
        self.episode = 1
        self.shot_id = 1

        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(
                book_id=self.book_id,
                name="山门夜雨",
                negative_prompt="不要游客",
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
                    asset_name="山门夜雨",
                    image_url="https://example.com/ref-night-rain.png",
                    reference_token="@山门夜雨",
                    status="locked",
                    prompt="scene locked",
                    model="mock-image",
                )
            )

            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="山门夜雨",
                    shot_id=self.shot_id,
                    action_process="小和尚站在山门前，雨丝斜切过灯笼。",
                    start_state="夜雨压低光线，小和尚抬头看向山门。",
                    end_state="镜头停在山门与灯笼的轮廓上。",
                    visual_prompt_static="山门夜雨，冷色灯笼照亮石阶，小和尚站在门前，场景参考 @山门夜雨。",
                    visual_prompt_motion="镜头先保持首帧构图，再轻轻推进到小和尚肩后，雨丝与灯笼反光保持一致。",
                    visual_prompt_final="低质量，不要游客",
                    asset_links=json.dumps({"images": [], "references": {}}, ensure_ascii=False),
                    meta_info=json.dumps(
                        {
                            "structured_shot": {
                                "scene_asset_id": self.scene_id,
                                "character_asset_ids": [],
                                "prop_asset_ids": [],
                                "style_key": "default",
                                "character_blocking": [],
                                "action_beats": [],
                            },
                            "prompt_compiler": {
                                "latest_version": 1,
                                "negative_prompt": "低质量，不要游客",
                                "reference_asset_ids": ["ref-night-1"],
                                "reference_images": [
                                    {
                                        "asset_type": "scene",
                                        "asset_id": self.scene_id,
                                        "asset_name": "山门夜雨",
                                        "reference_asset_id": "ref-night-1",
                                        "reference_token": "@山门夜雨",
                                        "image_url": "https://example.com/ref-night-rain.png",
                                        "reference_status": "locked",
                                        "role": "scene",
                                        "weight": 1.0,
                                    }
                                ],
                            },
                        },
                        ensure_ascii=False,
                    ),
                    asset_status="pending",
                )
            )
            session.commit()

        save_registry(
            profiles=[
                {
                    "id": "poyo-image-default",
                    "name": "PoYo Seedream 5 Lite",
                    "capability": "image",
                    "provider": "poyo-async",
                    "base_url": "https://api.poyo.ai",
                    "model_name": "seedream-5.0-lite",
                    "default_params": {
                        "task_modes": ["text_to_image", "image_to_image"],
                        "supports_reference_images": True,
                        "max_reference_images": 14,
                        "poll_interval_seconds": 1,
                        "poll_timeout_seconds": 10,
                    },
                    "enabled": True,
                    "api_key": "secret-test-key",
                }
            ],
            defaults={"image": "poyo-image-default"},
        )

    def tearDown(self):
        set_kv(MODEL_REGISTRY_PROFILES_KEY, self._original_profiles)
        set_kv(MODEL_REGISTRY_DEFAULTS_KEY, self._original_defaults)
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.commit()

    def test_poyo_success_persists_external_task_fields_to_task_and_asset(self):
        generated = {
            "previewUrl": "https://cdn.example.com/poyo-frame.png",
            "uri": "https://cdn.example.com/poyo-frame.png",
            "externalTaskId": "poyo-task-2001",
            "externalStatus": "finished",
            "pollAttempts": 4,
            "providerRequestPayload": {
                "model": "seedream-5.0-lite",
                "input": {
                    "prompt": "山门夜雨，冷色灯笼照亮石阶，小和尚站在门前，场景参考 @山门夜雨。",
                    "aspect_ratio": "16:9",
                },
            },
            "providerResponse": {"status": "finished", "files": [{"file_url": "https://cdn.example.com/poyo-frame.png"}]},
        }

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(return_value=generated),
        ):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-frame",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/prototyping/tasks/{task_id}").json()
        self.assertEqual(task_payload["status"], "done")
        self.assertEqual(task_payload["provider"], "poyo-async")
        self.assertEqual(task_payload["external_task_id"], "poyo-task-2001")
        self.assertEqual(task_payload["external_status"], "finished")
        self.assertEqual(task_payload["poll_attempts"], 4)
        self.assertEqual(task_payload["provider_response"]["status"], "finished")
        self.assertEqual(task_payload["provider_request_payload"]["model"], "seedream-5.0-lite")
        self.assertIn("prompt", task_payload["provider_request_payload"]["input"])
        self.assertTrue(task_payload["prompt_encoding_audit"]["provider_payload_captured"])
        self.assertTrue(task_payload["prompt_encoding_audit"]["submitted_contains_cjk"])
        self.assertFalse(task_payload["prompt_encoding_audit"]["submitted_looks_garbled"])

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            payload = json.loads(shot.asset_links)
            latest = payload["images"][-1]
            self.assertEqual(latest["metadata"]["externalTaskId"], "poyo-task-2001")
            self.assertEqual(latest["metadata"]["externalStatus"], "finished")
            self.assertEqual(latest["metadata"]["pollAttempts"], 4)
            self.assertEqual(latest["metadata"]["providerResponse"]["status"], "finished")
            self.assertEqual(latest["metadata"]["providerRequestPayload"]["model"], "seedream-5.0-lite")
            self.assertTrue(latest["metadata"]["promptEncodingAudit"]["submitted_contains_cjk"])

    def test_poyo_failure_preserves_external_error_state_on_task(self):
        failure = ModelProfileError(
            "PoYo quota exceeded",
            provider_response={"status": "failed", "error": "quota exceeded"},
            external_status="failed",
            poll_attempts=6,
            external_task_id="poyo-task-2002",
        )

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(side_effect=failure),
        ):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-frame",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/prototyping/tasks/{task_id}").json()
        self.assertEqual(task_payload["status"], "error")
        self.assertEqual(task_payload["error"], "quota exceeded")
        self.assertEqual(task_payload["external_task_id"], "poyo-task-2002")
        self.assertEqual(task_payload["external_status"], "failed")
        self.assertEqual(task_payload["poll_attempts"], 6)
        self.assertEqual(task_payload["provider_response"]["error"], "quota exceeded")
        self.assertEqual(task_payload["provider_request_payload"], None)
        self.assertTrue(task_payload["prompt_encoding_audit"]["original_contains_cjk"])
        self.assertFalse(task_payload["prompt_encoding_audit"]["provider_payload_captured"])

    def test_poyo_connect_failure_captures_provider_request_payload_for_audit(self):
        failure = ModelProfileError(
            "PoYo submit failed",
            provider_request_payload={
                "model": "seedream-5.0-lite",
                "input": {
                    "prompt": "山门夜雨，冷色灯笼照亮石阶，小和尚站在门前，场景参考 @山门夜雨。",
                    "aspect_ratio": "16:9",
                },
            },
        )

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(side_effect=failure),
        ):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-frame",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/prototyping/tasks/{task_id}").json()
        self.assertEqual(task_payload["status"], "error")
        self.assertEqual(task_payload["provider_request_payload"]["model"], "seedream-5.0-lite")
        self.assertEqual(
            task_payload["provider_request_payload"]["input"]["prompt"],
            "山门夜雨，冷色灯笼照亮石阶，小和尚站在门前，场景参考 @山门夜雨。",
        )
        self.assertTrue(task_payload["prompt_encoding_audit"]["provider_payload_captured"])
        self.assertTrue(task_payload["prompt_encoding_audit"]["submitted_contains_cjk"])
        self.assertFalse(task_payload["prompt_encoding_audit"]["submitted_looks_garbled"])

    def test_storyboard_frame_retries_with_provider_safe_prompt_after_minor_safety_rejection(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot.visual_prompt_static = (
                "俯拍视角，原始丛林林间空地，角色以高速下坠姿态出现在泥坑正上方，"
                "他是一名9岁男孩，部分发丝贴在额前，额头和鼻尖带汗与泥点，"
                "衣摆和裤腿已被泥点与湿气打脏边缘贴身，双肩小背包背带被下坠拉紧。"
            )
            session.commit()

        failure = ModelProfileError(
            "PoYo task failed",
            provider_response={
                "code": 200,
                "data": {
                    "status": "failed",
                    "error_message": (
                        'API call failed: HTTP 500: {"error":{"message":"非常抱歉，生成的图片可能违反了关于青少年与儿童形象适当描绘的防护限制。"}}'
                    ),
                },
            },
            external_status="failed",
            poll_attempts=3,
            external_task_id="poyo-task-minor-1",
        )
        generated = {
            "previewUrl": "https://cdn.example.com/poyo-frame-retried.png",
            "uri": "https://cdn.example.com/poyo-frame-retried.png",
            "externalTaskId": "poyo-task-minor-2",
            "externalStatus": "finished",
            "pollAttempts": 2,
            "providerResponse": {"status": "finished"},
        }

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(side_effect=[failure, generated]),
        ) as mocked_generate:
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-frame",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/prototyping/tasks/{task_id}").json()
        self.assertEqual(task_payload["status"], "done")
        self.assertEqual(mocked_generate.await_count, 2)
        first_prompt = mocked_generate.await_args_list[0].kwargs["prompt"]
        second_prompt = mocked_generate.await_args_list[1].kwargs["prompt"]
        self.assertIn("9岁男孩", first_prompt)
        self.assertIn("体型轻巧的探险者", second_prompt)
        self.assertNotEqual(first_prompt, second_prompt)

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            payload = json.loads(shot.asset_links)
            latest = payload["images"][-1]
            self.assertTrue(latest["metadata"]["providerPromptAdjusted"])
            self.assertIn("青少年与儿童形象适当描绘", latest["metadata"]["providerPromptAdjustmentReason"])
            self.assertIn("体型轻巧的探险者", latest["metadata"]["providerSafePrompt"])

    def test_reference_image_task_auto_persists_visual_reference_asset(self):
        generated = {
            "previewUrl": "https://cdn.example.com/poyo-reference.png",
            "uri": "https://cdn.example.com/poyo-reference.png",
            "externalTaskId": "poyo-task-ref-1",
            "externalStatus": "finished",
            "pollAttempts": 3,
            "providerResponse": {"status": "finished", "data": {"images": [{"image_url": "https://cdn.example.com/poyo-reference.png"}]}},
        }

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(return_value=generated),
        ):
            response = self.client.post(
                "/api/prototyping/generate-reference-image",
                json={
                    "book_id": self.book_id,
                    "episode": self.episode,
                    "shot_id": str(self.shot_id),
                    "source_node_id": f"visual-scene-{self.scene_id}",
                    "source_asset_id": self.scene_id,
                    "asset_scope": "location",
                    "asset_subject": "山门夜雨",
                    "target_kind": "image",
                    "prompt": "山门夜雨参考图",
                    "aspect_ratio": "1:1",
                },
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/prototyping/tasks/{task_id}").json()
        self.assertEqual(task_payload["status"], "done")
        self.assertIsNotNone(task_payload.get("reference_asset"))
        self.assertEqual(task_payload["reference_asset"]["image_url"], "https://cdn.example.com/poyo-reference.png")

        with Session() as session:
            rows = session.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == self.book_id,
                VisualReferenceAsset.asset_type == "scene",
                VisualReferenceAsset.asset_id == self.scene_id,
                VisualReferenceAsset.image_url == "https://cdn.example.com/poyo-reference.png",
            ).all()
            self.assertEqual(len(rows), 1)

    def test_character_reference_image_task_persists_structured_prompt(self):
        structured_prompt = (
            "人物分镜精调定妆设定板，展示同一个角色在当前分镜状态下的六个视角。\n"
            "上排为脸部特写：正面、侧面、45度；\n"
            "下排为全身展示：正面、侧面、背面。"
        )
        generated = {
            "previewUrl": "https://cdn.example.com/poyo-character-reference.png",
            "uri": "https://cdn.example.com/poyo-character-reference.png",
            "externalTaskId": "poyo-task-ref-character-1",
            "externalStatus": "finished",
            "pollAttempts": 2,
            "providerResponse": {"status": "finished"},
        }

        with Session() as session:
            makeup = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Little Monk",
                visual_prompt_zh=structured_prompt,
                scene_prompt_zh="Cold stone floor and dim temple light.",
            )
            session.add(makeup)
            session.commit()
            makeup_id = str(makeup.id)

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(return_value=generated),
        ):
            response = self.client.post(
                "/api/prototyping/generate-reference-image",
                json={
                    "book_id": self.book_id,
                    "episode": self.episode,
                    "shot_id": str(self.shot_id),
                    "source_node_id": f"visual-character-{makeup_id}",
                    "source_asset_id": makeup_id,
                    "asset_scope": "character",
                    "asset_subject": "Little Monk",
                    "target_kind": "image",
                    "prompt": structured_prompt,
                    "aspect_ratio": "1:1",
                },
            )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        task_payload = self.client.get(f"/api/prototyping/tasks/{task_id}").json()
        self.assertEqual(task_payload["status"], "done")
        self.assertEqual(task_payload["reference_asset"]["prompt"], structured_prompt)

        with Session() as session:
            row = session.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == self.book_id,
                VisualReferenceAsset.asset_type == "character",
                VisualReferenceAsset.asset_id == makeup_id,
            ).order_by(VisualReferenceAsset.id.desc()).first()
            self.assertIsNotNone(row)
            self.assertEqual(row.prompt, structured_prompt)

    def test_reconcile_endpoint_recovers_finished_reference_asset_after_timeout(self):
        response = self.client.post(
            "/api/prototyping/generate-reference-image",
            json={
                "book_id": self.book_id,
                "episode": self.episode,
                "shot_id": str(self.shot_id),
                "source_node_id": f"visual-scene-{self.scene_id}",
                "source_asset_id": self.scene_id,
                "asset_scope": "location",
                "asset_subject": "灞遍棬澶滈洦",
                "target_kind": "image",
                "prompt": "灞遍棬澶滈洦鍙傝€冨浘",
                "aspect_ratio": "1:1",
            },
        )
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]

        _creative_tasks[task_id]["status"] = "error"
        _creative_tasks[task_id]["error"] = "Generation timed out. The task may still be running on the provider side."
        _creative_tasks[task_id]["provider"] = "poyo-async"
        _creative_tasks[task_id]["external_task_id"] = "poyo-task-reconcile-1"
        _creative_tasks[task_id]["external_status"] = "running"

        with patch("api.server.reconcile_poyo_generation", new=AsyncMock(return_value={
            "status": "done",
            "previewUrl": "https://cdn.example.com/poyo-reference-recovered.png",
            "uri": "https://cdn.example.com/poyo-reference-recovered.png",
            "externalTaskId": "poyo-task-reconcile-1",
            "externalStatus": "finished",
            "pollAttempts": 1,
            "providerResponse": {"status": "finished"},
        })):
            reconciled = self.client.post(f"/api/prototyping/tasks/{task_id}/reconcile")

        self.assertEqual(reconciled.status_code, 200)
        payload = reconciled.json()
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["reference_asset"]["image_url"], "https://cdn.example.com/poyo-reference-recovered.png")

    def test_reconcile_endpoint_keeps_task_running_when_provider_still_processing(self):
        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/generate-frame",
            json={},
        )
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]

        _creative_tasks[task_id]["status"] = "error"
        _creative_tasks[task_id]["error"] = "Generation timed out. The task may still be running on the provider side."
        _creative_tasks[task_id]["provider"] = "poyo-async"
        _creative_tasks[task_id]["external_task_id"] = "poyo-task-reconcile-2"
        _creative_tasks[task_id]["external_status"] = "running"

        with patch("api.server.reconcile_poyo_generation", new=AsyncMock(return_value={
            "status": "running",
            "externalTaskId": "poyo-task-reconcile-2",
            "externalStatus": "running",
            "pollAttempts": 1,
            "providerResponse": {"status": "running"},
        })):
            reconciled = self.client.post(f"/api/prototyping/tasks/{task_id}/reconcile")

        self.assertEqual(reconciled.status_code, 200)
        payload = reconciled.json()
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["external_status"], "running")

    def test_restart_endpoint_requeues_creative_task_with_original_payload(self):
        generated = {
            "previewUrl": "https://cdn.example.com/poyo-reference-retry.png",
            "uri": "https://cdn.example.com/poyo-reference-retry.png",
            "externalTaskId": "poyo-task-retry-1",
            "externalStatus": "finished",
            "pollAttempts": 2,
            "providerResponse": {"status": "finished"},
        }

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)):
            failed = self.client.post(
                "/api/prototyping/generate-reference-image",
                json={
                    "book_id": self.book_id,
                    "episode": self.episode,
                    "shot_id": str(self.shot_id),
                    "source_node_id": f"visual-scene-{self.scene_id}",
                    "source_asset_id": self.scene_id,
                    "asset_scope": "location",
                    "asset_subject": "灞遍棬澶滈洦",
                    "target_kind": "image",
                    "prompt": "灞遍棬澶滈洦鍙傝€冨浘",
                    "aspect_ratio": "1:1",
                    "simulate_error": True,
                },
            )

        self.assertEqual(failed.status_code, 200)
        failed_task_id = failed.json()["task_id"]
        failed_payload = self.client.get(f"/api/prototyping/tasks/{failed_task_id}").json()
        self.assertEqual(failed_payload["status"], "error")
        self.assertTrue(failed_payload["request_payload"]["simulate_error"])

        with patch("api.server.asyncio.sleep", new=AsyncMock(return_value=None)), patch(
            "api.server.generate_image_asset",
            new=AsyncMock(return_value=generated),
        ):
            restarted = self.client.post(f"/api/prototyping/tasks/{failed_task_id}/restart")

        self.assertEqual(restarted.status_code, 200)
        restarted_payload = restarted.json()
        self.assertEqual(restarted_payload["restarted_from_task_id"], failed_task_id)
        self.assertEqual(restarted_payload["kind"], "reference-image")
        self.assertNotEqual(restarted_payload["task_id"], failed_task_id)

        new_task_payload = self.client.get(f"/api/prototyping/tasks/{restarted_payload['task_id']}").json()
        self.assertEqual(new_task_payload["status"], "done")
        self.assertFalse(new_task_payload["request_payload"]["simulate_error"])
        self.assertEqual(new_task_payload["reference_asset"]["image_url"], "https://cdn.example.com/poyo-reference-retry.png")
        self.assertEqual(new_task_payload["restarted_from_task_id"], failed_task_id)
        self.assertEqual(new_task_payload["restart_count"], 1)
        self.assertTrue(new_task_payload["last_restarted_at"])

    def test_book_creative_tasks_endpoint_lists_recent_tasks_for_current_project(self):
        _creative_tasks["task-list-a"] = {
            "task_id": "task-list-a",
            "kind": "reference-image",
            "status": "error",
            "book_id": self.book_id,
            "episode": 1,
            "shot_id": "1",
            "created_at": "2026-07-17T10:00:00",
            "updated_at": "2026-07-17T10:05:00",
            "error": "mock failure",
        }
        _creative_tasks["task-list-b"] = {
            "task_id": "task-list-b",
            "kind": "video",
            "status": "done",
            "book_id": self.book_id,
            "episode": 1,
            "shot_id": "2",
            "created_at": "2026-07-17T11:00:00",
            "updated_at": "2026-07-17T11:05:00",
        }
        _creative_tasks["task-list-other-book"] = {
            "task_id": "task-list-other-book",
            "kind": "video",
            "status": "done",
            "book_id": self.book_id + 1,
            "episode": 1,
            "shot_id": "3",
            "created_at": "2026-07-17T12:00:00",
            "updated_at": "2026-07-17T12:05:00",
        }

        response = self.client.get(f"/api/books/{self.book_id}/creative-tasks?limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        task_ids = [item["task_id"] for item in payload["tasks"]]

        self.assertEqual(task_ids[:2], ["task-list-b", "task-list-a"])
        self.assertNotIn("task-list-other-book", task_ids)


if __name__ == "__main__":
    unittest.main()
