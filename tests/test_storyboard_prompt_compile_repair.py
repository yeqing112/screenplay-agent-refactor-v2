import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardShot, VisualMakeup, VisualProp
from tests.test_storyboard_prompt_compile import StoryboardPromptCompileTests


class StoryboardPromptCompileRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        StoryboardPromptCompileTests.setUpClass()
        cls.client = TestClient(app)

    def setUp(self):
        self.base = StoryboardPromptCompileTests()
        self.base.setUp()

    def tearDown(self):
        self.base.tearDown()

    def test_compile_retries_once_when_first_candidate_has_warning(self):
        first_payload = self.base._valid_llm_payload()
        first_payload["visual_prompt_static"] = "暴雨中的出租屋内，姐姐和阿宁对视，气氛压抑。"

        second_payload = self.base._valid_llm_payload()
        second_payload["visual_prompt_static"] = (
            "暴雨中的出租屋内景，中景构图，姐姐站在门口偏左，湿透的雨衣贴在肩背，"
            "阿宁抱着旧水壶缩在屋内偏右，冷色雨夜光线压低室内亮度，"
            "人物外观严格参考@姐姐与@阿宁，场景保持@出租屋的狭窄潮湿压迫感。"
        )

        with patch("core.llm.call_llm_json", side_effect=[first_payload, second_payload]) as mocked_call:
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["compiler_diagnostics"]["status"], "pass")
        self.assertEqual(body["prompt_static"], second_payload["visual_prompt_static"])
        self.assertTrue(body["repair_attempted"])
        self.assertEqual(mocked_call.call_count, 2)

    def test_compile_blocks_after_repair_if_high_importance_prop_still_missing(self):
        with Session() as session:
            prop = session.query(VisualProp).filter(VisualProp.book_id == self.base.book_id).first()
            prop.importance = "high"
            session.commit()

        first_payload = self.base._valid_llm_payload()
        first_payload["visual_prompt_static"] = "暴雨中的出租屋内景，姐姐与阿宁对视，冷色光线压住空间。"
        second_payload = dict(first_payload)

        with patch("core.llm.call_llm_json", side_effect=[first_payload, second_payload]) as mocked_call:
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["compiler_diagnostics"]["status"], "blocked")
        self.assertTrue(any("高重要度道具" in issue for issue in detail["compiler_diagnostics"]["blocking_issues"]))
        self.assertEqual(mocked_call.call_count, 2)

    def test_compile_blocks_after_repair_if_bound_characters_disappear_from_used_assets(self):
        with patch("core.llm.call_llm_json", return_value=self.base._valid_llm_payload()):
            ok_response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )
        self.assertEqual(ok_response.status_code, 200)
        previous_static = ok_response.json()["prompt_static"]

        degraded_payload = {
            "visual_prompt_static": "暴雨中的出租屋内景，门外冷雨敲打窗框，屋内低亮度冷色光线压低空间，墙角只剩潮湿墙皮与旧木桌，画面参考 @出租屋。",
            "visual_prompt_motion": "镜头从门口缓慢推进到屋内角落，保持阴冷潮湿氛围与空间连续性，最后停在出租屋内部的压迫感上。",
            "negative_prompt": "低质量，多余手指，多余人物，不要现代汽车",
            "used_assets": [
                {
                    "asset_type": "scene",
                    "asset_id": self.base.scene_id,
                    "asset_name": "暴雨中的出租屋",
                    "reference_token": "@出租屋",
                    "reference_status": "locked",
                }
            ],
            "warnings": [],
        }

        with patch("core.llm.call_llm_json", side_effect=[degraded_payload, degraded_payload]) as mocked_call:
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/compile-prompts",
                json={"compileReason": "acceptance-repair", "force": True},
            )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["compiler_diagnostics"]["status"], "blocked")
        self.assertTrue(detail["repair_attempted"])
        self.assertEqual(mocked_call.call_count, 2)
        self.assertTrue(
            any(
                check["key"] == "critical_bound_asset_usage" and not check["passed"]
                for check in detail["compiler_diagnostics"]["checks"]
            )
        )
        self.assertTrue(any("used_assets" in issue for issue in detail["compiler_diagnostics"]["blocking_issues"]))

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.base.book_id,
                StoryboardShot.episode == self.base.episode,
                StoryboardShot.shot_id == self.base.shot_id,
            ).first()
            self.assertEqual(shot.visual_prompt_static, previous_static)

    def test_compile_supplements_critical_used_assets_when_prompt_already_mentions_prop(self):
        payload = self.base._valid_llm_payload()
        payload["used_assets"] = [
            item
            for item in payload["used_assets"]
            if not (
                str(item.get("asset_type") or "").strip() == "prop"
                and str(item.get("asset_id") or "").strip() == self.base.prop_id
            )
        ]

        with Session() as session:
            prop = session.query(VisualProp).filter(VisualProp.book_id == self.base.book_id).first()
            prop.importance = "high"
            session.commit()

        with patch("core.llm.call_llm_json", return_value=payload):
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["compiler_diagnostics"]["status"], "pass")
        self.assertTrue(
            any(
                str(item.get("asset_type") or "").strip() == "prop"
                and str(item.get("asset_id") or "").strip() == self.base.prop_id
                for item in body["used_assets"]
            )
        )
        critical_check = next(
            check
            for check in body["compiler_diagnostics"]["checks"]
            if check["key"] == "critical_bound_asset_usage"
        )
        self.assertTrue(critical_check["passed"])

    def test_compile_auto_binds_from_end_state_and_blocks_scene_only_candidate(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.base.book_id,
                StoryboardShot.episode == self.base.episode,
                StoryboardShot.shot_id == self.base.shot_id,
            ).first()
            makeups = session.query(VisualMakeup).filter(
                VisualMakeup.book_id == self.base.book_id,
                VisualMakeup.episode == self.base.episode,
            ).order_by(VisualMakeup.id.asc()).all()
            first_character_name = str(makeups[0].character_name or "").strip()
            second_character_name = str(makeups[1].character_name or "").strip()

            meta_info = json.loads(shot.meta_info)
            meta_info["structured_shot"] = {
                "shot_id": str(self.base.shot_id),
                "scene_name": shot.scene_name,
                "duration": shot.duration,
                "camera_angle": shot.camera_angle,
                "camera_movement": shot.camera_movement,
                "transition": shot.transition,
                "scene_asset_id": "",
                "character_asset_ids": [],
                "prop_asset_ids": [],
                "style_key": "default",
                "character_blocking": [],
                "action_beats": [],
                "action_process": "",
                "dialogue": "",
                "start_state": "",
                "end_state": "",
            }
            shot.action_process = "A splash lands before anyone fully reacts."
            shot.start_state = "The room is still before the prank is revealed."
            shot.end_state = f"{second_character_name} turns back while {first_character_name} looks toward her."
            shot.dialogue = f"{second_character_name}, do not make a sound."
            shot.meta_info = json.dumps(meta_info, ensure_ascii=False)
            session.commit()

        degraded_payload = {
            "visual_prompt_static": "暴雨中的出租屋内景，门外冷雨敲打窗框，屋内低亮度冷色光线压低空间，墙角只剩潮湿墙皮与旧木桌，画面参考 @出租屋。",
            "visual_prompt_motion": "镜头从门口缓慢推进到屋内角落，保持阴冷潮湿氛围与空间连续性，最后停在出租屋内部的压迫感上。",
            "negative_prompt": "低质量，多余手指，多余人物，不要现代汽车",
            "used_assets": [
                {
                    "asset_type": "scene",
                    "asset_id": self.base.scene_id,
                    "asset_name": "暴雨中的出租屋",
                    "reference_token": "@出租屋",
                    "reference_status": "locked",
                }
            ],
            "warnings": [],
        }

        with patch("core.llm.call_llm_json", side_effect=[degraded_payload, degraded_payload]):
            response = self.client.post(
                f"/api/books/{self.base.book_id}/storyboard/{self.base.episode}/{self.base.shot_id}/compile-prompts",
                json={"compileReason": "auto-bind-regression", "force": True},
            )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        critical_check = next(
            check
            for check in detail["compiler_diagnostics"]["checks"]
            if check["key"] == "critical_bound_asset_usage"
        )
        self.assertFalse(critical_check["passed"])
        self.assertTrue(any(first_character_name in item for item in critical_check["details"]))
        self.assertTrue(any(second_character_name in item for item in critical_check["details"]))


if __name__ == "__main__":
    unittest.main()
