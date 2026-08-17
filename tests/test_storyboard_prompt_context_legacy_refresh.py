import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardShot, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset, init_db


class StoryboardPromptContextLegacyRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990303
        self.episode = 1
        self.shot_id = "1"

        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()

            location = VisualLocation(
                book_id=self.book_id,
                name="Temple Water Room",
                visual_prompt_zh="Stone water room, damp floor, cold dawn light.",
                description="An old water room in the back courtyard, with damp ground and mottled walls.",
                lighting_mood="cold dawn light",
            )
            session.add(location)
            session.flush()

            character = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Monk Jia",
                stage_name="episode_1_default",
                visual_prompt_zh="Episode default six-panel board, keep the same character stable.",
                core_prompt_zh="Young monk, medium build, gray old monk robe.",
                refined_outfit="Gray old monk robe, slightly wrinkled hem.",
                hair_style="Fully shaved head with faint blue scalp tint.",
                makeup_spec="Natural skin tone with faint sweat on the forehead.",
                consistency_notes="All six views must remain the same character.",
                meta_info=json.dumps(
                    {
                        "scope": "episode_default",
                        "structured_result": {
                            "identity": "Temple monk",
                            "temperament": "lazy and evasive",
                            "variant_name": "Episode 1 default look",
                            "stage_name": "episode_1_default",
                        },
                    },
                    ensure_ascii=False,
                ),
            )
            session.add(character)
            session.flush()

            scene_reference = VisualReferenceAsset(
                book_id=self.book_id,
                episode=self.episode,
                asset_type="scene",
                asset_id=str(location.id),
                asset_name="Temple Water Room",
                image_url="https://example.com/ref-scene-legacy.png",
                reference_token="@TempleWaterRoom",
                status="selected",
            )
            session.add(scene_reference)

            character_reference = VisualReferenceAsset(
                book_id=self.book_id,
                episode=self.episode,
                asset_type="character",
                asset_id=str(character.id),
                asset_name="Monk Jia",
                image_url="https://example.com/ref-monk-jia.png",
                reference_token="@MonkJia",
                status="selected",
            )
            session.add(character_reference)
            session.flush()

            prop = VisualProp(
                book_id=self.book_id,
                name="Old Wooden Bucket",
                visual_prompt_zh="A worn old wooden bucket with visible water stains.",
                description="An often-used old wooden bucket with worn edges.",
                importance="high",
            )
            session.add(prop)
            session.flush()

            legacy_context = {
                "asset_bindings": {
                    "scene": {
                        "asset_id": str(location.id),
                        "asset_name": "Temple Water Room",
                        "reference_status": "selected",
                    },
                    "characters": [
                        {
                            "asset_id": str(character.id),
                            "asset_name": "Monk Jia",
                            "variant_scope": "episode_default",
                            "stage_name": "episode_1_default",
                            "reference_status": "missing",
                        }
                    ],
                    "props": [
                        {
                            "asset_id": str(prop.id),
                            "asset_name": "Old Wooden Bucket",
                            "reference_status": "missing",
                        }
                    ],
                }
            }

            shot = StoryboardShot(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                scene_name="Temple Water Room",
                start_state="Monk Jia stands beside the water room.",
                action_process="He bends down to lift the old bucket.",
                end_state="The bucket is lifted off the ground.",
                dialogue="",
                camera_angle="MS",
                camera_movement="static",
                lighting="cool",
                duration=4,
                meta_info=json.dumps(
                    {
                        "structured_shot": {
                            "scene_asset_id": str(location.id),
                            "character_asset_ids": [str(character.id)],
                            "prop_asset_ids": [str(prop.id)],
                            "style_key": "default",
                        },
                        "prompt_compiler": {
                            "latest_version": 3,
                            "prompt_compile_context": legacy_context,
                            "used_assets": [
                                {
                                    "asset_type": "scene",
                                    "asset_id": str(location.id),
                                    "asset_name": "Temple Water Room",
                                    "reference_token": "@TempleWaterRoom",
                                    "reference_status": "locked",
                                    "has_reference": True,
                                    "locked_reference": True,
                                },
                                {
                                    "asset_type": "character",
                                    "asset_id": str(character.id),
                                    "asset_name": "Monk Jia",
                                    "reference_token": "@MonkJia",
                                    "reference_status": "missing",
                                    "has_reference": False,
                                    "locked_reference": False,
                                },
                                {
                                    "asset_type": "prop",
                                    "asset_id": str(prop.id),
                                    "asset_name": "Old Wooden Bucket",
                                    "reference_token": "@OldWoodenBucket",
                                    "reference_status": "missing",
                                    "has_reference": False,
                                    "locked_reference": False,
                                },
                            ],
                            "compiler_warnings": [
                                "Monk Jia has no reference image.",
                                "Old Wooden Bucket has no reference image.",
                            ],
                            "locked_reference_summary": {},
                            "reference_images": [
                                {
                                    "reference_asset_id": "ref-scene-legacy",
                                    "asset_type": "scene",
                                    "asset_id": str(location.id),
                                    "asset_name": "Temple Water Room",
                                    "reference_token": "@TempleWaterRoom",
                                    "image_url": "https://example.com/ref-scene-legacy.png",
                                    "reference_status": "selected",
                                }
                            ],
                            "reference_asset_ids": ["ref-scene-legacy"],
                        },
                    },
                    ensure_ascii=False,
                ),
            )
            session.add(shot)
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.commit()

    def test_outputs_refresh_legacy_prompt_compile_context(self):
        response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(response.status_code, 200)

        storyboard = response.json()["storyboard"][0]
        scene = storyboard["prompt_compile_context"]["asset_bindings"]["scene"]
        character = storyboard["prompt_compile_context"]["asset_bindings"]["characters"][0]
        prop = storyboard["prompt_compile_context"]["asset_bindings"]["props"][0]

        self.assertEqual(scene["authority_prompt_source"], "scene_asset")
        self.assertEqual(scene["variant_scope"], "")
        self.assertEqual(scene["scope_label"], "")
        self.assertEqual(scene["stage_name"], "")
        scene_reference_asset_id = scene["reference_asset_id"]

        self.assertEqual(character["authority_prompt_source"], "character_makeup")
        self.assertEqual(character["variant_scope"], "episode_default")
        self.assertEqual(character["stage_name"], "episode_1_default")

        self.assertEqual(prop["authority_prompt_source"], "prop_asset")
        self.assertEqual(prop["variant_scope"], "")
        self.assertEqual(prop["scope_label"], "")
        self.assertEqual(prop["stage_name"], "")
        self.assertEqual(
            storyboard["prompt_compile_context"]["compiled_reference_asset_ids"],
            [scene_reference_asset_id, character["reference_asset_id"]],
        )
        self.assertEqual(
            [item["reference_asset_id"] for item in storyboard["prompt_compile_context"]["compiled_reference_images"]],
            [scene_reference_asset_id, character["reference_asset_id"]],
        )
        self.assertIn("compile_prompt_contract", storyboard["prompt_compile_context"])
        self.assertTrue(storyboard["prompt_compile_context"]["visual_fact_targets"])
        self.assertTrue(storyboard["prompt_compile_context"]["required_used_assets"])
        self.assertTrue(
            any(
                item["asset_name"] == "Monk Jia"
                for item in storyboard["prompt_compile_context"]["required_used_assets"]
            )
        )
        check_keys = {
            str(item.get("key") or "").strip()
            for item in (storyboard["compiler_diagnostics"].get("checks") or [])
            if isinstance(item, dict)
        }
        self.assertIn("screenplay_prompt_residue", check_keys)
        self.assertIn("visual_fact_target_coverage", check_keys)
        self.assertIn("high_importance_prop_presence", check_keys)
        self.assertEqual(
            [item["asset_name"] for item in storyboard["used_assets"]],
            ["Temple Water Room", "Monk Jia", "Old Wooden Bucket"],
        )
        self.assertTrue(storyboard["used_assets"][1]["has_reference"])
        self.assertFalse(storyboard["used_assets"][2]["has_reference"])
        warnings = storyboard["compiler_warnings"]
        self.assertFalse(any("Monk Jia" in item and "reference" in item for item in warnings))
        self.assertTrue(any("Old Wooden Bucket" in item for item in warnings))

    def test_outputs_refresh_stale_visual_fact_detail_strings(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            meta = json.loads(shot.meta_info)
            meta["prompt_compiler"]["compiler_diagnostics"] = {
                "status": "warning",
                "checks": [
                    {"key": "meta_prompt_leakage", "passed": True},
                    {"key": "static_prompt_quality", "passed": True},
                    {"key": "motion_prompt_quality", "passed": True},
                    {"key": "screenplay_prompt_residue", "passed": True},
                    {
                        "key": "visual_fact_target_coverage",
                        "passed": False,
                        "details": [
                            "Temple Water Room：至少补入 2 条视觉事实 / stone floor / old well / mottled wall / cold dawn light / wooden rack / wet ground"
                        ],
                    },
                    {"key": "authority_prompt_inheritance", "passed": True},
                    {"key": "character_variant_state", "passed": True},
                    {"key": "scene_variant_state", "passed": True},
                    {"key": "prop_variant_state", "passed": True},
                    {"key": "high_importance_prop_presence", "passed": True},
                    {"key": "critical_bound_asset_usage", "passed": True},
                ],
            }
            shot.meta_info = json.dumps(meta, ensure_ascii=False)
            session.commit()

        response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(response.status_code, 200)

        storyboard = response.json()["storyboard"][0]
        visual_fact_check = next(
            item
            for item in (storyboard["compiler_diagnostics"].get("checks") or [])
            if isinstance(item, dict) and str(item.get("key") or "").strip() == "visual_fact_target_coverage"
        )
        self.assertTrue(visual_fact_check["details"])
        self.assertTrue(all(detail.count(" / ") <= 4 for detail in visual_fact_check["details"]))

    def test_outputs_refresh_when_legacy_diagnostics_miss_new_screenplay_residue_check(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot.visual_prompt_static = "Monk Jia: Wake up. [Cut to the bucket on the floor]"
            shot.visual_prompt_motion = "Dialogue shot. [Cut to Monk Jia picking up the bucket]"
            meta = json.loads(shot.meta_info)
            meta["prompt_compiler"]["compiler_diagnostics"] = {
                "status": "warning",
                "checks": [
                    {"key": "meta_prompt_leakage", "passed": True},
                    {"key": "static_prompt_quality", "passed": True},
                    {"key": "motion_prompt_quality", "passed": True},
                    {
                        "key": "visual_fact_target_coverage",
                        "passed": True,
                        "details": [],
                    },
                    {"key": "authority_prompt_inheritance", "passed": True},
                    {"key": "critical_bound_asset_usage", "passed": True},
                ],
            }
            shot.meta_info = json.dumps(meta, ensure_ascii=False)
            session.commit()

        response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(response.status_code, 200)

        storyboard = response.json()["storyboard"][0]
        residue_check = next(
            item
            for item in (storyboard["compiler_diagnostics"].get("checks") or [])
            if isinstance(item, dict) and str(item.get("key") or "").strip() == "screenplay_prompt_residue"
        )
        self.assertFalse(residue_check["passed"])


if __name__ == "__main__":
    unittest.main()
