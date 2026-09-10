import unittest

from core.director_tool_registry import list_tools, resolve_tool


class DirectorToolRegistryTests(unittest.TestCase):
    def test_d_actions_require_confirmation_and_external_cost(self):
        tool = resolve_tool("video_generation")
        self.assertEqual(tool["tier"], "D")
        self.assertTrue(tool["requires_confirmation"])
        self.assertTrue(tool["external_cost"])

    def test_c_action_requires_confirmation_without_external_cost(self):
        tool = resolve_tool("write_prompt_version")
        self.assertEqual(tool["tier"], "C")
        self.assertTrue(tool["requires_confirmation"])
        self.assertFalse(tool["external_cost"])

    def test_unknown_operation_defaults_to_blocked_d(self):
        tool = resolve_tool("untrusted_execution")
        self.assertEqual(tool["tier"], "D")
        self.assertEqual(tool["execution"], "blocked")

    def test_registry_has_unique_operations(self):
        tools = list_tools()
        self.assertEqual(len(tools), len({tool["operation"] for tool in tools}))
