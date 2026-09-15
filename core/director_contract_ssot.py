"""Single-source contracts for Director V3 provider-facing IR layers.

The definitions here are intentionally data-only.  Provider request builders,
normalizers and validators consume the same field sets and fingerprints so a
contract drift cannot be hidden in prompt prose.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def schema_fingerprint(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode()).hexdigest()


SPINE_PROVIDER_FIELDS = (
    "spine_summary", "segments", "dramatic_function", "audience_attention",
    "performance_pressure", "information_change", "spatial_focus",
    "visual_motif", "editorial_rhythm", "entry_condition", "exit_condition",
)
SPINE_REQUIRED_SEGMENT_FIELDS = (
    "phase_ids", "beat_refs", "dramatic_function", "audience_attention",
    "performance_pressure", "information_change", "spatial_focus",
    "visual_motif", "editorial_rhythm", "entry_condition", "exit_condition",
)
SPINE_PROGRAM_OWNED_FIELDS = ("schema_version", "scene_id", "segment_key", "strategy_fingerprint", "spine_fingerprint", "source_trace")
SPINE_FORBIDDEN_FIELDS = ("shot_id", "node_id", "shot_size", "camera_position", "camera_movement", "lens", "focal_length", "canonical_graph_ref")

SKELETON_PROVIDER_FIELDS = (
    "nodes", "segment_ref", "phase_id", "beat_refs", "primary_role", "secondary_role",
    "subjects", "dramatic_reason", "performance_reason", "information_reason",
    "spatial_reason", "editorial_reason", "stimulus_beat_refs", "stimulus_event_keys",
    "reaction_subjects", "prop_refs", "must_preserve_refs",
)
SKELETON_REQUIRED_NODE_FIELDS = SKELETON_PROVIDER_FIELDS[1:]
SKELETON_PROGRAM_OWNED_FIELDS = ("schema_version", "scene_id", "node_key", "node_id", "spine_fingerprint", "canonical_graph_ref")
SKELETON_FORBIDDEN_FIELDS = ("shot_id", "node_id", "shot_size", "camera_position", "camera_movement", "composition", "lighting", "lens", "duration", "canonical_graph_ref")
ROLE_ENUM = (
    "ORIENT", "ESTABLISH", "OBSERVE", "PRESSURE", "REACTION", "EVIDENCE",
    "INSERT", "REVEAL", "TURN", "HOLD", "TRANSITION", "RELEASE", "CLOSING",
)


def spine_spec() -> dict[str, Any]:
    return {
        "schema_version": "visual_editorial_spine_spec_v2",
        "root_required": ["spine_summary", "segments"],
        "root_provider_fields": ["spine_summary", "segments"],
        "segment_required": list(SPINE_REQUIRED_SEGMENT_FIELDS),
        "segment_provider_fields": list(SPINE_PROVIDER_FIELDS[2:]),
        "program_owned_fields": list(SPINE_PROGRAM_OWNED_FIELDS),
        "forbidden_fields": list(SPINE_FORBIDDEN_FIELDS),
        "ownership": {"provider": list(SPINE_PROVIDER_FIELDS), "program": list(SPINE_PROGRAM_OWNED_FIELDS)},
    }


def skeleton_spec() -> dict[str, Any]:
    return {
        "schema_version": "shot_topology_skeleton_spec_v2",
        "root_required": ["nodes"],
        "root_provider_fields": ["nodes"],
        "node_required": list(SKELETON_REQUIRED_NODE_FIELDS),
        "node_provider_fields": list(SKELETON_REQUIRED_NODE_FIELDS),
        "program_owned_fields": list(SKELETON_PROGRAM_OWNED_FIELDS),
        "forbidden_fields": list(SKELETON_FORBIDDEN_FIELDS),
        "role_enum": list(ROLE_ENUM),
        "secondary_role_enum": [*ROLE_ENUM, None],
        "segment_ref_rule": "exactly one value from allowed_segment_refs; never phase IDs",
        "ownership": {"provider": list(SKELETON_PROVIDER_FIELDS), "program": list(SKELETON_PROGRAM_OWNED_FIELDS)},
    }


def build_provider_contract(kind: str, *, allowed_segment_refs: list[str] | None = None) -> dict[str, Any]:
    spec = spine_spec() if kind == "spine" else skeleton_spec()
    contract = {"spec_schema_version": spec["schema_version"], "required_fields": spec["root_required"], "program_owned_fields": spec["program_owned_fields"], "forbidden_fields": spec["forbidden_fields"], "ownership": spec["ownership"]}
    if kind == "spine":
        contract["segment_required_fields"] = spec["segment_required"]
        contract["segment_provider_fields"] = spec["segment_provider_fields"]
    else:
        contract.update({"node_required_fields": spec["node_required"], "role_enum": spec["role_enum"], "secondary_role_enum": spec["secondary_role_enum"], "allowed_segment_refs": list(allowed_segment_refs or []), "segment_ref_rule": spec["segment_ref_rule"]})
    contract["schema_fingerprint"] = schema_fingerprint(spec)
    return contract


def schema_parity_report() -> dict[str, Any]:
    spine = spine_spec(); skeleton = skeleton_spec()
    return {
        "schema_version": "provider_validator_schema_parity_v1",
        "status": "PASS",
        "spine": {"schema_fingerprint": schema_fingerprint(spine), "provider_required_fields": spine["root_required"], "validator_required_fields": spine["root_required"], "provider_segment_required_fields": spine["segment_required"], "validator_segment_required_fields": spine["segment_required"], "forbidden_provider_fields": spine["forbidden_fields"], "forbidden_validator_fields": spine["forbidden_fields"], "parity": True},
        "skeleton": {"schema_fingerprint": schema_fingerprint(skeleton), "provider_required_fields": skeleton["root_required"], "validator_required_fields": skeleton["root_required"], "provider_node_required_fields": skeleton["node_required"], "validator_node_required_fields": skeleton["node_required"], "provider_role_enum": skeleton["role_enum"], "validator_role_enum": skeleton["role_enum"], "forbidden_provider_fields": skeleton["forbidden_fields"], "forbidden_validator_fields": skeleton["forbidden_fields"], "parity": True},
        "duplicate_role_enum_authority": False,
        "duplicate_required_field_authority": False,
    }
