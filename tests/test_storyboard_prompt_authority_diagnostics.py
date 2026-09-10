import unittest

from api.server import (
    _apply_prompt_compiler_hard_gates,
    _build_prompt_compiler_diagnostics,
    _prompt_compiler_diagnostics_need_refresh,
)


class StoryboardPromptAuthorityDiagnosticsTests(unittest.TestCase):
    def test_stale_visual_fact_details_request_refresh(self):
        self.assertTrue(
            _prompt_compiler_diagnostics_need_refresh(
                {
                    "checks": [
                        {"key": "meta_prompt_leakage", "passed": True},
                        {"key": "static_prompt_quality", "passed": True},
                        {"key": "motion_prompt_quality", "passed": True},
                        {
                            "key": "visual_fact_target_coverage",
                            "passed": False,
                            "details": [
                                "Temple Water Room：至少补入 2 条视觉事实 / stone floor / old well / mottled wall / cold dawn light / wooden rack / wet ground"
                            ],
                        },
                        {"key": "authority_prompt_inheritance", "passed": True},
                        {"key": "critical_bound_asset_usage", "passed": True},
                    ]
                }
            )
        )

    def test_missing_authority_inheritance_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "暴雨中的出租屋内景，中景构图，姐姐与阿宁对视，冷色光线压低空间亮度。",
            "镜头缓慢推进，人物动作与服装保持和首帧一致，最后停在两人对视的瞬间。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "character",
                        "asset_id": "char-1",
                        "asset_name": "姐姐",
                        "has_reference": True,
                        "authority_prompt_parts": [
                            {"key": "refined_outfit", "text": "深色便服被雨水打湿，外套贴身，衣摆有泥点"},
                            {"key": "hair_style", "text": "半扎中长深棕直发，发尾被雨水打湿"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [
                {
                    "asset_type": "character",
                    "asset_id": "char-1",
                    "asset_name": "姐姐",
                    "reference_token": "@姐姐",
                    "locked_reference": False,
                }
            ],
        )

        self.assertEqual(diagnostics["status"], "warning")
        self.assertTrue(
            any(check["key"] == "authority_prompt_inheritance" and not check["passed"] for check in diagnostics["checks"])
        )
        self.assertTrue(any("权威原文继承不足" in warning for warning in diagnostics["warnings"]))
        authority_check = next(check for check in diagnostics["checks"] if check["key"] == "authority_prompt_inheritance")
        self.assertTrue(any("姐姐" in detail for detail in authority_check["details"]))

    def test_authority_inheritance_accepts_equivalent_character_and_scene_phrases(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "清晨，寺庙后院的水房里，青石板铺地，中央一口青石砌成的老井靠着灰白色墙壁。和尚站在井边，神情懒散轻慢，带着一点粗鄙气。",
            "镜头缓慢推进，场景与服装保持一致。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "寺庙后院水房",
                        "authority_prompt_parts": [
                            {"key": "canonical_description", "text": "寺庙后院的水房 / 中央一口老井 / 井口由青石砌成 / 四周为灰白色墙壁"},
                        ],
                    },
                    {
                        "asset_type": "character",
                        "asset_id": "char-1",
                        "asset_name": "和尚甲",
                        "authority_prompt_parts": [
                            {"key": "canonical_identity", "text": "和尚（寺庙僧侣）"},
                            {"key": "canonical_temperament", "text": "懒散、轻慢、略显粗鄙"},
                        ],
                    },
                ],
                "reference_images": [],
            },
            [],
        )

        check = next(check for check in diagnostics["checks"] if check["key"] == "authority_prompt_inheritance")
        self.assertTrue(check["passed"])

    def test_visual_fact_target_coverage_becomes_warning_when_required_facts_are_missing(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房内，一个和尚站在木架旁边。",
            "镜头缓慢推进，动作与首帧保持一致。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "寺庙后院水房",
                        "required_facts": ["青石板地面", "老井", "灰白墙壁"],
                        "min_facts_to_include": 2,
                    }
                ],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        self.assertEqual(diagnostics["status"], "warning")
        fact_check = next(check for check in diagnostics["checks"] if check["key"] == "visual_fact_target_coverage")
        self.assertFalse(fact_check["passed"])
        self.assertTrue(any("寺庙后院水房" in detail for detail in fact_check["details"]))
        self.assertTrue(any("首轮视觉事实继承不足" in warning for warning in diagnostics["warnings"]))
        self.assertTrue(all(detail.count(" / ") <= 4 for detail in fact_check["details"]))

    def test_visual_fact_target_coverage_passes_when_required_facts_are_present(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房内，青石板地面潮湿发亮，老井贴着灰白墙壁，和尚站在木架旁边。",
            "镜头缓慢推进，动作与首帧保持一致。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "寺庙后院水房",
                        "required_facts": ["青石板地面", "老井", "灰白墙壁"],
                        "min_facts_to_include": 2,
                    }
                ],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        fact_check = next(check for check in diagnostics["checks"] if check["key"] == "visual_fact_target_coverage")
        self.assertTrue(fact_check["passed"])

    def test_prop_visual_fact_target_allows_single_concrete_fact(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙大殿内，一只传统圆形木鱼摆在供桌前，由深色硬木雕刻而成，表面暗红色漆有磨损痕迹，旁边放着小木槌。",
            "镜头缓慢推近木鱼，桌面与光线保持稳定。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-1",
                        "asset_name": "木鱼",
                        "required_facts": ["传统圆形木鱼，深色硬木，暗红漆，磨损痕迹", "传统木鱼，圆形，深色硬木，暗红漆"],
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

    def test_retention_coverage_passes_with_hygiene_terms_instead_of_literal_label(self):
        # A composer may preserve "hair" by naming an actual hairstyle (e.g.
        # "黑色短发") without repeating the literal label "发型".  The retention
        # check must recognise the dimension generically, not by exact keyword.
        diagnostics = _build_prompt_compiler_diagnostics(
            "青年男性黑色短发，面部轮廓与锁定参考图一致，身穿朴素员工基础服装。",
            "镜头缓慢推进，动作与首帧保持一致。",
            {
                "warnings": [],
                "retention": {
                    "face": "fully_preserved",
                    "hair": "fully_preserved",
                    "costume": "fully_preserved",
                },
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        retention_check = next(check for check in diagnostics["checks"] if check["key"] == "retention_coverage")
        self.assertTrue(retention_check["passed"])
        self.assertFalse(any("retention 维护不足" in warning for warning in diagnostics["warnings"]))

    def test_visual_fact_target_coverage_passes_on_near_equivalent_scene_lighting(self):
        # "冷白荧光灯从头顶压下" and the required "惨白荧光灯" describe the same
        # overhead fluorescent fact.  The matcher resolves this by the established
        # authority overlap logic, not via a project-specific alias.
        diagnostics = _build_prompt_compiler_diagnostics(
            "深夜便利店收银区，冷白荧光灯从头顶压下，狭窄收银台、扫码器、烟架形成压迫感。",
            "镜头缓慢推进，动作与首帧保持一致。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "便利店收银台",
                        "required_facts": ["深夜便利店收银区", "惨白荧光灯", "从头顶直射"],
                        "min_facts_to_include": 2,
                    }
                ],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        fact_check = next(check for check in diagnostics["checks"] if check["key"] == "visual_fact_target_coverage")
        self.assertTrue(fact_check["passed"])

    def test_visual_fact_target_coverage_still_flags_distinct_missing_fact(self):
        # The generic matcher must not collapse a genuinely absent style fact.
        # "写实电影感" is not reflected by "中景构图"; when the minimum requires
        # it, coverage must remain a warning rather than a false pass.
        diagnostics = _build_prompt_compiler_diagnostics(
            "深夜便利店收银区，中景构图，冷白荧光灯从头顶压下。",
            "镜头缓慢推进，动作与首帧保持一致。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "便利店收银台",
                        "required_facts": ["写实电影感", "冷白荧光灯从头顶压下"],
                        "min_facts_to_include": 2,
                    }
                ],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        fact_check = next(check for check in diagnostics["checks"] if check["key"] == "visual_fact_target_coverage")
        self.assertFalse(fact_check["passed"])
        self.assertTrue(any("写实电影感" in detail for detail in fact_check["details"]))

    def test_screenplay_prompt_residue_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房·清晨，人物互动中景。和尚丙：（大笑）新来的，醒醒！[和尚甲抹去脸上的水]",
            "人物对话镜头，保持稳定构图。[画面切：和尚乙倚在门框上]",
            {
                "warnings": [],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        self.assertEqual(diagnostics["status"], "warning")
        check = next(check for check in diagnostics["checks"] if check["key"] == "screenplay_prompt_residue")
        self.assertFalse(check["passed"])
        self.assertTrue(any("方括号" in detail or "对白" in detail or "和尚丙" in detail for detail in check["details"]))

    def test_screenplay_prompt_residue_ignores_camera_stage_labels(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房，清晨，起始全景：青石板地面潮湿发亮，和尚甲站在井边，木桶放在前景。",
            "镜头从起始全景缓慢推进到中景，角色、服装、场景和木桶与首帧保持一致，最后停在和尚甲抬头的瞬间。",
            {
                "warnings": [],
                "bound_assets": [],
                "reference_images": [],
            },
            [],
        )

        check = next(check for check in diagnostics["checks"] if check["key"] == "screenplay_prompt_residue")
        self.assertTrue(check["passed"])

    def test_screenplay_prompt_residue_detects_unlabelled_dialogue_and_parenthetical_stage_direction(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房，和尚甲挑水停下。",
            "镜头固定不动。和尚丙拦在路中间，站住！你看看你！这桶不合格，倒回去重新挑！和尚甲停下脚步。",
            {"warnings": [], "bound_assets": [], "reference_images": []},
            [],
        )
        check = next(check for check in diagnostics["checks"] if check["key"] == "screenplay_prompt_residue")
        self.assertFalse(check["passed"])
        self.assertTrue(any("感叹句对白" in detail for detail in check["details"]))

        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后山乱葬岗，和尚甲站在坟前。",
            "固定机位，和尚甲，（低声自语）师父，你放心，我会找到的。随后他跪下。",
            {"warnings": [], "bound_assets": [], "reference_images": []},
            [],
        )
        check = next(check for check in diagnostics["checks"] if check["key"] == "screenplay_prompt_residue")
        self.assertFalse(check["passed"])
        self.assertTrue(any("括号舞台动作" in detail for detail in check["details"]))

    def test_character_variant_state_missing_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "暴雨中的出租屋内景，姐姐与阿宁对视，冷色光线压低空间亮度。",
            "镜头缓慢推进，人物动作与服装保持和首帧一致，最后停在两人对视的瞬间。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "character",
                        "asset_id": "char-1",
                        "asset_name": "姐姐",
                        "variant_scope": "shot_variant",
                        "authority_prompt_parts": [
                            {"key": "canonical_outfit", "text": "被雨水打湿的深色外套紧贴肩背"},
                            {"key": "canonical_makeup_expression", "text": "眼下疲惫，嘴唇发白"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        self.assertEqual(diagnostics["status"], "warning")
        check = next(check for check in diagnostics["checks"] if check["key"] == "character_variant_state")
        self.assertFalse(check["passed"])
        self.assertTrue(any("姐姐" in detail for detail in check["details"]))
        self.assertTrue(any("疲惫" in detail or "深色外套" in detail for detail in check["details"]))

    def test_scene_variant_state_missing_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙院落中景，一个和尚站在空地中央，画面整体冷灰。",
            "镜头缓慢推进，人物动作与首帧保持一致。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-variant-1",
                        "asset_name": "寺庙院落",
                        "variant_scope": "scene_variant",
                        "authority_prompt_parts": [
                            {"key": "canonical_lighting_mood", "text": "黄昏冷光压低院落亮度"},
                            {"key": "canonical_core_visual", "text": "青石板地面残留潮湿反光，土黄色墙面斑驳老旧"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        self.assertEqual(diagnostics["status"], "warning")
        check = next(check for check in diagnostics["checks"] if check["key"] == "scene_variant_state")
        self.assertFalse(check["passed"])
        self.assertTrue(any("寺庙院落" in detail for detail in check["details"]))
        self.assertTrue(any("潮湿反光" in detail or "黄昏冷光" in detail for detail in check["details"]))

    def test_prop_variant_state_missing_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙水房中景，和尚站在木架旁，手边放着一个木桶。",
            "镜头缓慢推进，角色动作与首帧保持一致。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-variant-1",
                        "asset_name": "木桶",
                        "variant_scope": "prop_variant",
                        "authority_prompt_parts": [
                            {"key": "canonical_description", "text": "木桶边缘磨损开裂，桶身潮湿发暗"},
                            {"key": "canonical_core_visual", "text": "铁箍轻微生锈，桶壁留有旧水渍"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        self.assertEqual(diagnostics["status"], "warning")
        check = next(check for check in diagnostics["checks"] if check["key"] == "prop_variant_state")
        self.assertFalse(check["passed"])
        self.assertTrue(any("木桶" in detail for detail in check["details"]))
        self.assertTrue(any("磨损开裂" in detail or "旧水渍" in detail for detail in check["details"]))

    def test_authority_warning_is_suppressed_when_visual_fact_target_already_covers_same_asset_gap(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房内，一个和尚站在木架旁边。",
            "镜头缓慢推进，动作与首帧保持一致。",
            {
                "warnings": [],
                "visual_fact_targets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "寺庙后院水房",
                        "required_facts": ["青石板地面", "老井", "灰白墙壁"],
                        "min_facts_to_include": 2,
                    }
                ],
                "bound_assets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "寺庙后院水房",
                        "has_reference": True,
                        "authority_prompt_parts": [
                            {"key": "canonical_description", "text": "青石板地面，老井，灰白墙壁"},
                        ],
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        fact_check = next(check for check in diagnostics["checks"] if check["key"] == "visual_fact_target_coverage")
        authority_check = next(check for check in diagnostics["checks"] if check["key"] == "authority_prompt_inheritance")
        self.assertFalse(fact_check["passed"])
        self.assertTrue(authority_check["passed"])

    def test_high_importance_prop_missing_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "暴雨中的出租屋内景，姐姐与阿宁对视，冷色光线压低空间亮度。",
            "镜头缓慢推进，人物动作与服装保持和首帧一致，最后停在两人对视的瞬间。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-1",
                        "asset_name": "旧水壶",
                        "reference_token": "@旧水壶",
                        "canonical_prompt_profile": {"importance": "high"},
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        self.assertEqual(diagnostics["status"], "warning")
        self.assertTrue(
            any(check["key"] == "high_importance_prop_presence" and not check["passed"] for check in diagnostics["checks"])
        )

    def test_high_importance_prop_presence_passes_when_core_visual_facts_are_present(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "寺庙后院水房里，灰褐色木质水桶呈圆柱形，外壁有多道竹箍和铁箍固定，桶口两侧有对称桶耳，桶身木纹磨损清晰。",
            "镜头缓慢推进，角色动作与首帧保持一致。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-1",
                        "asset_name": "木桶",
                        "reference_token": "@木桶",
                        "canonical_prompt_profile": {
                            "importance": "high",
                            "description": "木质或竹编水桶，圆柱形，外壁多道竹箍或铁箍固定，桶口两侧有对称桶耳",
                            "core_visual": "表面木纹清晰有使用磨损痕迹",
                        },
                    }
                ],
                "reference_images": [],
            },
            [],
        )

        check = next(check for check in diagnostics["checks"] if check["key"] == "high_importance_prop_presence")
        self.assertTrue(check["passed"])

    def test_critical_bound_assets_missing_from_used_assets_becomes_warning(self):
        diagnostics = _build_prompt_compiler_diagnostics(
            "暴雨中的出租屋内景，姐姐与阿宁对视，冷色光线压低空间亮度，旧水壶放在画面前景。",
            "镜头缓慢推进，人物动作与服装保持和首帧一致，最后停在两人对视的瞬间。",
            {
                "warnings": [],
                "bound_assets": [
                    {
                        "asset_type": "scene",
                        "asset_id": "scene-1",
                        "asset_name": "出租屋",
                        "has_reference": True,
                    },
                    {
                        "asset_type": "character",
                        "asset_id": "char-1",
                        "asset_name": "姐姐",
                        "has_reference": True,
                    },
                    {
                        "asset_type": "prop",
                        "asset_id": "prop-1",
                        "asset_name": "旧水壶",
                        "has_reference": True,
                        "canonical_prompt_profile": {"importance": "high"},
                    },
                ],
                "reference_images": [],
            },
            [
                {
                    "asset_type": "scene",
                    "asset_id": "scene-1",
                    "asset_name": "出租屋",
                    "reference_token": "@出租屋",
                    "locked_reference": False,
                }
            ],
        )

        self.assertEqual(diagnostics["status"], "warning")
        critical_check = next(check for check in diagnostics["checks"] if check["key"] == "critical_bound_asset_usage")
        self.assertFalse(critical_check["passed"])
        self.assertIn("姐姐", "".join(critical_check["details"]))
        self.assertIn("旧水壶", "".join(critical_check["details"]))


    def test_scene_variant_state_becomes_blocking_after_failed_repair(self):
        diagnostics = {
            "status": "warning",
            "blocking_issues": [],
            "checks": [
                {"key": "scene_variant_state", "passed": False, "details": ["寺庙后院水房：补入 青石板地面 / 土黄色墙面"]},
            ],
        }

        gated = _apply_prompt_compiler_hard_gates(diagnostics, repair_attempted=True)

        self.assertEqual(gated["status"], "blocked")
        self.assertTrue(any("场景变体" in issue for issue in gated["blocking_issues"]))

    def test_prop_variant_state_becomes_blocking_after_failed_repair(self):
        diagnostics = {
            "status": "warning",
            "blocking_issues": [],
            "checks": [
                {"key": "prop_variant_state", "passed": False, "details": ["旧木桶：补入 桶边磨损 / 桶身水渍"]},
            ],
        }

        gated = _apply_prompt_compiler_hard_gates(diagnostics, repair_attempted=True)

        self.assertEqual(gated["status"], "blocked")
        self.assertTrue(any("道具变体" in issue for issue in gated["blocking_issues"]))

    def test_screenplay_prompt_residue_becomes_blocking_after_failed_repair(self):
        diagnostics = {
            "status": "warning",
            "blocking_issues": [],
            "checks": [
                {"key": "screenplay_prompt_residue", "passed": False, "details": ["方括号舞台提示", "角色对白标签：和尚丙"]},
            ],
        }

        gated = _apply_prompt_compiler_hard_gates(diagnostics, repair_attempted=True)

        self.assertEqual(gated["status"], "blocked")
        self.assertTrue(any("对白稿" in issue or "舞台提示" in issue for issue in gated["blocking_issues"]))

    def test_locked_scene_material_conflict_is_blocked_but_surface_scratch_is_allowed(self):
        context = {
            "warnings": [],
            "bound_assets": [
                {
                    "asset_type": "scene",
                    "asset_id": "scene-1",
                    "asset_name": "钟楼阁楼",
                    "locked_reference": True,
                    "canonical_prompt_profile": {
                        "description": "钟楼顶层阁楼，木质结构，陈旧破败",
                    },
                }
            ],
            "motion_contract": {
                "start_state": "林晚站在木门前",
                "camera": "static",
                "action_beats": [{"action": "推门"}],
                "end_state": "木门打开",
                "preserve_first_frame": True,
            },
        }
        allowed = _build_prompt_compiler_diagnostics(
            "钟楼阁楼木门前，木质结构，林晚站在门边，冷灰氛围。",
            "镜头固定，保持首帧一致。",
            context,
            [{"asset_name": "钟楼阁楼", "locked_reference": True}],
        )
        self.assertTrue(next(item for item in allowed["checks"] if item["key"] == "locked_asset_fact_conflicts")["passed"])

        blocked = _build_prompt_compiler_diagnostics(
            "钟楼阁楼铁门前，木质结构，林晚站在门边，冷灰氛围。",
            "镜头固定，保持首帧一致。",
            context,
            [{"asset_name": "钟楼阁楼", "locked_reference": True}],
        )
        conflict_check = next(item for item in blocked["checks"] if item["key"] == "locked_asset_fact_conflicts")
        self.assertFalse(conflict_check["passed"])
        self.assertEqual(blocked["status"], "blocked")

        surface_detail = _build_prompt_compiler_diagnostics(
            "钟楼阁楼木门边，木质结构，门轴处有金属刮痕，林晚站在门边，冷灰氛围。",
            "镜头固定，保持首帧一致。",
            context,
            [{"asset_name": "钟楼阁楼", "locked_reference": True}],
        )
        self.assertTrue(next(item for item in surface_detail["checks"] if item["key"] == "locked_asset_fact_conflicts")["passed"])


if __name__ == "__main__":
    unittest.main()
