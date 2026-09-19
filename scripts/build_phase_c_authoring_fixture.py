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
        {"beat_refs": ["SC01-B01", "SC01-B02"], "shot_purpose": "ESTABLISH_SPACE", "framing_class": "WIDE", "movement": "NONE", "information_visibility": "AUDIENCE_ONLY", "subjects": ["林晚", "售票员"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": [], "information_refs": []},
        {"beat_refs": ["SC01-B03"], "shot_purpose": "REVEAL_INFORMATION", "framing_class": "WIDE", "movement": "REFRAME", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["林晚"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC01-B03_林晚"], "information_refs": ["INFO_SC01_B03_001"]},
        {"beat_refs": ["SC01-B04"], "shot_purpose": "CONFIRM_EVIDENCE", "framing_class": "INSERT", "movement": "NONE", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["林晚", "顾沉"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC01-B04_林晚"], "information_refs": ["INFO_SC01_B04_001"]},
        {"beat_refs": ["SC01-B05", "SC01-B06"], "shot_purpose": "INTRODUCE_INFORMATION", "framing_class": "TWO_SHOT", "movement": "NONE", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["顾沉", "林晚"], "action_actor": "顾沉", "movement_target": "顾沉", "reaction_contract_refs": ["RC_SC01-B05_顾沉", "RC_SC01-B06_顾沉"], "information_refs": ["INFO_SC01_B06_001"]},
        {"beat_refs": ["SC01-B07", "SC01-B08"], "shot_purpose": "SHIFT_POWER", "framing_class": "MEDIUM_WIDE", "movement": "TRACK", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["陆叔", "林晚"], "action_actor": "陆叔", "movement_target": "陆叔", "reaction_contract_refs": ["RC_SC01-B08_陆叔"], "information_refs": ["INFO_SC01_B08_001"]},
        {"beat_refs": ["SC01-B09", "SC01-B10"], "shot_purpose": "SHOW_PROP_STATE", "framing_class": "INSERT", "movement": "NONE", "information_visibility": "AUDIENCE_ONLY", "subjects": ["林晚"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC01-B09_林晚", "RC_SC01-B10_林晚"], "information_refs": ["INFO_SC01_B09_001", "INFO_SC01_B10_001"]},
        {"beat_refs": ["SC01-B11", "SC01-B12"], "shot_purpose": "REDIRECT_ATTENTION", "framing_class": "MEDIUM", "movement": "PAN", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["林晚", "陆叔"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC01-B11_林晚", "RC_SC01-B12_陆叔"], "information_refs": ["INFO_SC01_B11_001"]},
        {"beat_refs": ["SC01-B13"], "shot_purpose": "SCENE_EXIT", "framing_class": "MEDIUM_CLOSE", "movement": "DOLLY_IN", "information_visibility": "AUDIENCE_ONLY", "subjects": ["顾沉", "林晚"], "action_actor": "顾沉", "movement_target": "顾沉", "reaction_contract_refs": ["RC_SC01-B13_顾沉"], "information_refs": ["INFO_SC01_B13_001"]},
    ],
    "E01_SC002": [
        {"beat_refs": ["SC02-B01", "SC02-B02"], "shot_purpose": "ESTABLISH_RELATIONSHIP", "framing_class": "WIDE", "movement": "NONE", "information_visibility": "AUDIENCE_ONLY", "subjects": ["陆叔", "林晚"], "action_actor": "陆叔", "movement_target": "陆叔", "reaction_contract_refs": ["RC_SC02-B02_林晚"], "information_refs": []},
        {"beat_refs": ["SC02-B03"], "shot_purpose": "INTRODUCE_INFORMATION", "framing_class": "OVER_SHOULDER", "movement": "NONE", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["陆叔", "林晚"], "action_actor": "陆叔", "movement_target": "陆叔", "reaction_contract_refs": ["RC_SC02-B03_陆叔"], "information_refs": ["INFO_SC02_B03_001"]},
        {"beat_refs": ["SC02-B04"], "shot_purpose": "CAPTURE_REACTION", "framing_class": "MEDIUM_CLOSE", "movement": "NONE", "information_visibility": "AUDIENCE_OBSERVES_CHARACTER_DOUBT", "subjects": ["林晚"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC02-B04_林晚"], "information_refs": []},
        {"beat_refs": ["SC02-B05"], "shot_purpose": "CAPTURE_REACTION", "framing_class": "MEDIUM_CLOSE", "movement": "REFRAME", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["陆叔", "林晚"], "action_actor": "陆叔", "movement_target": "陆叔", "reaction_contract_refs": ["RC_SC02-B05_陆叔"], "information_refs": ["INFO_SC02_B05_001"]},
        {"beat_refs": ["SC02-B06"], "shot_purpose": "CONFIRM_EVIDENCE", "framing_class": "INSERT", "movement": "NONE", "information_visibility": "AUDIENCE_ONLY", "subjects": ["林晚"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC02-B06_林晚"], "information_refs": ["INFO_SC02_B06_001"]},
        {"beat_refs": ["SC02-B07"], "shot_purpose": "ESCALATE_THREAT", "framing_class": "CLOSE", "movement": "DOLLY_IN", "information_visibility": "CHARACTER_AND_AUDIENCE", "subjects": ["陆叔", "林晚"], "action_actor": "陆叔", "movement_target": "陆叔", "reaction_contract_refs": ["RC_SC02-B07_陆叔"], "information_refs": []},
        {"beat_refs": ["SC02-B08", "SC02-B09"], "shot_purpose": "SCENE_EXIT", "framing_class": "TWO_SHOT", "movement": "ARC", "information_visibility": "AUDIENCE_ONLY", "subjects": ["林晚", "陆叔"], "action_actor": "林晚", "movement_target": "林晚", "reaction_contract_refs": ["RC_SC02-B08_林晚", "RC_SC02-B09_陆叔"], "information_refs": ["INFO_SC02_B08_001"]},
    ],
}

def _state(blocking: dict, beat_id: str) -> dict:
    for state in blocking.get("beat_spatial_states", []):
        if isinstance(state, dict) and str(state.get("beat_ref")) == beat_id:
            chars = state.get("characters") if isinstance(state.get("characters"), dict) else {}
            return {"state_ref": beat_id, "subject_zones": {str(k): (v.get("zone") if isinstance(v, dict) else v) for k, v in chars.items()}}
    return {"state_ref": beat_id, "subject_zones": {}}


def _axes(blocking: dict) -> list[dict]:
    raw = blocking.get("interaction_axes")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

def build_scene(treatment: dict, blocking: dict) -> dict:
    req = build_shot_requirements(treatment=treatment, blocking=blocking, script_authority={"source": "current_phase_b_authority"})
    by_beat = {str(r["beat_refs"][0]): r for r in req["requirements"]}
    beat_map = {str(b["beat_id"]): b for b in treatment.get("beat_map", [])}
    shots = []
    for index, authored in enumerate(GROUPS[str(treatment["scene_id"])], 1):
        beats = list(authored["beat_refs"])
        purpose = authored["shot_purpose"]
        framing = authored["framing_class"]
        movement = authored["movement"]
        visibility = authored["information_visibility"]
        bound = [by_beat[beat] for beat in beats]
        subjects = list(authored["subjects"])
        expected_subjects = {s for item in bound for s in item["required_subjects"]}
        if not expected_subjects.issubset(set(subjects)):
            raise ValueError(f"authored subjects do not cover upstream subjects for {beats}")
        requirement_refs = [item["requirement_id"] for item in bound]
        reaction_refs = list(authored["reaction_contract_refs"])
        expected_reactions = {x for item in bound for x in item["reaction_contract_refs"]}
        if set(reaction_refs) != expected_reactions:
            raise ValueError(f"authored reaction refs do not match upstream contracts for {beats}")
        information_refs = list(authored.get("information_refs", []))
        expected_information = {x for item in bound for x in item.get("required_information_refs", [])}
        if set(information_refs) != expected_information:
            raise ValueError(f"authored information refs do not match upstream requirements for {beats}")
        prop_refs = sorted({x for item in bound for x in item["required_prop_refs"]})
        axis_refs = sorted({x for item in bound for x in item["required_axis_refs"]})
        coverage = sorted({x for item in bound for x in item["required_coverages"]})
        first_state = _state(blocking, beats[0])
        axis = {"axis_applicability": "REQUIRED" if axis_refs else "NOT_APPLICABLE", "axis_ref": axis_refs[0] if axis_refs else None, "axis_refs": axis_refs, "axis_policy": "PRESERVE", "screen_side_assignments": {}, "look_direction": {}}
        if axis_refs:
            axis_def = next((item for item in _axes(blocking) if str(item.get("axis_id") or item.get("axis_ref")) == axis_refs[0]), {})
            axis_subjects = [str(item) for item in (axis_def.get("subjects") or axis_def.get("participants") or [])]
            axis["screen_side_assignments"] = {subject: ("LEFT" if offset == 0 else "RIGHT") for offset, subject in enumerate(axis_subjects)}
            axis["look_direction"] = {subject: ("SCREEN_RIGHT" if offset == 0 else "SCREEN_LEFT") for offset, subject in enumerate(axis_subjects)}
        camera = {"framing_class": framing, "orientation": "EYE_LEVEL", "support": "STATIC" if movement == "NONE" else "DOLLY", "movement": movement, "subject_binding": subjects}
        if movement != "NONE":
            camera.update({"movement_trigger": "AUTHORED_BEAT_TRANSITION", "movement_target": authored["movement_target"], "movement_end_condition": "BEAT_INFORMATION_LANDS"})
        event = " / ".join(str(beat_map[b].get("event") or "") for b in beats)
        participants = sorted(first_state["subject_zones"])
        shot = {"plan_shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "scene_id": treatment["scene_id"], "beat_refs": beats, "beat_id": beats[0], "director_decision_refs": sorted({x for item in bound for x in item["director_decision_refs"]}), "requirement_refs": requirement_refs, "shot_purpose": purpose, "coverage_roles": coverage, "subjects": subjects, "participants": participants, "reaction_contract_refs": reaction_refs, "information_refs": information_refs, "spatial_binding": {"blocking_state_refs": [x for item in bound for x in item["blocking_state_refs"]], "subject_zones": first_state["subject_zones"], "prop_refs": prop_refs}, "camera_state": camera, "axis_contract": axis, "temporal_intent": {"duration_mode": "REACTION_HOLD" if "REACTION_COVERAGE" in coverage else "ACTION_COMPLETION", "cut_trigger": "AUTHORED_INFORMATION_LANDS"}, "information_visibility": visibility, "authoring_provenance": {"proposal_origin": "HUMAN_INPUT"}, "continuous_take": True, "cut_events": [], "shot_description": event, "camera": {"shot_size": framing, "angle": "eye_level", "movement": movement.lower(), "speed": "authored", "camera_side": "center"}, "duration_hint_seconds": 4, "action_beats": [{"action_id": f"{beats[0]}_A01", "actor": authored["action_actor"], "action": event, "start_seconds": 0, "end_seconds": 3}], "entry_state": {"scene_id": treatment["scene_id"], "shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "characters": first_state["subject_zones"], "props": [], "source": "approved_scene_blocking"}, "exit_state": {"scene_id": treatment["scene_id"], "shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "characters": first_state["subject_zones"], "props": [], "source": "authored_shot_design"}, "asset_bindings": {"scene": treatment["scene_id"], "characters": subjects, "props": prop_refs}, "continuity_contract": {"screen_direction": "maintain", "axis_ref": axis.get("axis_ref"), "axis_policy": axis.get("axis_policy"), "blocking_state_ref": beats[0]}}
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


