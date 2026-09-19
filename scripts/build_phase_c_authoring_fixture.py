"""Build the recorded HUMAN_INPUT Phase C ShotDesign fixture.

This is intentionally an authoring fixture, not a creative builder.  The
groupings, framing, movement and information visibility below are reviewed
decisions; the requirements compiler is only used to bind and validate them.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.phase_c_shot_plan import build_shot_requirements

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"

GROUPS = {
    "E01_SC001": [
        (["SC01-B01", "SC01-B02"], "ESTABLISH_SPACE", "WIDE", "NONE", "AUDIENCE_ONLY"),
        (["SC01-B03"], "REVEAL_INFORMATION", "WIDE", "REFRAME", "CHARACTER_AND_AUDIENCE"),
        (["SC01-B04"], "CONFIRM_EVIDENCE", "INSERT", "NONE", "CHARACTER_AND_AUDIENCE"),
        (["SC01-B05", "SC01-B06"], "INTRODUCE_INFORMATION", "TWO_SHOT", "NONE", "CHARACTER_AND_AUDIENCE"),
        (["SC01-B07", "SC01-B08"], "SHIFT_POWER", "MEDIUM_WIDE", "TRACK", "CHARACTER_AND_AUDIENCE"),
        (["SC01-B09", "SC01-B10"], "SHOW_PROP_STATE", "INSERT", "NONE", "AUDIENCE_ONLY"),
        (["SC01-B11", "SC01-B12"], "REDIRECT_ATTENTION", "MEDIUM", "PAN", "CHARACTER_AND_AUDIENCE"),
        (["SC01-B13"], "SCENE_EXIT", "MEDIUM_CLOSE", "DOLLY_IN", "AUDIENCE_ONLY"),
    ],
    "E01_SC002": [
        (["SC02-B01", "SC02-B02"], "ESTABLISH_RELATIONSHIP", "WIDE", "NONE", "AUDIENCE_ONLY"),
        (["SC02-B03"], "INTRODUCE_INFORMATION", "OVER_SHOULDER", "NONE", "CHARACTER_AND_AUDIENCE"),
        (["SC02-B04", "SC02-B05"], "CAPTURE_REACTION", "MEDIUM_CLOSE", "REFRAME", "AUDIENCE_OBSERVES_CHARACTER_DOUBT"),
        (["SC02-B06"], "CONFIRM_EVIDENCE", "INSERT", "NONE", "AUDIENCE_ONLY"),
        (["SC02-B07"], "ESCALATE_THREAT", "CLOSE", "DOLLY_IN", "CHARACTER_AND_AUDIENCE"),
        (["SC02-B08", "SC02-B09"], "SCENE_EXIT", "TWO_SHOT", "ARC", "AUDIENCE_ONLY"),
    ],
}

def _state(blocking: dict, beat_id: str) -> dict:
    for state in blocking.get("beat_spatial_states", []):
        if isinstance(state, dict) and str(state.get("beat_ref")) == beat_id:
            chars = state.get("characters") if isinstance(state.get("characters"), dict) else {}
            return {"state_ref": beat_id, "subject_zones": {str(k): (v.get("zone") if isinstance(v, dict) else v) for k, v in chars.items()}}
    return {"state_ref": beat_id, "subject_zones": {}}

def build_scene(treatment: dict, blocking: dict) -> dict:
    req = build_shot_requirements(treatment=treatment, blocking=blocking, script_authority={"source": "current_phase_b_authority"})
    by_beat = {str(r["beat_refs"][0]): r for r in req["requirements"]}
    beat_map = {str(b["beat_id"]): b for b in treatment.get("beat_map", [])}
    shots = []
    for index, (beats, purpose, framing, movement, visibility) in enumerate(GROUPS[str(treatment["scene_id"])], 1):
        bound = [by_beat[beat] for beat in beats]
        subjects = sorted({s for item in bound for s in item["required_subjects"]})
        requirement_refs = [item["requirement_id"] for item in bound]
        reaction_refs = sorted({x for item in bound for x in item["reaction_contract_refs"]})
        prop_refs = sorted({x for item in bound for x in item["required_prop_refs"]})
        axis_refs = sorted({x for item in bound for x in item["required_axis_refs"]})
        coverage = sorted({x for item in bound for x in item["required_coverages"]})
        first_state = _state(blocking, beats[0])
        axis = {"axis_applicability": "REQUIRED" if axis_refs else "NOT_APPLICABLE", "axis_ref": axis_refs[0] if axis_refs else None, "axis_refs": axis_refs, "axis_policy": "PRESERVE", "screen_side_assignments": {}}
        camera = {"framing_class": framing, "orientation": "EYE_LEVEL", "support": "STATIC" if movement == "NONE" else "DOLLY", "movement": movement, "subject_binding": subjects}
        if movement != "NONE":
            camera.update({"movement_trigger": "AUTHORED_BEAT_TRANSITION", "movement_target": subjects[0] if subjects else "PRIMARY_SUBJECT", "movement_end_condition": "BEAT_INFORMATION_LANDS"})
        event = " / ".join(str(beat_map[b].get("event") or "") for b in beats)
        participants = sorted(first_state["subject_zones"])
        shot = {"plan_shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "scene_id": treatment["scene_id"], "beat_refs": beats, "beat_id": beats[0], "director_decision_refs": sorted({x for item in bound for x in item["director_decision_refs"]}), "requirement_refs": requirement_refs, "shot_purpose": purpose, "coverage_roles": coverage, "subjects": subjects, "participants": participants, "reaction_contract_refs": reaction_refs, "spatial_binding": {"blocking_state_refs": [x for item in bound for x in item["blocking_state_refs"]], "subject_zones": first_state["subject_zones"], "prop_refs": prop_refs}, "camera_state": camera, "axis_contract": axis, "temporal_intent": {"duration_mode": "REACTION_HOLD" if "REACTION_COVERAGE" in coverage else "ACTION_COMPLETION", "cut_trigger": "AUTHORED_INFORMATION_LANDS"}, "information_visibility": visibility, "authoring_provenance": {"proposal_origin": "HUMAN_INPUT"}, "continuous_take": True, "cut_events": [], "shot_description": event, "camera": {"shot_size": framing, "angle": "eye_level", "movement": movement.lower(), "speed": "authored", "camera_side": "center"}, "duration_hint_seconds": 4, "action_beats": [{"action_id": f"{beats[0]}_A01", "actor": subjects[0] if subjects else "", "action": event, "start_seconds": 0, "end_seconds": 3}], "entry_state": {"scene_id": treatment["scene_id"], "shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "characters": first_state["subject_zones"], "props": [], "source": "approved_scene_blocking"}, "exit_state": {"scene_id": treatment["scene_id"], "shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "characters": first_state["subject_zones"], "props": [], "source": "authored_shot_design"}, "asset_bindings": {"scene": treatment["scene_id"], "characters": subjects, "props": prop_refs}, "continuity_contract": {"screen_direction": "maintain", "axis_ref": axis.get("axis_ref"), "axis_policy": axis.get("axis_policy"), "blocking_state_ref": beats[0]}}
        shots.append(shot)
    return {"scene_id": treatment["scene_id"], "shots": shots, "requirements": req, "authoring_provenance": {"proposal_origin": "HUMAN_INPUT", "confirmed": True, "canonical_origin": "HUMAN_AUTHORED", "provider": {"called": False, "calls": 0}}}

def main() -> None:
    treatment_doc = json.loads((ART / "episode_01_director_treatment_phase_b.json").read_text(encoding="utf8"))
    blocking_doc = json.loads((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf8"))
    blocking_by_scene = {str(x["scene_id"]): x for x in blocking_doc["scenes"]}
    proposal = {"schema_version": "shot_design_proposal_phase_c_v1", "book_id": 990401, "episode": 1, "proposal_origin": "HUMAN_INPUT", "provider_calls": 0, "scenes": [build_scene(t, blocking_by_scene[str(t["scene_id"])]) for t in treatment_doc["scenes"]]}
    (ART / "episode_01_shot_design_human_input_fixture.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf8")

if __name__ == "__main__":
    main()


