import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api import server
from api.server import app


class ApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check_returns_service_status(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "screenplay-devcanvas-api")

    def test_cors_allows_configured_local_frontend(self):
        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://127.0.0.1:5173")

    def test_cors_rejects_unconfigured_origin(self):
        response = self.client.options(
            "/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "https://evil.example")

    def test_legacy_node_api_can_be_disabled_without_affecting_formal_health_api(self):
        original_value = server.config.ENABLE_LEGACY_NODE_API
        try:
            server.config.ENABLE_LEGACY_NODE_API = False
            response = self.client.get("/api/nodes/registry")
            self.assertEqual(response.status_code, 410)
            self.assertIn("Legacy node API is disabled", response.json()["detail"])
            self.assertEqual(self.client.get("/health").status_code, 200)
        finally:
            server.config.ENABLE_LEGACY_NODE_API = original_value

    def test_upload_sanitizes_filename_and_stays_inside_upload_dir(self):
        original_dir = server.config.UPLOAD_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                server.config.UPLOAD_DIR = Path(tmpdir)
                response = self.client.post(
                    "/api/upload",
                    files={"file": ("../../evil.txt", b"hello", "text/plain")},
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                saved_path = Path(payload["filepath"]).resolve()
                self.assertEqual(saved_path.parent, Path(tmpdir).resolve())
                self.assertEqual(payload["filename"], "evil.txt")
                self.assertEqual(saved_path.read_bytes(), b"hello")
        finally:
            server.config.UPLOAD_DIR = original_dir

    def test_upload_rejects_unsupported_extension(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("payload.exe", b"not allowed", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported upload file type", response.json()["detail"])

    def test_upload_rejects_files_over_size_limit(self):
        original_limit = server.config.UPLOAD_MAX_BYTES
        try:
            server.config.UPLOAD_MAX_BYTES = 4
            response = self.client.post(
                "/api/upload",
                files={"file": ("too-large.txt", b"12345", "text/plain")},
            )

            self.assertEqual(response.status_code, 413)
            self.assertIn("too large", response.json()["detail"])
        finally:
            server.config.UPLOAD_MAX_BYTES = original_limit


if __name__ == "__main__":
    unittest.main()
