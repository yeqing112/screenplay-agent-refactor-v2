import copy
import json
from pathlib import Path

import pytest

from core.storyboard_handoff import (
    HANDOFF_SCHEMA_VERSION,
    project_shot_design_to_storyboard_handoff,
    validate_storyboard_handoff,
)
from core.storyboard_materializer import materialize_storyboard_from_handoff


ART = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"


def _pilot():
    plans = json.loads((ART / "episode_01_shot_plan_phase_c.json").read_text(encoding="utf-8"))["plans"]
    blocking = json.loads((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf-8"))["scenes"]
    for plan, scene_blocking in zip(plans, blocking):
        plan = copy.deepcopy(plan)
        # The recorded artifact is a shot-plan-only export; the real Authority
        # row supplies scene_name separately.
        plan["scene_name"] = plan["scene_id"]
        yield plan, scene_blocking


def test_phase_c_handoff_schema_and_n_to_n_materialization():
    for plan, blocking in _pilot():
        handoff = project_shot_design_to_storyboard_handoff(plan, blocking=blocking)
        assert handoff["schema_version"] == HANDOFF_SCHEMA_VERSION
        assert validate_storyboard_handoff(handoff) == []
        materialized = materialize_storyboard_from_handoff(handoff)
        assert len(materialized) == len(plan["shots"]) == len(handoff["shots"])
        assert [x["plan_shot_id"] for x in handoff["shots"]] == [x["plan_shot_id"] for x in materialized]
        assert all(x["meta_info"]["handoff"]["projection_version"] for x in materialized)
        assert all("start_seconds" not in action and "end_seconds" not in action for shot in handoff["shots"] for action in shot["action_beats"])


def test_projection_ignores_legacy_camera_and_purpose_copies():
    plan, blocking = next(_pilot())
    first = project_shot_design_to_storyboard_handoff(plan, blocking=blocking)
    tampered = copy.deepcopy(plan)
    tampered["shots"][0]["camera"] = {"shot_size": "BAD", "angle": "BAD", "movement": "BAD", "speed": "BAD"}
    tampered["shots"][0]["purpose"] = "BAD"
    second = project_shot_design_to_storyboard_handoff(tampered, blocking=blocking)
    assert first["shots"][0]["camera"] == second["shots"][0]["camera"]
    assert first["shots"][0]["purpose"] == second["shots"][0]["purpose"]
    assert first["handoff_fingerprint"] == second["handoff_fingerprint"]


@pytest.mark.parametrize(
    ("field", "code"),
    [("shot_purpose", "STORYBOARD_HANDOFF_SHOT_PURPOSE_REQUIRED"),
     ("camera_state", "STORYBOARD_HANDOFF_CAMERA_STATE_REQUIRED"),
     ("duration_hint_seconds", "STORYBOARD_HANDOFF_DURATION_REQUIRED")],
)
def test_missing_canonical_source_fails_before_projection(field, code):
    plan, blocking = next(_pilot())
    plan["shots"][0].pop(field)
    with pytest.raises(ValueError, match=code):
        project_shot_design_to_storyboard_handoff(plan, blocking=blocking)


def test_invalid_blocking_state_fails_closed():
    plan, blocking = next(_pilot())
    plan["shots"][0]["spatial_binding"]["blocking_state_refs"] = ["MISSING_STATE"]
    with pytest.raises(ValueError, match="STORYBOARD_HANDOFF_STATE_BINDING_INVALID"):
        project_shot_design_to_storyboard_handoff(plan, blocking=blocking)


def test_projection_is_deterministic():
    plan, blocking = next(_pilot())
    first = project_shot_design_to_storyboard_handoff(plan, blocking=blocking)
    second = project_shot_design_to_storyboard_handoff(plan, blocking=blocking)
    assert first == second
