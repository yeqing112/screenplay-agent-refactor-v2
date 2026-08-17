import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardShot, VisualLocation, VisualMakeup, VisualProp, init_db


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
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            location = VisualLocation(book_id=self.book_id, name="Forest Camp")
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

    def test_structure_patch_persists_and_round_trips(self):
        patch_response = self.client.patch(
            f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/structure",
            json={
                "duration": 5,
                "cameraAngle": "CU",
                "cameraMovement": "push-in",
                "transition": "dissolve",
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
        self.assertEqual(storyboard["transition"], "dissolve")
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


if __name__ == "__main__":
    unittest.main()
