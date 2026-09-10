import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import (
    AgentViolationLog,
    Session,
    StoryboardAcceptanceRecord,
    StoryboardPromptVersion,
    StoryboardShot,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    init_db,
)


class StoryboardStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990201
        self.episode = 1
        self.shot_id = 1
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardAcceptanceRecord).filter(StoryboardAcceptanceRecord.book_id == self.book_id).delete()
            session.query(AgentViolationLog).filter(AgentViolationLog.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            location = VisualLocation(book_id=self.book_id, name="Forest Camp", shot_ids=json.dumps(["1-1", "1-2"]))
            makeup = VisualMakeup(book_id=self.book_id, episode=self.episode, character_name="Hu Tu")
            prop = VisualProp(book_id=self.book_id, name="Clay Bowl")
            session.add(location)
            session.add(makeup)
            session.add(prop)
            session.flush()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="Forest Camp·Night",
                    shot_id=self.shot_id,
                    dialogue="Test dialogue",
                    action_process="Hu Tu turns and points at the clay bowl.",
                    meta_info=json.dumps({}, ensure_ascii=False),
                    asset_links="{}",
                    asset_status="pending",
                ),
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardAcceptanceRecord).filter(StoryboardAcceptanceRecord.book_id == self.book_id).delete()
            session.query(AgentViolationLog).filter(AgentViolationLog.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.commit()

    def test_structure_endpoint_derives_default_payload_for_legacy_shot(self):
        response = self.client.get(f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/structure")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["structured_shot"]
        self.assertEqual(payload["duration"], 3)
        self.assertEqual(payload["camera_angle"], "MS")
        self.assertEqual(payload["camera_movement"], "static")
        self.assertEqual(payload["transition"], "cut")
        self.assertNotEqual(payload["scene_asset_id"], "")
        self.assertEqual(len(payload["character_asset_ids"]), 1)
        self.assertEqual(len(payload["prop_asset_ids"]), 1)
        self.assertEqual(payload["style_key"], "default")
        self.assertEqual(payload["action_beats"][0]["description"], "Hu Tu turns and points at the clay bowl.")

    def test_split_apply_rejects_screenplay_dialogue_residue(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter_by(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
            ).one()
            shot.meta_info = json.dumps({
                "executability_split_draft": {
                    "status": "draft",
                    "candidates": [
                        {"sequence": 1, "recommended_duration": 3, "action_beats": ["人物甲：（抬头）看向门口"]},
                        {"sequence": 2, "recommended_duration": 3, "action_beats": ["人物甲后退一步"]},
                    ],
                },
            }, ensure_ascii=False)
            session.commit()

        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/executability/split-draft/apply",
            json={"confirmed": True},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("对白或舞台标记", response.json()["detail"])

    def test_llm_split_preview_is_read_only_and_draft_requires_confirmation(self):
        preview = self.client.get(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/executability/split-draft/llm-preview",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["llm_called"])
        fingerprint = preview.json()["source_fingerprint"]
        with patch("api.server.llm_client.call_llm_json") as call:
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/executability/split-draft/llm",
                json={"confirmed": False, "allowExternalCall": False, "sourceFingerprint": fingerprint},
            )
            self.assertEqual(response.status_code, 409)
            call.assert_not_called()

    def test_llm_split_saves_only_visual_action_candidates(self):
        preview = self.client.get(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/executability/split-draft/llm-preview",
        ).json()
        model_result = {
            "segments": [
                {"purpose": "建立动作", "recommended_duration": 3, "action_beats": ["人物甲抬头看向门口"], "start_state": "站在桌旁", "end_state": "视线转向门口"},
                {"purpose": "完成反应", "recommended_duration": 3, "action_beats": ["人物甲后退一步并停下"], "start_state": "视线转向门口", "end_state": "退后停住"},
            ],
            "rationale": "将观察与后退拆为两个可拍动作段落。",
        }
        with patch("api.server.llm_client.call_llm_json", return_value=model_result) as call:
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/executability/split-draft/llm",
                json={"confirmed": True, "allowExternalCall": True, "sourceFingerprint": preview["source_fingerprint"]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["llm_called"])
        self.assertEqual(len(response.json()["draft"]["candidates"]), 2)
        call.assert_called_once()

    def test_structure_patch_persists_and_round_trips(self):
        patch_response = self.client.patch(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/structure",
            json={
                "duration": 5,
                "cameraAngle": "CU",
                "cameraMovement": "push-in",
                "cameraSpeed": "medium",
                "shotPurpose": "reveal",
                "emotionArc": {"start": "疑惑", "end": "警觉", "intensity": "high"},
                "transition": "dissolve",
                "startState": "Hu Tu enters the camp.",
                "actionProcess": "Hu Tu raises the bowl.",
                "endState": "The bowl is held at eye level.",
                "sceneAssetId": "12",
                "characterAssetIds": ["21", "34"],
                "propAssetIds": ["55"],
                "styleKey": "cinematic-default",
                "characterBlocking": [
                    {
                        "character_id": "21",
                        "screen_position": "left",
                        "pose": "standing",
                        "status": "active",
                        "emotion": "angry",
                        "visual_alias": "Hu Tu",
                    }
                ],
                "actionBeats": [
                    {
                        "sequence": 1,
                        "subject_type": "character",
                        "subject_id": "21",
                        "time_slice": "0-2s",
                        "description": "Points at the bowl",
                        "emotion": "angry",
                        "intensity": "high",
                    }
                ],
            },
        )
        self.assertEqual(patch_response.status_code, 200)
        structured = patch_response.json()["structured_shot"]
        self.assertEqual(structured["duration"], 5)
        self.assertEqual(structured["camera_angle"], "CU")
        self.assertEqual(structured["camera_movement"], "push-in")
        self.assertEqual(structured["camera_speed"], "medium")
        self.assertEqual(structured["shot_purpose"], "reveal")
        self.assertEqual(structured["emotion_arc"]["end"], "警觉")
        self.assertEqual(structured["transition"], "dissolve")
        self.assertEqual(structured["scene_asset_id"], "12")
        self.assertEqual(structured["character_asset_ids"], ["21", "34"])
        self.assertEqual(structured["prop_asset_ids"], ["55"])

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(outputs_response.status_code, 200)
        storyboard = outputs_response.json()["storyboard"][0]
        self.assertEqual(storyboard["duration"], 5)
        self.assertEqual(storyboard["camera_angle"], "CU")
        self.assertEqual(storyboard["camera_movement"], "push-in")
        self.assertEqual(storyboard["camera_speed"], "medium")
        self.assertEqual(storyboard["shot_purpose"], "reveal")
        self.assertEqual(storyboard["emotion_arc"]["start"], "疑惑")
        with Session() as session:
            stored = session.query(StoryboardShot).filter_by(
                book_id=self.book_id, episode=self.episode, shot_id=self.shot_id,
            ).one()
            self.assertEqual(stored.camera_speed, "medium")
            self.assertEqual(stored.shot_purpose, "reveal")
            self.assertEqual(json.loads(stored.emotion_arc)["intensity"], "high")
        self.assertEqual(storyboard["transition"], "dissolve")
        self.assertEqual(storyboard["start_state"], "Hu Tu enters the camp.")
        self.assertEqual(storyboard["action_process"], "Hu Tu raises the bowl.")
        self.assertEqual(storyboard["end_state"], "The bowl is held at eye level.")
        self.assertEqual(storyboard["structured_shot"]["scene_asset_id"], "12")
        self.assertEqual(storyboard["structured_shot"]["character_blocking"][0]["visual_alias"], "Hu Tu")

    def test_auto_bind_endpoint_persists_derived_visual_asset_ids(self):
        response = self.client.post(
            f"/api/books/{self.book_id}/storyboard/auto-bind-visual-assets",
            json={"episodes": [self.episode]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["inspected_shots"], 1)
        self.assertEqual(payload["changed_shots"], 1)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        storyboard = outputs_response.json()["storyboard"][0]
        self.assertNotEqual(storyboard["structured_shot"]["scene_asset_id"], "")
        self.assertEqual(len(storyboard["structured_shot"]["character_asset_ids"]), 1)
        self.assertEqual(len(storyboard["structured_shot"]["prop_asset_ids"]), 1)

    def test_structure_endpoint_derives_character_and_prop_from_end_state_when_action_process_is_sparse(self):
        shot_id = 3
        with Session() as session:
            makeup = VisualMakeup(book_id=self.book_id, episode=self.episode, character_name="Monk Yi")
            prop = VisualProp(book_id=self.book_id, name="Wooden Bucket")
            session.add(makeup)
            session.add(prop)
            session.flush()
            makeup_id = str(makeup.id)
            prop_id = str(prop.id)
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="Forest Camp",
                    shot_id=shot_id,
                    dialogue="Do not spill the bucket again.",
                    action_process="A splash of cold water lands first.",
                    start_state="The room is quiet before the prank is revealed.",
                    end_state="Monk Yi leans on the doorframe while the Wooden Bucket hangs empty in his hand.",
                    meta_info=json.dumps({}, ensure_ascii=False),
                    asset_links="{}",
                    asset_status="pending",
                ),
            )
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/storyboard/{self.episode}/{shot_id}/structure")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["structured_shot"]
        self.assertIn(makeup_id, payload["character_asset_ids"])
        self.assertIn(prop_id, payload["prop_asset_ids"])

    def test_structure_endpoint_matches_scene_alias_name(self):
        shot_id = 2
        with Session() as session:
            location = VisualLocation(book_id=self.book_id, name="寺庙水井旁")
            session.add(location)
            session.flush()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="寺庙井边·夜晚",
                    shot_id=shot_id,
                    dialogue="",
                    action_process="和尚甲蹲在井边洗手。",
                    meta_info=json.dumps({}, ensure_ascii=False),
                    asset_links="{}",
                    asset_status="pending",
                ),
            )
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/storyboard/{self.episode}/{shot_id}/structure")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["structured_shot"]
        self.assertNotEqual(payload["scene_asset_id"], "")

    def test_apply_split_draft_requires_confirmation_and_inserts_new_shot(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot.visual_prompt_static = "old static"
            shot.visual_prompt_motion = "old motion"
            shot.asset_links = json.dumps({"images": [{"id": "old-image"}], "references": {"scene": [{"id": "ref-1"}]}}, ensure_ascii=False)
            shot.meta_info = json.dumps({
                "executability_split_draft": {
                    "status": "draft",
                    "candidates": [
                        {"sequence": 1, "recommended_duration": 2, "action_beats": ["Hu Tu notices the bowl"]},
                        {"sequence": 2, "recommended_duration": 2, "action_beats": ["Hu Tu points at the bowl"]},
                    ],
                },
            }, ensure_ascii=False)
            session.add(StoryboardShot(
                book_id=self.book_id,
                episode=self.episode,
                scene_name="Forest Camp·Night",
                shot_id=2,
                action_process="Later shot",
                meta_info="{}",
                asset_links="{}",
            ))
            session.add_all([
                StoryboardPromptVersion(
                    book_id=self.book_id,
                    episode=self.episode,
                    shot_id=1,
                    version=1,
                    prompt_static="source static history",
                    prompt_motion="source motion history",
                ),
                StoryboardPromptVersion(
                    book_id=self.book_id,
                    episode=self.episode,
                    shot_id=2,
                    version=1,
                    prompt_static="following static history",
                    prompt_motion="following motion history",
                ),
                StoryboardAcceptanceRecord(book_id=self.book_id, episode=self.episode, shot_id=2, asset_id="old-shot-2"),
                AgentViolationLog(
                    agent_type="compiler",
                    book_id=self.book_id,
                    episode=self.episode,
                    shot_id=2,
                    violation_id="TEST",
                    field="test",
                    severity="warn",
                ),
            ])
            session.commit()

        base_url = f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/executability/split-draft/apply"
        self.assertEqual(self.client.post(base_url, json={"confirmed": False}).status_code, 409)
        response = self.client.post(base_url, json={"confirmed": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created_shot_id"], 2)

        with Session() as session:
            rows = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
            ).order_by(StoryboardShot.shot_id).all()
            self.assertEqual([row.shot_id for row in rows], [1, 2, 3])
            self.assertEqual(rows[0].action_process, "Hu Tu notices the bowl")
            self.assertEqual(rows[1].action_process, "Hu Tu points at the bowl")
            self.assertEqual(rows[0].visual_prompt_static, "")
            self.assertEqual(rows[1].visual_prompt_motion, "")
            self.assertEqual(json.loads(rows[0].asset_links)["references"]["scene"][0]["id"], "ref-1")
            applied_draft = json.loads(rows[0].meta_info)["executability_split_draft"]
            self.assertEqual(applied_draft["archived_asset_links"]["images"][0]["id"], "old-image")
            self.assertTrue(json.loads(rows[0].meta_info)["prompt_compiler"]["recompile_required"])
            self.assertTrue(json.loads(rows[1].meta_info)["prompt_compiler"]["recompile_required"])
            self.assertEqual(
                session.query(StoryboardPromptVersion).filter_by(book_id=self.book_id, episode=self.episode, shot_id=3).count(),
                1,
            )
            self.assertEqual(
                session.query(StoryboardAcceptanceRecord).filter_by(book_id=self.book_id, episode=self.episode, shot_id=3).count(),
                1,
            )
            self.assertEqual(
                session.query(AgentViolationLog).filter_by(book_id=self.book_id, episode=self.episode, shot_id=3).count(),
                1,
            )
            location = session.query(VisualLocation).filter_by(book_id=self.book_id, name="Forest Camp").first()
            self.assertEqual(json.loads(location.shot_ids), ["1-1", "1-2", "1-3"])

        # Split source history stays auditable in storage, but is unavailable
        # to restore into either newly-defined narrative unit.
        source_versions = self.client.get(f"/api/books/{self.book_id}/storyboard/1/1/prompt-versions").json()
        created_versions = self.client.get(f"/api/books/{self.book_id}/storyboard/1/2/prompt-versions").json()
        self.assertTrue(source_versions["recompile_required"])
        self.assertEqual(source_versions["versions"], [])
        self.assertTrue(created_versions["recompile_required"])
        self.assertEqual(created_versions["versions"], [])


if __name__ == "__main__":
    unittest.main()
