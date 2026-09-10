import json
import unittest

from fastapi.testclient import TestClient

from api.server import app
from models import Book, Session, StoryboardShot, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset, init_db


class ProductionReadinessApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990306
        with Session() as session:
            for model in (VisualReferenceAsset, StoryboardShot, VisualMakeup, VisualLocation, VisualProp, Book):
                session.query(model).filter(model.book_id == self.book_id if model is not Book else model.id == self.book_id).delete()
            session.add(Book(id=self.book_id, title="生产就绪度测试", filename="readiness.txt", chapter_count=1, total_words=100, status="imported"))
            scene = VisualLocation(
                book_id=self.book_id,
                name="深夜便利店",
                asset_status="locked",
                description="狭窄便利店收银区，货架与玻璃门形成纵深。",
                style="写实电影感",
                lighting_mood="冷白荧光灯下，男人进入后伸手把照片放在台面。",
            )
            character = VisualMakeup(
                book_id=self.book_id,
                episode=1,
                character_name="神秘女人",
                asset_status="locked",
                hair_style="穿着白色连衣裙",
                negative_prompt="",
            )
            prop = VisualProp(book_id=self.book_id, name="旧照片", asset_status="locked", description="")
            session.add_all([scene, character, prop])
            session.flush()
            session.add(VisualReferenceAsset(
                book_id=self.book_id,
                asset_type="scene",
                asset_id=str(scene.id),
                asset_name=scene.name,
                image_url="https://example.com/scene.png",
                status="locked",
            ))
            pass_meta = {
                "structured_shot": {"static_prompt_sections": {"scene": "深夜便利店"}, "executability": {"status": "pass"}},
                "prompt_compiler": {"compiler_diagnostics": {"status": "pass"}, "prompt_compile_context": {"executability": {"status": "pass"}, "bound_assets": [{"has_reference": True, "locked_reference": True}]}},
            }
            blocked_meta = {
                "prompt_compiler": {"compiler_diagnostics": {"status": "blocked"}, "prompt_compile_context": {"executability": {"status": "blocked"}}},
            }
            session.add_all([
                StoryboardShot(book_id=self.book_id, episode=1, shot_id=1, scene_name=scene.name, duration=4, meta_info=json.dumps(pass_meta, ensure_ascii=False)),
                StoryboardShot(book_id=self.book_id, episode=1, shot_id=2, scene_name=scene.name, duration=3, meta_info=json.dumps(blocked_meta, ensure_ascii=False)),
            ])
            session.commit()

    def test_readiness_is_read_only_and_reports_asset_and_shot_quality(self):
        response = self.client.get(f"/api/books/{self.book_id}/production-readiness")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["mode"], "readonly-production-readiness")
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["summary"]["shots"], 2)
        self.assertGreaterEqual(payload["summary"]["blocked_items"], 1)
        # Legacy persisted diagnostics intentionally lack a source fingerprint;
        # readiness must not present them as current production evidence.
        self.assertEqual(payload["shots"][0]["status"], "warning")
        self.assertFalse(payload["shots"][0]["prompt_diagnostics_fresh"])
        self.assertIn("stale_prompt_diagnostics", {issue["code"] for issue in payload["shots"][0]["issues"]})
        self.assertEqual(payload["shots"][1]["status"], "blocked")

        character_codes = {issue["code"] for issue in payload["assets"]["character"][0]["issues"]}
        scene_codes = {issue["code"] for issue in payload["assets"]["scene"][0]["issues"]}
        self.assertIn("character_field_semantic_mismatch", character_codes)
        self.assertIn("missing_character_negative_prompt", character_codes)
        self.assertIn("scene_lighting_contaminated_by_shot", scene_codes)

        with Session() as session:
            self.assertEqual(session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).count(), 2)
            self.assertEqual(session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).count(), 1)

    def test_repair_plan_exposes_a_specific_human_asset_action_without_mutating_data(self):
        response = self.client.get(f"/api/books/{self.book_id}/production-readiness/repair-plan")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        character_action = next(item for item in payload["asset_actions"] if item["asset_type"] == "character")
        self.assertEqual(character_action["action"], "upload_or_select_reference")
        self.assertEqual(character_action["label"], "上传或选定正式参考图")
        self.assertTrue(character_action["confirmation_required"])
        with Session() as session:
            self.assertEqual(session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).count(), 1)

    def test_readiness_scopes_asset_checks_to_bound_assets_when_stable_keys_exist(self):
        with Session() as session:
            scene = session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).one()
            session.add(VisualProp(
                book_id=self.book_id,
                name="未绑定备用道具",
                asset_status="draft",
                description="",
            ))
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.shot_id == 1,
            ).one()
            meta = json.loads(shot.meta_info)
            meta["prompt_compiler"]["prompt_compile_context"]["bound_assets"] = [{
                "asset_type": "scene",
                "asset_id": str(scene.id),
                "has_reference": True,
                "locked_reference": True,
            }]
            shot.meta_info = json.dumps(meta, ensure_ascii=False)
            session.commit()

        payload = self.client.get(f"/api/books/{self.book_id}/production-readiness").json()
        self.assertEqual(payload["summary"]["asset_scope"], "bound_to_shots")
        self.assertEqual(payload["summary"]["assets"], 1)
        self.assertEqual(len(payload["assets"]["scene"]), 1)
        self.assertEqual(payload["assets"]["character"], [])
        self.assertEqual(payload["assets"]["prop"], [])
