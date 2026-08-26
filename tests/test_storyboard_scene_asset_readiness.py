import importlib.util
import os
import unittest
from pathlib import Path

from models import Session, StoryboardShot, VisualLocation, VisualReferenceAsset, init_db


def load_readiness_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit-storyboard-scene-asset-readiness.py"
    spec = importlib.util.spec_from_file_location("audit_storyboard_scene_asset_readiness", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_scene_reference_plan_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "plan-storyboard-scene-reference-assets.py"
    spec = importlib.util.spec_from_file_location("plan_storyboard_scene_reference_assets", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_scene_reference_enqueue_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "enqueue-storyboard-scene-reference-generation.py"
    spec = importlib.util.spec_from_file_location("enqueue_storyboard_scene_reference_generation", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_scene_reference_apply_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apply-storyboard-scene-reference-plan.py"
    spec = importlib.util.spec_from_file_location("apply_storyboard_scene_reference_plan", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class StoryboardSceneAssetReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.audit = load_readiness_module()
        cls.plan = load_scene_reference_plan_module()
        cls.enqueue = load_scene_reference_enqueue_module()
        cls.apply_plan = load_scene_reference_apply_module()

    def setUp(self):
        self.book_id = 990875
        with Session() as session:
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="便利店收银台",
                    shot_id=1,
                    start_state="店员靠在收银台后。",
                    action_process="门铃响起。",
                    end_state="店员看向门口。",
                )
            )
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.commit()

    def test_bindable_draft_scene_without_reference_blocks_production_apply(self):
        with Session() as session:
            session.add(
                VisualLocation(
                    book_id=self.book_id,
                    name="便利店收银台",
                    description="由分镜批量修复前置检查创建的最小场景资产",
                    asset_status="draft",
                    notes="requires-human-asset-refinement-before-production",
                )
            )
            session.commit()

        result = self.audit.audit_book(self.book_id)
        scene = result["scenes"][0]
        summary = self.audit.summarize([result])

        self.assertEqual(scene["status"], "ready")
        self.assertEqual(scene["production_status"], "needs_refinement")
        self.assertIn("场景资产没有 selected/locked 参考图", scene["production_issues"])
        self.assertTrue(summary["ready_for_binding_repair_apply"])
        self.assertFalse(summary["ready_for_prompt_batch_apply"])

    def test_selected_scene_reference_allows_production_apply(self):
        with Session() as session:
            location = VisualLocation(
                book_id=self.book_id,
                name="便利店收银台",
                description="深夜便利店收银区，货架压迫，冷白荧光灯，玻璃门外是黑暗街道。",
                asset_status="ref_ready",
                notes="production scene asset",
            )
            session.add(location)
            session.flush()
            session.add(
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(location.id),
                    asset_name="便利店收银台",
                    image_url="https://cdn.example.test/scene.png",
                    reference_token="@便利店收银台",
                    status="selected",
                )
            )
            session.commit()

        result = self.audit.audit_book(self.book_id)
        scene = result["scenes"][0]
        summary = self.audit.summarize([result])

        self.assertEqual(scene["status"], "ready")
        self.assertEqual(scene["production_status"], "ready")
        self.assertEqual(scene["selected_reference_count"], 1)
        self.assertTrue(summary["ready_for_binding_repair_apply"])
        self.assertTrue(summary["ready_for_prompt_batch_apply"])

    def test_square_scene_reference_blocks_when_dimension_validation_enabled(self):
        previous = os.environ.get("SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS")
        os.environ["SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS"] = "1"
        try:
            one_by_one_png = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/"
                "l5Y4VwAAAABJRU5ErkJggg=="
            )
            with Session() as session:
                location = VisualLocation(
                    book_id=self.book_id,
                    name="便利店收银台",
                    description="深夜便利店收银区，正式描述。",
                    asset_status="ref_ready",
                )
                session.add(location)
                session.flush()
                session.add(
                    VisualReferenceAsset(
                        book_id=self.book_id,
                        episode=1,
                        asset_type="scene",
                        asset_id=str(location.id),
                        asset_name="便利店收银台",
                        image_url=f"data:image/png;base64,{one_by_one_png}",
                        reference_token="@便利店收银台",
                        status="selected",
                    )
                )
                session.commit()

            result = self.audit.audit_book(self.book_id)
            scene = result["scenes"][0]
            self.assertEqual(scene["production_status"], "needs_refinement")
            self.assertIn("场景资产没有符合横构图比例的 selected/locked 参考图", scene["production_issues"])
        finally:
            if previous is None:
                os.environ.pop("SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS", None)
            else:
                os.environ["SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS"] = previous

    def test_scene_reference_plan_outputs_generation_request_draft(self):
        with Session() as session:
            session.add(
                VisualLocation(
                    book_id=self.book_id,
                    name="便利店收银台",
                    description="由分镜批量修复前置检查创建的最小场景资产",
                    asset_status="draft",
                    notes="requires-human-asset-refinement-before-production",
                )
            )
            session.commit()

        plan = self.plan.plan_book(self.book_id)
        item = plan["items"][0]
        request = item["reference_generation"]["api_request"]

        self.assertEqual(plan["summary"]["planned_scene_references"], 1)
        self.assertEqual(item["status"], "planned")
        self.assertEqual(request["bookId"], self.book_id)
        self.assertEqual(request["assetScope"], "location")
        self.assertEqual(request["targetKind"], "reference-image")
        self.assertIn("便利店收银台", request["prompt"])
        self.assertIn("sourceAssetId", request)
        self.assertIn("单张 16:9 横构图", request["prompt"])
        self.assertIn("不分格", request["prompt"])
        self.assertIn("人物", request["negativePrompt"])

    def test_scene_reference_plan_sanitizes_grid_and_character_fragments(self):
        scene_name = "测试山洞"
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name=scene_name,
                    shot_id=1,
                    lighting="主角面部被火光照亮；洞壁潮湿反光；手指投下阴影",
                    action_process="主角走入山洞。",
                )
            )
            session.add(
                VisualLocation(
                    book_id=self.book_id,
                    name=scene_name,
                    description=(
                        "潮湿山洞入口，岩壁有苔藓；高质量专业场景设定图，"
                        "以2行2列四宫格展示四个大全景视角；不得出现任何人物"
                    ),
                    asset_status="draft",
                )
            )
            session.commit()

        plan = self.plan.plan_book(self.book_id)
        request = plan["items"][0]["reference_generation"]["api_request"]
        prompt = request["prompt"]

        self.assertIn("潮湿山洞入口", prompt)
        self.assertIn("洞壁潮湿反光", prompt)
        self.assertIn("单张 16:9 横构图", prompt)
        self.assertNotIn("2行2列", prompt)
        self.assertNotIn("四宫格", prompt)
        self.assertNotIn("主角面部", prompt)
        self.assertNotIn("手指", prompt)

    def test_scene_reference_plan_preserves_exact_storyboard_scene_name(self):
        scene_name = "原始丛林深处"
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name=scene_name,
                    shot_id=1,
                    lighting="斑驳顶光",
                    action_process="穿过密林。",
                )
            )
            session.add(
                VisualLocation(
                    book_id=self.book_id,
                    name=scene_name,
                    description="原始森林深处，古树参天。",
                    asset_status="ref_ready",
                )
            )
            session.commit()

        plan = self.plan.plan_book(self.book_id)
        item = plan["items"][0]

        self.assertEqual(item["status"], "planned")
        self.assertIn("场景资产描述未包含精确分镜场景名", item["issues"])
        self.assertIn(scene_name, item["planned_asset_update"]["formal_description"])

    def test_scene_reference_enqueue_extracts_planned_requests(self):
        with Session() as session:
            session.add(
                VisualLocation(
                    book_id=self.book_id,
                    name="便利店收银台",
                    description="由分镜批量修复前置检查创建的最小场景资产",
                    asset_status="draft",
                    notes="requires-human-asset-refinement-before-production",
                )
            )
            session.commit()

        plan = self.plan.plan_book(self.book_id)
        requests = self.enqueue.planned_requests(plan)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["scene_name"], "便利店收银台")
        self.assertEqual(requests[0]["api_request"]["targetKind"], "reference-image")
        self.assertTrue(plan["confirmationToken"])

    def test_scene_reference_enqueue_filters_requests(self):
        requests = [
            {"scene_name": "A", "api_request": {"targetKind": "reference-image"}},
            {"scene_name": "B", "api_request": {"targetKind": "reference-image"}},
        ]

        selected = self.enqueue.filter_requests(requests, scene_name="B", limit=1)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["scene_name"], "B")

    def test_scene_reference_plan_apply_promotes_scene_after_reference_exists(self):
        with Session() as session:
            location = VisualLocation(
                book_id=self.book_id,
                name="便利店收银台",
                description="由分镜批量修复前置检查创建的最小场景资产",
                asset_status="draft",
                notes="requires-human-asset-refinement-before-production",
            )
            session.add(location)
            session.flush()
            session.add(
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(location.id),
                    asset_name="便利店收银台",
                    image_url="https://cdn.example.test/store.png",
                    reference_token="@便利店收银台",
                    status="selected",
                    notes="瑙嗚璧勪骇搴撶敓鎴?路 2026-08-24 15:28",
                )
            )
            session.commit()

        plan = self.plan.plan_book(self.book_id)
        updates = self.apply_plan.planned_updates(plan)
        results = self.apply_plan.apply_updates(plan, updates, real=True)

        self.assertEqual(results[0]["status"], "updated")
        with Session() as session:
            location = session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).first()
            ref = session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).first()
            self.assertEqual(location.asset_status, "ref_ready")
            self.assertNotIn("最小场景资产", location.description)
            self.assertIn("视觉资产库生成", ref.notes)


if __name__ == "__main__":
    unittest.main()
