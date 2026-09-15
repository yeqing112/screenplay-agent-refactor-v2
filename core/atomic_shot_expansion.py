"""Atomic execution detail and deterministic candidate materialization."""
from __future__ import annotations
import hashlib, json
from typing import Any

EXPANSION_SCHEMA = "atomic_shot_expansion_ir_v1"
EXPANSION_FIELDS = {"node_id", "shot_size", "camera_position", "camera_movement", "composition_intent", "performance_focus", "information_focus", "prop_focus", "spatial_anchor", "entry_state", "exit_state", "cut_in_motivation", "cut_out_motivation", "hold_logic", "continuity_requirements"}
SIZES = {"EWS", "WS", "MWS", "MS", "MCU", "CU", "ECU", "INSERT"}; MOVES = {"STATIC", "PAN", "TILT", "PUSH_IN", "PULL_OUT", "TRACK", "DOLLY", "HANDHELD_SUBTLE", "REFRAME", "NONE"}
def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def fingerprint(v): return hashlib.sha256(_canon(v).encode()).hexdigest()

def validate_atomic_expansion(bound: dict[str, Any], expansion: Any) -> dict[str, Any]:
    records = _l(expansion.get("expansions")) if isinstance(expansion, dict) else _l(expansion); nodes = _l(bound.get("nodes")); expected = [_t(n.get("node_id")) for n in nodes]; actual = [_t(_d(x).get("node_id")) for x in records]; errors = []
    if set(actual) != set(expected): errors.append({"code": "EXPANSION_NODE_COVERAGE_INVALID", "missing_node_ids": sorted(set(expected) - set(actual)), "unknown_node_ids": sorted(set(actual) - set(expected))})
    if len(actual) != len(set(actual)): errors.append({"code": "EXPANSION_DUPLICATE_NODE"})
    allowed_roles = { _t(n.get("node_id")): (_t(n.get("phase_id")), tuple(_l(n.get("beat_refs"))), _t(n.get("primary_role")), _d(n.get("stimulus_binding"))) for n in nodes }
    for row in records:
        node_id = _t(_d(row).get("node_id")); unknown = sorted(set(_d(row)) - EXPANSION_FIELDS); errors += [{"code": "UNKNOWN_EXPANSION_FIELD", "node_id": node_id, "field": x} for x in unknown]
        if _t(_d(row).get("shot_size")) not in SIZES: errors.append({"code": "EXPANSION_SHOT_SIZE_INVALID", "node_id": node_id})
        if _t(_d(row).get("camera_movement")) not in MOVES: errors.append({"code": "EXPANSION_CAMERA_MOVEMENT_INVALID", "node_id": node_id})
        if node_id not in allowed_roles: continue
        forbidden = set(_d(row)) & {"phase_id", "beat_refs", "primary_role", "secondary_role", "stimulus_binding", "segment_key"}
        errors += [{"code": "EXPANSION_TOPOLOGY_MUTATION", "node_id": node_id, "field": x} for x in sorted(forbidden)]
    return {"status": "PASS" if not errors else "FAIL", "hard_errors": errors, "expected_node_ids": expected, "actual_node_ids": actual}

def materialize_candidate(bound: dict[str, Any], expansion: Any) -> dict[str, Any]:
    validation = validate_atomic_expansion(bound, expansion)
    if validation["status"] != "PASS": return {"status": "FAIL", "errors": validation["hard_errors"], "validation": validation}
    records = { _t(_d(x).get("node_id")): _d(x) for x in (_l(expansion.get("expansions")) if isinstance(expansion, dict) else _l(expansion)) }; shots = []
    node_to_shot = { _t(n.get("node_id")): f"SA{i:02d}" for i, n in enumerate(_l(bound.get("nodes")), 1) }
    for node in _l(bound.get("nodes")):
        node_id = _t(node.get("node_id")); detail = records[node_id]; shot = {"shot_id": node_to_shot[node_id], "node_id": node_id, "phase_id": node.get("phase_id"), "beat_refs": list(_l(node.get("beat_refs"))), "primary_function": node.get("primary_role"), "secondary_function": node.get("secondary_role"), "subject": list(_l(node.get("subjects"))), **{k: detail.get(k) for k in EXPANSION_FIELDS if k not in {"node_id"}}}
        binding = _d(node.get("stimulus_binding")); target = _t(binding.get("to_node_id") or binding.get("bound_node_id")); shot["stimulus_ref"] = f"shot:{node_to_shot[target]}" if target in node_to_shot else None
        shots.append(shot)
    candidate = {"schema_version": "shot_architecture_candidate_v3", "scene_id": _t(bound.get("scene_id")), "bound_topology_fingerprint": _t(bound.get("bound_topology_fingerprint")), "shots": shots}
    candidate["architecture_candidate_fingerprint"] = fingerprint(candidate)
    return {"status": "PASS", "candidate": candidate, "architecture_candidate_fingerprint": candidate["architecture_candidate_fingerprint"], "validation": validation}
