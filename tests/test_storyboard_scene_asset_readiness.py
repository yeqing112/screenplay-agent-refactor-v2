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


def load_scene_reference_merge_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "merge-scene-reference-plans.py"
    spec = importlib.util.spec_from_file_location("merge_scene_reference_plans", path)
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
        cls.merge = load_scene_reference_merge_module()

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

    def test_candidate_scene_reference_dimensions_are_reported_without_becoming_active(self):
        with Session() as session:
            location = VisualLocation(
                book_id=self.book_id,
                name="便利店收银台",
                description="正式场景描述。",
                asset_status="ref_ready",
            )
            session.add(location)
            session.flush()
            # A tiny valid PNG is intentionally used here: the audit should
            # report the candidate dimensions while keeping it inactive.
            one_by_one_png = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/"
                "l5Y4VwAAAABJRU5ErkJggg=="
            )
            session.add(
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(location.id),
                    asset_name="便利店收银台",
                    image_url=f"data:image/png;base64,{one_by_one_png}",
                    reference_token="@便利店收银台",
                    status="candidate",
                )
            )
            session.commit()

        previous = os.environ.get("SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS")
        os.environ["SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS"] = "1"
        try:
            result = self.audit.audit_book(self.book_id)
        finally:
            if previous is None:
                os.environ.pop("SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS", None)
            else:
                os.environ["SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS"] = previous
        scene = result["scenes"][0]
        self.assertEqual(scene["candidate_reference_count"], 1)
        self.assertEqual(scene["landscape_candidate_count"], 0)
        self.assertEqual(scene["selected_reference_count"], 0)

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
        self.assertIn("16:9 横向四视图场景设定板", request["prompt"])
        self.assertIn("固定 2×2 四宫格布局", request["prompt"])
        self.assertIn("左上为主视角空间全景", request["prompt"])
        self.assertEqual(item["planned_asset_update"]["reference_layout"], "2x2_four_view")
        self.assertEqual(len(item["planned_asset_update"]["reference_view_schema"]), 4)
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
        # Shot-level lighting is evidence for shot planning only.  It must
        # not be promoted into a reusable scene reference asset implicitly.
        self.assertNotIn("洞壁潮湿反光", prompt)
        self.assertIn("16:9 横向四视图场景设定板", prompt)
        self.assertIn("固定 2×2 四宫格布局", prompt)
        self.assertIn("四宫格", prompt)
        self.assertNotIn("2行2列", prompt)
        self.assertNotIn("主角面部", prompt)
        self.assertNotIn("手指", prompt)

    def test_scene_reference_plan_prompt_matches_formal_scene_contract(self):
        """The read-only plan must use the same prompt contract as the API."""
        scene_name = "旧公寓门厅"
        with Session() as session:
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.add(
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name=scene_name,
                    shot_id=1,
                    lighting="镜头临时使用强烈侧逆光",
                    action_process="人物推门进入。",
                )
            )
            location = VisualLocation(
                book_id=self.book_id,
                name=scene_name,
                description="公寓门厅，入口连接狭长走廊，右侧固定鞋柜。",
                canonical_facts='{"description":"公寓门厅，入口连接狭长走廊","fixed_assets":["固定鞋柜"]}',
                state_variants='{"lighting":"常态顶灯开启"}',
                look_profile='{"palette":"中性灰"}',
                asset_status="draft",
            )
            session.add(location)
            session.commit()
            location_id = location.id

        plan = self.plan.plan_book(self.book_id)
        item = plan["items"][0]
        with Session() as session:
            location = session.query(VisualLocation).filter(VisualLocation.id == location_id).one()
            contract = self.plan._build_scene_asset_prompt_contract(location)

        self.assertEqual(item["reference_generation"]["prompt"], contract["rendered_prompt_preview"])
        self.assertEqual(item["reference_generation"]["negative_prompt"], contract["reference_negative_prompt"])
        self.assertIn("常态顶灯开启", item["reference_generation"]["prompt"])
        self.assertIn("中性灰", item["reference_generation"]["prompt"])
        self.assertNotIn("强烈侧逆光", item["reference_generation"]["prompt"])

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

    def test_scene_reference_batch_merge_is_readonly_and_keeps_only_planned_items(self):
        batch = self.merge.merge_plans([
            {
                "mode": "readonly-scene-reference-plan",
                "book_id": 11,
                "confirmationToken": "a",
                "items": [
                    {
                        "scene_name": "场景A",
                        "location_id": 1,
                        "status": "planned",
                        "shot_ids": ["1-1"],
                        "issues": ["缺少参考图"],
                        "planned_asset_update": {"formal_description": "空间A"},
                        "reference_generation": {
                            "prompt": "场景A prompt",
                            "negative_prompt": "negative",
                            "api_request": {"targetKind": "reference-image"},
                        },
                    },
                    {"scene_name": "已就绪", "location_id": 2, "status": "already_ready"},
                ],
            },
        ])

        self.assertEqual(batch["summary"]["planned_items"], 1)
        self.assertEqual(batch["summary"]["affected_shots"], 1)
        self.assertTrue(batch["requires_user_confirmation"])
        self.assertFalse(batch["writes_performed"])
        self.assertFalse(batch["external_calls_performed"])
        self.assertEqual(batch["items"][0]["status"], "awaiting_user_confirmation")
        self.assertEqual(batch["items"][0]["book_id"], 11)

    def test_scene_reference_plan_apply_rejects_changed_source_snapshot(self):
        with Session() as session:
            location = VisualLocation(
                book_id=self.book_id,
                name="便利店收银台",
                description="初始场景空间描述。",
                asset_status="draft",
            )
            session.add(location)
            session.commit()

        plan = self.plan.plan_book(self.book_id)
        updates = self.apply_plan.planned_updates(plan)
        with Session() as session:
            location = session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).first()
            location.description = "人工修改后的场景空间描述。"
            session.commit()

        results = self.apply_plan.apply_updates(plan, updates, real=True)

        self.assertEqual(results[0]["status"], "stale")
        with Session() as session:
            location = session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).first()
            self.assertEqual(location.description, "人工修改后的场景空间描述。")


if __name__ == "__main__":
    unittest.main()
