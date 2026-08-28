import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core.public_asset_storage import ensure_provider_accessible_url
from models import KV, Session, init_db


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
        self.assertFalse(payload["migration_apply_supported"])
        self.assertIn("summary", payload)
        self.assertIn("external_unchecked", payload["summary"])
        self.assertLessEqual(payload["summary"]["total_scanned"], 5)

    def test_storage_migration_plan_skips_external_checks_by_default(self):
        with patch("api.server.check_public_url_accessible") as check:
            response = self.client.get("/api/public-asset-storage/migration-plan?limit=20")

        self.assertEqual(response.status_code, 200)
        check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
