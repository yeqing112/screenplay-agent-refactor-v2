import unittest
from unittest.mock import patch

from agents.storyboard import StoryboardAgent


class StoryboardSceneRetryTests(unittest.TestCase):
    def test_scene_retry_falls_back_to_structured_storyboard_after_second_failure(self):
        events = []
        agent = StoryboardAgent(book_id=1, progress_callback=events.append)
        context = {
            "scene_name": "Scene A",
            "scene_prompt": "寺庙内景",
            "lighting_mood": "cold",
            "color_palette": "gray",
            "script_block": "一段很长的场景内容",
            "characters_context": "角色：和尚",
            "props_context": "道具：木鱼",
        }
        fallback_scene = {
            "name": "Scene A",
            "prompt": "寺庙内景",
            "script_block": "**[钟声回荡]**\n**和尚：** 阿弥陀佛",
        }

        with patch("agents.storyboard.load_prompt", return_value="PROMPT"), patch(
            "agents.storyboard.call_llm_json",
            side_effect=[
                ValueError("Failed to parse LLM JSON response"),
                ValueError("LLM output truncated"),
            ],
        ):
            shots = agent._generate_scene_shots(context, fallback_scene=fallback_scene)

        self.assertEqual(len(shots), 3)
        self.assertTrue(all(shot.get("metadata", {}).get("source") == "fallback-structured-script" for shot in shots))
        self.assertEqual(
            [event.get("stage") for event in events],
            ["scene_retrying", "scene_fallback_used"],
        )


if __name__ == "__main__":
    unittest.main()
