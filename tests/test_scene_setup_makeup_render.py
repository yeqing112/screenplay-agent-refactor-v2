import unittest
from types import SimpleNamespace

from agents.scene_setup import SceneSetupAgent


class SceneSetupMakeupRenderTests(unittest.TestCase):
    def setUp(self):
        self.agent = SceneSetupAgent(1)
        self.profile = SimpleNamespace(
            precise_age=26,
            age_range="青年(18-35)",
            nationality="中国",
            gender="女性",
            identity="姐姐",
            temperament="温柔、病弱、神秘",
            facial_features="肤色苍白，五官清秀，眼神平静",
            signature_outfit="深色简约便服",
            accessories="家族信物项链",
            hairstyle="半扎中长深棕直发",
        )

    def test_base_identity_prompt_uses_fixed_template(self):
        result = {
            "scope": "base_identity",
            "stage_name": "base_identity",
            "core_prompt_zh": "肤色苍白，五官清秀，眼神平静",
            "refined_outfit": "深色简约便服",
            "refined_accessories": "家族信物项链",
            "hair_style": "半扎中长深棕直发",
            "age": "二十多岁",
            "region": "中国",
            "gender": "女性",
            "identity": "姐姐",
            "temperament": "温柔、病弱、神秘",
        }

        prompt = self.agent._render_makeup_prompt_from_result("姐姐", 1, self.profile, result)

        self.assertIn("人物定妆设定板，展示同一个角色的六个视角", prompt)
        self.assertIn("上排为脸部特写：正面、侧面、45度", prompt)
        self.assertIn("下排为全身展示：正面、侧面、背面", prompt)
        self.assertIn("六宫格排版", prompt)

    def test_variant_prompt_uses_fixed_variant_template(self):
        result = {
            "scope": "shot_variant",
            "stage_name": "shot_6_对峙湿衣",
            "variant_name": "暴雨出租屋对峙",
            "shot_ids": ["6"],
            "core_prompt_zh": "脸型、发型、体型和基础气质保持不变",
            "refined_outfit": "深色便服被雨水打湿，外套贴身，衣摆有泥点",
            "refined_accessories": "保留银色吊坠",
            "hair_style": "半扎中长深棕直发，发尾被雨水打湿",
            "makeup_spec": "脸色苍白，眼下疲惫，唇色偏淡",
            "expression_mood": "克制、紧张、隐忍",
            "scene_prompt_zh": "暴雨夜室内冷光，衣物湿痕明显",
            "age": "二十多岁",
            "region": "中国",
            "gender": "女性",
            "identity": "姐姐",
            "temperament": "温柔、病弱、神秘",
        }

        prompt = self.agent._render_makeup_prompt_from_result("姐姐", 1, self.profile, result)

        self.assertIn("人物分镜精调定妆设定板", prompt)
        self.assertIn("严格继承基础定妆的面部一致性", prompt)
        self.assertIn("当前分镜状态：第1集 / 镜头 6 · 对峙湿衣 / 镜号 6 / 暴雨出租屋对峙", prompt)
        self.assertIn("场景影响：【暴雨夜室内冷光，衣物湿痕明显】", prompt)
        self.assertIn("六宫格排版", prompt)
        self.assertNotIn("shot_6_对峙湿衣", prompt)

    def test_episode_default_prompt_uses_episode_default_template(self):
        result = {
            "scope": "episode_default",
            "stage_name": "episode_1_default",
            "variant_name": "第1集默认造型",
            "core_prompt_zh": "脸型、发型、体型和基础气质保持不变",
            "refined_outfit": "深色简约便服，便于行动",
            "refined_accessories": "保留银色吊坠",
            "hair_style": "半扎中长深棕直发",
            "makeup_spec": "苍白底妆，神情克制",
            "expression_mood": "平静、克制、神秘",
            "scene_prompt_zh": "无额外场景污损，保持标准影棚状态",
            "age": "二十多岁",
            "region": "中国",
            "gender": "女性",
            "identity": "姐姐",
            "temperament": "温柔、病弱、神秘",
        }

        prompt = self.agent._render_makeup_prompt_from_result("姐姐", 1, self.profile, result)

        self.assertIn("人物分集默认定妆设定板", prompt)
        self.assertIn("当前剧集状态：第1集 / 分集默认 / 第1集默认造型", prompt)
        self.assertNotIn("episode_1_default", prompt)
        self.assertNotIn("人物分镜精调定妆设定板", prompt)

    def test_concrete_outfit_prompt_overrides_generic_state_label(self):
        result = {
            "scope": "episode_default",
            "stage_name": "episode_1_default",
            "variant_name": "第1集默认造型",
            "core_prompt_zh": "青年女性，五官清晰",
            "refined_outfit": "符合继承人身份的基础服装，材质朴素",
            "outfit_prompt_zh": "洗得发白的牛仔外套，内搭简约T恤，深色修身牛仔裤，平底短靴",
            "refined_accessories": "无明显配饰",
            "hair_style": "黑色长发扎成马尾",
            "makeup_spec": "淡妆或素颜",
            "age": "青年(18-35)",
            "region": "中国",
            "gender": "女性",
            "identity": "继承人",
            "temperament": "谨慎",
        }

        prompt = self.agent._render_makeup_prompt_from_result("角色", 1, self.profile, result)

        self.assertIn("洗得发白的牛仔外套", prompt)
        self.assertIn("深色修身牛仔裤", prompt)

    def test_base_identity_prompt_uses_profile_age_range_when_result_age_missing(self):
        profile = SimpleNamespace(
            precise_age=None,
            age_range="青年(18-35)",
            nationality="中国",
            gender="男性",
            identity="和尚（寺庙僧侣）",
            temperament="懒惰、推诿、轻慢",
            facial_features="剃着光头，神情懒散",
            signature_outfit="灰旧僧袍",
            accessories="磨旧念珠",
            hairstyle="剃度光头",
        )
        result = {
            "scope": "base_identity",
            "stage_name": "base_identity",
            "core_prompt_zh": "剃着光头，神情懒散",
            "refined_outfit": "灰旧僧袍",
            "refined_accessories": "磨旧念珠",
            "hair_style": "剃度光头",
            "region": "中国",
            "gender": "男性",
            "identity": "和尚（寺庙僧侣）",
            "temperament": "懒惰、推诿、轻慢",
        }

        prompt = self.agent._render_makeup_prompt_from_result("和尚甲", 1, profile, result)

        self.assertIn("【青年(18-35)】岁", prompt)
        self.assertNotIn("-岁", prompt)


if __name__ == "__main__":
    unittest.main()
