"""Deterministic tests for the Contract-First director prompt builder."""

from __future__ import annotations

import hashlib
import unittest

from core.director_prompt import (
    DIRECTOR_PROMPT_PROTOCOL_VERSION,
    SEMI_STABLE_USER_PREFIX,
    STABLE_SYSTEM_PREFIX,
    build_director_patch_prompt,
)


def _contract(scene_name: str) -> dict:
    return {
        "schema_version": "director_creative_contract_v1",
        "contract_fingerprint": f"contract-{scene_name}",
        "immutable_fields": ["scene_name", "event", "asset_bindings"],
        "allowed_patch_paths": ["/shots/*/camera/shot_size", "/shots/*/why_this_shot"],
        "auxiliary_shot_policy": {"allowed_types": ["reaction"], "max_per_source_beat": 2},
        "source_beat_map": {"B01": {"beat_id": "B01", "event": "进入"}},
        "immutable_projection": {"facts": {"participants": ["CHAR_001"]}},
    }


def _strategy(scene_name: str) -> dict:
    return {
        "schema_version": "scene_directing_strategy_v1",
        "strategy_fingerprint": f"strategy-{scene_name}",
        "scene_objective": f"objective-{scene_name}",
        "visual_strategy": "空间关系优先",
        "emotional_curve": [{"beat_id": "B01", "intensity": 5}],
        "information_strategy": {"reveal_order": ["B01"], "withhold_until": [], "audience_focus": []},
        "power_curve": [{"beat_id": "B01", "dominant_character": "CHAR_001"}],
        "rhythm_strategy": "按节拍剪辑",
        "camera_language": {"base_style": "自然透视", "movement_rule": "有动机才移动", "closeup_rule": "服务反应", "reaction_rule": "完成反应再切"},
        "forbidden_tendencies": ["gratuitous_camera_movement"],
    }


def _plan(scene_name: str) -> dict:
    return {
        "scene_name": scene_name,
        "evidence_fingerprint": f"plan-{scene_name}",
        "unknowns": [],
        "shots": [{"plan_shot_id": "S01", "beat_id": "B01", "event": "进入", "camera": {"shot_size": "MS"}}],
    }


class DirectorPromptTests(unittest.TestCase):
    def test_stable_prefix_is_scene_independent_and_contains_contract_rules(self):
        first = build_director_patch_prompt(contract=_contract("A"), strategy=_strategy("A"), structural_shot_plan=_plan("A"))
        second = build_director_patch_prompt(contract=_contract("B"), strategy=_strategy("B"), structural_shot_plan=_plan("B"))

        self.assertEqual(first["protocol_version"], DIRECTOR_PROMPT_PROTOCOL_VERSION)
        self.assertEqual(first["system_prompt"], second["system_prompt"])
        self.assertEqual(first["stable_prefix_fingerprint"], second["stable_prefix_fingerprint"])
        self.assertEqual(first["prompt_prefix_fingerprint"], first["stable_prefix_fingerprint"])
        self.assertEqual(first["stable_prefix_hash"], first["stable_prefix_fingerprint"])
        self.assertGreater(first["stable_prefix_length"], 0)
        self.assertNotEqual(first["variable_tail_hash"], second["variable_tail_hash"])
        self.assertIn("ALLOWED PATCH PATHS", first["system_prompt"])
        self.assertIn("FORBIDDEN PATHS", first["system_prompt"])
        self.assertIn("AUXILIARY SHOT POLICY", first["system_prompt"])
        self.assertIn("QUALITY RULES", first["system_prompt"])
        self.assertNotEqual(first["user_prompt"], second["user_prompt"])

    def test_hashes_are_content_based_and_user_context_is_canonical(self):
        result = build_director_patch_prompt(
            contract=_contract("A"),
            strategy=_strategy("A"),
            structural_shot_plan=_plan("A"),
            task="仅返回安全 patch",
        )

        self.assertEqual(result["system_prompt_hash"], hashlib.sha256(result["system_prompt"].encode("utf-8")).hexdigest())
        self.assertEqual(result["user_prompt_hash"], hashlib.sha256(result["user_prompt"].encode("utf-8")).hexdigest())
        self.assertIn(SEMI_STABLE_USER_PREFIX.strip(), result["user_prompt"])
        self.assertIn('"contract_fingerprint":"contract-A"', result["user_prompt"])
        self.assertIn("仅返回安全 patch", result["user_prompt"])

    def test_request_identity_includes_safe_model_parameters_but_no_credentials(self):
        profile_a = {
            "id": "mimo",
            "provider": "openai-compatible",
            "model_name": "mimo-2.5",
            "api_key": "DO-NOT-LEAK",
            "base_url": "https://example.invalid/v1",
            "default_params": {"temperature": 0.2, "thinking": {"type": "disabled"}},
        }
        profile_b = {**profile_a, "default_params": {"temperature": 0.7, "thinking": {"type": "disabled"}}}
        first = build_director_patch_prompt(contract=_contract("A"), strategy=_strategy("A"), structural_shot_plan=_plan("A"), model_profile=profile_a)
        second = build_director_patch_prompt(contract=_contract("A"), strategy=_strategy("A"), structural_shot_plan=_plan("A"), model_profile=profile_b)

        self.assertNotEqual(first["request_fingerprint"], second["request_fingerprint"])
        serialized = str(first)
        self.assertNotIn("DO-NOT-LEAK", serialized)
        self.assertNotIn("example.invalid", serialized)
        self.assertEqual(first["model_snapshot"]["model_name"], "mimo-2.5")

    def test_v23_prompt_requires_canonical_quality_signal_shapes_and_strategy_refs(self):
        strategy = {
            "schema_version": "scene_directing_strategy_v2",
            "strategy_fingerprint": "strategy-v23",
            "scene_objective": "完成反应节拍",
            "visual_strategy": "反应优先",
            "performance_arc": [{"beat_id": "B01", "character_id": "CHAR_001", "objective": "确认声音", "internal_shift": "警觉", "visible_behavior": "抬眼"}],
            "rhythm_curve": [{"beat_id": "B01", "pace": "hold", "cut_strategy": "反应完成后切", "target_duration_range": [3, 4], "hold_reason": "读取反应"}],
            "emotion_curve": [{"beat_id": "B01", "character_id": "CHAR_001", "state": "警觉", "intensity": 6}],
            "information_plan": [{"beat_id": "B01", "audience_should_know": ["听见声音"], "audience_should_not_know_yet": ["声音来源"], "reveal_trigger": "抬眼", "reaction_priority": "人物"}],
            "camera_language": {"base_style": "自然透视", "movement_rule": "有动机才移动", "closeup_rule": "服务反应", "reaction_rule": "完成反应再切"},
            "forbidden_tendencies": ["gratuitous_camera_movement"],
        }
        result = build_director_patch_prompt(contract=_contract("A"), strategy=strategy, structural_shot_plan=_plan("A"))
        self.assertIn("performance_direction is a list of objects", result["system_prompt"])
        self.assertIn("plural reveals/withholds", result["system_prompt"])
        self.assertIn("strategy_refs", result["user_prompt"])
        self.assertIn('"schema_version":"scene_directing_strategy_v2"', result["user_prompt"])

    def test_v23_prompt_clarifies_structural_duration_and_strategy_signal_completeness(self):
        result = build_director_patch_prompt(
            contract=_contract("A"),
            strategy={
                "schema_version": "scene_directing_strategy_v2",
                "emotion_curve": [{"beat_id": "B01", "character_id": "C1", "intensity": 4}],
                "rhythm_curve": [{"beat_id": "B01", "target_duration_range": [3, 4]}],
                "information_plan": [{"beat_id": "B01"}],
                "performance_arc": [{"beat_id": "B01", "character_id": "C1"}],
            },
            structural_shot_plan=_plan("A"),
        )
        self.assertIn("duration/duration_hint_seconds is immutable", result["system_prompt"])
        self.assertIn("execute each applicable", result["system_prompt"])


if __name__ == "__main__":
    unittest.main()
