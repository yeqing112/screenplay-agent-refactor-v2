import unittest

from core.model_adapter import adapt_ir_to_model, sanitize_machine_prompt_text
from core.prompt_ir import AssetBinding, EmotionArc, ShotIR


class ModelAdapterTests(unittest.TestCase):
    def _shot_ir(self) -> ShotIR:
        return ShotIR(
            shot_id=1,
            scene_name="深夜便利店收银台",
            duration=5,
            camera_angle="MS",
            camera_movement="push-in",
            camera_speed="slow",
            shot_purpose="suspense",
            emotion_arc=EmotionArc(start="平静", end="紧张", intensity="medium"),
            start_state="女店员站在收银台后，抬头看向推门而入的男人。",
            action_process="男人缓慢走近收银台，女店员的手指停在报警按钮旁边。",
            end_state="两人隔着收银台对视，便利店灯光轻微闪烁。",
            lighting="冷白色便利店顶灯，夜色压暗玻璃门外背景",
            scene_binding=AssetBinding(
                asset_type="scene",
                asset_id="159",
                asset_name="深夜便利店收银台",
                reference_token="@便利店收银台",
                authority_prompt_raw="便利店收银台、冷白荧光灯、狭窄通道、夜晚玻璃门反光",
            ),
            character_bindings=[
                AssetBinding(
                    asset_type="character",
                    asset_id="1",
                    asset_name="女店员",
                    reference_token="@女店员",
                    authority_prompt_raw="年轻女性店员、蓝色制服、短发、警惕眼神",
                )
            ],
            prop_bindings=[
                AssetBinding(
                    asset_type="prop",
                    asset_id="8",
                    asset_name="报警按钮",
                    reference_token="@报警按钮",
                    authority_prompt_raw="收银台下方红色小按钮、塑料外壳、半隐藏位置",
                )
            ],
        )

    def test_same_ir_same_model_outputs_stable_prompt(self):
        ir = self._shot_ir()
        first = adapt_ir_to_model(ir, "jimeng")
        second = adapt_ir_to_model(ir, "jimeng")

        self.assertEqual(first, second)
        self.assertIn("@女店员", first["static_prompt"])
        self.assertIn("缓慢向主体推进", first["motion_prompt"])
        self.assertIn("身份漂移", first["negative_prompt"])

    def test_same_ir_can_target_multiple_model_adapters(self):
        ir = self._shot_ir()
        jimeng = adapt_ir_to_model(ir, "jimeng")
        kling = adapt_ir_to_model(ir, "kling")
        veo = adapt_ir_to_model(ir, "veo")

        self.assertEqual(jimeng["adapter"], "StoryboardChineseAdapter")
        self.assertEqual(kling["adapter"], "KlingStoryboardAdapter")
        self.assertEqual(veo["adapter"], "VeoStoryboardAdapter")
        self.assertNotEqual(jimeng["motion_prompt"], kling["motion_prompt"])
        self.assertNotEqual(kling["motion_prompt"], veo["motion_prompt"])

    def test_static_prompt_preserves_exact_scene_name_when_binding_uses_synonym(self):
        ir = self._shot_ir()
        ir.scene_name = "原始丛林深处"
        ir.scene_binding.asset_name = "原始森林深处"
        ir.scene_binding.reference_token = "@原始丛林深处"

        result = adapt_ir_to_model(ir, "jimeng")

        self.assertIn("原始丛林深处", result["static_prompt"])
        self.assertIn("原始森林深处", result["static_prompt"])

    def test_adapter_compiles_director_cut_language_into_continuous_motion(self):
        ir = self._shot_ir()
        ir.action_process = "女店员低头确认报警按钮，画面切到门口男人的背影，他缓慢回头，画面切：她重新抬眼，两秒后画面切出。"

        result = adapt_ir_to_model(ir, "jimeng")

        self.assertNotIn("画面切到", result["motion_prompt"])
        self.assertNotIn("画面切出", result["motion_prompt"])
        self.assertNotIn("画面切：", result["motion_prompt"])
        self.assertNotIn("切到", result["motion_prompt"])
        self.assertNotIn("切出", result["motion_prompt"])
        self.assertIn("同一连续画面中转向门口男人的背影", result["motion_prompt"])
        self.assertIn("画面转为她重新抬眼", result["motion_prompt"])
        self.assertIn("画面自然结束", result["motion_prompt"])

    def test_adapter_compiles_director_dialogue_marker_into_visual_action(self):
        ir = self._shot_ir()
        ir.action_process = "女店员（大笑）说出对白，语气平静但眼神紧张，然后垂下眼帘。"

        result = adapt_ir_to_model(ir, "jimeng")

        self.assertNotIn("对白", result["motion_prompt"])
        self.assertNotIn("（大笑）", result["motion_prompt"])
        self.assertIn("开口回应", result["motion_prompt"])

    def test_adapter_removes_legacy_asset_fallback_markers(self):
        ir = self._shot_ir()
        ir.character_bindings[0].authority_prompt_raw = "蓝色制服、短发、警惕眼神；legacy-character-profile-fallback"

        result = adapt_ir_to_model(ir, "jimeng")

        self.assertNotIn("legacy-character-profile-fallback", result["static_prompt"])
        self.assertNotIn("legacy", result["static_prompt"])

    def test_sanitize_machine_prompt_compiles_label_like_motion_into_continuous_language(self):
        text = "镜头推进为：泼水后的静止瞬间转为三人对峙，动作推进为和尚丙拎着空桶得意站立。"

        result = sanitize_machine_prompt_text(text)

        self.assertNotIn("镜头推进为", result)
        self.assertNotIn("动作推进为", result)
        self.assertIn("镜头继续推进到泼水后的静止瞬间", result)
        self.assertIn("随后和尚丙拎着空桶得意站立", result)

    def test_sanitize_machine_prompt_removes_director_opening_and_cut_markers(self):
        text = "[画面开场：一桶冷水泼下来]，画面切：和尚乙倚在门框上。"

        result = sanitize_machine_prompt_text(text)

        self.assertNotIn("画面开场", result)
        self.assertNotIn("画面切", result)
        self.assertNotIn("[", result)
        self.assertNotIn("]", result)
        self.assertIn("一桶冷水泼下来", result)
        self.assertIn("画面转为和尚乙倚在门框上", result)


if __name__ == "__main__":
    unittest.main()
