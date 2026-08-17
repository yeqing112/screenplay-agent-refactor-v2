import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from models import Session, StoryboardPromptVersion, StoryboardShot, VisualLocation, VisualMakeup, VisualReferenceAsset, init_db


class MakeupVariantResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990401
        self.episode = 1
        self.shot_id = 1

        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(book_id=self.book_id, name="\u96e8\u68da")
            session.add(location)
            session.flush()

            hero_base = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Hero",
                stage_name="base_identity",
                visual_prompt_zh="\u57fa\u7840\u5b9a\u5986\uff1a\u4e94\u5b98\u7a33\u5b9a\uff0c\u9ed1\u53d1\uff0c\u4f53\u578b\u7a33\u5b9a",
                core_prompt_zh="\u56fa\u5b9a\u8138\u90e8\u3001\u53d1\u578b\u548c\u4f53\u578b",
            )
            session.add(hero_base)
            session.flush()

            hero_variant = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Hero",
                stage_name="shot_1_rain",
                shot_ids=json.dumps(["1"], ensure_ascii=False),
                visual_prompt_zh="\u955c\u5934\u4e00\u6dcb\u96e8\u72b6\u6001\u5b9a\u5986",
                refined_outfit="\u6e7f\u888d",
            )
            session.add(hero_variant)
            session.flush()

            session.add_all([
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="character",
                    asset_id=str(hero_base.id),
                    asset_name="Hero",
                    image_url="https://example.com/hero-base.png",
                    reference_token="@hero-base",
                    status="locked",
                ),
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="character",
                    asset_id=str(hero_variant.id),
                    asset_name="Hero",
                    image_url="https://example.com/hero-rain.png",
                    reference_token="@hero-rain",
                    status="locked",
                ),
            ])

            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="Rain Hut",
                    shot_id=self.shot_id,
                    action_process="Hero steps into the hut soaked by rain.",
                    asset_links=json.dumps({"references": {}}, ensure_ascii=False),
                    meta_info=json.dumps({
                        "structured_shot": {
                            "scene_asset_id": str(location.id),
                            "character_asset_ids": [str(hero_base.id)],
                            "prop_asset_ids": [],
                            "style_key": "default",
                            "character_blocking": [],
                            "action_beats": [],
                        }
                    }, ensure_ascii=False),
                )
            )
            session.commit()
            self.location_id = str(location.id)
            self.hero_base_id = str(hero_base.id)
            self.hero_variant_id = str(hero_variant.id)

    def tearDown(self):
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.commit()

    def test_outputs_expose_makeup_scope_and_stage(self):
        response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        makeups = payload["visual"]["makeups"]
        by_stage = {item["stage_name"]: item for item in makeups}

        self.assertEqual(by_stage["base_identity"]["makeup_scope"], "base_identity")
        self.assertEqual(by_stage["shot_1_rain"]["makeup_scope"], "shot_variant")
        self.assertEqual(by_stage["base_identity"]["core_prompt_zh"], "固定脸部、发型和体型")
        shot_makeup = payload["storyboard"][0]["makeup_prompts"][0]
        self.assertEqual(shot_makeup["stage_name"], "shot_1_rain")
        self.assertTrue(shot_makeup["scope_label"])

    def test_compile_context_uses_shot_variant_and_keeps_base_reference(self):
        llm_payload = {
            "visual_prompt_static": "\u96e8\u68da\u5185\u7684\u4e2d\u666f\u753b\u9762\uff0cHero \u4f7f\u7528 @hero-rain \u7684\u6e7f\u888d\u9020\u578b\u8d70\u5165\u5c4b\u5185\uff0c\u8863\u6446\u88ab\u96e8\u6c34\u6253\u6e7f\u8d34\u8eab\uff0c\u53d1\u68a2\u6f6e\u6e7f\uff0c\u9762\u90e8\u4e0e\u57fa\u7840\u5b9a\u5986\u4fdd\u6301\u4e00\u81f4\uff0c\u96e8\u68da\u6728\u5899\u548c\u95e8\u53e3\u96e8\u5e18\u6e05\u6670\u53ef\u89c1\u3002",
            "visual_prompt_motion": "\u955c\u5934\u7f13\u6162\u63a8\u8fdb\uff0c\u4fdd\u6301 @hero-rain \u7684\u6e7f\u888d\u3001\u6e7f\u53d1\u548c\u6dcb\u96e8\u540e\u7684\u72b6\u6001\u4e00\u81f4\uff0cHero \u8fc8\u6b65\u8fdb\u5165\u96e8\u68da\u540e\u505c\u4e0b\uff0c\u52a8\u4f5c\u8fde\u7eed\uff0c\u573a\u666f\u548c\u89d2\u8272\u5916\u5f62\u524d\u540e\u4e00\u81f4\u3002",
            "negative_prompt": "low quality",
            "used_assets": [
                {
                    "asset_type": "character",
                    "asset_id": self.hero_variant_id,
                    "asset_name": "Hero",
                    "reference_token": "@hero-rain",
                    "reference_status": "locked",
                }
            ],
            "warnings": [],
        }

        with patch("core.llm.call_llm_json", return_value=llm_payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        context = response.json()["prompt_compile_context"]
        character = context["asset_bindings"]["characters"][0]

        self.assertEqual(character["asset_id"], self.hero_variant_id)
        self.assertEqual(character["variant_scope"], "shot_variant")
        self.assertEqual(character["stage_name"], "shot_1_rain")
        self.assertEqual(character["reference_token"], "@hero-rain")
        self.assertEqual(character["base_reference"]["reference_token"], "@hero-base")
        self.assertEqual(context["character_variants"][0]["reference_source"], "active_variant")

    def test_compile_context_warns_when_state_change_only_has_base_reference_fallback(self):
        with Session() as session:
            session.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == self.book_id,
                VisualReferenceAsset.asset_id == self.hero_variant_id,
            ).delete()
            session.commit()

        llm_payload = {
            "visual_prompt_static": "\u96e8\u68da\u5185\u7684\u4e2d\u666f\u753b\u9762\uff0cHero \u4f7f\u7528 @hero-base \u7684\u57fa\u7840\u5b9a\u5986\u5f62\u8c61\u8d70\u5165\u5c4b\u5185\uff0c\u4f46\u8eab\u4f53\u5df2\u7ecf\u88ab\u96e8\u6dcb\u6e7f\uff0c\u8863\u6446\u6c89\u91cd\u8d34\u8eab\uff0c\u95e8\u53e3\u96e8\u5e18\u548c\u6f6e\u6e7f\u5730\u9762\u6e05\u6670\u53ef\u89c1\u3002",
            "visual_prompt_motion": "\u955c\u5934\u7f13\u6162\u63a8\u8fdb\uff0c\u4fdd\u6301 @hero-base \u7684\u89d2\u8272\u8138\u90e8\u4e00\u81f4\uff0c\u540c\u65f6\u8868\u73b0 Hero \u6dcb\u96e8\u540e\u8fdb\u5165\u96e8\u68da\u3001\u6e7f\u888d\u8d34\u8eab\u3001\u52a8\u4f5c\u6536\u7d27\u7684\u72b6\u6001\u53d8\u5316\uff0c\u573a\u666f\u4e0e\u89d2\u8272\u8fde\u7eed\u4e00\u81f4\u3002",
            "negative_prompt": "low quality",
            "used_assets": [
                {
                    "asset_type": "character",
                    "asset_id": self.hero_variant_id,
                    "asset_name": "Hero",
                    "reference_token": "@hero-base",
                    "reference_status": "locked",
                }
            ],
            "warnings": [],
        }

        with patch("core.llm.call_llm_json", return_value=llm_payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        diagnostics = detail["compiler_diagnostics"]
        self.assertEqual(diagnostics["status"], "blocked")
        checks = {item["key"]: item for item in diagnostics["checks"]}
        self.assertFalse(checks["character_variant_state"]["passed"])
        self.assertTrue(any("Hero" in item for item in checks["character_variant_state"].get("details", [])))

    def test_single_legacy_makeup_record_falls_back_to_base_identity_scope(self):
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(book_id=self.book_id, name="Legacy Courtyard")
            session.add(location)
            session.flush()

            legacy_makeup = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Legacy Hero",
                stage_name="legacy-first-look",
                visual_prompt_zh="legacy makeup",
            )
            session.add(legacy_makeup)
            session.flush()

            session.add(
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="character",
                    asset_id=str(legacy_makeup.id),
                    asset_name="Legacy Hero",
                    image_url="https://example.com/legacy-hero.png",
                    reference_token="@legacy-hero",
                    status="selected",
                )
            )
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="Legacy Courtyard",
                    shot_id=self.shot_id,
                    action_process="Legacy hero enters the courtyard.",
                    asset_links=json.dumps({"references": {}}, ensure_ascii=False),
                    meta_info=json.dumps({
                        "structured_shot": {
                            "scene_asset_id": str(location.id),
                            "character_asset_ids": [str(legacy_makeup.id)],
                            "prop_asset_ids": [],
                            "style_key": "default",
                            "character_blocking": [],
                            "action_beats": [],
                        }
                    }, ensure_ascii=False),
                )
            )
            session.commit()

        response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        visual_makeup = payload["visual"]["makeups"][0]
        shot_makeup = payload["storyboard"][0]["makeup_prompts"][0]

        self.assertEqual(visual_makeup["makeup_scope"], "base_identity")
        self.assertEqual(shot_makeup["makeup_scope"], "base_identity")
        self.assertTrue(visual_makeup["scope_label"])
        self.assertTrue(shot_makeup["scope_label"])

    def test_episode_default_without_explicit_base_still_builds_base_reference(self):
        with Session() as session:
            session.query(StoryboardPromptVersion).filter(StoryboardPromptVersion.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(book_id=self.book_id, name="Fallback Temple")
            session.add(location)
            session.flush()

            episode_default = VisualMakeup(
                book_id=self.book_id,
                episode=self.episode,
                character_name="Fallback Hero",
                stage_name="episode_1_default",
                visual_prompt_zh="episode default makeup",
            )
            session.add(episode_default)
            session.flush()

            session.add(
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=self.episode,
                    asset_type="character",
                    asset_id=str(episode_default.id),
                    asset_name="Fallback Hero",
                    image_url="https://example.com/fallback-hero.png",
                    reference_token="@fallback-hero",
                    status="locked",
                )
            )
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=self.episode,
                    scene_name="Fallback Temple",
                    shot_id=self.shot_id,
                    action_process="Fallback hero stands in the temple courtyard.",
                    asset_links=json.dumps({"references": {}}, ensure_ascii=False),
                    meta_info=json.dumps({
                        "structured_shot": {
                            "scene_asset_id": str(location.id),
                            "character_asset_ids": [str(episode_default.id)],
                            "prop_asset_ids": [],
                            "style_key": "default",
                            "character_blocking": [],
                            "action_beats": [],
                        }
                    }, ensure_ascii=False),
                )
            )
            session.commit()
            fallback_id = str(episode_default.id)

        llm_payload = {
            "visual_prompt_static": "Fallback hero uses @fallback-hero",
            "visual_prompt_motion": "Keep @fallback-hero stable.",
            "negative_prompt": "low quality",
            "used_assets": [
                {
                    "asset_type": "character",
                    "asset_id": fallback_id,
                    "asset_name": "Fallback Hero",
                    "reference_token": "@fallback-hero",
                    "reference_status": "locked",
                }
            ],
            "warnings": [],
        }

        with patch("core.llm.call_llm_json", return_value=llm_payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        context = response.json()["prompt_compile_context"]
        character = context["asset_bindings"]["characters"][0]

        self.assertEqual(character["variant_scope"], "episode_default")
        self.assertEqual(character["reference_token"], "@fallback-hero")
        self.assertEqual(character["base_reference"]["reference_token"], "@fallback-hero")
        self.assertEqual(character["base_stage_name"], "episode_1_default")

    def test_state_change_with_only_episode_default_still_warns_for_shot_variant(self):
        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == self.episode,
                StoryboardShot.shot_id == self.shot_id,
            ).first()
            shot.action_process = "Hero staggers in soaked by rain and mud."

            session.query(VisualReferenceAsset).filter(
                VisualReferenceAsset.book_id == self.book_id,
                VisualReferenceAsset.asset_id == self.hero_variant_id,
            ).delete()
            session.query(VisualMakeup).filter(
                VisualMakeup.book_id == self.book_id,
                VisualMakeup.id == int(self.hero_variant_id),
            ).delete()
            session.commit()

        llm_payload = {
            "visual_prompt_static": "Hero in the rain hut using @hero-base",
            "visual_prompt_motion": "Keep @hero-base consistent while the camera pushes in.",
            "negative_prompt": "low quality",
            "used_assets": [
                {
                    "asset_type": "character",
                    "asset_id": self.hero_base_id,
                    "asset_name": "Hero",
                    "reference_token": "@hero-base",
                    "reference_status": "locked",
                }
            ],
            "warnings": [],
        }

        with patch("core.llm.call_llm_json", return_value=llm_payload):
            response = self.client.post(
                f"/api/books/{self.book_id}/storyboard/{self.episode}/{self.shot_id}/compile-prompts",
                json={"compileReason": "manual"},
            )

        self.assertEqual(response.status_code, 200)
        context = response.json()["prompt_compile_context"]
        character = context["asset_bindings"]["characters"][0]
        warnings = context["warnings"]

        self.assertEqual(character["variant_scope"], "base_identity")
        self.assertEqual(character["reference_source"], "active_variant")
        self.assertTrue(any("分镜精调定妆" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
