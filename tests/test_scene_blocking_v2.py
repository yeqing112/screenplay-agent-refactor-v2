import json
import unittest

from core.scene_blocking import (
    CREATIVE_CHOICE,
    DERIVED_CONSTRAINT,
    SOURCE_FACT,
    build_scene_blocking_v2,
    extract_spatial_evidence,
    plan_director_spatial,
    repair_scene_blocking,
    validate_scene_blocking,
)


class SceneBlockingV2Tests(unittest.TestCase):
    def _inputs(self, blocking=None, canonical=None):
        return {
            "scene": {"name": "门厅", **({"character_blocking": blocking} if blocking is not None else {})},
            "treatment": {"scene_name": "门厅", "character_intents": {"c1": {"name": "林默"}, "c2": {"name": "苏晴"}}, "beat_map": [{"beat_id": "B01", "event": "两人对视"}]},
            "canonical": canonical,
        }

    def test_silent_screen_side_becomes_creative_choice(self):
        inputs = self._inputs()
        result = build_scene_blocking_v2(scene=inputs["scene"], treatment=inputs["treatment"])
        self.assertEqual(result["schema_version"], "scene_blocking_v2")
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["unknowns"], [])
        self.assertTrue(any(item["authority"] == CREATIVE_CHOICE for item in result["creative_decisions"]))
        self.assertEqual(result["participants"][0]["screen_side"]["authority"], DERIVED_CONSTRAINT)

    def test_explicit_position_is_source_fact_and_cannot_be_overridden(self):
        inputs = self._inputs([{"character": "林默", "position": "门口"}, {"character": "苏晴", "anchor": "沙发"}])
        result = build_scene_blocking_v2(scene=inputs["scene"], treatment=inputs["treatment"], scene_canonical={"anchors": ["门口", "沙发"]})
        facts = {(item["subject_id"], item["predicate"]): item for item in result["source_spatial_facts"]}
        self.assertEqual(facts[("c1", "position")]["authority"], SOURCE_FACT)
        self.assertEqual(result["participants"][0]["start_position"]["authority"], SOURCE_FACT)
        candidate = dict(result)
        candidate["participants"] = [dict(item) for item in result["participants"]]
        candidate["participants"][0]["start_position"] = {"value": "沙发", "authority": CREATIVE_CHOICE}
        self.assertEqual(validate_scene_blocking(candidate)["status"], "blocked")

    def test_conflicting_source_facts_fail_closed(self):
        inputs = self._inputs([{"character": "林默", "position": "门口"}], canonical=None)
        inputs["scene"]["spatial_facts"] = [{"subject_id": "c1", "predicate": "position", "value": "窗边"}]
        result = build_scene_blocking_v2(scene=inputs["scene"], treatment=inputs["treatment"])
        self.assertEqual(result["status"], "needs_information")
        self.assertIn("FACT_SPATIAL_CONFLICT", [item["code"] for item in result["validation"]["errors"]])

    def test_invalid_eyeline_can_be_repaired_without_touching_source_facts(self):
        inputs = self._inputs()
        evidence = extract_spatial_evidence(scene=inputs["scene"], treatment=inputs["treatment"])
        planned = plan_director_spatial(evidence=evidence, treatment=inputs["treatment"])
        planned["participants"][0]["eyeline_target"] = {"value": "missing_character", "authority": CREATIVE_CHOICE}
        candidate = {**planned, "source_spatial_facts": evidence["source_spatial_facts"], "space": evidence["space"]}
        self.assertEqual(validate_scene_blocking(candidate)["status"], "blocked")
        repaired = repair_scene_blocking(candidate)
        self.assertEqual(repaired["status"], "qualified")
        self.assertEqual(repaired["candidate"]["participants"][0]["eyeline_target"]["value"], "scene_action")

    def test_missing_geometry_does_not_block_director_choices(self):
        inputs = self._inputs()
        result = build_scene_blocking_v2(scene=inputs["scene"], treatment=inputs["treatment"])
        self.assertEqual(result["space"]["anchors"], [])
        self.assertEqual(result["status"], "ready_for_review")

    def test_required_missing_anchor_remains_a_production_blocker(self):
        inputs = self._inputs()
        inputs["scene"]["required_anchors"] = ["second_door"]
        result = build_scene_blocking_v2(scene=inputs["scene"], treatment=inputs["treatment"])
        self.assertEqual(result["status"], "needs_information")
        self.assertIn("MISSING_SCENE_ANCHOR", [item["code"] for item in result["validation"]["errors"]])

    def test_axis_violation_is_a_blocker_and_can_be_locally_repaired(self):
        inputs = self._inputs()
        result = build_scene_blocking_v2(scene=inputs["scene"], treatment=inputs["treatment"])
        result["camera_axis"]["axis_violation"] = True
        self.assertEqual(validate_scene_blocking(result)["status"], "blocked")
        repaired = repair_scene_blocking(result)
        self.assertEqual(repaired["status"], "qualified")


if __name__ == "__main__":
    unittest.main()
