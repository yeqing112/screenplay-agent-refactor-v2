import unittest
from types import SimpleNamespace

from agents.scene_setup import SceneSetupAgent


class SceneSetupVariantCanonicalizationTests(unittest.TestCase):
    def setUp(self):
        self.agent = SceneSetupAgent(1)

    def test_variant_prompt_normalizes_monk_identity_and_temperament(self):
        profile = SimpleNamespace(
            precise_age=None,
            age_range="青年(18-35)",
            nationality="中国",
            gender="男性",
            identity="寺庙守门僧人（推测）",
            temperament="懒散、轻慢、欺弱、混日子",
            facial_features="剃着光头，神情懒散，眼神带一点轻慢，像个混日子的僧人",
            signature_outfit="灰旧僧袍",
            accessories="一串磨旧念珠",
            hairstyle="剃着光头",
            body_type="中等体型，姿态略松散，带着久居寺中的朴素与懈怠感",
            skin_tone="肤色自然，带有真实生活痕迹",
            distinguishing_marks="无明显特殊标记",
        )
        result = {
            "scope": "shot_variant",
            "stage_name": "shot_2_gate_block",
            "variant_name": "寺门刁难新人",
            "shot_ids": ["2"],
            "identity": "守门僧人（推测）",
            "temperament": "懒散、轻慢、欺弱、混日子",
            "core_prompt_zh": "剃着光头，神情懒散，眼神带一点轻慢，像个混日子的僧人",
            "refined_outfit": "灰旧僧袍，布料磨旧发暗，穿着松散",
            "refined_accessories": "一串磨旧念珠",
            "hair_style": "剃着光头，头皮干净，略带青色头皮质感",
            "makeup_spec": "剃着光头，神情懒散，眼神带一点轻慢，像个混日子的僧人",
            "scene_prompt_zh": "寺门冷雨夜，潮湿石板反光",
        }

        prompt = self.agent._render_makeup_prompt_from_result("和尚甲", 1, profile, result)

        self.assertIn("身份是【和尚（寺庙僧侣）】", prompt)
        self.assertIn("气质【懒散、轻慢、爱欺负新人、略显粗鄙】", prompt)

    def test_variant_prompt_normalizes_disciple_makeup_and_scene_effects(self):
        profile = SimpleNamespace(
            precise_age=None,
            age_range="青年(18-35)",
            nationality="中国",
            gender="男性",
            identity="寺中新入门的弟子（推测）",
            temperament="克制、隐忍、坚韧、内心有不屈和傲气",
            facial_features="面色偏白，雨夜奔波后的疲态轻压在眼下，情绪克制，目光里仍压着不服气",
            signature_outfit="朴素弟子衣装因雨夜受潮贴身，整体简洁克制",
            accessories="旧包袱",
            hairstyle="黑色短发或束发，稍显凌乱但克制",
            body_type="中等偏瘦体型，动作克制，带着新入门弟子的拘谨感",
            skin_tone="肤色自然，带有真实生活痕迹",
            distinguishing_marks="无明显特殊标记",
        )
        result = {
            "scope": "shot_variant",
            "stage_name": "shot_3_rain_return",
            "variant_name": "雨夜归门",
            "shot_ids": ["3"],
            "identity": "寺庙新入弟子（推测）",
            "temperament": "表面顺从、隐忍、倔强",
            "core_prompt_zh": "面色偏白，雨夜奔波后的疲态轻压在眼下，情绪克制，目光里仍压着不服气",
            "refined_outfit": "朴素弟子衣装因雨夜受潮贴身，整体简洁克制",
            "refined_accessories": "旧包袱",
            "hair_style": "黑色短发或束发，稍显凌乱但克制",
            "makeup_spec": "脸色发白，眼神倔强",
            "scene_prompt_zh": "",
        }

        prompt = self.agent._render_makeup_prompt_from_result("阿宁", 1, profile, result)

        self.assertIn("身份是【寺中新入门的弟子（推测）】", prompt)
        self.assertIn("当前妆容与表情：【面色偏白，雨夜奔波后的疲态轻压在眼下，情绪克制，目光里仍压着不服气】", prompt)
        self.assertIn("场景影响：【无额外场景污染，保持标准影棚状态】", prompt)


if __name__ == "__main__":
    unittest.main()
