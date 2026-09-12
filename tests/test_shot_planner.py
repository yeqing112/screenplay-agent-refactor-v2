import unittest

from core.shot_planner import build_action_timing_plan, build_shot_intent_plan


class ShotPlannerTests(unittest.TestCase):
    def test_intent_plan_preserves_declared_facts_and_reports_missing_state(self):
        result = build_shot_intent_plan(
            shot_purpose="reveal",
            core_action="人物抬头看向门口",
            action_beats=[{"description": "人物抬头看向门口"}],
            start_state="坐在桌旁",
            end_state="视线停在门口",
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["primary_action_source"], "core_action")
        self.assertEqual(result["unknowns"], [])

    def test_intent_plan_does_not_guess_purpose_or_emotion(self):
        result = build_shot_intent_plan(action_process="人物停下")
        self.assertEqual(result["status"], "needs_information")
        self.assertIn("shot_purpose", result["unknowns"])
        self.assertEqual(result["emotion_arc"], {"start": "", "end": "", "intensity": ""})

    def test_timing_plan_equal_allocation_is_deterministic(self):
        result = build_action_timing_plan(
            duration=3,
            action_beats=[{"description": "抬头"}, {"description": "看向门口"}],
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual([item["duration_ms"] for item in result["segments"]], [1500, 1500])
        self.assertEqual(result["segments"][-1]["end_ms"], 3000)

    def test_timing_plan_keeps_declared_durations_and_allocates_remainder(self):
        result = build_action_timing_plan(
            duration=4,
            action_beats=[
                {"description": "开门", "duration_seconds": 1},
                {"description": "停住"},
            ],
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["segments"][0]["duration_ms"], 1000)
        self.assertEqual(result["segments"][1]["duration_ms"], 3000)

    def test_timing_plan_rejects_overallocated_declared_durations(self):
        result = build_action_timing_plan(
            duration=2,
            action_beats=[{"description": "A", "duration_seconds": 1.5}, {"description": "B", "duration_seconds": 1}],
        )
        self.assertEqual(result["status"], "conflict")
        self.assertIn("declared_beat_durations_exceed_shot_duration", result["unknowns"])

    def test_timing_plan_requires_both_duration_and_action(self):
        result = build_action_timing_plan(duration=4)
        self.assertEqual(result["status"], "needs_information")
        self.assertIn("action_beats", result["unknowns"])


if __name__ == "__main__":
    unittest.main()
