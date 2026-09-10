import unittest

from core.shot_executability import validate_shot_executability


class ShotExecutabilityTests(unittest.TestCase):
    def test_four_second_shot_with_dense_action_chain_is_blocked(self):
        result = validate_shot_executability(
            duration=4,
            action_process="男人扫码支付成功。随后取出照片。然后推到她面前。她抬眼凝视照片。",
            camera_movement="static",
            start_state="男人站在收银台前",
            end_state="照片停在收银台上",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["action_count"], 4)
        self.assertTrue(any(item["type"] == "split_shot" for item in result["suggestions"]))
        split = next(item for item in result["suggestions"] if item["type"] == "split_shot")
        self.assertEqual(len(split["candidates"]), 4)
        self.assertTrue(split["candidates"][0]["action_beats"])

    def test_six_second_three_beat_shot_passes(self):
        result = validate_shot_executability(
            duration=6,
            action_beats=[
                {"description": "手进入画面"},
                {"description": "取出折叠旧照片"},
                {"description": "将照片推到对方身前"},
            ],
            camera_movement="static",
            start_state="男人停在收银台前",
            end_state="照片停在收银台上",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["action_count"], 3)

    def test_missing_states_are_warning_not_blocked(self):
        result = validate_shot_executability(
            duration=5,
            action_process="人物轻轻抬头。",
        )

        self.assertEqual(result["status"], "warning")
        self.assertTrue(any(item["code"] == "continuity_state_incomplete" for item in result["findings"]))

    def test_final_motion_prompt_overrides_understated_structured_beats(self):
        result = validate_shot_executability(
            duration=4,
            action_process="男人把照片推到林小夏面前。",
            action_beats=[{"description": "男人把照片推到林小夏面前"}],
            camera_movement="static",
            start_state="男人站在收银台前",
            end_state="林小夏凝视照片",
            motion_prompt="男人扫码支付成功，随后掏出旧照片，放在收银台上，推到林小夏面前，收回手，林小夏凝视照片。",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertGreater(result["motion_prompt_action_count"], result["structured_action_count"])
        self.assertTrue(any(item["code"] == "motion_prompt_action_drift" for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
