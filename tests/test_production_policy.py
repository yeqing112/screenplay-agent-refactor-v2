import unittest

from fastapi.testclient import TestClient

from core.production_policy import (
    evaluate_production_boundary,
    normalize_artifact_states,
    resolve_workflow_profile,
)
from api.server import StoryboardRequest, app


class ProductionPolicyTests(unittest.TestCase):
    def test_creative_draft_is_always_blocked(self):
        result = evaluate_production_boundary(
            "creative_draft",
            script_ir_qualified=True,
            director_treatment_approved=True,
            scene_blocking_approved=True,
            shot_plan_approved=True,
            compiler_phase_a_pass=True,
            executability_pass=True,
            required_assets_ready=True,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["production_status"], "blocked")
        self.assertEqual(result["blocking_reasons"][0]["code"], "CREATIVE_DRAFT_BOUNDARY")

    def test_production_reports_actionable_missing_gates(self):
        result = evaluate_production_boundary("production", shot_plan_approved=True)
        self.assertFalse(result["allowed"])
        codes = {item["code"] for item in result["blocking_reasons"]}
        self.assertIn("SCRIPT_IR_NOT_QUALIFIED", codes)
        self.assertIn("REQUIRED_ASSETS_NOT_READY", codes)

    def test_production_passes_only_when_all_gates_are_true(self):
        result = evaluate_production_boundary(
            "production",
            script_ir_qualified=True,
            director_treatment_approved=True,
            scene_blocking_approved=True,
            shot_plan_approved=True,
            compiler_phase_a_pass=True,
            executability_pass=True,
            required_assets_ready=True,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["production_status"], "ready")

    def test_state_normalization_keeps_creative_draft_blocked(self):
        state = normalize_artifact_states(
            execution_status="succeeded",
            quality_status="qualified",
            production_status="ready",
            workflow_profile="creative_draft",
        )
        self.assertEqual(state["production_status"], "blocked")

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_workflow_profile("bypass")

    def test_storyboard_production_profile_cannot_be_weakened_by_request_flags(self):
        self.assertEqual(StoryboardRequest(book_id=1).workflow_profile, "creative_draft")
        response = TestClient(app).post(
            "/api/pipeline/storyboard",
            json={"book_id": 1, "workflow_profile": "production", "require_shot_plan": False},
        )
        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "PRODUCTION_BOUNDARY_BLOCKED")
        self.assertFalse(detail["allowed"])


if __name__ == "__main__":
    unittest.main()
