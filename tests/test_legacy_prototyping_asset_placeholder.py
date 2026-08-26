import unittest

from fastapi.testclient import TestClient

from api.server import app


class LegacyPrototypingAssetPlaceholderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_missing_legacy_prototyping_asset_returns_svg_placeholder(self):
        response = self.client.get("/api/prototyping/assets/image-missing-legacy")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("content-type"), "image/svg+xml")
        self.assertEqual(response.headers.get("x-legacy-prototyping-asset"), "image-missing-legacy")
        self.assertIn("历史预览图不可用", response.text)
        self.assertIn("image-missing-legacy", response.text)


if __name__ == "__main__":
    unittest.main()
