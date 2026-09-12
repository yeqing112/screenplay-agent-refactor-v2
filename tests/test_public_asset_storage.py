import json
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import config
from api.server import _prepare_shapi_gemini_reference_images, app
from core.public_asset_storage import ensure_provider_accessible_url, _load_source_bytes
from models import KV, PublicAssetStorageMigrationRecord, Session, TaskRun, VisualReferenceAsset, init_db


class PublicAssetStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        with Session() as session:
            row = session.query(KV).filter(KV.key == "public_asset_storage_config").first()
            self._previous_storage_config = row.value if row else None
            session.query(KV).filter(KV.key == "public_asset_storage_config").delete()
            session.commit()

    def tearDown(self):
        with Session() as session:
            session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == 990501).delete()
            session.query(PublicAssetStorageMigrationRecord).filter(PublicAssetStorageMigrationRecord.task_id.like("storage-migration-%")).delete()
            session.query(KV).filter(KV.key == "public_asset_storage_config").delete()
            if self._previous_storage_config is not None:
                session.add(KV(key="public_asset_storage_config", value=self._previous_storage_config))
            session.commit()

    def test_disabled_storage_rejects_local_provider_url(self):
        with patch("core.public_asset_storage.config.PUBLIC_ASSET_STORAGE_PROVIDER", ""), patch(
            "core.public_asset_storage.config.QINIU_ACCESS_KEY", ""
        ):
            result = ensure_provider_accessible_url(
                "/api/prototyping/assets/image-local",
                key_hint="book-1-shot-1-first-frame",
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "public_asset_storage_not_configured")
        self.assertEqual(result.public_url, "")

    def test_public_accessible_url_is_reused_without_upload(self):
        with patch("core.public_asset_storage.check_public_url_accessible", return_value=(True, "")):
            result = ensure_provider_accessible_url(
                "https://cdn.example.com/frame.png",
                key_hint="book-1-shot-1-first-frame",
            )

        self.assertTrue(result.ok)
        self.assertFalse(result.uploaded)
        self.assertEqual(result.public_url, "https://cdn.example.com/frame.png")
        self.assertTrue(result.source_accessible)

    def test_svg_source_is_rasterized_to_png_before_upload(self):
        self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu",
                "localBaseUrl": "http://127.0.0.1:18765",
                "qiniuAccessKey": "ak-test",
                "qiniuSecretKey": "sk-test",
                "qiniuBucket": "ai-ku01",
                "qiniuRegion": "z2",
                "qiniuPublicBaseUrl": "https://assets.example.com",
                "qiniuBucketPrivate": True,
                "qiniuKeyPrefix": "screenplay-agent",
            },
        )
        svg = (
            "data:image/svg+xml,"
            "%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20width%3D%22640%22%20height%3D%22360%22%3E"
            "%3Crect%20width%3D%22640%22%20height%3D%22360%22%20fill%3D%22%23000%22/%3E%3C/svg%3E"
        )
        with patch("core.public_asset_storage.check_public_url_accessible", return_value=(True, "")), patch(
            "core.public_asset_storage._upload_bytes_to_qiniu",
            return_value=("https://assets.example.com/screenplay-agent/test.png", "screenplay-agent/test.png", True),
        ) as upload:
            result = ensure_provider_accessible_url(svg, key_hint="svg-first-frame")

        self.assertTrue(result.ok)
        _, kwargs = upload.call_args
        self.assertEqual(kwargs["content_type"], "image/png")
        self.assertTrue(upload.call_args.args[0].startswith(b"\x89PNG\r\n\x1a\n"))

    def test_qiniu_upload_success_downgrades_transient_public_check_timeout(self):
        self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu",
                "localBaseUrl": "http://127.0.0.1:18765",
                "qiniuAccessKey": "ak-test",
                "qiniuSecretKey": "sk-test",
                "qiniuBucket": "ai-ku01",
                "qiniuRegion": "z2",
                "qiniuPublicBaseUrl": "https://assets.example.com",
                "qiniuBucketPrivate": True,
                "qiniuKeyPrefix": "screenplay-agent",
            },
        )
        with patch("core.public_asset_storage._upload_bytes_to_qiniu") as upload, patch(
            "core.public_asset_storage.check_public_url_accessible",
            return_value=(False, "timed out"),
        ):
            upload.return_value = (
                "https://assets.example.com/screenplay-agent/test.png?e=1&token=mock",
                "screenplay-agent/test.png",
                True,
            )
            result = ensure_provider_accessible_url(
                "data:image/png;base64,iVBORw0KGgo=",
                key_hint="qiniu-transient-timeout",
            )

        self.assertTrue(result.ok)
        self.assertTrue(result.uploaded)
        self.assertTrue(result.signed)
        self.assertFalse(result.source_accessible)
        self.assertEqual(result.error, "timed out")

    def test_force_storage_rejects_temporary_http_domain_before_upload(self):
        self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu",
                "qiniuAccessKey": "ak-test",
                "qiniuSecretKey": "sk-test",
                "qiniuBucket": "ai-ku01",
                "qiniuRegion": "z2",
                "qiniuPublicBaseUrl": "http://temporary.hn-bkt.clouddn.com",
                "qiniuBucketPrivate": True,
            },
        )
        with patch("core.public_asset_storage._upload_bytes_to_qiniu") as upload:
            result = ensure_provider_accessible_url(
                "data:image/png;base64,iVBORw0KGgo=",
                key_hint="production-reference",
                force_storage=True,
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "public_asset_storage_requires_custom_https_domain")
        upload.assert_not_called()

    def test_manual_media_relative_url_reads_local_file_without_http_callback(self):
        media_dir = Path(config.UPLOAD_DIR) / "manual-media"
        media_dir.mkdir(parents=True, exist_ok=True)
        path = media_dir / "unit-manual-media-direct-read.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\nunit-test")
        try:
            with patch("core.public_asset_storage._download_bytes") as download:
                data, content_type = _load_source_bytes(
                    "/api/prototyping/manual-media/unit-manual-media-direct-read.png",
                    local_base_url="http://127.0.0.1:18765",
                )
        finally:
            path.unlink(missing_ok=True)

        download.assert_not_called()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(content_type, "image/png")

    def test_shapi_gemini_prepares_bound_manual_reference_as_data_uri(self):
        media_dir = Path(config.UPLOAD_DIR) / "manual-media"
        media_dir.mkdir(parents=True, exist_ok=True)
        path = media_dir / "unit-nano-reference.png"
        raw = b"\x89PNG\r\n\x1a\nunit-nano-reference"
        path.write_bytes(raw)
        try:
            prepared = _prepare_shapi_gemini_reference_images(
                {
                    "provider": "shapi-gemini-image",
                    "default_params": {
                        "max_reference_images": 14,
                        "max_reference_image_bytes": 1024 * 1024,
                    },
                },
                [
                    {
                        "reference_asset_id": "ref-asset-1",
                        "image_url": "/api/prototyping/manual-media/unit-nano-reference.png",
                    }
                ],
            )
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(len(prepared), 1)
        self.assertTrue(prepared[0]["image_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("imageUrl", prepared[0])

    def test_storage_config_api_masks_secrets_and_preserves_existing_secret_on_blank_update(self):
        save_response = self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu",
                "localBaseUrl": "http://127.0.0.1:18765",
                "qiniuAccessKey": "ak-test",
                "qiniuSecretKey": "sk-test",
                "qiniuBucket": "ai-ku01",
                "qiniuRegion": "z2",
                "qiniuPublicBaseUrl": "http://tkgj4ur0t.hn-bkt.clouddn.com",
                "qiniuBucketPrivate": True,
                "qiniuKeyPrefix": "screenplay-agent",
            },
        )
        self.assertEqual(save_response.status_code, 200)
        payload = save_response.json()
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["qiniu_access_key_configured"])
        self.assertTrue(payload["qiniu_secret_key_configured"])
        self.assertNotIn("ak-test", str(payload))
        self.assertNotIn("sk-test", str(payload))

        update_response = self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu",
                "localBaseUrl": "http://127.0.0.1:18765",
                "qiniuAccessKey": "",
                "qiniuSecretKey": "",
                "qiniuBucket": "ai-ku02",
                "qiniuRegion": "z2",
                "qiniuPublicBaseUrl": "https://assets.example.com",
                "qiniuBucketPrivate": True,
                "qiniuKeyPrefix": "screenplay-agent-v2",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertTrue(updated["enabled"])
        self.assertEqual(updated["qiniu_bucket"], "ai-ku02")
        self.assertTrue(updated["qiniu_access_key_configured"])
        self.assertTrue(updated["qiniu_secret_key_configured"])

    def test_storage_migration_plan_is_read_only(self):
        response = self.client.get("/api/public-asset-storage/migration-plan?limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "readonly-storage-migration-plan")
        self.assertFalse(payload["real_data_mutated"])
        self.assertEqual(payload["confirmation_token"], payload["plan_fingerprint"])
        self.assertEqual(len(payload["confirmation_token"]), 16)
        self.assertFalse(payload["migration_apply_supported"])
        self.assertIn("summary", payload)
        self.assertIn("external_unchecked", payload["summary"])
        self.assertLessEqual(payload["summary"]["total_scanned"], 5)

    def test_storage_migration_plan_skips_external_checks_by_default(self):
        with patch("api.server.check_public_url_accessible") as check:
            response = self.client.get("/api/public-asset-storage/migration-plan?limit=20")

        self.assertEqual(response.status_code, 200)
        check.assert_not_called()

    def test_storage_migration_writer_requires_custom_https_domain(self):
        self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu", "qiniuAccessKey": "ak-test", "qiniuSecretKey": "sk-test",
                "qiniuBucket": "ai-ku01", "qiniuRegion": "z2",
                "qiniuPublicBaseUrl": "http://temporary.hn-bkt.clouddn.com", "qiniuBucketPrivate": True,
            },
        )
        plan = self.client.get("/api/public-asset-storage/migration-plan?limit=1").json()
        self.assertFalse(plan["migration_apply_supported"])
        blocked = self.client.post(
            "/api/public-asset-storage/migration-plan/execute",
            json={
                "confirmationToken": plan["confirmation_token"], "limit": 1, "executeWrite": True,
                "confirmed": True, "allowWrite": True,
                "executionConfirmationToken": "CONFIRM_PUBLIC_ASSET_STORAGE_MIGRATION",
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"], "storage_migration_requires_custom_https_storage_domain")

    def test_storage_migration_execute_requires_current_plan_token_and_stays_dry_run(self):
        plan = self.client.get("/api/public-asset-storage/migration-plan?limit=5").json()
        stale = self.client.post("/api/public-asset-storage/migration-plan/execute", json={"confirmationToken": "stale"})
        self.assertEqual(stale.status_code, 409)
        response = self.client.post(
            "/api/public-asset-storage/migration-plan/execute",
            json={"confirmationToken": plan["confirmation_token"], "limit": 5, "confirmed": True, "allowWrite": True},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "storage-migration-dry-run")
        self.assertFalse(payload["real_data_mutated"])
        self.assertTrue(payload["write_requested"])
        self.assertFalse(payload["write_supported"])
        self.assertFalse(payload["old_objects_deleted"])
        self.assertTrue(payload["task_id"].startswith("storage-migration-dryrun-"))
        with Session() as session:
            task = session.query(TaskRun).filter(TaskRun.task_id == payload["task_id"]).first()
            self.assertIsNotNone(task)
            self.assertEqual(task.task_kind, "public-asset-storage-migration")
            self.assertEqual(task.status, "dry_run")

    def test_confirmed_storage_migration_publishes_and_rewrites_one_planned_reference_without_deleting_old_data(self):
        with Session() as session:
            reference = VisualReferenceAsset(
                book_id=990501, episode=1, asset_type="character", asset_id="hero", asset_name="Hero",
                image_url="data:image/png;base64,aGVsbG8=", local_path="C:/durable/hero.png", status="selected",
            )
            session.add(reference)
            session.commit()
            reference_id = reference.id
        self.client.put(
            "/api/public-asset-storage/config",
            json={
                "provider": "qiniu", "qiniuAccessKey": "ak-test", "qiniuSecretKey": "sk-test",
                "qiniuBucket": "ai-ku01", "qiniuRegion": "z2", "qiniuPublicBaseUrl": "https://assets.example.com",
                "qiniuBucketPrivate": True, "qiniuKeyPrefix": "screenplay-agent",
            },
        )
        item = {
            "source": "visual_reference.image_url", "owner": {"book_id": 990501, "reference_id": reference_id},
            "url": "data:image/png;base64,aGVsbG8=",
            "locator": {"kind": "visual_reference", "reference_id": reference_id, "field": "image_url", "source_field": "image_url"},
        }
        published = SimpleNamespace(ok=True, public_url="https://assets.example.com/screenplay-agent/hero.png?e=1&token=temporary", object_key="screenplay-agent/hero.png", bytes_count=5)
        with patch("api.server._collect_storage_migration_assets", return_value=[item]), patch("api.server.ensure_provider_accessible_url", return_value=published) as publish:
            plan = self.client.get("/api/public-asset-storage/migration-plan?limit=1").json()
            self.assertTrue(plan["migration_apply_supported"])
            response = self.client.post(
                "/api/public-asset-storage/migration-plan/execute",
                json={
                    "confirmationToken": plan["confirmation_token"], "limit": 1, "executeWrite": True,
                    "confirmed": True, "allowWrite": True,
                    "executionConfirmationToken": "CONFIRM_PUBLIC_ASSET_STORAGE_MIGRATION",
                },
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "storage-migration-submitted")
        publish.assert_called_once_with(item["url"], key_hint=publish.call_args.kwargs["key_hint"], force_storage=True)
        with Session() as session:
            migrated = session.query(VisualReferenceAsset).filter_by(id=reference_id).first()
            record = session.query(PublicAssetStorageMigrationRecord).filter_by(id=payload["record_id"]).first()
            self.assertEqual(migrated.image_url, published.public_url)
            self.assertEqual(migrated.local_path, "C:/durable/hero.png")
            self.assertEqual(record.status, "completed")
            self.assertFalse(record.old_objects_deleted)
            self.assertEqual(json.loads(record.result)["migrated"], 1)


if __name__ == "__main__":
    unittest.main()
