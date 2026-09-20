"""Build the recorded HUMAN_INPUT Phase C ShotDesign fixture.

This is intentionally an authoring fixture, not a creative builder.  Every
canonical creative field is written in GROUPS as reviewed HUMAN_INPUT; the
requirements compiler is only used to bind and validate those decisions.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.phase_c_shot_plan import build_shot_requirements

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "e2e-production-pilot"

GROUPS = {
    "E01_SC001": [
        {
            "beat_refs": [
                "SC01-B01",
                "SC01-B02"
            ],
            "shot_purpose": "ESTABLISH_SPACE",
            "information_visibility": "AUDIENCE_ONLY",
            "subjects": [
                "林晚",
                "售票员"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [],
            "information_refs": [],
            "camera_state": {
                "framing_class": "WIDE",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "NOT_APPLICABLE",
                "axis_ref": None,
                "axis_refs": [],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {},
                "look_direction": {}
            },
            "temporal_intent": {
                "duration_mode": "ACTION_COMPLETION",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B03"
            ],
            "shot_purpose": "REVEAL_INFORMATION",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "林晚"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC01-B03_林晚"
            ],
            "information_refs": [
                "INFO_SC01_B03_001"
            ],
            "camera_state": {
                "framing_class": "WIDE",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "REFRAME",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "林晚",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "NOT_APPLICABLE",
                "axis_ref": None,
                "axis_refs": [],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {},
                "look_direction": {}
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B04"
            ],
            "shot_purpose": "CONFIRM_EVIDENCE",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "林晚",
                "顾沉"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC01-B04_林晚"
            ],
            "information_refs": [
                "INFO_SC01_B04_001"
            ],
            "camera_state": {
                "framing_class": "INSERT",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "NOT_APPLICABLE",
                "axis_ref": None,
                "axis_refs": [],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {},
                "look_direction": {}
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B05",
                "SC01-B06"
            ],
            "shot_purpose": "INTRODUCE_INFORMATION",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "顾沉",
                "林晚"
            ],
            "action_actor": "顾沉",
            "movement_target": "顾沉",
            "reaction_contract_refs": [
                "RC_SC01-B05_顾沉",
                "RC_SC01-B06_顾沉"
            ],
            "information_refs": [
                "INFO_SC01_B06_001"
            ],
            "camera_state": {
                "framing_class": "TWO_SHOT",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_GC",
                "axis_refs": [
                    "AXIS_LW_GC"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "顾沉": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "顾沉": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B07",
                "SC01-B08"
            ],
            "shot_purpose": "SHIFT_POWER",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "陆叔",
                "林晚"
            ],
            "action_actor": "陆叔",
            "movement_target": "陆叔",
            "reaction_contract_refs": [
                "RC_SC01-B08_陆叔"
            ],
            "information_refs": [
                "INFO_SC01_B08_001"
            ],
            "camera_state": {
                "framing_class": "MEDIUM_WIDE",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "TRACK",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "陆叔",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_GC",
                "axis_refs": [
                    "AXIS_LW_GC",
                    "AXIS_LW_LS"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "顾沉": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "顾沉": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B09",
                "SC01-B10"
            ],
            "shot_purpose": "SHOW_PROP_STATE",
            "information_visibility": "AUDIENCE_ONLY",
            "subjects": [
                "林晚"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC01-B09_林晚",
                "RC_SC01-B10_林晚"
            ],
            "information_refs": [
                "INFO_SC01_B09_001",
                "INFO_SC01_B10_001"
            ],
            "camera_state": {
                "framing_class": "INSERT",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_GC",
                "axis_refs": [
                    "AXIS_LW_GC",
                    "AXIS_LW_LS"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "顾沉": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "顾沉": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B11",
                "SC01-B12"
            ],
            "shot_purpose": "REDIRECT_ATTENTION",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "林晚",
                "陆叔"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC01-B11_林晚",
                "RC_SC01-B12_陆叔"
            ],
            "information_refs": [
                "INFO_SC01_B11_001"
            ],
            "camera_state": {
                "framing_class": "MEDIUM",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "PAN",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "林晚",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_GC",
                "axis_refs": [
                    "AXIS_LW_GC",
                    "AXIS_LW_LS"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "顾沉": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "顾沉": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC01-B13"
            ],
            "shot_purpose": "SCENE_EXIT",
            "information_visibility": "AUDIENCE_ONLY",
            "subjects": [
                "顾沉",
                "林晚"
            ],
            "action_actor": "顾沉",
            "movement_target": "顾沉",
            "reaction_contract_refs": [
                "RC_SC01-B13_顾沉"
            ],
            "information_refs": [
                "INFO_SC01_B13_001"
            ],
            "camera_state": {
                "framing_class": "MEDIUM_CLOSE",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "DOLLY_IN",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "顾沉",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_GC",
                "axis_refs": [
                    "AXIS_LW_GC",
                    "AXIS_LW_LS"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "顾沉": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "顾沉": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        }
    ],
    "E01_SC002": [
        {
            "beat_refs": [
                "SC02-B01",
                "SC02-B02"
            ],
            "shot_purpose": "ESTABLISH_RELATIONSHIP",
            "information_visibility": "AUDIENCE_ONLY",
            "subjects": [
                "陆叔",
                "林晚"
            ],
            "action_actor": "陆叔",
            "movement_target": "陆叔",
            "reaction_contract_refs": [
                "RC_SC02-B02_林晚"
            ],
            "information_refs": [],
            "camera_state": {
                "framing_class": "WIDE",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC02-B03"
            ],
            "shot_purpose": "INTRODUCE_INFORMATION",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "陆叔",
                "林晚"
            ],
            "action_actor": "陆叔",
            "movement_target": "陆叔",
            "reaction_contract_refs": [
                "RC_SC02-B03_陆叔"
            ],
            "information_refs": [
                "INFO_SC02_B03_001"
            ],
            "camera_state": {
                "framing_class": "OVER_SHOULDER",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC02-B04"
            ],
            "shot_purpose": "CAPTURE_REACTION",
            "information_visibility": "AUDIENCE_OBSERVES_CHARACTER_DOUBT",
            "subjects": [
                "林晚"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC02-B04_林晚"
            ],
            "information_refs": [],
            "camera_state": {
                "framing_class": "MEDIUM_CLOSE",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC02-B05"
            ],
            "shot_purpose": "CAPTURE_REACTION",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "陆叔",
                "林晚"
            ],
            "action_actor": "陆叔",
            "movement_target": "陆叔",
            "reaction_contract_refs": [
                "RC_SC02-B05_陆叔"
            ],
            "information_refs": [
                "INFO_SC02_B05_001"
            ],
            "camera_state": {
                "framing_class": "MEDIUM_CLOSE",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "REFRAME",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "陆叔",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC02-B06"
            ],
            "shot_purpose": "CONFIRM_EVIDENCE",
            "information_visibility": "AUDIENCE_ONLY",
            "subjects": [
                "林晚"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC02-B06_林晚"
            ],
            "information_refs": [
                "INFO_SC02_B06_001"
            ],
            "camera_state": {
                "framing_class": "INSERT",
                "orientation": "EYE_LEVEL",
                "support": "STATIC",
                "movement": "NONE"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC02-B07"
            ],
            "shot_purpose": "ESCALATE_THREAT",
            "information_visibility": "CHARACTER_AND_AUDIENCE",
            "subjects": [
                "陆叔",
                "林晚"
            ],
            "action_actor": "陆叔",
            "movement_target": "陆叔",
            "reaction_contract_refs": [
                "RC_SC02-B07_陆叔"
            ],
            "information_refs": [],
            "camera_state": {
                "framing_class": "CLOSE",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "DOLLY_IN",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "陆叔",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        },
        {
            "beat_refs": [
                "SC02-B08",
                "SC02-B09"
            ],
            "shot_purpose": "SCENE_EXIT",
            "information_visibility": "AUDIENCE_ONLY",
            "subjects": [
                "林晚",
                "陆叔"
            ],
            "action_actor": "林晚",
            "movement_target": "林晚",
            "reaction_contract_refs": [
                "RC_SC02-B08_林晚",
                "RC_SC02-B09_陆叔"
            ],
            "information_refs": [
                "INFO_SC02_B08_001"
            ],
            "camera_state": {
                "framing_class": "TWO_SHOT",
                "orientation": "EYE_LEVEL",
                "support": "DOLLY",
                "movement": "ARC",
                "movement_trigger": "AUTHORED_BEAT_TRANSITION",
                "movement_target": "林晚",
                "movement_end_condition": "BEAT_INFORMATION_LANDS"
            },
            "axis_contract": {
                "axis_applicability": "REQUIRED",
                "axis_ref": "AXIS_LW_LS_APT",
                "axis_refs": [
                    "AXIS_LW_LS_APT"
                ],
                "axis_policy": "PRESERVE",
                "screen_side_assignments": {
                    "林晚": "LEFT",
                    "陆叔": "RIGHT"
                },
                "look_direction": {
                    "林晚": "SCREEN_RIGHT",
                    "陆叔": "SCREEN_LEFT"
                }
            },
            "temporal_intent": {
                "duration_mode": "REACTION_HOLD",
                "cut_trigger": "AUTHORED_INFORMATION_LANDS"
            },
            "duration_hint_seconds": 4
        }
    ]
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
    for index, authored in enumerate(GROUPS[str(treatment["scene_id"])], 1):
        beats = list(authored["beat_refs"])
        visibility = authored["information_visibility"]
        camera_authored = authored.get("camera_state")
        axis_authored = authored.get("axis_contract")
        temporal_authored = authored.get("temporal_intent")
        if not isinstance(camera_authored, dict):
            raise ValueError(f"camera_state must be explicitly authored for {beats}")
        if not isinstance(axis_authored, dict):
            raise ValueError(f"axis_contract must be explicitly authored for {beats}")
        if not isinstance(temporal_authored, dict):
            raise ValueError(f"temporal_intent must be explicitly authored for {beats}")
        for field in ("framing_class", "orientation", "support", "movement"):
            if not camera_authored.get(field):
                raise ValueError(f"camera_state.{field} must be explicitly authored for {beats}")
        for field in ("axis_applicability", "axis_policy", "screen_side_assignments", "look_direction"):
            if field not in axis_authored:
                raise ValueError(f"axis_contract.{field} must be explicitly authored for {beats}")
        for field in ("duration_mode", "cut_trigger"):
            if not temporal_authored.get(field):
                raise ValueError(f"temporal_intent.{field} must be explicitly authored for {beats}")
        if "duration_hint_seconds" not in authored:
            raise ValueError(f"duration_hint_seconds must be explicitly authored for {beats}")
        movement = str(camera_authored["movement"])
        if movement != "NONE" and not all(camera_authored.get(field) for field in ("movement_trigger", "movement_target", "movement_end_condition")):
            raise ValueError(f"movement authoring is incomplete for {beats}")
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
        axis = dict(axis_authored)
        axis["axis_refs"] = list(axis.get("axis_refs") or [])
        axis["screen_side_assignments"] = dict(axis.get("screen_side_assignments") or {})
        axis["look_direction"] = dict(axis.get("look_direction") or {})
        if axis_refs != sorted(set(map(str, axis.get("axis_refs", [])))):
            raise ValueError(f"authored axis refs do not match upstream requirements for {beats}")
        if axis_refs and str(axis.get("axis_ref") or "") not in axis_refs:
            raise ValueError(f"authored axis_ref does not match upstream requirements for {beats}")
        if bool(axis_refs) != (axis.get("axis_applicability") == "REQUIRED"):
            raise ValueError(f"authored axis applicability does not match upstream requirements for {beats}")
        camera = dict(camera_authored)
        camera["subject_binding"] = subjects
        temporal = dict(temporal_authored)
        duration_hint = authored["duration_hint_seconds"]
        event = " / ".join(str(beat_map[b].get("event") or "") for b in beats)
        participants = sorted(first_state["subject_zones"])
        shot = {"plan_shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "scene_id": treatment["scene_id"], "beat_refs": beats, "beat_id": beats[0], "director_decision_refs": sorted({x for item in bound for x in item["director_decision_refs"]}), "requirement_refs": requirement_refs, "shot_purpose": authored["shot_purpose"], "coverage_roles": coverage, "subjects": subjects, "participants": participants, "reaction_contract_refs": reaction_refs, "information_refs": information_refs, "spatial_binding": {"blocking_state_refs": [x for item in bound for x in item["blocking_state_refs"]], "subject_zones": first_state["subject_zones"], "prop_refs": prop_refs}, "camera_state": camera, "axis_contract": axis, "temporal_intent": temporal, "information_visibility": visibility, "authoring_provenance": {"proposal_origin": "HUMAN_INPUT"}, "continuous_take": True, "cut_events": [], "shot_description": event, "camera": {"shot_size": camera["framing_class"], "angle": str(camera["orientation"]).lower(), "movement": movement.lower(), "speed": "authored", "camera_side": "center"}, "duration_hint_seconds": duration_hint, "action_beats": [{"action_id": f"{beats[0]}_A01", "actor": authored["action_actor"], "action": event, "start_seconds": 0, "end_seconds": min(3, duration_hint)}], "entry_state": {"scene_id": treatment["scene_id"], "shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "characters": first_state["subject_zones"], "props": [], "source": "approved_scene_blocking"}, "exit_state": {"scene_id": treatment["scene_id"], "shot_id": f"SH_{treatment['scene_id'].replace('-', '_')}_{index:03d}", "characters": first_state["subject_zones"], "props": [], "source": "authored_shot_design"}, "asset_bindings": {"scene": treatment["scene_id"], "characters": subjects, "props": prop_refs}, "continuity_contract": {"screen_direction": "maintain", "axis_ref": axis.get("axis_ref"), "axis_policy": axis.get("axis_policy"), "blocking_state_ref": beats[0]}}
        shots.append(shot)
    return {"scene_id": treatment["scene_id"], "shots": shots, "requirements": req, "authoring_provenance": {"proposal_origin": "HUMAN_INPUT"}}

def main() -> None:
    treatment_doc = json.loads((ART / "episode_01_director_treatment_phase_b.json").read_text(encoding="utf8"))
    blocking_doc = json.loads((ART / "episode_01_scene_blocking_phase_b.json").read_text(encoding="utf8"))
    blocking_by_scene = {str(x["scene_id"]): x for x in blocking_doc["scenes"]}
    proposal = {"schema_version": "shot_design_proposal_phase_c_v1", "book_id": 990401, "episode": 1, "proposal_origin": "HUMAN_INPUT", "provider_calls": 0, "scenes": [build_scene(t, blocking_by_scene[str(t["scene_id"])]) for t in treatment_doc["scenes"]]}
    (ART / "episode_01_shot_design_human_input_fixture.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    audit = {
        "schema_version": "phase_c_authoring_provenance_audit_v1",
        "source": "HUMAN_INPUT_FIXTURE",
        "canonical_creative_fields": [
            "shot_purpose", "subjects", "camera_state.framing_class", "camera_state.orientation",
            "camera_state.support", "camera_state.movement", "camera_state.movement_trigger",
            "camera_state.movement_target", "camera_state.movement_end_condition",
            "axis_contract.axis_policy", "axis_contract.screen_side_assignments", "axis_contract.look_direction",
            "temporal_intent.duration_mode", "temporal_intent.cut_trigger", "duration_hint_seconds",
            "information_visibility",
        ],
        "deterministic_binding_fields": [
            "plan_shot_id", "scene_id", "beat_id", "director_decision_refs", "requirement_refs",
            "blocking_state_refs", "prop_refs", "participants", "asset_bindings",
        ],
        "builder_generated_creative_fields": [],
        "proposal_origin": proposal["proposal_origin"],
        "provider": {"called": False, "calls": 0},
    }
    (ART / "phase_c_authoring_provenance_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf8")

if __name__ == "__main__":
    main()

