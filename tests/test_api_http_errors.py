import unittest

from fastapi.testclient import TestClient

from api.server import _derive_issue_source_excerpt, app


class ApiHttpErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def assert_http_error(self, method: str, path: str, status_code: int):
        response = self.client.request(method, path)
        self.assertEqual(response.status_code, status_code)
        payload = response.json()
        self.assertIsInstance(payload, dict)
        self.assertIn("detail", payload)
        self.assertNotIsInstance(payload, list)

    def test_missing_workflow_uses_http_exception(self):
        self.assert_http_error("GET", "/api/workflows/__missing_workflow__", 404)

    def test_missing_prompt_uses_http_exception(self):
        self.assert_http_error("GET", "/api/prompts/__missing_prompt__", 404)

    def test_missing_pipeline_task_uses_http_exception(self):
        self.assert_http_error("GET", "/api/pipeline/task/__missing_task__", 404)

    def test_missing_creative_task_uses_http_exception(self):
        self.assert_http_error("GET", "/api/prototyping/tasks/__missing_task__", 404)

    def test_missing_book_update_uses_http_exception(self):
        response = self.client.patch("/api/books/99999999", json={"title": "不会存在"})
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertIsInstance(payload, dict)
        self.assertIn("detail", payload)
        self.assertNotIsInstance(payload, list)

    def test_qa_excerpt_keyword_extraction_accepts_chinese_text(self):
        content = "\n".join(
            [
                "**Scene 1:[便利店-夜]**",
                "林夏握着染血账册，盯着监控屏。",
                "店员忽然沉默，门外传来警笛。",
            ]
        )
        excerpt = _derive_issue_source_excerpt(
            content,
            script_section="账册线索",
            title="染血账册缺少交代",
            description="需要补足染血账册的来源和用途。",
        )

        self.assertIn("染血账册", excerpt)


if __name__ == "__main__":
    unittest.main()
