"""Production API boundary tests for the Phase C readiness gate."""

import inspect
import json
from pathlib import Path

from core.storyboard_handoff import HANDOFF_SCHEMA_VERSION, project_shot_design_to_storyboard_handoff
from core.storyboard_materializer import materialize_storyboard_from_handoff
import api.storyboard_materializer_api as materializer_api


ART = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"


def test_production_api_has_explicit_phase_c_gate_and_no_legacy_fallback():
    source = inspect.getsource(materializer_api.materialize_storyboard)
    assert "SHOT_PLAN_PHASE_C_NOT_READY" in source
    assert "materialize_storyboard_from_handoff" in source
    assert "materialize_storyboard_from_shot_plan" not in source
    assert "legacy_storyboard_compatibility" not in source


def test_current_phase_c_artifact_still_materializes_through_handoff_schema():
    plans = json.loads((ART / "episode_01_shot_plan_phase_c.json").read_text(encoding="utf-8"))["plans"]
    blocking = json.loads((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf-8"))["scenes"]
    for plan, scene_blocking in zip(plans, blocking):
        source = dict(plan)
        source["scene_name"] = source["scene_id"]
        handoff = project_shot_design_to_storyboard_handoff(source, blocking=scene_blocking, require_phase_c=True)
        materialized = materialize_storyboard_from_handoff(handoff, production=True)
        assert handoff["schema_version"] == HANDOFF_SCHEMA_VERSION
        assert len(materialized) == len(source["shots"])
        assert [item["plan_shot_id"] for item in materialized] == [item["plan_shot_id"] for item in source["shots"]]
