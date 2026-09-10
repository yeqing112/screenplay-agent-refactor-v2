import unittest
from io import BytesIO
from datetime import datetime, timedelta
import json
from urllib.parse import unquote

from fastapi.testclient import TestClient

from api.server import app
from models import AssetSemanticGovernanceRecord, Session, StoryboardShot, VisualLocation, VisualMakeup, VisualProp, VisualReferenceAsset, init_db


class VisualAssetLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        self.book_id = 990101
        with Session() as session:
            session.query(AssetSemanticGovernanceRecord).filter(AssetSemanticGovernanceRecord.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()

            location = VisualLocation(book_id=self.book_id, name="Forest Camp")
            prop = VisualProp(book_id=self.book_id, name="Clay Bowl")
            location.description = "Forest camp structured scene prompt."
            location.visual_prompt_zh = "森林营地结构化场景提示词。"
            location.core_prompt_zh = "森林营地核心空间锚点。"
            location.lighting_mood = "冷月顶光；林小夏面部处于阴影中；货架反光。"
            prop.description = "Clay bowl structured prop prompt."
            prop.visual_prompt_zh = "陶碗结构化道具提示词。"
            prop.core_prompt_zh = "陶碗核心材质锚点。"
            makeup = VisualMakeup(book_id=self.book_id, episode=1, character_name="Ji You")
            shot = StoryboardShot(
                book_id=self.book_id,
                episode=1,
                scene_name="Forest Camp",
                shot_id=1,
                dialogue="Ji You stands by the clay bowl",
                asset_links="{}",
                asset_status="pending",
            )
            session.add_all([location, prop, makeup, shot])
            session.commit()

            self.location_id = location.id
            self.prop_id = prop.id
            self.makeup_id = makeup.id

    def tearDown(self):
        with Session() as session:
            session.query(AssetSemanticGovernanceRecord).filter(AssetSemanticGovernanceRecord.book_id == self.book_id).delete()
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).delete()
            session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).delete()
            session.query(VisualMakeup).filter(VisualMakeup.book_id == self.book_id).delete()
            session.query(VisualProp).filter(VisualProp.book_id == self.book_id).delete()
            session.query(VisualLocation).filter(VisualLocation.book_id == self.book_id).delete()
            session.commit()

    def test_manual_reference_upload_supports_character_scene_and_prop_assets(self):
        one_pixel_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
            b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        targets = [
            ("character", self.makeup_id, "Ji You"),
            ("scene", self.location_id, "Forest Camp"),
            ("prop", self.prop_id, "Clay Bowl"),
        ]

        for asset_type, asset_id, asset_name in targets:
            response = self.client.post(
                f"/api/books/{self.book_id}/visual-assets/{asset_type}/{asset_id}/manual-reference-assets",
                data={"assetName": asset_name, "notes": f"manual {asset_type} reference"},
                files={"file": (f"{asset_type}.png", BytesIO(one_pixel_png), "image/png")},
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["asset_type"], asset_type)
            self.assertEqual(payload["asset_id"], str(asset_id))
            self.assertEqual(payload["reference"]["status"], "locked")
            self.assertEqual(payload["reference"]["model"], "manual-upload")
            self.assertTrue(payload["reference"]["image_url"].startswith("/api/prototyping/manual-media/"))

        with Session() as session:
            rows = session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == self.book_id).all()
            self.assertEqual(len(rows), 3)
            self.assertEqual({row.asset_type for row in rows}, {"character", "scene", "prop"})
            self.assertTrue(all(row.status == "locked" for row in rows))

    def test_visual_assets_endpoint_returns_defaults(self):
        response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["book_id"], self.book_id)
        self.assertEqual(payload["locations"][0]["asset_status"], "draft")
        self.assertEqual(payload["locations"][0]["jimeng_ref_name"], "")
        self.assertEqual(payload["locations"][0]["description"], "Forest camp structured scene prompt.")
        self.assertEqual(payload["locations"][0]["visual_prompt_zh"], "森林营地结构化场景提示词。")
        self.assertEqual(payload["locations"][0]["core_prompt_zh"], "森林营地核心空间锚点。")
        self.assertEqual(payload["locations"][0]["confirmed_prompt_raw"], "森林营地结构化场景提示词。")
        self.assertIn("Forest Camp 场景参考图", payload["locations"][0]["rendered_prompt_preview"])
        self.assertIn("单张 16:9 横构图", payload["locations"][0]["rendered_prompt_preview"])
        self.assertIn("无人物、无人脸、不出现角色", payload["locations"][0]["rendered_prompt_preview"])
        self.assertIn("写实电影感", payload["locations"][0]["rendered_prompt_preview"])
        self.assertIn("冷月顶光", payload["locations"][0]["rendered_prompt_preview"])
        self.assertIn("货架反光", payload["locations"][0]["rendered_prompt_preview"])
        self.assertNotIn("林小夏", payload["locations"][0]["rendered_prompt_preview"])
        self.assertNotIn("面部", payload["locations"][0]["rendered_prompt_preview"])
        self.assertEqual(payload["locations"][0]["structured_variant_fields"]["scene_name"], "Forest Camp")
        self.assertIn("人物", payload["locations"][0]["reference_negative_prompt"])
        self.assertIn("分格", payload["locations"][0]["reference_negative_prompt"])
        self.assertEqual(payload["props"][0]["asset_status"], "draft")
        self.assertEqual(payload["props"][0]["description"], "Clay bowl structured prop prompt.")
        self.assertEqual(payload["props"][0]["visual_prompt_zh"], "陶碗结构化道具提示词。")
        self.assertEqual(payload["props"][0]["core_prompt_zh"], "陶碗核心材质锚点。")
        self.assertEqual(payload["props"][0]["confirmed_prompt_raw"], "陶碗结构化道具提示词。")
        self.assertIn("Clay Bowl 道具参考图", payload["props"][0]["rendered_prompt_preview"])
        self.assertIn("主体明确", payload["props"][0]["rendered_prompt_preview"])
        self.assertEqual(payload["props"][0]["structured_variant_fields"]["prop_name"], "Clay Bowl")
        self.assertEqual(payload["characters"][0]["asset_status"], "draft")
        self.assertEqual(payload["locations"][0]["variant_scope"], "")
        self.assertEqual(payload["locations"][0]["scope_label"], "")
        self.assertEqual(payload["locations"][0]["stage_name"], "")
        self.assertIn("references", payload["locations"][0])
        self.assertIn("reference_assets", payload["locations"][0])
        self.assertEqual(payload["locations"][0]["reference_assets"], payload["locations"][0]["references"])
        self.assertEqual(payload["props"][0]["variant_scope"], "")
        self.assertEqual(payload["props"][0]["scope_label"], "")
        self.assertEqual(payload["props"][0]["stage_name"], "")
        self.assertIn("references", payload["props"][0])
        self.assertIn("reference_assets", payload["props"][0])
        self.assertEqual(payload["props"][0]["reference_assets"], payload["props"][0]["references"])

    def test_prop_reference_contract_removes_legacy_multi_view_boilerplate(self):
        from api.server import _build_prop_asset_prompt_contract

        with Session() as session:
            prop = session.query(VisualProp).filter(VisualProp.id == self.prop_id).first()
            prop.visual_prompt_zh = (
                "道具视觉描述，高质量写实道具多角度展示图，横向构图，2行3列干净网格排版，"
                "六个极正视角：绝对正前方视图、绝对正后方视图。"
                "深色桃花心木，黄铜机构，玻璃表面有斜向裂痕，指针停在11:47。"
                "画面中不得出现任何人物、角色、手、脚、人脸、场景、建筑、自然景观。"
            )
            session.commit()
            contract = _build_prop_asset_prompt_contract(prop)

        rendered = contract["rendered_prompt_preview"]
        self.assertIn("深色桃花心木", rendered)
        self.assertIn("斜向裂痕", rendered)
        self.assertIn("单张 1:1 或 4:3", rendered)
        self.assertIn("道具完整入画", rendered)
        self.assertIn("主体不裁切", rendered)
        self.assertNotIn("2行3列", rendered)
        self.assertNotIn("多角度展示图", rendered)
        self.assertNotIn("六个极正视角", rendered)
        self.assertNotIn("不得出现任何人物", rendered)
        self.assertNotIn("关联人物", rendered)
        self.assertNotIn("林小夏", rendered)
        self.assertIn("safe_reference_description", contract["structured_variant_fields"])

    def test_reference_version_counts_canonical_history_when_asset_is_unbound(self):
        from api.server import _next_reference_asset_version

        with Session() as session:
            session.add_all([
                VisualReferenceAsset(
                    book_id=self.book_id, episode=1, asset_type="prop", asset_id=str(self.prop_id),
                    asset_name="Clay Bowl", image_url="/old-a.png", status="stale",
                    meta_info=json.dumps({"version": "v1"}, ensure_ascii=False),
                ),
                VisualReferenceAsset(
                    book_id=self.book_id, episode=1, asset_type="prop", asset_id=str(self.prop_id),
                    asset_name="Clay Bowl", image_url="/old-b.png", status="candidate",
                    meta_info=json.dumps({"version": "v1"}, ensure_ascii=False),
                ),
            ])
            session.commit()

        self.assertEqual(
            _next_reference_asset_version(self.book_id, 1, "prop", "Clay Bowl", str(self.prop_id)),
            3,
        )

    def test_scene_and_prop_formal_variant_metadata_round_trip_through_outputs(self):
        with Session() as session:
            session.add_all([
                VisualLocation(
                    book_id=self.book_id,
                    name="Forest Camp",
                    style="Night Variant",
                    lighting_mood="Cold moonlight",
                    color_palette="Blue gray",
                ),
                VisualProp(
                    book_id=self.book_id,
                    name="Clay Bowl",
                    associated_characters="Ji You",
                    importance="high",
                    time_period="Late Ming",
                ),
            ])
            session.commit()

        visual_assets_response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(visual_assets_response.status_code, 200)
        assets_payload = visual_assets_response.json()

        locations = [item for item in assets_payload["locations"] if item["name"] == "Forest Camp"]
        props = [item for item in assets_payload["props"] if item["name"] == "Clay Bowl"]
        self.assertEqual(len(locations), 2)
        self.assertEqual(len(props), 2)
        self.assertTrue(all(item["variant_scope"] == "scene_variant" for item in locations))
        self.assertTrue(all(item["scope_label"] == "场景变体" for item in locations))
        self.assertTrue(any(item["stage_name"] == "Cold moonlight" for item in locations))
        self.assertTrue(all(item["variant_scope"] == "prop_variant" for item in props))
        self.assertTrue(all(item["scope_label"] == "道具变体" for item in props))
        self.assertTrue(any(item["stage_name"] == "Ji You" for item in props))

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(outputs_response.status_code, 200)
        outputs_payload = outputs_response.json()["visual"]

        output_locations = [item for item in outputs_payload["locations"] if item["name"] == "Forest Camp"]
        output_props = [item for item in outputs_payload["props"] if item["name"] == "Clay Bowl"]
        self.assertEqual(len(output_locations), 2)
        self.assertEqual(len(output_props), 2)
        self.assertTrue(all(item["variant_scope"] == "scene_variant" for item in output_locations))
        self.assertTrue(all(item["scope_label"] == "场景变体" for item in output_locations))
        self.assertTrue(any(item["stage_name"] == "Cold moonlight" for item in output_locations))
        self.assertTrue(all(item["variant_scope"] == "prop_variant" for item in output_props))
        self.assertTrue(all(item["scope_label"] == "道具变体" for item in output_props))
        self.assertTrue(any(item["stage_name"] == "Ji You" for item in output_props))

    def test_patch_visual_asset_updates_stage1_fields(self):
        response = self.client.patch(
            f"/api/books/{self.book_id}/visual-assets/scene/{self.location_id}",
            json={
                "jimengRefName": "@forest-camp",
                "negativePrompt": "no modern objects",
                "assetStatus": "locked",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["jimeng_ref_name"], "@forest-camp")
        self.assertEqual(payload["negative_prompt"], "no modern objects")
        self.assertEqual(payload["asset_status"], "locked")

    def test_asset_semantic_governance_draft_is_read_only_and_confirm_is_guarded(self):
        from unittest.mock import patch
        with Session() as session:
            makeup = session.query(VisualMakeup).filter(VisualMakeup.id == self.makeup_id).first()
            makeup.refined_outfit = "穿着白色连衣裙，长发披肩"
            makeup.hair_style = "穿着白色连衣裙，长发披肩"
            shot = session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).first()
            shot.meta_info = json.dumps({"structured_shot": {"character_asset_ids": [str(self.makeup_id)]}}, ensure_ascii=False)
            session.commit()

        compiler_result = {
            "proposed_fields": {"refined_outfit": "白色连衣裙", "hair_style": "长发披肩"},
            "field_moves": [{"source_field": "hair_style", "target_field": "refined_outfit", "text": "白色连衣裙"}],
            "shot_layer_extractions": [],
            "rationale": ["服装与发型属于不同的稳定人物外观字段。"],
            "affected_shots": [],
        }
        with patch("api.server.llm_client.call_llm_json", return_value=compiler_result):
            response = self.client.post(
                f"/api/books/{self.book_id}/visual-assets/character/{self.makeup_id}/semantic-governance-drafts"
            )
        self.assertEqual(response.status_code, 200, response.text)
        evidence = response.json()
        self.assertFalse(evidence["llm_called"])
        with patch("api.server.llm_client.call_llm_json", return_value=compiler_result) as mock_call:
            response = self.client.post(
                f"/api/books/{self.book_id}/visual-assets/character/{self.makeup_id}/semantic-governance-drafts/llm-draft",
                json={"packetFingerprint": evidence["plan_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(response.status_code, 200, response.text)
        mock_call.assert_called_once()
        draft = response.json()
        repeated_draft = self.client.post(
            f"/api/books/{self.book_id}/visual-assets/character/{self.makeup_id}/semantic-governance-drafts/llm-draft",
            json={"packetFingerprint": evidence["plan_fingerprint"], "confirmed": True, "allowExternalCall": True},
        )
        self.assertEqual(repeated_draft.status_code, 200, repeated_draft.text)
        self.assertTrue(repeated_draft.json()["deduplicated"])
        mock_call.assert_called_once()
        self.assertTrue(draft["requires_confirmation"])
        self.assertEqual(draft["proposed_fields"]["hair_style"], "长发披肩")
        self.assertEqual(draft["affected_shots"][0]["composite_shot_id"], "1-1")

        with Session() as session:
            makeup = session.query(VisualMakeup).filter(VisualMakeup.id == self.makeup_id).first()
            self.assertEqual(makeup.hair_style, "穿着白色连衣裙，长发披肩")
            self.assertEqual(
                session.query(AssetSemanticGovernanceRecord)
                .filter(AssetSemanticGovernanceRecord.book_id == self.book_id)
                .count(),
                1,
            )

        unguarded = self.client.post(
            f"/api/books/{self.book_id}/visual-assets/character/{self.makeup_id}/semantic-governance-drafts/confirm",
            json={"planFingerprint": draft["plan_fingerprint"], "confirmed": True},
        )
        self.assertEqual(unguarded.status_code, 400)
        confirmed = self.client.post(
            f"/api/books/{self.book_id}/visual-assets/character/{self.makeup_id}/semantic-governance-drafts/confirm",
            json={"planFingerprint": draft["plan_fingerprint"], "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["recompile_plan_status"], "pending_recompile")
        repeated = self.client.post(
            f"/api/books/{self.book_id}/visual-assets/character/{self.makeup_id}/semantic-governance-drafts/confirm",
            json={"planFingerprint": draft["plan_fingerprint"], "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertTrue(repeated.json()["already_confirmed"])
        with Session() as session:
            makeup = session.query(VisualMakeup).filter(VisualMakeup.id == self.makeup_id).first()
            self.assertEqual(makeup.refined_outfit, "白色连衣裙")
            self.assertEqual(makeup.hair_style, "长发披肩")
            shot = session.query(StoryboardShot).filter(StoryboardShot.book_id == self.book_id).first()
            self.assertTrue(json.loads(shot.meta_info)["prompt_compiler"]["recompile_required"])

    def test_asset_semantic_governance_rejects_stale_source_snapshot(self):
        from unittest.mock import patch

        compiler_result = {
            "proposed_fields": {"lighting_mood": "冷月顶光"},
            "field_moves": [], "shot_layer_extractions": [], "rationale": [], "affected_shots": [],
        }
        response = self.client.post(f"/api/books/{self.book_id}/visual-assets/scene/{self.location_id}/semantic-governance-drafts")
        self.assertEqual(response.status_code, 200, response.text)
        evidence = response.json()
        with Session() as session:
            location = session.query(VisualLocation).filter(VisualLocation.id == self.location_id).first()
            location.lighting_mood = "已被其他编辑更新"
            session.commit()
        with patch("api.server.llm_client.call_llm_json", return_value=compiler_result):
            stale = self.client.post(
                f"/api/books/{self.book_id}/visual-assets/scene/{self.location_id}/semantic-governance-drafts/llm-draft",
                json={"packetFingerprint": evidence["plan_fingerprint"], "confirmed": True, "allowExternalCall": True},
            )
        self.assertEqual(stale.status_code, 409)

    def test_reference_assets_round_trip_through_visual_assets_endpoint(self):
        create_response = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "scene",
                "assetId": str(self.location_id),
                "assetName": "Forest Camp",
                "imageUrl": "https://example.com/forest-camp.png",
                "referenceToken": "@forest-camp",
                "status": "selected",
                "prompt": "misty forest camp at dawn",
                "model": "gpt-image-1",
                "metaInfo": {"source": "test"},
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertEqual(created["asset_type"], "scene")
        self.assertEqual(created["asset_id"], str(self.location_id))

        list_response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        references = payload["locations"][0]["references"]
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["reference_token"], "@forest-camp")
        self.assertEqual(references[0]["status"], "selected")
        self.assertEqual(payload["locations"][0]["derived_asset_status"], "ref_ready")
        self.assertEqual(payload["locations"][0]["primary_reference_token"], "@forest-camp")

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        self.assertEqual(outputs_response.status_code, 200)
        outputs = outputs_response.json()
        storyboard_refs = outputs["storyboard"][0]["asset_links"]["references"]["scene"]
        self.assertEqual(len(storyboard_refs), 1)
        self.assertEqual(storyboard_refs[0]["metadata"]["imageRole"], "reference")

    def test_reference_asset_create_returns_warning_when_storyboard_sync_fails(self):
        create_response = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "prop",
                "assetId": str(self.prop_id),
                "assetName": "Clay Bowl",
                "imageUrl": "https://example.com/clay-bowl.png",
                "referenceToken": "@clay-bowl",
                "status": "selected",
                "prompt": "weathered clay bowl on a monk table",
                "model": "gpt-image-1",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertEqual(created["asset_type"], "prop")
        self.assertIn("sync_warning", created)

        list_response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        references = payload["props"][0]["references"]
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["reference_token"], "@clay-bowl")

    def test_patch_reference_asset_to_rejected_removes_storyboard_reference(self):
        created = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "scene",
                "assetId": str(self.location_id),
                "assetName": "Forest Camp",
                "imageUrl": "https://example.com/forest-camp-2.png",
                "referenceToken": "@forest-camp-2",
                "status": "selected",
            },
        ).json()

        patch_response = self.client.patch(
            f"/api/books/{self.book_id}/visual-reference-assets/{created['id']}",
            json={"status": "rejected"},
        )
        self.assertEqual(patch_response.status_code, 200)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_refs = outputs["storyboard"][0]["asset_links"]["references"]["scene"]
        self.assertEqual(storyboard_refs, [])

    def test_delete_reference_asset_removes_visual_asset_and_storyboard_reference(self):
        created = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "scene",
                "assetId": str(self.location_id),
                "assetName": "Forest Camp",
                "imageUrl": "https://example.com/forest-camp-3.png",
                "referenceToken": "@forest-camp-3",
                "status": "selected",
            },
        ).json()

        delete_response = self.client.delete(
            f"/api/books/{self.book_id}/visual-reference-assets/{created['id']}",
        )
        self.assertEqual(delete_response.status_code, 200)
        deleted = delete_response.json()
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["removed_storyboard_references"], 1)

        list_response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        payload = list_response.json()
        self.assertEqual(payload["locations"][0]["references"], [])

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_refs = outputs["storyboard"][0]["asset_links"]["references"]["scene"]
        self.assertEqual(storyboard_refs, [])

    def test_only_one_selected_reference_is_kept_per_asset(self):
        first = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "scene",
                "assetId": str(self.location_id),
                "assetName": "Forest Camp",
                "imageUrl": "https://example.com/forest-camp-a.png",
                "referenceToken": "@forest-camp-a",
                "status": "selected",
            },
        ).json()
        second = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "scene",
                "assetId": str(self.location_id),
                "assetName": "Forest Camp",
                "imageUrl": "https://example.com/forest-camp-b.png",
                "referenceToken": "@forest-camp-b",
                "status": "selected",
            },
        ).json()

        list_response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        references = list_response.json()["locations"][0]["references"]
        status_by_token = {item["reference_token"]: item["status"] for item in references}
        self.assertEqual(status_by_token["@forest-camp-a"], "candidate")
        self.assertEqual(status_by_token["@forest-camp-b"], "selected")

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        storyboard_refs = outputs_response.json()["storyboard"][0]["asset_links"]["references"]["scene"]
        self.assertEqual(len(storyboard_refs), 1)
        self.assertEqual(storyboard_refs[0]["metadata"]["referenceToken"], "@forest-camp-b")

    def test_patch_visual_asset_shot_links_invalidates_legacy_reference(self):
        created = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "prop",
                "assetId": str(self.prop_id),
                "assetName": "Clay Bowl",
                "imageUrl": "https://example.com/clay-bowl-2.png",
                "referenceToken": "@clay-bowl-2",
                "status": "selected",
            },
        ).json()
        self.assertIn("sync_warning", created)

        patch_response = self.client.patch(
            f"/api/books/{self.book_id}/visual-assets/prop/{self.prop_id}",
            json={"shotIds": ["1"]},
        )
        self.assertEqual(patch_response.status_code, 200)
        payload = patch_response.json()
        self.assertEqual(payload["shot_ids"], ["1"])

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_props = outputs["storyboard"][0]["asset_links"]["references"].get("props", {})
        self.assertNotIn("Clay Bowl", storyboard_props)
        listed = self.client.get(f"/api/books/{self.book_id}/visual-assets").json()
        prop = next(item for item in listed["props"] if item["id"] == self.prop_id)
        reference = next(item for item in prop["references"] if item["reference_token"] == "@clay-bowl-2")
        self.assertEqual(reference["status"], "stale")

    def test_reference_asset_create_can_fallback_to_meta_shot_id_when_asset_has_no_bound_shots(self):
        create_response = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "prop",
                "assetId": str(self.prop_id),
                "assetName": "Clay Bowl",
                "imageUrl": "https://example.com/clay-bowl-fallback.png",
                "referenceToken": "@clay-bowl-fallback",
                "status": "selected",
                "metaInfo": {
                    "shotId": "1",
                    "source": "asset-center-fallback-test",
                },
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertNotIn("sync_warning", created)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_refs = outputs["storyboard"][0]["asset_links"]["references"]["props"]["Clay Bowl"]
        self.assertEqual(len(storyboard_refs), 1)
        self.assertEqual(storyboard_refs[0]["metadata"]["referenceToken"], "@clay-bowl-fallback")
        self.assertEqual(storyboard_refs[0]["metadata"]["shotId"], "1")

    def test_reference_asset_create_can_fallback_to_meta_shot_ids_when_asset_has_no_bound_shots(self):
        with Session() as session:
            session.add_all([
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="Forest Camp",
                    shot_id=2,
                    dialogue="Ji You lifts the clay bowl again",
                    asset_links="{}",
                    asset_status="pending",
                ),
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="Forest Camp",
                    shot_id=3,
                    dialogue="The clay bowl falls to the ground",
                    asset_links="{}",
                    asset_status="pending",
                ),
            ])
            session.commit()

        create_response = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "prop",
                "assetId": str(self.prop_id),
                "assetName": "Clay Bowl",
                "imageUrl": "https://example.com/clay-bowl-fallback-multi.png",
                "referenceToken": "@clay-bowl-fallback-multi",
                "status": "selected",
                "metaInfo": {
                    "shotId": "1",
                    "shotIds": ["1-1", "1-2", "1-3"],
                    "source": "asset-center-fallback-multi-test",
                },
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertNotIn("sync_warning", created)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_by_id = {int(item["shot_id"]): item for item in outputs["storyboard"]}
        for shot_id in [1, 2, 3]:
            storyboard_refs = storyboard_by_id[shot_id]["asset_links"]["references"]["props"]["Clay Bowl"]
            self.assertEqual(len(storyboard_refs), 1)
            self.assertEqual(storyboard_refs[0]["metadata"]["referenceToken"], "@clay-bowl-fallback-multi")

        visual_assets_response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(visual_assets_response.status_code, 200)
        props = visual_assets_response.json()["props"]
        clay_bowl = next(item for item in props if item["id"] == self.prop_id)
        self.assertEqual(clay_bowl["shot_ids"], ["1-1", "1-2", "1-3"])

    def test_delete_reference_asset_removes_meta_shot_ids_fallback_references(self):
        with Session() as session:
            session.add_all([
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="Forest Camp",
                    shot_id=2,
                    dialogue="Ji You lifts the clay bowl again",
                    asset_links="{}",
                    asset_status="pending",
                ),
                StoryboardShot(
                    book_id=self.book_id,
                    episode=1,
                    scene_name="Forest Camp",
                    shot_id=3,
                    dialogue="The clay bowl falls to the ground",
                    asset_links="{}",
                    asset_status="pending",
                ),
            ])
            session.commit()

        created = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "prop",
                "assetId": str(self.prop_id),
                "assetName": "Clay Bowl",
                "imageUrl": "https://example.com/clay-bowl-delete-multi.png",
                "referenceToken": "@clay-bowl-delete-multi",
                "status": "selected",
                "metaInfo": {
                    "shotId": "1",
                    "shotIds": ["1-1", "1-2", "1-3"],
                    "source": "asset-center-delete-fallback-multi-test",
                },
            },
        ).json()

        delete_response = self.client.delete(
            f"/api/books/{self.book_id}/visual-reference-assets/{created['id']}",
        )
        self.assertEqual(delete_response.status_code, 200)
        deleted = delete_response.json()
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["removed_storyboard_references"], 3)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_by_id = {int(item["shot_id"]): item for item in outputs["storyboard"]}
        for shot_id in [1, 2, 3]:
            props = storyboard_by_id[shot_id]["asset_links"]["references"]["props"]
            self.assertFalse(props.get("Clay Bowl"))

    def test_makeup_targets_shot_accepts_episode_prefixed_shot_ids(self):
        from api.server import _makeup_targets_shot

        self.assertTrue(_makeup_targets_shot(["1-6"], "6"))
        self.assertTrue(_makeup_targets_shot(["1-6", "1-8"], 8))
        self.assertFalse(_makeup_targets_shot(["1-6"], "5"))

    def test_character_reference_sync_uses_structured_shot_when_makeup_has_no_shot_ids(self):
        structure_response = self.client.patch(
            f"/api/books/{self.book_id}/storyboard/1/1/structure",
            json={
                "characterAssetIds": [str(self.makeup_id)],
                "characterBlocking": [
                    {
                        "characterId": str(self.makeup_id),
                        "visualAlias": "Ji You",
                        "screenPosition": "center",
                    }
                ],
            },
        )
        self.assertEqual(structure_response.status_code, 200)

        create_response = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "character",
                "assetId": str(self.makeup_id),
                "assetName": "Ji You",
                "imageUrl": "https://example.com/ji-you-structured.png",
                "referenceToken": "@ji-you-structured",
                "status": "selected",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertNotIn("sync_warning", created)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_refs = outputs["storyboard"][0]["asset_links"]["references"]["characters"]["Ji You"]
        self.assertEqual(len(storyboard_refs), 1)
        self.assertEqual(storyboard_refs[0]["metadata"]["referenceToken"], "@ji-you-structured")

    def test_character_reference_sync_falls_back_to_story_text_when_legacy_shot_has_no_structure(self):
        create_response = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "character",
                "assetId": str(self.makeup_id),
                "assetName": "Ji You",
                "imageUrl": "https://example.com/ji-you-legacy.png",
                "referenceToken": "@ji-you-legacy",
                "status": "selected",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        self.assertNotIn("sync_warning", created)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        storyboard_refs = outputs["storyboard"][0]["asset_links"]["references"]["characters"]["Ji You"]
        self.assertEqual(len(storyboard_refs), 1)
        self.assertEqual(storyboard_refs[0]["metadata"]["referenceToken"], "@ji-you-legacy")

    def test_patch_reference_asset_cleans_legacy_wrong_character_bucket(self):
        with Session() as session:
            makeup = session.query(VisualMakeup).filter(
                VisualMakeup.book_id == self.book_id,
                VisualMakeup.id == self.makeup_id,
            ).first()
            makeup.shot_ids = json.dumps(["1"])
            session.commit()

        created = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "character",
                "assetId": str(self.makeup_id),
                "assetName": "Ji You",
                "imageUrl": "https://example.com/ji-you.png",
                "referenceToken": "@ji-you",
                "status": "selected",
            },
        ).json()

        with Session() as session:
            shot = session.query(StoryboardShot).filter(
                StoryboardShot.book_id == self.book_id,
                StoryboardShot.episode == 1,
                StoryboardShot.shot_id == 1,
            ).first()
            asset_links = json.loads(shot.asset_links)
            asset_links["references"]["characters"] = {
                "???": [{
                    "id": "image-legacy-ref",
                    "kind": "image",
                    "title": "Unnamed Asset Ref v1",
                    "status": "done",
                    "adopted": True,
                    "sourceAssetId": str(self.makeup_id),
                    "metadata": {
                        "assetScope": "character",
                        "assetSubject": "Unnamed Asset",
                        "sourceAssetId": str(self.makeup_id),
                        "imageRole": "reference",
                    },
                    "previewUrl": "https://example.com/legacy-ref.png",
                    "uri": "https://example.com/legacy-ref.png",
                }],
            }
            shot.asset_links = json.dumps(asset_links, ensure_ascii=False)
            session.commit()

        patch_response = self.client.patch(
            f"/api/books/{self.book_id}/visual-reference-assets/{created['id']}",
            json={
                "assetName": "Ji You",
                "referenceToken": "@ji-you",
                "metaInfo": {"assetSubject": "Ji You"},
            },
        )
        self.assertEqual(patch_response.status_code, 200)

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        outputs = outputs_response.json()
        characters = outputs["storyboard"][0]["asset_links"]["references"]["characters"]
        self.assertNotIn("???", characters)
        self.assertIn("Ji You", characters)
        self.assertEqual(len(characters["Ji You"]), 1)
        self.assertEqual(characters["Ji You"][0]["id"], f"ref-{created['id']}")

    def test_patch_reference_asset_refreshes_mock_preview_title(self):
        created = self.client.post(
            f"/api/books/{self.book_id}/visual-reference-assets",
            json={
                "assetType": "character",
                "assetId": str(self.makeup_id),
                "assetName": "Unnamed Asset",
                "imageUrl": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22/%3E",
                "referenceToken": "@unnamed",
                "status": "selected",
                "model": "mock-image-v1",
                "metaInfo": {"usesMock": True, "version": "v1"},
            },
        ).json()

        patch_response = self.client.patch(
            f"/api/books/{self.book_id}/visual-reference-assets/{created['id']}",
            json={
                "assetName": "Ji You",
                "referenceToken": "@ji-you",
                "metaInfo": {"usesMock": True, "version": "v1", "assetSubject": "Ji You"},
            },
        )
        self.assertEqual(patch_response.status_code, 200)
        payload = patch_response.json()
        decoded = unquote(payload["image_url"])
        self.assertIn("Ji You 参考图 v1", decoded)
        self.assertNotIn("Unnamed Asset", decoded)

    def test_visual_assets_endpoint_normalizes_legacy_duplicate_selected_references(self):
        now = datetime.utcnow()
        with Session() as session:
            session.add_all([
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(self.location_id),
                    asset_name="Forest Camp",
                    image_url="https://example.com/forest-camp-old.png",
                    reference_token="@forest-camp-old",
                    status="selected",
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                ),
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(self.location_id),
                    asset_name="Forest Camp",
                    image_url="https://example.com/forest-camp-new.png",
                    reference_token="@forest-camp-new",
                    status="selected",
                    created_at=now,
                    updated_at=now,
                ),
            ])
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        references = payload["locations"][0]["references"]
        status_by_token = {item["reference_token"]: item["status"] for item in references}
        self.assertEqual(status_by_token["@forest-camp-old"], "candidate")
        self.assertEqual(status_by_token["@forest-camp-new"], "selected")
        self.assertEqual(payload["locations"][0]["selected_reference_count"], 1)
        self.assertEqual(payload["locations"][0]["primary_reference_token"], "@forest-camp-new")

        outputs_response = self.client.get(f"/api/pipeline/book/{self.book_id}/outputs")
        storyboard_refs = outputs_response.json()["storyboard"][0]["asset_links"]["references"]["scene"]
        self.assertEqual(len(storyboard_refs), 1)
        self.assertEqual(storyboard_refs[0]["metadata"]["referenceToken"], "@forest-camp-new")

    def test_visual_assets_endpoint_orders_locked_reference_first(self):
        now = datetime.utcnow()
        with Session() as session:
            session.add_all([
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(self.location_id),
                    asset_name="Forest Camp",
                    image_url="https://example.com/forest-camp-candidate.png",
                    reference_token="@forest-camp-candidate",
                    status="candidate",
                    created_at=now,
                    updated_at=now,
                ),
                VisualReferenceAsset(
                    book_id=self.book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(self.location_id),
                    asset_name="Forest Camp",
                    image_url="https://example.com/forest-camp-locked.png",
                    reference_token="@forest-camp-locked",
                    status="locked",
                    created_at=now - timedelta(minutes=10),
                    updated_at=now - timedelta(minutes=10),
                ),
            ])
            session.commit()

        response = self.client.get(f"/api/books/{self.book_id}/visual-assets")
        self.assertEqual(response.status_code, 200)
        location = response.json()["locations"][0]
        self.assertEqual(location["references"][0]["reference_token"], "@forest-camp-locked")
        self.assertEqual(location["reference_assets"][0]["reference_token"], "@forest-camp-locked")
        self.assertEqual(location["primary_reference_token"], "@forest-camp-locked")
        self.assertEqual(location["locked_reference_token"], "@forest-camp-locked")


if __name__ == "__main__":
    unittest.main()
