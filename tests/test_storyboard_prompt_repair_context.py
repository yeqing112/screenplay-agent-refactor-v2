import unittest

from api.server import _build_prompt_compiler_diagnostics, _build_prompt_repair_context


class StoryboardPromptRepairContextTests(unittest.TestCase):
    def test_authority_inheritance_check_exposes_missing_visual_details(self):
        context = {
            "bound_assets": [
                {
                    "asset_type": "scene",
                    "asset_id": "scene-1",
                    "asset_name": "寺庙后院水房",
                    "authority_prompt_parts": [
                        {"key": "canonical_description", "text": "青石板地面，老井，灰白墙壁"},
                    ],
                },
                {
                    "asset_type": "prop",
                    "asset_id": "prop-1",
                    "asset_name": "木桶",
                    "authority_prompt_parts": [
                        {"key": "canonical_description", "text": "木质水桶，竹箍，木纹"},
                    ],
                    "canonical_prompt_profile": {"importance": "high"},
                },
            ],
            "warnings": [],
            "compiled_reference_images": [],
        }

        diagnostics = _build_prompt_compiler_diagnostics(
            "全景镜头，寺庙后院水房内，一个和尚拎着木桶站着。",
            "镜头缓慢推进，动作保持一致。",
            context,
            [],
        )

        failed_check = next(item for item in diagnostics["checks"] if item["key"] == "authority_prompt_inheritance")
        self.assertFalse(failed_check["passed"])
        detail_text = " ".join(failed_check.get("details", []))
        self.assertIn("寺庙后院水房", detail_text)
        self.assertIn("青石板地面", detail_text)
        self.assertIn("木桶", detail_text)
        self.assertIn("木质水桶", detail_text)

    def test_repair_context_keeps_failed_check_details(self):
        diagnostics = {
            "checks": [
                {
                    "key": "authority_prompt_inheritance",
                    "passed": False,
                    "message": "这些资产的权威原文关键特征没有明显进入静态提示词：寺庙后院水房、木桶",
                    "details": [
                        "寺庙后院水房：补入 青石板地面 / 老井 / 灰白墙壁",
                        "木桶：补入 木质水桶 / 竹箍 / 木纹",
                    ],
                }
            ],
            "warnings": ["静态提示词对这些资产的权威原文继承不足：寺庙后院水房、木桶。"],
        }

        repair_context = _build_prompt_repair_context(
            {"scene_name": "寺庙后院水房"},
            {
                "visual_prompt_static": "全景镜头，寺庙后院水房内，一个和尚拎着木桶站着。",
                "visual_prompt_motion": "镜头缓慢推进。",
                "negative_prompt": "",
                "used_assets": [],
            },
            diagnostics,
            1,
        )

        failed_checks = repair_context["repair_request"]["failed_checks"]
        self.assertEqual(len(failed_checks), 1)
        self.assertEqual(
            failed_checks[0]["details"],
            [
                "寺庙后院水房：补入 青石板地面 / 老井 / 灰白墙壁",
                "木桶：补入 木质水桶 / 竹箍 / 木纹",
            ],
        )
        visual_targets = repair_context["repair_request"]["visual_fact_targets"]
        self.assertEqual(visual_targets[0]["asset_name"], "寺庙后院水房")
        self.assertGreaterEqual(len(visual_targets[0]["required_facts"]), 2)

    def test_repair_context_exposes_required_used_assets_for_critical_bindings(self):
        diagnostics = {
            "checks": [
                {
                    "key": "critical_bound_asset_usage",
                    "passed": False,
                    "message": "这些关键绑定资产没有被保留在 used_assets 中：木桶",
                    "details": ["木桶：高重要度道具已绑定且有参考图，但本次编译未纳入 used_assets"],
                }
            ],
            "warnings": [],
        }

        repair_context = _build_prompt_repair_context(
            {
                "bound_assets": [
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-1",
                        "asset_name": "木桶",
                        "reference_token": "@木桶",
                        "reference_status": "candidate",
                        "has_reference": True,
                        "canonical_prompt_profile": {"importance": "high"},
                    }
                ]
            },
            {
                "visual_prompt_static": "和尚拎着木桶站在水房里。",
                "visual_prompt_motion": "镜头缓慢推进。",
                "negative_prompt": "",
                "used_assets": [],
            },
            diagnostics,
            1,
        )

        required_used_assets = repair_context["repair_request"]["required_used_assets"]
        self.assertEqual(len(required_used_assets), 1)
        self.assertEqual(required_used_assets[0]["asset_name"], "木桶")
        self.assertEqual(required_used_assets[0]["reference_token"], "@木桶")

    def test_repair_context_parses_visual_fact_target_coverage_details(self):
        diagnostics = {
            "checks": [
                {
                    "key": "visual_fact_target_coverage",
                    "passed": False,
                    "message": "这些资产没有满足首轮编译要求的视觉事实覆盖：寺庙后院水房",
                    "details": ["寺庙后院水房：至少补入 1 条视觉事实 / 青石板地面 / 老井"],
                }
            ],
            "warnings": [],
        }

        repair_context = _build_prompt_repair_context(
            {"scene_name": "寺庙后院水房"},
            {
                "visual_prompt_static": "寺庙后院水房内，一个和尚站在木桶旁边。",
                "visual_prompt_motion": "镜头缓慢推进。",
                "negative_prompt": "",
                "used_assets": [],
            },
            diagnostics,
            1,
        )

        visual_targets = repair_context["repair_request"]["visual_fact_targets"]
        self.assertEqual(visual_targets[0]["asset_name"], "寺庙后院水房")
        self.assertIn("青石板地面", visual_targets[0]["required_facts"])
        self.assertIn("老井", visual_targets[0]["required_facts"])

    def test_repair_context_exposes_priority_fixes_in_expected_order(self):
        diagnostics = {
            "checks": [
                {
                    "key": "high_importance_prop_presence",
                    "passed": False,
                    "message": "高重要度道具缺失",
                    "details": ["旧木桶：补入 桶边磨损 / 桶身水渍"],
                },
                {
                    "key": "screenplay_prompt_residue",
                    "passed": False,
                    "message": "提示词里仍有对白稿残留",
                    "details": ["角色对白标签：和尚丙", "方括号舞台提示"],
                },
                {
                    "key": "visual_fact_target_coverage",
                    "passed": False,
                    "message": "视觉事实未覆盖",
                    "details": ["寺庙后院水房：至少补入 1 条视觉事实 / 青石板地面 / 老井"],
                },
            ],
            "warnings": [],
        }

        repair_context = _build_prompt_repair_context(
            {"scene_name": "寺庙后院水房"},
            {
                "visual_prompt_static": "和尚丙：新来的，醒醒！[画面切：和尚甲弯腰捡起木桶]",
                "visual_prompt_motion": "人物对话镜头，[画面切：和尚丙拎着木桶站在门口]",
                "negative_prompt": "",
                "used_assets": [],
            },
            diagnostics,
            1,
        )

        priority_fixes = repair_context["repair_request"]["priority_fixes"]
        self.assertEqual(priority_fixes[0]["key"], "screenplay_prompt_residue")
        self.assertEqual(priority_fixes[1]["key"], "visual_fact_target_coverage")
        self.assertEqual(priority_fixes[2]["key"], "high_importance_prop_presence")

    def test_repair_context_marks_full_rewrite_when_screenplay_residue_exists(self):
        diagnostics = {
            "checks": [
                {
                    "key": "screenplay_prompt_residue",
                    "passed": False,
                    "message": "提示词里仍有对白稿残留",
                    "details": ["角色对白标签：和尚丙", "方括号舞台提示"],
                }
            ],
            "warnings": [],
        }

        repair_context = _build_prompt_repair_context(
            {"scene_name": "寺庙后院水房"},
            {
                "visual_prompt_static": "和尚丙：新来的，醒醒！",
                "visual_prompt_motion": "[画面切：和尚丙拎着木桶站在门口]",
                "negative_prompt": "",
                "used_assets": [],
            },
            diagnostics,
            1,
        )

        repair_request = repair_context["repair_request"]
        self.assertEqual(repair_request["screenplay_residue_details"], ["角色对白标签：和尚丙", "方括号舞台提示"])
        self.assertTrue(repair_request["rewrite_constraints"]["full_rewrite_required"])


if __name__ == "__main__":
    unittest.main()
