import unittest

from core.prompts import load_prompt


class StoryboardPromptCompilerTemplateTests(unittest.TestCase):
    def test_template_requires_canonical_asset_inheritance_and_reference_tokens(self):
        prompt = load_prompt("storyboard/prompt_compiler", context_json="{}")

        self.assertIn("canonical_prompt_profile", prompt)
        self.assertIn("canonical_prompt_parts", prompt)
        self.assertIn("reference_token", prompt)
        self.assertIn("compile_prompt_contract.summary_lines", prompt)
        self.assertIn("visual_fact_targets", prompt)
        self.assertIn("required_used_assets", prompt)
        self.assertIn("优先把它作为显式参考锚点自然写入静态提示词", prompt)
        self.assertIn("将其当作静态提示词的视觉事实来源", prompt)
        self.assertIn("当前镜头所使用的人物状态版本", prompt)
        self.assertIn("本镜头首轮编译必须显式吸收的视觉事实清单", prompt)
        self.assertIn("对场景来说，不能只写“场景参考 @某场景”", prompt)
        self.assertIn("对高重要度道具来说，不能只写“拿着木桶 / 某道具”", prompt)


if __name__ == "__main__":
    unittest.main()
