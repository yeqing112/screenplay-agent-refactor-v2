import unittest
from unittest.mock import patch

from core.public_asset_storage import ensure_provider_accessible_url


class PublicAssetStorageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
