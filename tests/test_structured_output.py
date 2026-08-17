import unittest

from core.structured_output import parse_json_object


class StructuredOutputTests(unittest.TestCase):
    def test_parse_json_object_recovers_from_analysis_prefix(self):
        payload = parse_json_object(
            'analysis first\n{"issues":[{"type":"hook"}],"overall_score":7}',
            label="qa payload",
        )
        self.assertEqual(payload["overall_score"], 7)
        self.assertEqual(payload["issues"][0]["type"], "hook")

    def test_parse_json_object_recovers_from_trailing_text(self):
        payload = parse_json_object(
            '{"diagnosis":{"summary":"ok"},"rewritten_script":"x","change_summary":[]}\n\nignore this tail',
            label="rewrite payload",
        )
        self.assertEqual(payload["diagnosis"]["summary"], "ok")
        self.assertEqual(payload["rewritten_script"], "x")

    def test_parse_json_object_prefers_candidate_with_required_keys(self):
        payload = parse_json_object(
            '{"issues":[{"type":"hook"}],"errors":[],"overall_score":7}\n{"type":"inner","severity":"high"}',
            label="qa payload",
            required_keys={"issues", "errors"},
        )
        self.assertEqual(payload["issues"][0]["type"], "hook")


if __name__ == "__main__":
    unittest.main()
