import unittest

from core.machine_prompt import (
    build_director_shot_text,
    compile_machine_prompt,
    export_generic_zh_video_webui,
    export_minimax_h3_webui,
)
from core.prompt_ir import AssetBinding, EmotionArc, ShotIR


class MachinePromptExportTests(unittest.TestCase):
    def _shot_ir(self) -> ShotIR:
        return ShotIR(
            shot_id=7,
            scene_name="深夜便利店监控室",
            duration=5,
            camera_angle="CU",
            camera_movement="push-in",
            camera_speed="slow",
            shot_purpose="suspense",
            emotion_arc=EmotionArc(start="疑惑", end="警觉", intensity="medium"),
            start_state="监控屏幕显示收银台空无一人，咖啡杯印留在台面。",
            action_process="屏幕噪点闪烁，旧照片折角的轮廓在杯印旁逐渐显露。",
            end_state="照片边缘变清楚，监控室冷光压住画面。",
            dialogue="只有电流声和远处冰柜低鸣。",
            lighting="监控屏冷光与房间暗部形成强反差",
            scene_binding=AssetBinding(
                asset_type="scene",
                asset_id="159",
                asset_name="深夜便利店监控室",
                reference_token="@监控室",
                reference_status="selected",
                authority_prompt_raw="窄小监控室，多块屏幕，冷蓝色电子光，杂乱桌面",
            ),
            prop_bindings=[
                AssetBinding(
                    asset_type="prop",
                    asset_id="8",
                    asset_name="旧照片",
                    reference_token="@旧照片",
                    authority_prompt_raw="折角旧照片，边缘泛黄，藏在杯印旁",
                )
            ],
        )

    def test_director_text_is_human_readable_and_user_editable_layer(self):
        text = build_director_shot_text(self._shot_ir())

        self.assertIn("场景：深夜便利店监控室", text)
        self.assertIn("起始：监控屏幕显示收银台空无一人", text)
        self.assertIn("过程：屏幕噪点闪烁", text)
        self.assertIn("落点：照片边缘变清楚", text)

    def test_machine_prompt_keeps_api_submission_separate_from_export(self):
        prompt = compile_machine_prompt(
            self._shot_ir(),
            reference_images=[{"asset_name": "监控室参考图", "image_url": "https://cdn.test/room.png"}],
        )

        self.assertEqual(prompt["schema_version"], "machine_prompt_v1")
        self.assertFalse(prompt["api_submission"])
        self.assertTrue(prompt["export_contract"]["api_submission_is_separate_step"])
        self.assertEqual(len(prompt["visual_timeline"]), 3)
        self.assertIn("监控屏幕显示收银台空无一人", prompt["visual_timeline"][0]["visual_action"])
        self.assertIn("旧照片折角", prompt["visual_timeline"][1]["visual_action"])
        self.assertIn("照片边缘变清楚", prompt["visual_timeline"][2]["visual_action"])

    def test_h3_export_has_required_webui_sections_and_reference_policy(self):
        prompt = compile_machine_prompt(
            self._shot_ir(),
            reference_images=[{"asset_name": "监控室参考图", "image_url": "https://cdn.test/room.png"}],
        )
        export = export_minimax_h3_webui(prompt)

        self.assertEqual(export["target_model"], "minimax-h3")
        self.assertEqual(export["export_mode"], "webui_copy")
        self.assertFalse(export["api_submission"])
        self.assertIn("integrated_multimodal_description", export["fields"])
        self.assertIn("overall_soundscape", export["fields"])
        self.assertIn("non_diegetic_music", export["fields"])
        self.assertIn("reference image", export["fields"]["integrated_multimodal_description"])
        self.assertEqual(export["model_params"]["submission_policy"].split(";")[0], "export_only")

    def test_same_machine_prompt_exports_to_multiple_formats(self):
        prompt = compile_machine_prompt(self._shot_ir())
        h3 = export_minimax_h3_webui(prompt)
        generic = export_generic_zh_video_webui(prompt)

        self.assertNotEqual(h3["target_model"], generic["target_model"])
        self.assertIn("Observable action timeline", h3["fields"]["integrated_multimodal_description"])
        self.assertIn("动作时间线", generic["prompt"])
        self.assertFalse(generic["api_submission"])


if __name__ == "__main__":
    unittest.main()
