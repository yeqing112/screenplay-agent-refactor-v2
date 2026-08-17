import unittest

from api.server import _build_prompt_compile_context_v2
from models import Session, StoryboardShot, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset, init_db


class StoryboardPromptAuthorityContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.book_id = 990302
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
                name="Rainy Rental Room",
                visual_prompt_zh="A cramped old rental room in a cold rainy night.",
                description="The room is narrow, aged, and damp.",
                lighting_mood="cold backlight from rain",
            )
            session.add(location)
            session.flush()

            character = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Sister",
                visual_prompt_zh="Character six-panel board for the same person in the current shot state.",
                core_prompt_zh="Keep face, hair, body shape, and core temperament consistent.",
                refined_outfit="Dark casual clothing soaked by rain, jacket clinging to the body.",
                hair_style="Half-tied dark brown straight hair, damp from rain.",
                makeup_spec="Pale complexion, tired eyes, muted lips.",
                scene_prompt_zh="Scene influence only: cold rain outside the doorway.",
                consistency_notes="All six views must remain the same person with stable character identity.",
                meta_info='{"scope":"shot_variant","structured_result":{"identity":"Sister","temperament":"calm, guarded","variant_name":"doorway rain state","shot_ids":["1"]}}',
            )
            session.add(character)
            session.flush()

            prop = VisualProp(
                book_id=self.book_id,
                name="Old Kettle",
                visual_prompt_zh="An old kettle with worn corners and heavy use marks.",
                description="The spout is chipped and the surface is weathered.",
                importance="high",
            )
            session.add(prop)
            session.flush()

            session.add_all(
                [
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=self.episode,
                        asset_type="scene",
                        asset_id=str(location.id),
                        asset_name="Rainy Rental Room",
                        image_url="https://example.com/rainy-rental-room.png",
                        reference_token="@RainyRentalRoom",
                        status="selected",
                    ),
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=self.episode,
                        asset_type="character",
                        asset_id=str(character.id),
                        asset_name="Sister",
                        image_url="https://example.com/sister-shot-variant.png",
                        reference_token="@Sister",
                        status="selected",
                    ),
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=self.episode,
                        asset_type="prop",
                        asset_id=str(prop.id),
                        asset_name="Old Kettle",
                        image_url="https://example.com/old-kettle.png",
                        reference_token="@OldKettle",
                        status="selected",
                    ),
                ]
            )

            shot = StoryboardShot(
                book_id=self.book_id,
                episode=self.episode,
                shot_id=self.shot_id,
                scene_name="Rainy Rental Room",
                start_state="Sister stands near the doorway.",
                action_process="A Ning steps back while holding the old kettle.",
                end_state="They pause and lock eyes.",
                dialogue="Don't make a sound yet.",
                camera_angle="MS",
                camera_movement="push-in",
                lighting="cool",
                duration=4,
            )
            session.add(shot)
            session.commit()

            self.location_id = str(location.id)
            self.character_id = str(character.id)
            self.prop_id = str(prop.id)

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.commit()

    def test_compile_context_includes_authority_prompt_payloads(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()

            context = _build_prompt_compile_context_v2(
                self.book_id,
                shot,
                {
                    "scene_asset_id": self.location_id,
                    "character_asset_ids": [self.character_id],
                    "prop_asset_ids": [self.prop_id],
                    "style_key": "default",
                },
                {
                    "constraints": ["keep cold rainy tone"],
                    "notes": ["lower Sister eye line"],
                    "failure_tags": ["camera_motion_wrong"],
                },
                {},
            )

        scene = context["asset_bindings"]["scene"]
        character = context["asset_bindings"]["characters"][0]
        prop = context["asset_bindings"]["props"][0]

        self.assertEqual(scene["authority_prompt_source"], "scene_asset")
        self.assertIn("Rainy Rental Room", scene["asset_name"])
        self.assertIn("cramped old rental room", scene["authority_prompt_raw"])
        self.assertEqual(scene["variant_scope"], "")
        self.assertEqual(scene["scope_label"], "")
        self.assertEqual(scene["stage_name"], "")
        self.assertEqual(scene["reference_source"], "selected")
        self.assertTrue(any(item["key"] == "lighting_mood" for item in scene["authority_prompt_parts"]))
        self.assertEqual(scene["canonical_prompt_profile"]["lighting_mood"], "cold backlight from rain")
        self.assertTrue(any(item["key"] == "canonical_lighting_mood" for item in scene["authority_prompt_parts"]))

        self.assertEqual(character["authority_prompt_source"], "character_makeup")
        self.assertIn("core temperament", character["authority_prompt_raw"])
        self.assertNotIn("Scene influence only", character["authority_prompt_raw"].splitlines()[0])
        self.assertTrue(any(item["key"] == "refined_outfit" for item in character["authority_prompt_parts"]))
        self.assertTrue(any(item["key"] == "consistency_notes" for item in character["authority_prompt_parts"]))
        self.assertEqual(character["canonical_prompt_profile"]["identity"], "Sister")
        self.assertIn("Dark casual clothing soaked by rain", character["canonical_prompt_profile"]["outfit"])
        self.assertIn("jacket clinging to the body", character["canonical_prompt_profile"]["outfit"])
        self.assertTrue(any(item["key"] == "canonical_outfit" for item in character["authority_prompt_parts"]))

        self.assertEqual(prop["authority_prompt_source"], "prop_asset")
        self.assertIn("Old Kettle", prop["asset_name"])
        self.assertIn("old kettle", prop["authority_prompt_raw"].lower())
        self.assertEqual(prop["variant_scope"], "")
        self.assertEqual(prop["scope_label"], "")
        self.assertEqual(prop["stage_name"], "")
        self.assertEqual(prop["reference_source"], "selected")
        self.assertTrue(any(item["key"] == "importance" for item in prop["authority_prompt_parts"]))
        self.assertEqual(prop["canonical_prompt_profile"]["importance"], "high")
        self.assertIn("compile_prompt_contract", context)
        self.assertEqual(len(context["visual_fact_targets"]), 3)
        self.assertEqual(len(context["required_used_assets"]), 3)
        scene_target = next(item for item in context["visual_fact_targets"] if item["asset_type"] == "scene")
        self.assertIn("The room is narrow", scene_target["required_facts"][0])
        self.assertIn("aged", scene_target["required_facts"][0])
        self.assertGreaterEqual(scene_target["min_facts_to_include"], 1)
        character_target = next(item for item in context["visual_fact_targets"] if item["asset_type"] == "character")
        self.assertTrue(character_target["requires_used_asset"])
        prop_target = next(item for item in context["visual_fact_targets"] if item["asset_type"] == "prop")
        self.assertEqual(prop_target["min_facts_to_include"], 1)
        self.assertTrue(all("high quality realistic prop multi-angle display" not in fact.lower() for fact in prop_target["required_facts"]))
        self.assertTrue(any("Sister" in line for line in context["compile_prompt_contract"]["summary_lines"]))
        prop_required = next(item for item in context["required_used_assets"] if item["asset_type"] == "prop")
        self.assertEqual(prop_required["asset_name"], "Old Kettle")


if __name__ == "__main__":
    unittest.main()
