import unittest

from core.qa_resolution import build_resolution_criteria, evaluate_resolution_criteria, route_issue
from core.script_beat import find_issue_beats


SCRIPT = "\n".join([
    "## 场景1：钟楼外景",
    "",
    "**[开场]**",
    "",
    "林晚站在钟楼铁门前，仰头看着塔楼。",
    "",
    "**林晚**（自言自语）：",
    "“就这儿？”",
    "",
    "**[人物入场]**",
    "",
    "老周从阴影里走出来。",
])


class QaResolutionTests(unittest.TestCase):
    def test_issue_anchors_to_unique_beat_by_excerpt(self):
        beat_ids, reliable = find_issue_beats(SCRIPT, 1, source_excerpt="就这儿？")
        self.assertTrue(reliable)
        self.assertEqual(beat_ids, ["ep1-s1-b03"])

    def test_issue_without_matching_text_is_unreliable(self):
        beat_ids, reliable = find_issue_beats(SCRIPT, 1, source_excerpt="这里根本没有这段内容")
        self.assertFalse(reliable)
        self.assertEqual(beat_ids, [])

    def test_scene_end_criterion_is_decidable(self):
        criteria = build_resolution_criteria(
            {"type": "format", "title": "场景2结尾缺少结束标记", "description": "应在结尾补 [场景结束]。"},
            ["ep1-s2-b05"],
        )
        self.assertEqual(criteria["kind"], "structure_present")
        self.assertEqual(criteria["required_message"], "[场景结束]")

    def test_missing_visual_proof_criterion_is_decidable(self):
        criteria = build_resolution_criteria(
            {"type": "format", "title": "场景3缺少视觉证明4", "description": "视觉证明4缺失。"},
            ["ep1-s3-b07"],
        )
        self.assertEqual(criteria["kind"], "structure_present")
        self.assertEqual(criteria["required_message"], "视觉证明4")

    def test_subjective_issue_is_routed_to_human(self):
        criteria = build_resolution_criteria(
            {"type": "motivation", "title": "林晚动机单薄", "description": "动机较模糊。"},
            [],
        )
        self.assertEqual(criteria["kind"], "requires_human")

    def test_evaluate_contains_required_hits_beat(self):
        passed, _ = evaluate_resolution_criteria(
            SCRIPT, 1, {"kind": "contains_required", "beat_ids": ["ep1-s1-b03"], "required": "就这儿"},
        )
        self.assertTrue(passed)
        passed_miss, _ = evaluate_resolution_criteria(
            SCRIPT, 1, {"kind": "contains_required", "beat_ids": ["ep1-s1-b03"], "required": "完全不存在"},
        )
        self.assertFalse(passed_miss)

    def test_evaluate_structure_present_and_requires_human(self):
        passed, _ = evaluate_resolution_criteria(SCRIPT, 1, {"kind": "structure_present", "required_message": "视觉证明4"})
        self.assertFalse(passed)
        passed_h, _ = evaluate_resolution_criteria(SCRIPT, 1, {"kind": "requires_human", "beat_ids": []})
        self.assertTrue(passed_h)

    def test_route_auto_only_for_decidable_structural_with_reliable_anchor(self):
        self.assertEqual(route_issue({}, True, {"kind": "contains_required", "required": "[场景结束]"}), "auto")
        self.assertEqual(route_issue({}, True, {"kind": "structure_present", "required_message": "视觉证明4"}), "auto")

    def test_routes_subjective_or_unreliable_to_human(self):
        self.assertEqual(route_issue({}, True, {"kind": "requires_human", "reason": "主观项"}), "human")
        self.assertEqual(route_issue({}, False, {"kind": "contains_required"}), "human")
        self.assertEqual(route_issue({}, True, {}), "human")


if __name__ == "__main__":
    unittest.main()
