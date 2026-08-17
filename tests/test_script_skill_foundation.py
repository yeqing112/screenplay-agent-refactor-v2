import unittest

from core.production_skill import (
    _extract_scene_names_from_script,
    build_script_generation_brief,
    build_script_generation_brief_prompt_block,
    classify_script_qa_repair_stage,
    build_script_skill_execution_plan,
    build_script_issue_rewrite_directive,
    build_script_skill_execution_plan_prompt_block,
    build_script_skill_foundation,
    build_script_skill_foundation_prompt_block,
    build_script_skill_repair_packet,
    build_script_skill_repair_packet_prompt_block,
    classify_script_qa_rule_family,
    classify_script_qa_structure_layer,
    extract_script_qa_issues_from_result,
    load_latest_script_qa_issues,
)
from models import Book, KV, QAResult, Session, init_db


class ScriptSkillFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 991202
        self.kv_key = f"product_workspace:production_skill:{self.book_id}"
        with Session() as session:
            session.query(KV).filter(KV.key == self.kv_key).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.add(
                Book(
                    id=self.book_id,
                    title="Script Skill Foundation Book",
                    filename="script-skill-foundation-book.txt",
                    chapter_count=1,
                    total_words=880,
                    status="draft",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(KV).filter(KV.key == self.kv_key).delete()
            session.query(QAResult).filter(QAResult.book_id == self.book_id).delete()
            session.query(Book).filter(Book.id == self.book_id).delete()
            session.commit()

    def test_classify_script_qa_rule_family_maps_known_types(self):
        self.assertEqual(classify_script_qa_rule_family({"type": "hook"}), "episode_hook_strength")
        self.assertEqual(classify_script_qa_rule_family({"type": "continuity"}), "prop_evidence_continuity")
        self.assertEqual(
            classify_script_qa_rule_family(
                {
                    "type": "continuity",
                    "title": "lead monk persona conflicts with bound portrait",
                    "description": "character temperament drifts away from locked portrait canon",
                }
            ),
            "character_consistency",
        )
        self.assertEqual(classify_script_qa_rule_family({"type": "unknown_type"}), "generic_skill_gap")
        self.assertEqual(
            classify_script_qa_rule_family(
                {
                    "type": "logic_gap",
                    "title": "identity token conflict",
                    "description": "prop evidence chain is broken",
                }
            ),
            "prop_evidence_continuity",
        )
        self.assertEqual(
            classify_script_qa_rule_family(
                {
                    "type": "logic_gap",
                    "title": "motivation transition jump",
                    "description": "disguise reaction lacks trigger",
                }
            ),
            "character_state_transition",
        )

    def test_classify_script_qa_structure_layer_and_repair_stage(self):
        fact_issue = {"type": "continuity", "title": "法牌物证去向未交代"}
        scene_issue = {"type": "visual", "title": "线索没有入画"}
        compiler_issue = {"type": "hook", "title": "结尾钩子偏弱"}

        self.assertEqual(classify_script_qa_structure_layer(fact_issue), "fact_layer")
        self.assertEqual(classify_script_qa_repair_stage(fact_issue), "fact_generation")
        self.assertEqual(classify_script_qa_structure_layer(scene_issue), "scene_execution_layer")
        self.assertEqual(classify_script_qa_repair_stage(scene_issue), "scene_execution")
        self.assertEqual(classify_script_qa_structure_layer(compiler_issue), "compiler_layer")
        self.assertEqual(classify_script_qa_repair_stage(compiler_issue), "screenplay_compile")
        self.assertEqual(
            classify_script_qa_rule_family(
                {
                    "type": "logic_gap",
                    "title": "闂洖瑙嗚鏉ユ簮涓嶆槑",
                    "description": "memory provenance is unclear",
                }
            ),
            "character_state_transition",
        )
        self.assertEqual(
            classify_script_qa_rule_family(
                {
                    "type": "visual",
                    "title": "wax and copper trace never enter the frame",
                    "description": "visual evidence missing",
                }
            ),
            "clue_payoff_integrity",
        )
        self.assertEqual(
            classify_script_qa_rule_family(
                {
                    "type": "logic_gap",
                    "title": "scene-2 scripture appears without a transition beat",
                    "description": "the character appears in a new location without a handoff beat",
                }
            ),
            "character_state_transition",
        )

    def test_build_script_skill_foundation_creates_general_structure(self):
        outline = {
            "episode": 1,
            "title": "new monk episode",
            "core_event": "鏂颁汉鍏ュ鍚庤鍗峰叆寮傚父瑙勭煩",
            "opening_hook": "a bucket of cold water wakes the protagonist",
            "core_conflict": "three monks circle around hidden identity and temple rule pressure",
            "climax": "the key token is exposed before the standoff escalates",
            "ending_hook": "韬唤浠ゆ毚闇插悗鍏崇郴褰诲簳澶辫　",
            "characters": ["Monk A", "Monk B", "Monk C"],
            "scenes": ["姘存埧", "闄㈣惤", "鍘ㄦ埧"],
        }
        qa_issues = [
            {"type": "hook", "title": "缁撳熬閽╁瓙涓嶈冻", "severity": "medium", "fix_mode": "auto"},
            {"type": "continuity", "title": "浠ょ墝鏉ユ簮涓嶆竻", "severity": "high", "fix_mode": "semi_auto"},
        ]

        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline=outline,
            qa_issues=qa_issues,
        )

        self.assertEqual(payload["episode_goal_card"]["episode"], 1)
        self.assertEqual(payload["episode_goal_card"]["title"], "new monk episode")
        self.assertIn("story_fact_sheet", payload)
        self.assertEqual(payload["story_fact_sheet"]["episode_objective"], "three monks circle around hidden identity and temple rule pressure")
        self.assertEqual(len(payload["story_fact_sheet"]["character_fact_sheet"]), 3)
        self.assertEqual(payload["story_fact_sheet"]["character_fact_sheet"][0]["name"], "Monk A")
        self.assertEqual(len(payload["character_state_cards"]), 3)
        self.assertEqual(payload["character_state_cards"][0]["name"], "Monk A")
        self.assertEqual(len(payload["scene_goal_cards"]), 3)
        self.assertEqual(payload["scene_goal_cards"][1]["scene_name"], outline["scenes"][1])
        self.assertEqual(len(payload["clue_table"]), 3)
        self.assertEqual(payload["clue_table"][0]["scene_name"], outline["scenes"][0])
        self.assertEqual(len(payload["evidence_chain_table"]), 3)
        self.assertEqual(len(payload["hook_table"]), 3)
        self.assertEqual(payload["qa_backpressure"][0]["rule_family"], "episode_hook_strength")
        self.assertEqual(payload["qa_backpressure"][1]["rule_family"], "prop_evidence_continuity")
        self.assertIn("眼神变化", payload["character_state_cards"][0]["allowed_disguise_signals"])
        self.assertIn("speech_style_anchor", payload["character_state_cards"][0])
        self.assertIn("signature_speech_requirement", payload["character_state_cards"][0])
        self.assertIn("behavior_guardrails", payload["character_state_cards"][0])
        self.assertIn("omniscience_guardrail", payload["character_state_cards"][0])
        self.assertIn("flashback_provenance_guardrail", payload["character_state_cards"][0])
        self.assertIn("identity_cover_guardrail", payload["character_state_cards"][0])
        self.assertIn("asset_canon_reconciliation_guardrail", payload["character_state_cards"][0])
        self.assertIn("persona_layer_guardrail", payload["character_state_cards"][0])
        self.assertIn("hidden_layer_seed_requirement", payload["character_state_cards"][0])
        self.assertIn("hidden_layer_reveal_trigger_requirement", payload["character_state_cards"][0])
        self.assertIn("dialogue_format_guardrail", payload["character_state_cards"][0])
        self.assertIn("transition_requirement", payload["scene_goal_cards"][0])
        self.assertIn("relative_time_anchor_requirement", payload["scene_goal_cards"][0])
        self.assertIn("action_feasibility_requirement", payload["scene_goal_cards"][0])
        self.assertIn("investigation_trace_requirement", payload["scene_goal_cards"][0])
        self.assertIn("motivation_visibility_requirement", payload["scene_goal_cards"][0])
        self.assertIn("search_trigger_requirement", payload["scene_goal_cards"][0])
        self.assertIn("suggestive_glance_resolution_requirement", payload["scene_goal_cards"][0])
        self.assertIn("attitude_anchor_requirement", payload["scene_goal_cards"][0])
        self.assertIn("dialogue_evidence_order_requirement", payload["scene_goal_cards"][0])
        self.assertIn("visual_evidence_requirement", payload["scene_goal_cards"][0])
        self.assertIn("occluded_evidence_layer_requirement", payload["scene_goal_cards"][0])
        self.assertIn("seed_clue_visibility_requirement", payload["scene_goal_cards"][0])
        self.assertIn("concealed_clue_focus_requirement", payload["scene_goal_cards"][0])
        self.assertIn("prior_discovery_delta_requirement", payload["scene_goal_cards"][0])
        self.assertIn("comparison_visualization_requirement", payload["scene_goal_cards"][0])
        self.assertIn("multi_signal_match_requirement", payload["scene_goal_cards"][0])
        self.assertIn("color_signal_clarity_requirement", payload["scene_goal_cards"][0])
        self.assertIn("prop_asset_spec_requirement", payload["scene_goal_cards"][0])
        self.assertIn("audio_visual_pairing_requirement", payload["scene_goal_cards"][0])
        self.assertIn("delayed_discovery_gate_requirement", payload["scene_goal_cards"][0])
        self.assertIn("knowledge_provenance_requirement", payload["scene_goal_cards"][0])
        self.assertIn("split_evidence_timeline_requirement", payload["scene_goal_cards"][0])
        self.assertIn("ending_image_hook_requirement", payload["scene_goal_cards"][0])
        self.assertIn("orphan_clue_payoff_requirement", payload["scene_goal_cards"][0])
        self.assertIn("in_character_enforcement_requirement", payload["scene_goal_cards"][0])
        self.assertIn("hook_escalation_requirement", payload["scene_goal_cards"][0])
        self.assertIn("hook_delta_requirement", payload["scene_goal_cards"][0])
        self.assertIn("witness_silence_motivation_requirement", payload["scene_goal_cards"][0])
        self.assertIn("claim_evidence_ceiling_requirement", payload["scene_goal_cards"][0])
        self.assertIn("unique_clue_signature_requirement", payload["scene_goal_cards"][0])
        self.assertIn("evidence_observation_anchor_requirement", payload["scene_goal_cards"][0])
        self.assertIn("search_scope_requirement", payload["scene_goal_cards"][0])
        self.assertIn("route_trigger_requirement", payload["scene_goal_cards"][0])
        self.assertIn("repeat_inspection_trigger_requirement", payload["scene_goal_cards"][0])
        self.assertIn("anomaly_skip_reason_requirement", payload["scene_goal_cards"][0])
        self.assertIn("future_knowledge_guardrail", payload["scene_goal_cards"][0])
        self.assertIn("inference_disambiguation_requirement", payload["scene_goal_cards"][0])
        self.assertIn("accusation_evidence_threshold_requirement", payload["scene_goal_cards"][0])
        self.assertIn("next_action_objective_requirement", payload["scene_goal_cards"][0])
        self.assertIn("action_status_precision_requirement", payload["scene_goal_cards"][0])
        self.assertIn("escape_hardware_geometry_requirement", payload["scene_goal_cards"][0])
        self.assertIn("prop_custody_chain_requirement", payload["scene_goal_cards"][0])
        self.assertIn("core_prop_count_stability_requirement", payload["scene_goal_cards"][0])
        self.assertIn("restrained_access_sequence_requirement", payload["scene_goal_cards"][0])
        self.assertIn("helper_motive_seed_requirement", payload["scene_goal_cards"][0])
        self.assertIn("flashback_pressure_continuity_requirement", payload["scene_goal_cards"][0])
        self.assertIn("expository_dialogue_compression_requirement", payload["scene_goal_cards"][0])
        self.assertIn("revelation_density_guardrail", payload["scene_goal_cards"][0])
        self.assertIn("preloaded_tool_origin_requirement", payload["scene_goal_cards"][0])
        self.assertIn("offscreen_incident_anchor_requirement", payload["scene_goal_cards"][0])
        self.assertIn("environment_coherence_requirement", payload["scene_goal_cards"][0])
        self.assertIn("prop_restaging_requirement", payload["scene_goal_cards"][0])
        self.assertIn("hook_image_dominance_requirement", payload["scene_goal_cards"][0])
        self.assertIn("hook_question_specificity_requirement", payload["scene_goal_cards"][0])
        self.assertIn("identity_hint_calibration_requirement", payload["scene_goal_cards"][0])
        self.assertEqual(len(payload["prop_timeline_cards"]), 3)
        self.assertIn("prop_source_chain_requirement", payload["prop_timeline_cards"][0])
        self.assertIn("prop_state_reuse_requirement", payload["prop_timeline_cards"][0])
        self.assertIn("prop_repeat_take_requirement", payload["prop_timeline_cards"][0])
        self.assertIn("discarded_prop_recovery_requirement", payload["prop_timeline_cards"][0])
        self.assertIn("prop_naming_consistency_requirement", payload["prop_timeline_cards"][0])
        self.assertEqual(payload["investigation_trace_rules"][0]["applies_to"], "all_scenes")
        self.assertIn(qa_issues[1]["title"], payload["diagnostic_flags"])

    def test_character_consistency_issue_backfills_forbidden_conflicts(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "foundation-check",
                "characters": ["Monk A"],
                "scenes": ["well"],
            },
            qa_issues=[
                {
                    "type": "relationship_conflict",
                    "title": "character behavior conflicts with portrait canon",
                    "severity": "high",
                    "fix_mode": "manual",
                }
            ],
        )
        self.assertIn("character behavior conflicts with portrait canon", payload["character_state_cards"][0]["forbidden_behavior_conflicts"])
        self.assertIn(
            "QA flagged canon drift",
            payload["character_state_cards"][0]["asset_canon_reconciliation_guardrail"],
        )
        self.assertIn(
            "preserve the public layer",
            payload["character_state_cards"][0]["persona_layer_guardrail"],
        )

    def test_backpressure_adds_hidden_layer_seed_requirements_for_abrupt_capability_shift(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "hidden-layer-check",
                "characters": ["Monk A"],
                "scenes": ["well"],
            },
            qa_issues=[
                {
                    "type": "continuity",
                    "title": "the hidden competence arrives too abruptly after the robe stash reveal",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                }
            ],
        )
        self.assertIn(
            "plant at least one small on-screen seed",
            payload["character_state_cards"][0]["hidden_layer_seed_requirement"],
        )
        self.assertIn(
            "tie it to a visible trigger in the same beat",
            payload["character_state_cards"][0]["hidden_layer_reveal_trigger_requirement"],
        )

    def test_backpressure_adds_observation_anchor_and_specific_hook_question_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "observation-hook-check",
                "characters": ["Monk A"],
                "scenes": ["well"],
            },
            qa_issues=[
                {
                    "type": "foreshadowing",
                    "title": "白草纤维的提示功能被弱化",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "hook",
                    "title": "结尾钩子强度不足，缺少新问题",
                    "severity": "high",
                    "fix_mode": "auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn(
            "actively observe, compare, touch, or align the trace",
            scene_card["evidence_observation_anchor_requirement"],
        )
        self.assertIn(
            "leave one concrete unresolved question",
            scene_card["hook_question_specificity_requirement"],
        )

    def test_backpressure_adds_route_trigger_and_prop_custody_chain_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "route-custody-check",
                "characters": ["Monk A"],
                "scenes": ["well", "shrine"],
            },
            qa_issues=[
                {
                    "type": "logic_gap",
                    "title": "甲出库房直奔山门供台的推理断档",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "continuity",
                    "title": "法牌物证去向未交代",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn(
            "destination jump that felt like coincidence",
            scene_card["route_trigger_requirement"],
        )
        self.assertIn(
            "show who takes custody of it",
            scene_card["prop_custody_chain_requirement"],
        )

    def test_backpressure_adds_future_knowledge_count_stability_and_helper_motive_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "timeline-count-helper-check",
                "characters": ["Monk A"],
                "scenes": ["cell", "shrine"],
            },
            qa_issues=[
                {
                    "type": "logic_gap",
                    "title": "甲内心独白预知乙取牌，时间线倒置",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "logic_gap",
                    "title": "栽赃法牌与暗格法牌数量关系不清",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "logic_gap",
                    "title": "反绑状态下取前襟铜丝动作不可实现",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "motivation",
                    "title": "丙暗中帮助甲的动机不足",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn(
            "described a later event too early",
            scene_card["future_knowledge_guardrail"],
        )
        self.assertIn(
            "core prop multiplying without setup",
            scene_card["core_prop_count_stability_requirement"],
        )
        self.assertIn(
            "impossible front-body access under restraint",
            scene_card["restrained_access_sequence_requirement"],
        )
        self.assertIn(
            "repeated covert help without motive",
            scene_card["helper_motive_seed_requirement"],
        )

    def test_backpressure_adds_generalized_source_timeline_and_hook_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "source-timeline-check",
                "characters": ["Monk A"],
                "scenes": ["well", "courtyard"],
            },
            qa_issues=[
                {
                    "type": "motivation",
                    "title": "the protagonist reveals a hidden scripture trick without prior setup",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "continuity",
                    "title": "閫佸嚭瀵哄鐨勪竴寮忚处椤垫椂闂寸嚎鑷浉鐭涚浘",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "visual",
                    "title": "缁撳熬浜曞簳閽╁瓙缂轰箯鐢婚潰鍏戠幇",
                    "severity": "medium",
                    "fix_mode": "auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn("show where that knowledge came from", scene_card["knowledge_provenance_requirement"])
        self.assertIn("show the split explicitly", scene_card["split_evidence_timeline_requirement"])
        self.assertIn("hook should land on a visible image memory", scene_card["ending_image_hook_requirement"])

    def test_backpressure_adds_generalized_time_discovery_and_silence_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "time-discovery-check",
                "characters": ["Monk A"],
                "scenes": ["well", "quarters"],
            },
            qa_issues=[
                {
                    "type": "continuity",
                    "title": "the delivery time of the page conflicts with the staged timeline",
                    "severity": "high",
                    "fix_mode": "auto",
                },
                {
                    "type": "logic_gap",
                    "title": "鐧藉ぉ缈讳簳鍙ｆ湭鍙戠幇婀块夯甯冿紝澶滄櫄鍗磋兘鐩存帴鎶藉嚭",
                    "severity": "medium",
                    "fix_mode": "manual",
                },
                {
                    "type": "motivation",
                    "title": "the protagonist sees a bloodied hand at night but stays silent without motive",
                    "severity": "low",
                    "fix_mode": "semi_auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn("QA flagged a relative-time conflict", scene_card["relative_time_anchor_requirement"])
        self.assertIn("show why it was missed before", scene_card["delayed_discovery_gate_requirement"])
        self.assertIn("QA flagged unexplained silence", scene_card["witness_silence_motivation_requirement"])

    def test_backpressure_adds_asset_search_glance_and_comparison_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "asset-search-compare-check",
                "characters": ["Monk A"],
                "scenes": ["well", "shed"],
            },
            qa_issues=[
                {
                    "type": "visual",
                    "title": "法牌刻字位置与层叠关系含糊，关键道具无法资产化",
                    "severity": "high",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "motivation",
                    "title": "甲在柴房主动转向墙根查找，缺少镜头动机铺垫",
                    "severity": "high",
                    "fix_mode": "auto",
                },
                {
                    "type": "foreshadowing",
                    "title": "丙在柴房看了一眼墙根的镜头语意不明",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "continuity",
                    "title": "关键证据同一挂布仅靠台词判断，未进入画面",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "continuity",
                    "title": "木牌与法牌术语混用，同一道具出现两个名字",
                    "severity": "low",
                    "fix_mode": "auto",
                },
                {
                    "type": "visual",
                    "title": "布结浸水暗红散开易被误解为血水",
                    "severity": "low",
                    "fix_mode": "auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        prop_card = payload["prop_timeline_cards"][0]
        self.assertIn("asset-unsafe prop description", scene_card["prop_asset_spec_requirement"])
        self.assertIn("unmotivated targeted search", scene_card["search_trigger_requirement"])
        self.assertIn("suggestive glance without payoff", scene_card["suggestive_glance_resolution_requirement"])
        self.assertIn("readable pause", scene_card["attitude_anchor_requirement"])
        self.assertIn("claimed evidence match that was not visualized", scene_card["comparison_visualization_requirement"])
        self.assertIn("second confirming dimension", scene_card["multi_signal_match_requirement"])
        self.assertIn("misleading clue color", scene_card["color_signal_clarity_requirement"])
        self.assertIn("prop naming drift", prop_card["prop_naming_consistency_requirement"])

    def test_backpressure_adds_seed_skip_accusation_and_flashback_pressure_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "seed-skip-accusation-check",
                "characters": ["Monk A"],
                "scenes": ["well", "shed"],
            },
            qa_issues=[
                {
                    "type": "continuity",
                    "title": "关键压痕证据未进入画面",
                    "severity": "high",
                    "fix_mode": "auto",
                },
                {
                    "type": "logic_gap",
                    "title": "丙搜到铜线尖却未检查，行为不合常理",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "motivation",
                    "title": "乙丙锁定甲的动机证据链不足",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "pace",
                    "title": "场景二闪回段略长，影响门外影子的紧张延续",
                    "severity": "low",
                    "fix_mode": "auto",
                },
                {
                    "type": "continuity",
                    "title": "法牌与手抄经位置矛盾，乙看完后未见放回，丙却又从包袱里取出",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        prop_card = payload["prop_timeline_cards"][0]
        self.assertIn("seed detail in the active scene image", scene_card["seed_clue_visibility_requirement"])
        self.assertIn("interruption, bluff, concealed alliance", scene_card["anomaly_skip_reason_requirement"])
        self.assertIn("visible accusation trigger", scene_card["accusation_evidence_threshold_requirement"])
        self.assertIn("watch, isolate, stall, or seize objective", scene_card["detainer_intent_anchor_requirement"])
        self.assertIn("present-tense pressure alive across the cut", scene_card["flashback_pressure_continuity_requirement"])
        self.assertIn("handoff, return, concealment, or repossession beat", prop_card["same_scene_prop_handoff_requirement"])

    def test_backpressure_adds_occluded_status_and_identity_hint_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "layer-status-identity-check",
                "characters": ["Monk A"],
                "scenes": ["shed"],
            },
            qa_issues=[
                {
                    "type": "logic_gap",
                    "title": "法牌蜡块底下的刻痕被直接写成可见，视觉层级混乱",
                    "severity": "high",
                    "fix_mode": "auto",
                },
                {
                    "type": "dialogue_style",
                    "title": "“查清了”与“明早再放他走”语义冲突",
                    "severity": "low",
                    "fix_mode": "auto",
                },
                {
                    "type": "visual",
                    "title": "门外鞋影身份指向模糊，但镜头暗示过多",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn("visible surface trace from the still-covered inner mark", scene_card["occluded_evidence_layer_requirement"])
        self.assertIn("spoken status words such as checked, confirmed, solved, cleared, released", scene_card["action_status_precision_requirement"])
        self.assertIn("intended certainty level", scene_card["identity_hint_calibration_requirement"])

    def test_backpressure_adds_order_delta_enforcement_and_hook_delta_requirements(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "order-delta-hook-check",
                "characters": ["Monk A"],
                "scenes": ["water-room"],
            },
            qa_issues=[
                {
                    "type": "evidence_only_in_dialogue",
                    "title": "山门丢念珠只存在于台词中，未先进入画面",
                    "severity": "high",
                    "fix_mode": "auto",
                },
                {
                    "type": "continuity",
                    "title": "同一条蜡缝前面已展示，后面又被当作新发现",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "character_portrait_drift",
                    "title": "和尚丙主动调查倾向过强，超出推诿画像",
                    "severity": "medium",
                    "fix_mode": "semi_auto",
                },
                {
                    "type": "hook",
                    "title": "集尾钩子只是重复已知刀痕，没有新信息增量",
                    "severity": "medium",
                    "fix_mode": "auto",
                },
            ],
        )
        scene_card = payload["scene_goal_cards"][0]
        self.assertIn("first spoken mention", scene_card["dialogue_evidence_order_requirement"])
        self.assertIn("add a new layer of information instead of replaying the same discovery", scene_card["prior_discovery_delta_requirement"])
        self.assertIn("stage that action through their own mask", scene_card["in_character_enforcement_requirement"])
        self.assertIn("only restated known facts", scene_card["hook_delta_requirement"])

    def test_classify_dialogue_format_issue_as_output_completeness(self):
        family = classify_script_qa_rule_family(
            {
                "type": "format",
                "title": "对白格式不统一",
                "description": "部分对白没有使用角色：台词格式，影响字幕抽取。",
            }
        )
        self.assertEqual(family, "output_completeness")

    def test_build_script_skill_foundation_prompt_block_renders_json_block(self):
        block = build_script_skill_foundation_prompt_block(
            self.book_id,
            episode_outline={"episode": 2, "title": "prompt-block-demo"},
        )
        self.assertIn("## Script Skill Foundation", block)
        self.assertIn('"episode": 2', block)
        self.assertIn('"title": "prompt-block-demo"', block)

    def test_build_script_generation_brief_exposes_structured_middle_layer(self):
        payload = build_script_generation_brief(
            self.book_id,
            episode_outline={
                "episode": 2,
                "title": "brief-demo",
                "core_conflict": "temple clue pressure",
                "opening_hook": "bucket strike",
                "climax": "wax clue opens",
                "ending_hook": "shadow returns",
                "characters": ["Monk A", "Monk B"],
                "scenes": ["water-room", "shed"],
            },
        )
        self.assertEqual(payload["episode_goal"]["title"], "brief-demo")
        self.assertIn("story_fact_sheet", payload)
        self.assertEqual(payload["story_fact_sheet"]["episode_objective"], "temple clue pressure")
        self.assertEqual(len(payload["character_playbook"]), 2)
        self.assertEqual(payload["character_playbook"][0]["name"], "Monk A")
        self.assertEqual(len(payload["scene_compilation_cards"]), 2)
        self.assertEqual(len(payload["scene_execution_cards"]), 2)
        self.assertIn("opening_state", payload["scene_execution_cards"][0])
        self.assertIn("required_visual_proofs", payload["scene_execution_cards"][0])
        self.assertIn("handoff_to_next_scene", payload["scene_execution_cards"][0])
        self.assertIn("structural_goals", payload["scene_compilation_cards"][0])
        self.assertIn("scene_driver", payload["scene_compilation_cards"][0]["structural_goals"])
        self.assertIn("new_evidence", payload["scene_compilation_cards"][0]["structural_goals"])
        self.assertIn("exit_delta", payload["scene_compilation_cards"][0]["structural_goals"])
        self.assertIn("hook_delta", payload["scene_compilation_cards"][0]["requirements"])
        self.assertIn("unique_clue_signature", payload["scene_compilation_cards"][0]["requirements"])
        self.assertIn("repeat_inspection_trigger", payload["scene_compilation_cards"][0]["requirements"])
        self.assertIn("escape_hardware_geometry", payload["scene_compilation_cards"][0]["requirements"])
        self.assertIn("subjective_state_externalization", payload["scene_compilation_cards"][0]["requirements"])
        self.assertEqual(len(payload["prop_timeline_brief"]), 2)
        self.assertIn("tracking_requirement", payload["prop_timeline_brief"][0])
        self.assertIn("scene_open_state", payload["prop_timeline_brief"][0])
        self.assertIn("scene_close_target", payload["prop_timeline_brief"][0])
        self.assertIn("required_transfer_beats", payload["prop_timeline_brief"][0])
        self.assertIn("repeat_take_requirement", payload["prop_timeline_brief"][0])
        self.assertEqual(len(payload["hook_delta_targets"]), 3)

    def test_build_script_generation_brief_prompt_block_renders_json_block(self):
        block = build_script_generation_brief_prompt_block(
            self.book_id,
            episode_outline={"episode": 3, "title": "generation-brief-demo"},
        )
        self.assertIn("## Script Generation Brief", block)
        self.assertIn('"episode": 3', block)
        self.assertIn('"title": "generation-brief-demo"', block)

    def test_build_script_skill_foundation_prefers_real_script_scene_structure(self):
        payload = build_script_skill_foundation(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "scene-merge",
                "characters": ["A"],
                "scenes": ["legacy-scene-1", "legacy-scene-2"],
            },
            script_content="\n".join(
                [
                    "**场景一:[well-morning]**",
                    "beat A",
                    "**场景二:[courtyard-noon]**",
                    "beat B",
                    "**场景三:[room-night]**",
                    "beat C",
                ]
            ),
        )
        self.assertEqual(len(payload["scene_goal_cards"]), 3)
        self.assertEqual(payload["scene_goal_cards"][0]["scene_name"], "well-morning")
        self.assertEqual(payload["scene_goal_cards"][2]["scene_name"], "room-night")

    def test_extract_scene_names_from_script_supports_hash_scene_headers(self):
        names = _extract_scene_names_from_script(
            "\n".join(
                [
                    "## 场景一 [寺庙水房·清晨]",
                    "画面：冷水兜头泼下。",
                    "## 场景二 [库房·入夜]",
                    "画面：门闩落下，油灯一晃。",
                ]
            )
        )
        self.assertEqual(names, ["寺庙水房·清晨", "库房·入夜"])

    def test_build_script_skill_execution_plan_prioritizes_qa_rule_families(self):
        payload = build_script_skill_execution_plan(
            self.book_id,
            episode_outline={"episode": 1, "title": "execution-plan-demo"},
            qa_issues=[
                {"type": "hook", "title": "opening hook weak"},
                {"type": "hook", "title": "ending hook weak"},
                {"type": "continuity", "title": "閬撳叿鏂"},
            ],
        )
        self.assertEqual(payload["episode_title"], "execution-plan-demo")
        self.assertEqual(payload["compiler_stages"][0]["stage"], "fact_generation")
        self.assertEqual(payload["compiler_stages"][1]["stage"], "scene_execution")
        self.assertEqual(payload["compiler_stages"][2]["stage"], "screenplay_compile")
        self.assertEqual(payload["compiler_stages"][3]["stage"], "structure_qa")
        self.assertIn("structure_focus", payload)
        self.assertEqual(payload["structure_focus"]["dominant_stage"], "screenplay_compile")
        self.assertEqual(payload["stage_repair_priorities"][0]["repair_stage"], "screenplay_compile")
        self.assertEqual(payload["repair_priorities"][0]["rule_family"], "episode_hook_strength")
        self.assertEqual(payload["repair_priorities"][0]["issue_count"], 2)
        self.assertEqual(payload["repair_priorities"][1]["rule_family"], "prop_evidence_continuity")

    def test_build_script_skill_execution_plan_prompt_block_renders_json_block(self):
        block = build_script_skill_execution_plan_prompt_block(
            self.book_id,
            episode_outline={"episode": 3, "title": "鎵ц璁″垝娴嬭瘯"},
            qa_issues=[{"type": "hook", "title": "hook weak"}],
        )
        self.assertIn("## Script Skill Execution Plan", block)
        self.assertIn('"episode_title": "鎵ц璁″垝娴嬭瘯"', block)
        self.assertIn('"rule_family": "episode_hook_strength"', block)

    def test_build_script_skill_repair_packet_summarizes_priority_briefs(self):
        payload = build_script_skill_repair_packet(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "repair-packet",
                "characters": ["A", "B"],
            },
            qa_issues=[
                {
                    "type": "continuity",
                    "title": "prop chain broken",
                    "description": "token evidence handoff missing",
                    "location": {"script_section": "scene-4"},
                },
                {
                    "type": "hook",
                    "title": "ending hook weak",
                    "description": "next episode pull is unclear",
                    "location": {"script_section": "scene-8"},
                },
            ],
            script_content="\n".join(
                [
                    "**Scene 1:[well-morning]**",
                    "beat A",
                    "**Scene 2:[hall-night]**",
                    "beat B",
                ]
            ),
        )
        self.assertEqual(payload["scene_count"], 2)
        self.assertEqual(payload["character_count"], 2)
        self.assertIn("story_fact_sheet", payload)
        self.assertIn("structure_focus", payload)
        self.assertEqual(payload["structure_focus"]["dominant_layer"], "compiler_layer")
        self.assertTrue(payload["stage_repair_priorities"])
        self.assertEqual(len(payload["scene_execution_cards"]), 2)
        self.assertIn("opening_state", payload["scene_execution_cards"][0])
        self.assertIn("required_visual_proofs", payload["scene_execution_cards"][0])
        self.assertTrue(payload["issue_rewrite_directives"])
        self.assertIn("issue_title", payload["issue_rewrite_directives"][0])
        self.assertIn("directive", payload["issue_rewrite_directives"][0])
        self.assertIn("structure_layer", payload["issue_rewrite_directives"][0])
        self.assertIn("repair_stage", payload["issue_rewrite_directives"][0])
        self.assertTrue(payload["stage_repair_agenda"])
        self.assertEqual(payload["stage_repair_agenda"][0]["repair_stage"], "fact_generation")
        self.assertIn("ordered_actions", payload["stage_repair_agenda"][0])
        self.assertTrue(payload["scene_repair_agenda"])
        self.assertEqual(payload["scene_repair_agenda"][0]["scene_name"], "well-morning")
        self.assertIn("stage_tasks", payload["scene_repair_agenda"][0])
        self.assertEqual(payload["scene_names"][0], "well-morning")
        continuity_brief = next(item for item in payload["repair_briefs"] if item["rule_family"] == "prop_evidence_continuity")
        self.assertIn("scene-4", continuity_brief["target_sections"])
        self.assertIn("fact_layer", continuity_brief["structure_layers"])
        self.assertIn("fact_generation", continuity_brief["repair_stages"])
        self.assertIn("fact_generation", continuity_brief["compiler_stage_focus"])
        self.assertIn("scene_execution", continuity_brief["compiler_stage_focus"])
        self.assertIn("clue_evidence_compilation", continuity_brief["legacy_stage_focus"])
        self.assertEqual(payload["scene_transition_requirements"][0]["scene_name"], "well-morning")
        self.assertTrue(payload["scene_transition_requirements"][0]["transition_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["relative_time_anchor_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["action_feasibility_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["investigation_trace_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["motivation_visibility_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["visual_evidence_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["audio_visual_pairing_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["delayed_discovery_gate_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["knowledge_provenance_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["split_evidence_timeline_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["ending_image_hook_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["hook_escalation_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["witness_silence_motivation_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["claim_evidence_ceiling_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["unique_clue_signature_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["search_scope_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["repeat_inspection_trigger_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["inference_disambiguation_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["next_action_objective_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["escape_hardware_geometry_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["expository_dialogue_compression_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["revelation_density_guardrail"])
        self.assertTrue(payload["scene_transition_requirements"][0]["preloaded_tool_origin_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["environment_coherence_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["prop_restaging_requirement"])
        self.assertTrue(payload["scene_transition_requirements"][0]["hook_image_dominance_requirement"])
        self.assertEqual(payload["dialogue_guardrails"][0]["character"], "A")
        self.assertTrue(payload["dialogue_guardrails"][0]["speech_style_anchor"])
        self.assertTrue(payload["dialogue_guardrails"][0]["omniscience_guardrail"])
        self.assertTrue(payload["dialogue_guardrails"][0]["flashback_provenance_guardrail"])
        self.assertTrue(payload["dialogue_guardrails"][0]["identity_cover_guardrail"])
        self.assertTrue(payload["dialogue_guardrails"][0]["asset_canon_reconciliation_guardrail"])
        self.assertEqual(payload["prop_timeline_guardrails"][0]["scene_name"], "well-morning")
        self.assertTrue(payload["prop_timeline_guardrails"][0]["prop_tracking_requirement"])
        self.assertTrue(payload["prop_timeline_guardrails"][0]["prop_source_chain_requirement"])
        self.assertTrue(payload["prop_timeline_guardrails"][0]["prop_state_reuse_requirement"])
        self.assertTrue(payload["prop_timeline_guardrails"][0]["prop_repeat_take_requirement"])
        self.assertTrue(payload["prop_timeline_guardrails"][0]["discarded_prop_recovery_requirement"])

    def test_build_script_skill_repair_packet_prefers_hash_scene_headers_over_stale_outline(self):
        payload = build_script_skill_repair_packet(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "repair-packet-scene-sync",
                "characters": ["A", "B"],
                "scenes": ["寺庙水房", "住处"],
            },
            script_content="\n".join(
                [
                    "## 场景一 [寺庙水房·清晨]",
                    "画面：冷水兜头泼下。",
                    "## 场景二 [库房·入夜]",
                    "画面：门闩落下，油灯一晃。",
                ]
            ),
        )
        self.assertEqual(payload["scene_names"], ["寺庙水房·清晨", "库房·入夜"])
        self.assertTrue(payload["prop_timeline_guardrails"][0]["evidence_consistency_requirement"])
        self.assertTrue(payload["prop_timeline_guardrails"][0]["micro_fact_consistency_requirement"])
        self.assertEqual(payload["investigation_trace_rules"][0]["applies_to"], "all_scenes")
        self.assertEqual(payload["evidence_consistency_rules"][0]["applies_to"], "all_high_value_props")
        applies_to = {item["applies_to"] for item in payload["investigation_trace_rules"]}
        self.assertIn("all_hidden_method_reveals", applies_to)
        self.assertIn("all_split_document_or_duplicate_evidence_beats", applies_to)
        self.assertIn("all_relative_time_claims", applies_to)
        self.assertIn("all_delayed_discoveries_in_previously_searched_spaces", applies_to)
        self.assertIn("all_witness_silence_beats", applies_to)
        self.assertIn("all_body_constraint_beats", applies_to)
        self.assertIn("all_plot_relevant_sound_cues", applies_to)
        self.assertIn("all_repeated_hook_motifs", applies_to)
        self.assertIn("all_discarded_prop_recoveries", applies_to)
        self.assertIn("all_evidence_claims_in_dialogue", applies_to)
        self.assertIn("all_repair_level_changes", applies_to)

    def test_build_script_skill_repair_packet_builds_scene_and_stage_agenda_from_issue_targets(self):
        payload = build_script_skill_repair_packet(
            self.book_id,
            episode_outline={
                "episode": 1,
                "title": "agenda-check",
                "characters": ["A", "B"],
            },
            qa_issues=[
                {
                    "type": "continuity",
                    "title": "token chain broken",
                    "description": "token evidence handoff missing",
                    "location": {"script_section": "场景二-危机"},
                },
                {
                    "type": "visual",
                    "title": "clue never enters the frame",
                    "description": "the token comparison beat is missing on screen",
                    "location": {"script_section": "场景二-危机"},
                },
                {
                    "type": "characterization",
                    "title": "character behavior conflicts with portrait canon",
                    "description": "public persona drifts",
                    "location": {"script_section": "场景一-搜身"},
                },
            ],
            script_content="\n".join(
                [
                    "## 场景一 [寺庙水房·清晨]",
                    "画面：冷水兜头泼下。",
                    "## 场景二 [库房·入夜]",
                    "画面：门闩落下，油灯一晃。",
                ]
            ),
        )

        fact_stage = next(item for item in payload["stage_repair_agenda"] if item["repair_stage"] == "fact_generation")
        self.assertIn("寺庙水房·清晨", fact_stage["scene_targets"])
        scene_exec_stage = next(item for item in payload["stage_repair_agenda"] if item["repair_stage"] == "scene_execution")
        self.assertIn("库房·入夜", scene_exec_stage["scene_targets"])
        scene_one = next(item for item in payload["scene_repair_agenda"] if item["scene_name"] == "寺庙水房·清晨")
        self.assertTrue(scene_one["stage_tasks"])
        self.assertEqual(scene_one["stage_tasks"][0]["repair_stage"], "fact_generation")

    def test_build_script_issue_rewrite_directive_maps_common_real_sample_failures(self):
        self.assertIn(
            "bound character persona",
            build_script_issue_rewrite_directive(
                {"type": "characterization", "title": "鍜屽皻鐢蹭汉鐗╃敾鍍忎笌涓村満琛ㄧ幇婕傜Щ"}
            ),
        )
        self.assertIn(
            "reluctant efficiency",
            build_script_issue_rewrite_directive(
                {"type": "other", "title": "和尚乙丙懒散画像与主动搜身扣押行为冲突"}
            ),
        )
        self.assertIn(
            "smallest consistent adjustment",
            build_script_issue_rewrite_directive(
                {"type": "continuity", "title": "澶囩敤缁冲嚭鐜版椂闂翠笌瀵圭櫧鐭涚浘"}
            ),
        )
        self.assertIn(
            "smallest consistent adjustment",
            build_script_issue_rewrite_directive(
                {"type": "logic", "title": "琛€鎺屽嵃鍙鎬т笌纭肩爞鏄惧奖鐭涚浘"}
            ),
        )
        self.assertIn(
            "smallest consistent adjustment",
            build_script_issue_rewrite_directive(
                {"type": "continuity", "title": "a tied character cannot reach into the water without a release beat"}
            ),
        )
        self.assertIn(
            "visible shot-comparison beat",
            build_script_issue_rewrite_directive(
                {"type": "visual", "title": "鍦烘櫙涓€缁撳熬澹板儚閿瑰垉纰扮煶缂轰箯瑙嗚鏀拺"}
            ),
        )
        self.assertIn(
            "recovery",
            build_script_issue_rewrite_directive(
                {"type": "continuity", "title": "the scripture token reappears after being discarded without recovery"}
            ),
        )
        self.assertIn(
            "eyewitness fact",
            build_script_issue_rewrite_directive(
                {"type": "dialogue_style", "title": "speaker states eyewitness fact that the staged image does not support"}
            ),
        )
        self.assertIn(
            "search scope",
            build_script_issue_rewrite_directive(
                {"type": "continuity", "title": "search scope is unclear so the frisk misses hidden evidence"}
            ),
        )
        self.assertIn(
            "distinguishing feature",
            build_script_issue_rewrite_directive(
                {"type": "logic_gap", "title": "the cutter identity inference remains ambiguous"}
            ),
        )
        self.assertIn(
            "Apply the fix directly inside the screenplay body",
            build_script_issue_rewrite_directive(
                {"type": "motivation", "title": "the next risky action lacks a concrete objective on screen"}
            ),
        )
        self.assertIn(
            "places a high-value prop back into view and then handles it again soon after",
            build_script_issue_rewrite_directive(
                {"type": "continuity", "title": "the same character puts the token back and then re-takes it again without a reason"}
            ),
        )
        self.assertIn(
            "inspects the same hidden area again later",
            build_script_issue_rewrite_directive(
                {"type": "logic_gap", "title": "the guard checks the same robe seam again but no new trigger is shown"}
            ),
        )
        self.assertIn(
            "shared material is not enough for a decisive match",
            build_script_issue_rewrite_directive(
                {"type": "logic_gap", "title": "grass fiber clue lacks a unique signature and relies on same material only"}
            ),
        )
        self.assertIn(
            "Match the escape beat to the shown latch geometry",
            build_script_issue_rewrite_directive(
                {"type": "logic_gap", "title": "the hook opens the latch but the hardware geometry is never established"}
            ),
        )
        self.assertIn(
            "intentional choice",
            build_script_issue_rewrite_directive(
                {"type": "motivation", "title": "丙发现铜线尖却未揭穿，行为动机缺失"}
            ),
        )
        self.assertIn(
            "wording matches the current action phase",
            build_script_issue_rewrite_directive(
                {"type": "dialogue_style", "title": "“查清了”与“明早再放他走”语义冲突"}
            ),
        )
        self.assertIn(
            "Match accusation wording to the visible custody state",
            build_script_issue_rewrite_directive(
                {"type": "logic_gap", "title": "乙说甲撞进来，但画面里甲已被反绑控制"}
            ),
        )
        self.assertIn(
            "bounded unresolved question",
            build_script_issue_rewrite_directive(
                {"type": "foreshadowing", "title": "铜线用途留白过大，观众只剩困惑没有明确疑问"}
            ),
        )
        self.assertIn(
            "bound character persona",
            build_script_issue_rewrite_directive(
                {"type": "dialogue_style", "title": "鐢茬殑瑙ｈ皽鍙拌瘝杩囦簬瑙ｉ噴鎬э紝鐣ユ樉鐢熺‖"}
            ),
        )
        self.assertIn(
            "visible shot-comparison beat",
            build_script_issue_rewrite_directive(
                {"type": "visualization", "title": "鍏抽敭璇佹嵁渚濊禆瑙ｈ鑰岄潪鐢婚潰鍛堢幇"}
            ),
        )

    def test_build_script_skill_repair_packet_prompt_block_renders_json_block(self):
        block = build_script_skill_repair_packet_prompt_block(
            self.book_id,
            episode_outline={"episode": 4, "title": "repair-packet-prompt"},
            qa_issues=[{"type": "hook", "title": "hook weak"}],
            script_content="**Scene 1:[gate-dawn]**",
        )
        self.assertIn("## Script Skill Repair Packet", block)
        self.assertIn('"scene_count": 1', block)
        self.assertIn('"rule_family": "episode_hook_strength"', block)

    def test_extract_script_qa_issues_normalizes_errors_payload(self):
        items = extract_script_qa_issues_from_result(
            {
                "errors": [
                    {
                        "type": "format",
                        "severity": "high",
                        "description": "script is incomplete",
                    }
                ]
            }
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "format")
        self.assertEqual(items[0]["title"], "script is incomplete")

    def test_load_latest_script_qa_issues_returns_latest_result_items(self):
        with Session() as session:
            session.add(
                QAResult(
                    book_id=self.book_id,
                    episode=1,
                    result='{"issues":[{"type":"hook","severity":"medium","title":"old hook"}]}' ,
                    error_count=1,
                )
            )
            session.add(
                QAResult(
                    book_id=self.book_id,
                    episode=1,
                    result='{"issues":[{"type":"continuity","severity":"high","title":"new issue"}]}' ,
                    error_count=1,
                )
            )
            session.commit()

        items = load_latest_script_qa_issues(self.book_id, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "new issue")
        self.assertEqual(items[0]["type"], "continuity")


if __name__ == "__main__":
    unittest.main()
