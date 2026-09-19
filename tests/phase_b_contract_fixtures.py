"""Raw Phase B production candidates used by authority contract tests."""
from __future__ import annotations

import copy

from core.blocking_state_compiler import COMPILER_VERSION, compile_blocking_states
from core.director_provenance import confirmation_event, proposal_provenance, resolve_canonical_origin


def build_phase_b_production_director_provenance() -> tuple[dict, dict, str]:
    """Build the raw provenance/event pair used by Production fixtures."""
    provenance = proposal_provenance("HUMAN_INPUT", provider={"called": False, "calls": 0}, human_input=True)
    event = confirmation_event(provenance, confirmed_at="2026-09-20T00:00:00Z")
    return provenance, event, resolve_canonical_origin(provenance, event)


def build_phase_b_production_blocking_candidate(blocking: dict) -> dict:
    allowed = {"scene_id", "scene_name", "space", "spatial_model", "participants", "beat_transitions", "spatial_rules", "unknowns", "unknown_resolutions", "schema_version", "source_spatial_facts", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "continuity_state", "asset_authority", "validation", "conflicts", "space_model", "zones", "anchors", "connections", "characters", "movement_paths", "beat_spatial_states", "eyelines", "prop_spatial_states", "critical_props", "interactions", "interaction_axes", "director_direction_refs", "provenance", "initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash", "movement_path_projection"}
    candidate = {key: copy.deepcopy(value) for key, value in blocking.items() if key in allowed}
    zones = [str(item.get("zone_id")) for item in candidate.get("zones", []) if isinstance(item, dict) and item.get("zone_id")]
    zone = zones[0] if zones else "playing_area"
    characters = {}
    for item in candidate.get("participants", []):
        if isinstance(item, dict):
            ref = str(item.get("character_id") or item.get("id") or item.get("name") or "").strip()
        else:
            ref = str(item).strip()
        if ref:
            characters[ref] = {"zone": zone, "facing": "FORWARD", "attention_target": "UNFOCUSED"}
    if not characters:
        characters["SCENE_CAST"] = {"zone": zone, "facing": "FORWARD", "attention_target": "UNFOCUSED"}
    initial = {"characters": characters, "props": {}, "exit_access": {zone: {"state": "AVAILABLE"}}}
    beats = [item for item in candidate.get("beat_transitions", []) if isinstance(item, dict) and item.get("beat_id")]
    subject = next(iter(characters))
    transitions = []
    for item in beats:
        ref = str(item["beat_id"])
        transitions.append({"transition_id": f"BT_{ref}_{subject}_ATTENTION", "beat_ref": ref, "subject_type": "CHARACTER", "subject_ref": subject, "changes": [{"property": "ATTENTION_TARGET", "from": "UNFOCUSED", "to": ref}], "cause": "DIRECTOR_BEAT_DECISION", "director_decision_ref": f"DBD_{ref}"})
    compiled = compile_blocking_states(initial, [{"beat_id": item["beat_id"]} for item in beats], transitions, valid_zones=set(zones))
    assert compiled["status"] == "qualified", compiled
    candidate.update({"initial_state": initial, "blocking_transitions": transitions, "compiler_version": COMPILER_VERSION, "compiled_states_hash": compiled["compiled_states_hash"], "beat_spatial_states": compiled["states"], "movement_path_projection": []})
    return candidate
