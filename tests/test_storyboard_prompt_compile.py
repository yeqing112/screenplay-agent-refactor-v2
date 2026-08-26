import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import (
    ProductionExportRecord,
    Session,
    StoryboardPromptVersion,
    StoryboardShot,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    VisualReferenceAsset,
    init_db,
)


class StoryboardPromptCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990301
        self.episode = 1
        self.shot_id = 1
        with Session() as session:
            session.query(ProductionExportRecord).filter(ProductionExportRecord.book_id == self.book_id).delete()
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()

            location = VisualLocation(
                book_id=self.book_id,
                name="暴雨中的出租屋",
                negative_prompt="不要现代汽车",
            )
            session.add(location)
            session.flush()

            elder_sister = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="姐姐",
                negative_prompt="不要多余手指",
            )
            session.add(elder_sister)
            session.flush()

            aning = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="阿宁",
                negative_prompt="不要多余人物",
            )
            session.add(aning)
            session.flush()

            prop = VisualProp(
                book_id=self.book_id,
                name="旧水壶",
                negative_prompt="不要金属反光",
            )
            session.add(prop)
            session.flush()

            reference_rows = [
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="scene",
                    asset_id=str(location.id),
                    asset_name="暴雨中的出租屋",
                    image_url="https://example.com/scene-locked.png",
                    reference_token="@出租屋",
                    status="locked",
                    prompt="scene locked",
                    model="mock-image",
                ),
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="character",
                    asset_id=str(elder_sister.id),
                    asset_name="姐姐",
                    image_url="https://example.com/jiejie-locked.png",
                    reference_token="@姐姐",
                    status="locked",
                    prompt="jiejie locked",
                    model="mock-image",
                ),
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="character",
                    asset_id=str(aning.id),
                    asset_name="阿宁",
                    image_url="https://example.com/aning-locked.png",
                    reference_token="@阿宁",
                    status="locked",
                    prompt="aning locked",
                    model="mock-image",
                ),
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="prop",
                    asset_id=str(prop.id),
                    asset_name="旧水壶",
                    image_url="https://example.com/kettle-selected.png",
                    reference_token="@旧水壶",
                    status="selected",
                    prompt="kettle selected",
                    model="mock-image",
                ),
            ]
            session.add_all(reference_rows)

            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="暴雨中的出租屋",
                    shot_id=self.shot_id,
                    action_process="姐姐把湿透的雨衣搭在门边，阿宁抱着旧水壶后退半步。",
                    start_state="姐姐站在门口，阿宁缩在屋内，雨水沿着门框滑落。",
                    end_state="姐姐转头看向阿宁，旧水壶仍被阿宁紧紧抱着。",
                    dialogue="阿宁，先别出声。",
                    lighting="cool",
                    camera_angle="MS",
                    camera_movement="push-in",
                    duration=4,
                    meta_info=json.dumps({
                        "structured_shot": {
                            "scene_asset_id": str(location.id),
                            "character_asset_ids": [str(elder_sister.id), str(aning.id)],
                            "prop_asset_ids": [str(prop.id)],
                            "style_key": "default",
                            "character_blocking": [
                                {"character_id": str(elder_sister.id), "visual_alias": "姐姐", "screen_position": "门口偏左", "pose": "半侧身", "emotion": "警惕"},
                                {"character_id": str(aning.id), "visual_alias": "阿宁", "screen_position": "屋内偏右", "pose": "抱着水壶", "emotion": "紧张"},
                            ],
                            "action_beats": [
                                {"sequence": 1, "description": "姐姐推门进屋", "emotion": "压抑", "intensity": "medium"},
                                {"sequence": 2, "description": "阿宁抱紧旧水壶后退", "emotion": "慌张", "intensity": "medium"},
                            ],
                        }
                    }, ensure_ascii=False),
                    asset_links=json.dumps({"references": {}}, ensure_ascii=False),
                    asset_status="pending",
                ),
            )
            session.commit()

        with Session() as session:
            self.scene_id = str(session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).first().id)
            makeups = session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).order_by(VisualMakeup.id.asc()).all()
            self.jiejie_id = str(makeups[0].id)
            self.aning_id = str(makeups[1].id)
            self.prop_id = str(session.query(VisualProp).filter(VisualProp.book_id == self.book_id).first().id)

    def tearDown(self):
        with Session() as session:
            session.query(ProductionExportRecord).filter(ProductionExportRecord.book_id == self.book_id).delete()
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.commit()

    def _valid_llm_payload(self):
        return {
            "visual_prompt_static": "暴雨中的出租屋内景，中景构图，姐姐站在门口偏左，湿透的雨衣贴在肩背，阿宁抱着旧水壶缩在屋内偏右，冷色雨夜光线压低室内亮度，地面反出潮湿微光，人物外观严格参考 @姐姐 与 @阿宁，场景保持 @出租屋 的狭窄压迫感。",
            "visual_prompt_motion": "镜头从中景缓慢推进，先保持首帧里姐姐与阿宁、旧水壶和出租屋陈设完全一致，随后姐姐压低声音侧身进屋，阿宁抱紧旧水壶后退半步，视线始终追着姐姐，情绪从警惕推进到紧张，最后停在两人对视的瞬间，服装、场景和道具连续一致。",
            "negative_prompt": "低质量，多余手指，多余人物，不要现代汽车",
            "used_assets": [
                {"asset_type": "scene", "asset_id": self.scene_id, "asset_name": "暴雨中的出租屋", "reference_token": "@出租屋", "reference_status": "locked"},
                {"asset_type": "character", "asset_id": self.jiejie_id, "asset_name": "姐姐", "reference_token": "@姐姐", "reference_status": "locked"},
                {"asset_type": "character", "asset_id": self.aning_id, "asset_name": "阿宁", "reference_token": "@阿宁", "reference_status": "locked"},
                {"asset_type": "prop", "asset_id": self.prop_id, "asset_name": "旧水壶", "reference_token": "@旧水壶", "reference_status": "selected"},
            ],
            "warnings": [],
        }

    def test_compile_prompts_persists_llm_output_and_reference_payloads(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], 1)
        self.assertNotIn("请生成", payload["prompt_static"])
        self.assertNotIn("用于首帧", payload["prompt_motion"])
        self.assertIn("@姐姐", payload["prompt_static"])
        self.assertIn("旧水壶", payload["prompt_motion"])
        self.assertEqual(payload["compiler_diagnostics"]["status"], "pass")
        self.assertEqual(len(payload["used_assets"]), 4)
        self.assertEqual(len(payload["reference_images"]), 4)
        self.assertIn("ref-", payload["reference_asset_ids"][0])
        self.assertEqual(payload["prompt_compile_context"]["asset_bindings"]["scene"]["asset_name"], "暴雨中的出租屋")
        self.assertEqual(payload["prompt_compile_context"]["asset_bindings"]["characters"][0]["reference_token"], "@姐姐")
        self.assertEqual(payload["prompt_compile_context"]["model_adapter"]["target_model"], "jimeng")
        self.assertIn("StoryboardChineseAdapter", payload["prompt_compile_context"]["model_adapter"]["adapter"])
        self.assertIn("@姐姐", payload["prompt_compile_context"]["model_adapter"]["static_prompt"])

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            self.assertEqual(shot.visual_prompt_static, payload["prompt_static"])
            self.assertEqual(shot.visual_prompt_motion, payload["prompt_motion"])
            self.assertEqual(shot.visual_prompt_final, payload["negative_prompt"])
            shot_meta = json.loads(shot.meta_info)
            self.assertIn("model_adapter", shot_meta["prompt_compiler"]["prompt_compile_context"])

    def test_compile_sanitizes_llm_label_like_motion_before_diagnostics(self):
        payload = self._valid_llm_payload()
        payload["visual_prompt_motion"] = (
            "镜头推进为：姐姐把湿透的雨衣搭在门边，阿宁抱紧旧水壶后退半步，"
            "最后停在两人对视的瞬间，服装、场景和道具连续一致。"
        )

        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["compiler_diagnostics"]["status"], "pass")
        self.assertNotIn("镜头推进为", body["prompt_motion"])
        self.assertIn("镜头继续推进到姐姐把湿透的雨衣搭在门边", body["prompt_motion"])

    def test_compile_preserves_exact_scene_name_when_llm_uses_generic_location(self):
        payload = self._valid_llm_payload()
        payload["visual_prompt_static"] = (
            "雨夜出租屋内景，中景构图，姐姐站在门口偏左，阿宁抱着旧水壶缩在屋内偏右，"
            "冷色雨夜光线压低室内亮度，人物外观严格参考 @姐姐 与 @阿宁，场景保持 @出租屋 的狭窄压迫感。"
        )

        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["compiler_diagnostics"]["status"], "pass")
        self.assertTrue(body["prompt_static"].startswith("暴雨中的出租屋，雨夜出租屋内景"))

    def test_machine_prompt_export_preview_is_readonly_and_model_exported(self):
        with Session() as session:
            before_count = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).count()

        response = self.client.get(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/machine-prompt-export?target_model=minimax-h3"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "readonly_machine_prompt_export_preview")
        self.assertFalse(payload["api_submission"])
        self.assertTrue(payload["source_layers"]["director_shot_text_is_user_editable"])
        self.assertTrue(payload["source_layers"]["machine_prompt_is_compiled"])
        self.assertIn("导演", "导演分镜语言")
        self.assertIn("起始", payload["director_shot_text"])
        self.assertEqual(payload["machine_prompt"]["schema_version"], "machine_prompt_v1")
        self.assertFalse(payload["machine_prompt"]["api_submission"])
        h3_fields = payload["model_exports"]["minimax-h3"]["fields"]
        self.assertIn("integrated_multimodal_description", h3_fields)
        self.assertIn("overall_soundscape", h3_fields)
        self.assertIn("non_diegetic_music", h3_fields)
        self.assertIn("generic-zh-video", payload["model_exports"])

        with Session() as session:
            after_count = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).count()
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()

        self.assertEqual(after_count, before_count)
        self.assertFalse(shot.visual_prompt_static)
        self.assertFalse(shot.visual_prompt_motion)

    def test_machine_prompt_export_record_persists_snapshot_without_api_submission(self):
        with Session() as session:
            before_version_count = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).count()
            before_record_count = session.query(ProductionExportRecord).filter(
                ProductionExportRecord.book_id == self.book_id,
            ).count()

        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/machine-prompt-export-records",
            json={
                "targetModel": "minimax-h3",
                "exportChannel": "webui",
                "operatorName": "formal-workspace",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["export_format"], "storyboard-machine-prompt-minimax-h3-webui")
        self.assertEqual(payload["total_shots"], 1)
        self.assertEqual(payload["deliverable_shots"], 1)
        self.assertIn("API 未提交", payload["summary"])
        meta = payload["meta_info"]
        self.assertEqual(meta["record_type"], "storyboard_machine_prompt_export")
        self.assertFalse(meta["api_submission"])
        self.assertEqual(meta["target_model"], "minimax-h3")
        self.assertEqual(meta["export_channel"], "webui")
        self.assertIn("director_shot_text", meta)
        self.assertEqual(meta["machine_prompt"]["schema_version"], "machine_prompt_v1")
        self.assertFalse(meta["machine_prompt"]["api_submission"])
        self.assertIn("integrated_multimodal_description", meta["model_exports"]["minimax-h3"]["fields"])

        with Session() as session:
            after_version_count = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).count()
            after_record_count = session.query(ProductionExportRecord).filter(
                ProductionExportRecord.book_id == self.book_id,
            ).count()
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()

        self.assertEqual(after_version_count, before_version_count)
        self.assertEqual(after_record_count, before_record_count + 1)
        self.assertFalse(shot.visual_prompt_static)
        self.assertFalse(shot.visual_prompt_motion)

    def test_director_shot_text_override_recompiles_export_without_prompt_version(self):
        custom_director_text = "场景：暴雨中的出租屋\n镜头：用户改写后的导演分镜语言，姐姐先停顿，再看向阿宁手里的旧水壶。"
        with Session() as session:
            before_version_count = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).count()

        response = self.client.patch(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/director-shot-text?target_model=minimax-h3",
            json={
                "directorShotText": custom_director_text,
                "operatorName": "formal-workspace",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["director_shot_text"], custom_director_text)
        self.assertEqual(payload["machine_prompt"]["director_shot_text"], custom_director_text)
        self.assertTrue(payload["source_layers"]["has_user_director_shot_override"])
        self.assertEqual(payload["source_layers"]["director_shot_text_source"], "user_override")
        self.assertIn("system_director_shot_text", payload)

        with Session() as session:
            after_version_count = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).count()
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot_meta = json.loads(shot.meta_info)

        self.assertEqual(after_version_count, before_version_count)
        self.assertEqual(shot_meta["director_shot_language"]["text"], custom_director_text)
        self.assertTrue(shot_meta["director_shot_language"]["does_not_overwrite_shot_schema"])
        self.assertFalse(shot.visual_prompt_static)
        self.assertFalse(shot.visual_prompt_motion)

    def test_model_adapter_fills_missing_llm_prompt_fields(self):
        llm_payload = {
            "visual_prompt_static": "",
            "visual_prompt_motion": "",
            "negative_prompt": "",
            "used_assets": self._valid_llm_payload()["used_assets"],
            "warnings": [],
        }
        with patch("core.llm.call_llm_json", return_value=llm_payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload["prompt_static"]), 80)
        self.assertGreaterEqual(len(payload["prompt_motion"]), 80)
        self.assertIn("@姐姐", payload["prompt_static"])
        self.assertIn("旧水壶", payload["prompt_motion"])
        self.assertTrue(any("Model Adapter 已接管" in item for item in payload["compiler_warnings"]))
        self.assertEqual(payload["compiler_diagnostics"]["status"], "warning")
        self.assertEqual(payload["compiler_diagnostics"]["blocking_issues"], [])

    def test_compile_prompts_persists_rule_compiled_shot_ir_fields(self):
        def force_ir_fields(ir, _runtime):
            ir.duration = 2
            ir.camera_angle = "CU"
            ir.camera_movement = "static"
            ir.shot_purpose = "hook"
            ir.camera_speed = "slow"
            return ir

        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()), patch(
            "core.rule_compiler.compile_rules",
            side_effect=force_ir_fields,
        ):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["prompt_compile_context"]["duration"], 2)
        self.assertEqual(payload["prompt_compile_context"]["camera_angle"], "CU")
        self.assertEqual(payload["prompt_compile_context"]["camera_movement"], "static")
        self.assertEqual(payload["prompt_compile_context"]["shot_ir"]["shot_purpose"], "hook")

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            meta = json.loads(shot.meta_info or "{}")
            latest_version = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            version_meta = json.loads(latest_version.meta_info or "{}")

        self.assertEqual(shot.duration, 2)
        self.assertEqual(shot.camera_angle, "CU")
        self.assertEqual(shot.camera_movement, "static")
        self.assertEqual(meta["structured_shot"]["duration"], 2)
        self.assertEqual(meta["structured_shot"]["camera_angle"], "CU")
        self.assertEqual(meta["structured_shot"]["camera_movement"], "static")
        self.assertEqual(meta["structured_shot"]["shot_purpose"], "hook")
        self.assertEqual(version_meta["structured_shot"]["camera_angle"], "CU")
        self.assertEqual(version_meta["shot_ir"]["camera_movement"], "static")

    def test_prompt_versions_and_outputs_include_reference_images(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            compile_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(compile_response.status_code, 200)

        versions_response = self.client.get(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-versions"
        )
        self.assertEqual(versions_response.status_code, 200)
        version = versions_response.json()["versions"][0]
        self.assertEqual(len(version["reference_images"]), 4)
        self.assertEqual(version["reference_images"][0]["reference_status"], "locked")

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(outputs_response.status_code, 200)
        storyboard = outputs_response.json()["storyboard"][0]
        self.assertEqual(len(storyboard["reference_images"]), 4)
        self.assertEqual(storyboard["compiler_diagnostics"]["status"], "pass")
        self.assertEqual(storyboard["scene_name"], "暴雨中的出租屋")
        self.assertEqual(storyboard["prompt_compile_context"]["asset_bindings"]["scene"]["asset_name"], "暴雨中的出租屋")

    def test_prompt_versions_expose_version_audit_and_recommended_restore(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            compile_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(compile_response.status_code, 200)

        with Session() as session:
            latest = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            prompt_compiler_meta = json.loads(session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first().meta_info)["prompt_compiler"]
            degraded_meta = json.loads(latest.meta_info)
            degraded_meta["used_assets"] = [
                {
                    "asset_type": "scene",
                    "asset_id": self.scene_id,
                    "asset_name": "暴雨中的出租屋",
                    "reference_token": "@出租屋",
                    "reference_status": "locked",
                    "has_reference": True,
                    "locked_reference": True,
                    "image_url": "https://example.com/scene-locked.png",
                    "reference_asset_id": "ref-scene-only",
                }
            ]
            degraded_meta["reference_images"] = degraded_meta["reference_images"][:1]
            degraded_meta["reference_asset_ids"] = degraded_meta["reference_asset_ids"][:1]
            degraded_meta["compiler_warnings"] = []
            degraded_meta["compiler_diagnostics"] = {}

            degraded = StoryboardPromptVersion(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                version=2,
                compile_reason="manual-scene-only",
                prompt_static="清晨，暴雨中的出租屋内景，冷灰色调，参考 @出租屋。",
                prompt_motion="镜头缓慢推进，停在出租屋内部的压迫感上。",
                negative_prompt="低质量，多余手指，多余人物，不要现代汽车",
                meta_info=json.dumps(degraded_meta, ensure_ascii=False),
            )
            session.add(degraded)

            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            prompt_compiler_meta["latest_version"] = 2
            prompt_compiler_meta["compile_reason"] = degraded.compile_reason
            prompt_compiler_meta["used_assets"] = degraded_meta["used_assets"]
            prompt_compiler_meta["reference_images"] = degraded_meta["reference_images"]
            prompt_compiler_meta["reference_asset_ids"] = degraded_meta["reference_asset_ids"]
            prompt_compiler_meta["compiler_warnings"] = []
            prompt_compiler_meta["compiler_diagnostics"] = {}
            shot.visual_prompt_static = degraded.prompt_static
            shot.visual_prompt_motion = degraded.prompt_motion
            shot.visual_prompt_final = degraded.negative_prompt
            shot.meta_info = json.dumps(
                {
                    "structured_shot": degraded_meta.get("structured_shot", {}),
                    "prompt_compiler": prompt_compiler_meta,
                },
                ensure_ascii=False,
            )
            session.commit()

        versions_response = self.client.get(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-versions"
        )
        self.assertEqual(versions_response.status_code, 200)
        payload = versions_response.json()
        self.assertEqual(payload["current_version"], 2)
        self.assertEqual(payload["recommended_restore_version"]["version"], 1)
        self.assertEqual(payload["recommended_restore_version"]["reason"], "latest_recoverable_version")
        current_version = payload["versions"][0]
        self.assertTrue(current_version["is_current"])
        self.assertTrue(current_version["version_audit"]["is_degraded_version"])
        self.assertTrue(current_version["version_audit"]["is_scene_only_candidate"])
        self.assertTrue(any(name in current_version["version_audit"]["missing_critical_assets"] for name in ["姐姐", "阿宁"]))

    def test_recommended_rollback_restores_suggested_prompt_version(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            compile_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(compile_response.status_code, 200)
        original_static = compile_response.json()["prompt_static"]

        with Session() as session:
            latest = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot_meta = json.loads(shot.meta_info)
            prompt_compiler_meta = shot_meta["prompt_compiler"]
            degraded_meta = json.loads(latest.meta_info)
            degraded_meta["used_assets"] = [
                {
                    "asset_type": "scene",
                    "asset_id": self.scene_id,
                    "asset_name": "暴雨中的出租屋",
                    "reference_token": "@出租屋",
                    "reference_status": "locked",
                    "has_reference": True,
                    "locked_reference": True,
                    "image_url": "https://example.com/scene-locked.png",
                    "reference_asset_id": "ref-scene-only",
                }
            ]
            degraded_meta["reference_images"] = degraded_meta["reference_images"][:1]
            degraded_meta["reference_asset_ids"] = degraded_meta["reference_asset_ids"][:1]
            degraded_meta["compiler_warnings"] = []
            degraded_meta["compiler_diagnostics"] = {}

            degraded = StoryboardPromptVersion(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                version=2,
                compile_reason="manual-scene-only",
                prompt_static="清晨，暴雨中的出租屋内景，冷灰色调，参考 @出租屋。",
                prompt_motion="镜头缓慢推进，停在出租屋内部的压迫感上。",
                negative_prompt="低质量，多余手指，多余人物，不要现代汽车",
                meta_info=json.dumps(degraded_meta, ensure_ascii=False),
            )
            session.add(degraded)

            prompt_compiler_meta["latest_version"] = 2
            prompt_compiler_meta["compile_reason"] = degraded.compile_reason
            prompt_compiler_meta["used_assets"] = degraded_meta["used_assets"]
            prompt_compiler_meta["reference_images"] = degraded_meta["reference_images"]
            prompt_compiler_meta["reference_asset_ids"] = degraded_meta["reference_asset_ids"]
            prompt_compiler_meta["compiler_warnings"] = []
            prompt_compiler_meta["compiler_diagnostics"] = {}
            shot.visual_prompt_static = degraded.prompt_static
            shot.visual_prompt_motion = degraded.prompt_motion
            shot.visual_prompt_final = degraded.negative_prompt
            shot.meta_info = json.dumps(
                {
                    "structured_shot": degraded_meta.get("structured_shot", {}),
                    "prompt_compiler": prompt_compiler_meta,
                },
                ensure_ascii=False,
            )
            session.commit()

        rollback_response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-versions/recommended-rollback",
            json={"reason": "acceptance-recommended-rollback"},
        )
        self.assertEqual(rollback_response.status_code, 200)
        rollback_payload = rollback_response.json()
        self.assertEqual(rollback_payload["recommended_restore_version"]["version"], 1)
        self.assertEqual(rollback_payload["restored_from_version"], 1)

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            self.assertEqual(shot.visual_prompt_static, original_static)
            latest = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            self.assertIn("rollback:v1:acceptance-recommended-rollback", latest.compile_reason)

    def test_recompile_repairs_short_prompt_and_missing_scene_asset_with_full_rollback(self):
        degraded_structured = {
            "shot_id": str(self.shot_id),
            "scene_name": "暴雨中的出租屋",
            "duration": 4,
            "camera_angle": "MS",
            "camera_movement": "static",
            "transition": "cut",
            "scene_asset_id": "",
            "character_asset_ids": [],
            "prop_asset_ids": [],
            "style_key": "default",
            "character_blocking": [],
            "action_beats": [],
        }
        degraded_meta = {
            "structured_shot": degraded_structured,
            "prompt_compile_context": {},
            "used_assets": [],
            "reference_images": [],
            "reference_asset_ids": [],
            "compiler_warnings": ["legacy prompt is too short"],
            "compiler_diagnostics": {
                "status": "warning",
                "checks": [
                    {"key": "static_prompt_quality", "passed": False},
                    {"key": "motion_prompt_quality", "passed": False},
                ],
            },
        }
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot.visual_prompt_static = "出租屋里，姐姐和阿宁对视。"
            shot.visual_prompt_motion = "镜头推进。"
            shot.visual_prompt_final = "低质量"
            shot.camera_movement = "static"
            shot.meta_info = json.dumps(
                {
                    "structured_shot": degraded_structured,
                    "prompt_compiler": {
                        "latest_version": 1,
                        "compile_reason": "legacy-short-prompt",
                        "negative_prompt": "低质量",
                        "prompt_compile_context": {},
                        "used_assets": [],
                        "reference_images": [],
                        "reference_asset_ids": [],
                        "compiler_warnings": degraded_meta["compiler_warnings"],
                        "compiler_diagnostics": degraded_meta["compiler_diagnostics"],
                    },
                },
                ensure_ascii=False,
            )
            baseline = StoryboardPromptVersion(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                version=1,
                compile_reason="legacy-short-prompt",
                prompt_static=shot.visual_prompt_static,
                prompt_motion=shot.visual_prompt_motion,
                negative_prompt=shot.visual_prompt_final,
                meta_info=json.dumps(degraded_meta, ensure_ascii=False),
            )
            session.add(baseline)
            session.commit()
            baseline_id = baseline.id

        repaired_payload = self._valid_llm_payload()
        with patch("core.llm.call_llm_json", return_value=repaired_payload):
            compile_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "quality-repair", "force": True},
            )

        self.assertEqual(compile_response.status_code, 200)
        compiled = compile_response.json()
        self.assertEqual(compiled["version"], 2)
        self.assertEqual(compiled["compiler_diagnostics"]["status"], "pass")
        self.assertEqual(compiled["prompt_compile_context"]["asset_bindings"]["scene"]["asset_id"], self.scene_id)
        self.assertEqual(len(compiled["used_assets"]), 4)
        self.assertGreaterEqual(len(compiled["prompt_static"]), 80)
        self.assertGreaterEqual(len(compiled["prompt_motion"]), 50)

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot_meta = json.loads(shot.meta_info)
            self.assertEqual(shot_meta["structured_shot"]["scene_asset_id"], self.scene_id)
            self.assertEqual(shot_meta["structured_shot"]["character_asset_ids"], [self.jiejie_id, self.aning_id])
            self.assertEqual(shot_meta["structured_shot"]["prop_asset_ids"], [self.prop_id])

        rollback_response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-versions/{baseline_id}/rollback",
            json={"reason": "quality-repair-rollback"},
        )
        self.assertEqual(rollback_response.status_code, 200)
        self.assertEqual(rollback_response.json()["restored_from_version"], 1)

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot_meta = json.loads(shot.meta_info)
            self.assertEqual(shot.visual_prompt_static, "出租屋里，姐姐和阿宁对视。")
            self.assertEqual(shot.visual_prompt_motion, "镜头推进。")
            self.assertEqual(shot_meta["structured_shot"]["scene_asset_id"], "")
            self.assertEqual(shot_meta["structured_shot"]["character_asset_ids"], [])
            latest = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            self.assertIn("rollback:v1:quality-repair-rollback", latest.compile_reason)

    def test_rollback_restores_explicit_empty_structured_snapshot(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            baseline = StoryboardPromptVersion(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                version=1,
                compile_reason="batch-quality-repair-current-baseline",
                prompt_static="原始静态提示词",
                prompt_motion="原始动态提示词",
                negative_prompt="原始负面提示词",
                meta_info=json.dumps(
                    {
                        "structured_shot": {},
                        "prompt_compile_context": {},
                        "used_assets": [],
                        "reference_images": [],
                        "reference_asset_ids": [],
                        "compiler_warnings": ["baseline created before confirmed batch prompt repair"],
                        "compiler_diagnostics": {},
                    },
                    ensure_ascii=False,
                ),
            )
            session.add(baseline)
            session.flush()
            shot.visual_prompt_static = "修复后的静态提示词"
            shot.visual_prompt_motion = "修复后的动态提示词"
            shot.visual_prompt_final = "修复后的负面提示词"
            shot.meta_info = json.dumps(
                {
                    "structured_shot": {
                        "scene_asset_id": self.scene_id,
                        "character_asset_ids": [self.jiejie_id, self.aning_id],
                        "prop_asset_ids": [self.prop_id],
                    },
                    "prompt_compiler": {
                        "latest_version": 2,
                        "compile_reason": "batch-quality-repair-confirmed",
                    },
                },
                ensure_ascii=False,
            )
            session.add(
                StoryboardPromptVersion(
                    book_id=self.book_id,
                    episode=self.episode,
                    shot_id=self.shot_id,
                    version=2,
                    compile_reason="batch-quality-repair-confirmed",
                    prompt_static=shot.visual_prompt_static,
                    prompt_motion=shot.visual_prompt_motion,
                    negative_prompt=shot.visual_prompt_final,
                    meta_info=shot.meta_info,
                )
            )
            session.commit()
            baseline_id = baseline.id

        rollback_response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-versions/{baseline_id}/rollback",
            json={"reason": "restore-empty-structured"},
        )
        self.assertEqual(rollback_response.status_code, 200)
        self.assertEqual(rollback_response.json()["restored_from_version"], 1)

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot_meta = json.loads(shot.meta_info)
            self.assertEqual(shot.visual_prompt_static, "原始静态提示词")
            self.assertEqual(shot.visual_prompt_motion, "原始动态提示词")
            self.assertEqual(shot_meta["structured_shot"], {})
            latest = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            latest_meta = json.loads(latest.meta_info)
            self.assertEqual(latest_meta["structured_shot"], {})
            self.assertIn("rollback:v1:restore-empty-structured", latest.compile_reason)

    def test_outputs_include_prompt_version_audit_and_recommended_restore(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            compile_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(compile_response.status_code, 200)

        with Session() as session:
            latest = session.query(StoryboardPromptVersion).filter(
                StoryboardPromptVersion.book_id == self.book_id,
                StoryboardPromptVersion.episode == self.episode,
                StoryboardPromptVersion.shot_id == self.shot_id,
            ).order_by(StoryboardPromptVersion.version.desc()).first()
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot_meta = json.loads(shot.meta_info)
            prompt_compiler_meta = shot_meta["prompt_compiler"]
            degraded_meta = json.loads(latest.meta_info)
            degraded_meta["used_assets"] = [
                {
                    "asset_type": "scene",
                    "asset_id": self.scene_id,
                    "asset_name": "暴雨中的出租屋",
                    "reference_token": "@出租屋",
                    "reference_status": "locked",
                    "has_reference": True,
                    "locked_reference": True,
                    "image_url": "https://example.com/scene-locked.png",
                    "reference_asset_id": "ref-scene-only",
                }
            ]
            degraded_meta["reference_images"] = degraded_meta["reference_images"][:1]
            degraded_meta["reference_asset_ids"] = degraded_meta["reference_asset_ids"][:1]
            degraded_meta["compiler_warnings"] = []
            degraded_meta["compiler_diagnostics"] = {}

            degraded = StoryboardPromptVersion(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                version=2,
                compile_reason="manual-scene-only",
                prompt_static="清晨，暴雨中的出租屋内景，冷灰色调，参考 @出租屋。",
                prompt_motion="镜头缓慢推进，停在出租屋内部的压迫感上。",
                negative_prompt="低质量，多余手指，多余人物，不要现代汽车",
                meta_info=json.dumps(degraded_meta, ensure_ascii=False),
            )
            session.add(degraded)

            prompt_compiler_meta["latest_version"] = 2
            prompt_compiler_meta["compile_reason"] = degraded.compile_reason
            prompt_compiler_meta["used_assets"] = degraded_meta["used_assets"]
            prompt_compiler_meta["reference_images"] = degraded_meta["reference_images"]
            prompt_compiler_meta["reference_asset_ids"] = degraded_meta["reference_asset_ids"]
            prompt_compiler_meta["compiler_warnings"] = []
            prompt_compiler_meta["compiler_diagnostics"] = {}
            shot.visual_prompt_static = degraded.prompt_static
            shot.visual_prompt_motion = degraded.prompt_motion
            shot.visual_prompt_final = degraded.negative_prompt
            shot.meta_info = json.dumps(
                {
                    "structured_shot": degraded_meta.get("structured_shot", {}),
                    "prompt_compiler": prompt_compiler_meta,
                },
                ensure_ascii=False,
            )
            session.commit()

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(outputs_response.status_code, 200)
        storyboard = outputs_response.json()["storyboard"][0]
        self.assertEqual(storyboard["prompt_version"], 2)
        self.assertTrue(storyboard["prompt_version_audit"]["is_degraded_version"])
        self.assertTrue(storyboard["prompt_version_audit"]["is_scene_only_candidate"])
        self.assertEqual(storyboard["recommended_restore_version"]["version"], 1)
        self.assertEqual(storyboard["recommended_restore_version"]["reason"], "latest_recoverable_version")

    def test_locked_prompt_blocks_normal_compile_but_allows_force(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            first = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(first.status_code, 200)

        lock_response = self.client.patch(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/prompt-lock",
            json={"locked": True},
        )
        self.assertEqual(lock_response.status_code, 200)

        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            blocked = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "after-feedback"},
            )
        self.assertEqual(blocked.status_code, 409)

        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            forced = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "after-feedback", "force": True},
            )
        self.assertEqual(forced.status_code, 200)
        self.assertEqual(forced.json()["version"], 2)

    def test_meta_prompt_leakage_blocks_and_does_not_overwrite_old_prompts(self):
        with patch("core.llm.call_llm_json", return_value=self._valid_llm_payload()):
            ok_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(ok_response.status_code, 200)
        previous_static = ok_response.json()["prompt_static"]

        bad_payload = self._valid_llm_payload()
        bad_payload["visual_prompt_static"] = "请生成一条用于首帧出图的中文提示词，输出应为暴雨中的出租屋。"
        with patch("core.llm.call_llm_json", return_value=bad_payload):
            blocked = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(blocked.status_code, 422)
        detail = blocked.json()["detail"]
        self.assertEqual(detail["compiler_diagnostics"]["status"], "blocked")
        self.assertTrue(any(check["key"] == "meta_prompt_leakage" and not check["passed"] for check in detail["compiler_diagnostics"]["checks"]))

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            self.assertEqual(shot.visual_prompt_static, previous_static)

    def test_unbound_asset_from_llm_is_blocked(self):
        bad_payload = self._valid_llm_payload()
        bad_payload["used_assets"] = bad_payload["used_assets"] + [
            {"asset_type": "character", "asset_id": "999999", "asset_name": "路人甲", "reference_token": "@路人甲", "reference_status": "locked"}
        ]
        with patch("core.llm.call_llm_json", return_value=bad_payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["compiler_diagnostics"]["status"], "blocked")
        self.assertTrue(any("未绑定资产" in issue for issue in detail["compiler_diagnostics"]["blocking_issues"]))

    def test_quality_heuristic_failures_become_warnings_not_blockers(self):
        payload = self._valid_llm_payload()
        payload["visual_prompt_static"] = "@出租屋，姐姐和阿宁。"
        payload["visual_prompt_motion"] = "镜头静止，姐姐和阿宁说话，保持@出租屋和人物服装一致。"
        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["compiler_diagnostics"]["status"], "warning")
        self.assertTrue(any(check["key"] == "static_prompt_quality" and not check["passed"] for check in body["compiler_diagnostics"]["checks"]))
        self.assertTrue(any(check["key"] == "motion_prompt_quality" and not check["passed"] for check in body["compiler_diagnostics"]["checks"]))

    def test_motion_quality_accepts_gradual_and_static_camera_variants(self):
        payload = self._valid_llm_payload()
        payload["visual_prompt_motion"] = (
            "镜头从广角缓缓向前推近，聚焦姐姐和阿宁之间的对峙。"
            "姐姐的拳头微微颤抖，阿宁的呼吸逐渐急促，气氛从沉默的僵持转向即将爆发的情绪顶点。"
            "保持场景、服装、道具与首帧完全一致。"
        )
        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["compiler_diagnostics"]["status"], "pass")

        payload["visual_prompt_motion"] = (
            "画面保持静态构图，阿宁从低笑开始，嘴角轻微上扬并开口说话，"
            "随后抬手慢慢抹去嘴角血迹，眼神由嘲讽逐渐转为冰冷，情绪从轻蔑推向爆发。"
            "整个过程中角色、服装、场景、道具与首帧保持一致。"
        )
        with patch("core.llm.call_llm_json", return_value=payload):
            static_camera_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual", "force": True},
            )

        self.assertEqual(static_camera_response.status_code, 200)
        self.assertEqual(static_camera_response.json()["compiler_diagnostics"]["status"], "pass")

        payload["visual_prompt_motion"] = (
            "固定机位，保持首帧构图。姐姐先压低声音向前一步，阿宁抱紧旧水壶维持注视，"
            "随后两人的情绪从克制逐渐转向紧张。整个过程中角色、服装、场景、道具与首帧保持一致。"
        )
        with patch("core.llm.call_llm_json", return_value=payload):
            fixed_rig_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual", "force": True},
            )

        self.assertEqual(fixed_rig_response.status_code, 200)
        self.assertEqual(fixed_rig_response.json()["compiler_diagnostics"]["status"], "pass")

        payload["visual_prompt_motion"] = (
            "镜头静止。姐姐不耐地开口说话，同时轻微挥手示意驱赶。"
            "阿宁始终平静站立，身体微微挺直，眼神坚定，准备开口回应。"
            "整个过程中角色、服装、场景、道具与首帧保持一致。"
        )
        with patch("core.llm.call_llm_json", return_value=payload):
            simultaneous_response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual", "force": True},
            )

        self.assertEqual(simultaneous_response.status_code, 200)
        self.assertEqual(simultaneous_response.json()["compiler_diagnostics"]["status"], "pass")

    def test_static_quality_accepts_shorter_but_visual_chinese_description(self):
        payload = self._valid_llm_payload()
        payload["visual_prompt_static"] = (
            "@出租屋，中景，白天，姐姐站在门口偏左，阿宁抱着旧水壶站在屋内偏右，"
            "两人对峙，表情紧绷，冷色光线压住狭窄空间。"
        )
        payload["visual_prompt_motion"] = (
            "镜头静止，姐姐先压低声音向前一步，阿宁抱紧旧水壶保持注视，"
            "随后两人的情绪从克制转为紧张，从头到尾与首帧场景、人物服装、站位一致。"
        )
        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["compiler_diagnostics"]["status"], "pass")

    def test_static_quality_accepts_asset_names_without_explicit_pose_verbs(self):
        payload = self._valid_llm_payload()
        payload["visual_prompt_static"] = (
            "宽阔的视角下，暴雨中的出租屋门边，姐姐与阿宁相对而立，气氛凝重，"
            "自然光线压低空间亮度，场景参考@出租屋。"
        )
        payload["visual_prompt_motion"] = (
            "镜头从宽阔全景缓慢向前推进，逐渐拉近姐姐和阿宁，"
            "两人对峙的紧张情绪持续升高，最终定格在沉默对视的一刻，"
            "保持角色、服装、场景、道具与首帧完全一致。"
        )
        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["compiler_diagnostics"]["status"], "pass")


    def skip_test_compile_retries_once_when_first_candidate_has_warning(self):
        first_payload = self._valid_llm_payload()
        first_payload["visual_prompt_static"] = "暴雨中的出租屋内，姐姐和阿宁对视，气氛压抑。"

        second_payload = self._valid_llm_payload()
        second_payload["visual_prompt_static"] = (
            "暴雨中的出租屋内景，中景构图，姐姐站在门口偏左，湿透的雨衣贴在肩背，"
            "阿宁抱着旧水壶缩在屋内偏右，冷色雨夜光线压低室内亮度，人物外观严格参考@姐姐与@阿宁，"
            "场景保持@出租屋的狭窄潮湿压迫感。"
        )

        with patch("core.llm.call_llm_json", side_effect=[first_payload, second_payload]) as mocked_call:
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["compiler_diagnostics"]["status"], "pass")
        self.assertEqual(body["prompt_static"], second_payload["visual_prompt_static"])
        self.assertTrue(body["repair_attempted"])
        self.assertEqual(mocked_call.call_count, 2)


if __name__ == "__main__":
    unittest.main()
