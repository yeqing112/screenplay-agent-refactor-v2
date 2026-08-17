import unittest

from agents.scene_setup import SceneSetupAgent


class SceneAssetCanonicalizationTests(unittest.TestCase):
    def setUp(self):
        self.agent = SceneSetupAgent(1)

    def test_canonicalize_prop_payload_dedupes_and_fills_defaults(self):
        payload = self.agent._canonicalize_prop_payload(
            {
                "name": "旧铁壶",
                "category": "",
                "description": "旧铁壶，壶嘴磨损，旧铁壶",
                "visual_prompt_zh": "",
                "core_prompt_zh": "",
                "style_ref_zh": "未知",
                "importance": "重要",
                "associated_characters": "bad",
            },
            1,
        )

        self.assertEqual(payload["category"], "未分类道具")
        self.assertEqual(payload["description"], "旧铁壶，壶嘴磨损")
        self.assertEqual(payload["visual_prompt_zh"], "旧铁壶，壶嘴磨损")
        self.assertEqual(payload["style_ref_zh"], "写实影视道具设定图")
        self.assertEqual(payload["importance"], "high")
        self.assertEqual(payload["episodes"], [1])
        self.assertEqual(payload["associated_characters"], [])

    def test_canonicalize_location_payload_dedupes_and_fills_defaults(self):
        payload = self.agent._canonicalize_location_payload(
            {
                "name": "寺门外",
                "category": "",
                "style": "",
                "description": "青石板潮湿，青石板潮湿，土墙发冷",
                "visual_prompt_zh": "",
                "core_prompt_zh": "",
                "lighting_mood": "无",
                "color_palette": "",
                "scene_mood_zh": "",
                "importance": "次要",
            },
            2,
        )

        self.assertEqual(payload["category"], "未分类场景")
        self.assertEqual(payload["style"], "写实影视场景")
        self.assertEqual(payload["description"], "青石板潮湿，土墙发冷")
        self.assertEqual(payload["visual_prompt_zh"], "青石板潮湿，土墙发冷")
        self.assertEqual(payload["lighting_mood"], "柔和自然光")
        self.assertEqual(payload["importance"], "low")
        self.assertEqual(payload["episodes"], [2])


if __name__ == "__main__":
    unittest.main()
