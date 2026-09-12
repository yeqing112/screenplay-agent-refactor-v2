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

    def test_api_token_guard_is_disabled_by_default(self):
        original_enabled = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        try:
            server.config.API_AUTH_ENABLED = False
            server.config.API_AUTH_TOKEN = ""
            response = self.client.get("/api/production-skills")
            self.assertEqual(response.status_code, 200)
        finally:
            server.config.API_AUTH_ENABLED = original_enabled
            server.config.API_AUTH_TOKEN = original_token

    def test_api_token_guard_protects_api_and_keeps_health_and_preflight_public(self):
        original_enabled = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        original_exempt = server.config.API_AUTH_EXEMPT_PATHS
        token = "t" * 40
        try:
            server.config.API_AUTH_ENABLED = True
            server.config.API_AUTH_TOKEN = token
            server.config.API_AUTH_EXEMPT_PATHS = ["/health"]

            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.get("/api/production-skills").status_code, 401)
            self.assertEqual(self.client.get("/api/production-skills", headers={"Authorization": f"Bearer {token}"}).status_code, 200)
            self.assertEqual(self.client.get("/api/production-skills", headers={"X-API-Key": token}).status_code, 200)
            self.assertEqual(self.client.get("/api/production-skills", cookies={"screenplay_api_token": token}).status_code, 200)
            self.assertEqual(self.client.options("/api/production-skills", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"}).status_code, 200)
        finally:
            server.config.API_AUTH_ENABLED = original_enabled
            server.config.API_AUTH_TOKEN = original_token
            server.config.API_AUTH_EXEMPT_PATHS = original_exempt

    def test_api_token_guard_fails_closed_when_enabled_without_strong_token(self):
        original_enabled = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        try:
            server.config.API_AUTH_ENABLED = True
            server.config.API_AUTH_TOKEN = "short"
            response = self.client.get("/api/production-skills")
            self.assertEqual(response.status_code, 503)
        finally:
            server.config.API_AUTH_ENABLED = original_enabled
            server.config.API_AUTH_TOKEN = original_token

    def test_api_role_tokens_enforce_read_and_write_methods(self):
        original_enabled = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        original_roles = server.config.API_AUTH_ROLE_TOKENS
        original_roles_error = server.config.API_AUTH_ROLE_TOKENS_ERROR
        viewer = "v" * 40
        editor = "e" * 40
        try:
            server.config.API_AUTH_ENABLED = True
            server.config.API_AUTH_TOKEN = ""
            server.config.API_AUTH_ROLE_TOKENS = {"viewer": viewer, "editor": editor}
            server.config.API_AUTH_ROLE_TOKENS_ERROR = False
            self.assertEqual(self.client.get("/api/production-skills", headers={"X-API-Key": viewer}).status_code, 200)
            self.assertEqual(self.client.post("/api/production-skills", headers={"X-API-Key": viewer}).status_code, 403)
            self.assertNotEqual(self.client.post("/api/production-skills", headers={"X-API-Key": editor}).status_code, 403)
        finally:
            server.config.API_AUTH_ENABLED = original_enabled
            server.config.API_AUTH_TOKEN = original_token
            server.config.API_AUTH_ROLE_TOKENS = original_roles
            server.config.API_AUTH_ROLE_TOKENS_ERROR = original_roles_error

    def test_api_role_configuration_fails_closed_when_role_is_unknown_or_weak(self):
        original_enabled = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        original_roles = server.config.API_AUTH_ROLE_TOKENS
        original_roles_error = server.config.API_AUTH_ROLE_TOKENS_ERROR
        try:
            server.config.API_AUTH_ENABLED = True
            server.config.API_AUTH_TOKEN = ""
            server.config.API_AUTH_ROLE_TOKENS = {"operator": "x" * 40}
            server.config.API_AUTH_ROLE_TOKENS_ERROR = False
            response = self.client.get("/api/production-skills", headers={"X-API-Key": "x" * 40})
            self.assertEqual(response.status_code, 503)
        finally:
            server.config.API_AUTH_ENABLED = original_enabled
            server.config.API_AUTH_TOKEN = original_token
            server.config.API_AUTH_ROLE_TOKENS = original_roles
            server.config.API_AUTH_ROLE_TOKENS_ERROR = original_roles_error

    def test_api_rate_limit_is_opt_in_and_returns_retry_metadata(self):
        original_enabled = server.config.API_RATE_LIMIT_ENABLED
        original_requests = server.config.API_RATE_LIMIT_REQUESTS
        original_window = server.config.API_RATE_LIMIT_WINDOW_SECONDS
        original_max = server.config.API_RATE_LIMIT_MAX_IDENTITIES
        original_auth = server.config.API_AUTH_ENABLED
        original_token = server.config.API_AUTH_TOKEN
        token = "r" * 40
        try:
            server.config.API_RATE_LIMIT_ENABLED = True
            server.config.API_RATE_LIMIT_REQUESTS = 1
            server.config.API_RATE_LIMIT_WINDOW_SECONDS = 60
            server.config.API_RATE_LIMIT_MAX_IDENTITIES = 100
            server.config.API_AUTH_ENABLED = True
            server.config.API_AUTH_TOKEN = token
            server._reset_api_rate_limit_state()

            first = self.client.get("/api/production-skills", headers={"Authorization": f"Bearer {token}"})
            second = self.client.get("/api/production-skills", headers={"Authorization": f"Bearer {token}"})

            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.headers.get("x-ratelimit-limit"), "1")
            self.assertEqual(first.headers.get("x-ratelimit-remaining"), "0")
            self.assertEqual(second.status_code, 429)
            self.assertEqual(second.headers.get("retry-after"), "60")
            self.assertEqual(second.headers.get("x-ratelimit-remaining"), "0")
        finally:
            server._reset_api_rate_limit_state()
            server.config.API_RATE_LIMIT_ENABLED = original_enabled
            server.config.API_RATE_LIMIT_REQUESTS = original_requests
            server.config.API_RATE_LIMIT_WINDOW_SECONDS = original_window
            server.config.API_RATE_LIMIT_MAX_IDENTITIES = original_max
            server.config.API_AUTH_ENABLED = original_auth
            server.config.API_AUTH_TOKEN = original_token

    def test_api_rate_limit_does_not_count_health_or_cors_preflight(self):
        original_enabled = server.config.API_RATE_LIMIT_ENABLED
        original_requests = server.config.API_RATE_LIMIT_REQUESTS
        try:
            server.config.API_RATE_LIMIT_ENABLED = True
            server.config.API_RATE_LIMIT_REQUESTS = 1
            server._reset_api_rate_limit_state()
            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.get("/health").status_code, 200)
            preflight = self.client.options(
                "/api/production-skills",
                headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"},
            )
            self.assertEqual(preflight.status_code, 200)
        finally:
            server._reset_api_rate_limit_state()
            server.config.API_RATE_LIMIT_ENABLED = original_enabled
            server.config.API_RATE_LIMIT_REQUESTS = original_requests

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
