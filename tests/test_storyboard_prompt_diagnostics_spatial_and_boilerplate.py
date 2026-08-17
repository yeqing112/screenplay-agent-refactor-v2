import unittest

from api.server import _build_prompt_compiler_diagnostics


class StoryboardPromptDiagnosticsSpatialAndBoilerplateTests(unittest.TestCase):
    def test_screenplay_prompt_residue_ignores_spatial_composition_labels(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "清晨寺庙大殿内，中部：和尚乙盘腿敲击木鱼，右侧：和尚丙弯腰擦拭供桌，左侧大门处：和尚甲迈步跨入门槛。",
            "镜头平稳推近，三人动作节奏与首帧保持一致，最后停在和尚乙与和尚丙同时抬头的瞬间。",
            {
                "warnings": [],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        check = next(check for check in diagnostics["checks"] if check["key"] == "screenplay_prompt_residue")
        self.assertTrue(check["passed"])

    def test_visual_fact_target_coverage_ignores_reference_template_boilerplate(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙大殿内，和尚乙手持木槌敲击木鱼，木鱼为传统圆形深色硬木，暗红色漆面有磨损痕迹，置于供桌前方。",
            "镜头缓慢推近，保持人物、场景与木鱼形制一致。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-wood-fish",
                        "asset_name": "木鱼",
                        "required_facts": [
                            "道具视觉描述，高质量写实道具多角度展示图",
                            "传统木鱼，圆形，深色硬木，暗红漆，磨损痕迹，配小木槌，直径18厘米",
                        ],
                        "min_facts_to_include": 1,
                    }
                ],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        fact_check = next(check for check in diagnostics["checks"] if check["key"] == "visual_fact_target_coverage")
        self.assertTrue(fact_check["passed"])


if __name__ == "__main__":
    unittest.main()
