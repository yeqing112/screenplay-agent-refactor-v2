"""Provider-facing topology skeleton with a narrow authority boundary."""
from __future__ import annotations
import hashlib, json, re
from typing import Any

SKELETON_SCHEMA = "shot_topology_skeleton_ir_v1"
ROLE_ENUM = {"ORIENT", "ESTABLISH", "OBSERVE", "PRESSURE", "REACTION", "EVIDENCE", "INSERT", "REVEAL", "TURN", "HOLD", "TRANSITION", "RELEASE", "CLOSING"}
NODE_FIELDS = {"node_key", "segment_key", "segment_ref", "phase_id", "beat_refs", "primary_role", "secondary_role", "subjects", "dramatic_reason", "performance_reason", "information_reason", "spatial_reason", "editorial_reason", "stimulus_beat_refs", "stimulus_event_key", "stimulus_event_keys", "reaction_subjects", "prop_refs", "must_preserve_refs"}
FORBIDDEN_FIELDS = {"shot_size", "camera_movement", "camera_position", "composition_intent", "lighting", "lens", "stimulus_node_id", "stimulus_shot_id", "shot_id"}

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def fingerprint(v): return hashlib.sha256(_canon(v).encode()).hexdigest()
def _ref(v, namespace="beat"):
    text = _t(v)
    if not text: return ""
    if ":" in text: return text
    return f"{namespace}:{text[1:] if namespace == 'beat' and text.upper().startswith('B') else text}"

def normalize_skeleton(raw: dict[str, Any], *, scene_id: str, spine_fingerprint: str) -> dict[str, Any]:
    if not isinstance(raw, dict): return {"status": "FAIL", "errors": [{"code": "SKELETON_NOT_OBJECT"}], "ir": None}
    errors = [{"code": "UNKNOWN_SKELETON_FIELD", "field": k} for k in raw if k not in {"schema_version", "scene_id", "spine_fingerprint", "nodes"}]
    nodes = []
    for index, value in enumerate(_l(raw.get("nodes")), 1):
        row = _d(value); unknown = sorted(k for k in row if k not in NODE_FIELDS)
        errors += [{"code": "UNKNOWN_SKELETON_NODE_FIELD", "node_index": index, "field": k} for k in unknown]
        errors += [{"code": "FORBIDDEN_LAYER_FIELD", "node_index": index, "field": k} for k in sorted(set(row) & FORBIDDEN_FIELDS)]
        roles = row.get("primary_role") or row.get("role") or "OBSERVE"; primary = _t(roles[0] if isinstance(roles, list) else roles)
        second = row.get("secondary_role")
        event_keys = [_t(row.get("stimulus_event_key"))] if _t(row.get("stimulus_event_key")) else []
        event_keys += [_t(x) for x in _l(row.get("stimulus_event_keys")) if _t(x)]
        event_keys = list(dict.fromkeys(event_keys))
        raw_text = json.dumps(row, ensure_ascii=False, default=str)
        if re.search(r"(?:shot\s*:\s*SA\d+|node[_ ]?id\s*[:=]\s*ST\d+|\bST\d{2,}\b)", raw_text, re.IGNORECASE):
            errors.append({"code": "FORBIDDEN_PROGRAM_OWNED_GRAPH_REF", "node_index": index})
        nodes.append({"node_key": f"N{index:02d}", "segment_key": _t(row.get("segment_key") or row.get("segment_ref")), "phase_id": _t(row.get("phase_id")), "beat_refs": [_ref(x) for x in _l(row.get("beat_refs") or row.get("beats")) if _t(x)], "primary_role": primary, "secondary_role": _t(second) if second is not None else None, "subjects": [_ref(x, "character") for x in _l(row.get("subjects")) if _t(x)], "dramatic_reason": _t(row.get("dramatic_reason")), "performance_reason": _t(row.get("performance_reason")), "information_reason": _t(row.get("information_reason")), "spatial_reason": _t(row.get("spatial_reason")), "editorial_reason": _t(row.get("editorial_reason")), "stimulus_beat_refs": [_ref(x) for x in _l(row.get("stimulus_beat_refs")) if _t(x)], "stimulus_event_key": event_keys[0] if event_keys else "", "stimulus_event_keys": event_keys, "reaction_subjects": [_ref(x, "character") for x in _l(row.get("reaction_subjects")) if _t(x)], "prop_refs": [_ref(x, "prop") for x in _l(row.get("prop_refs")) if _t(x)], "must_preserve_refs": [_t(x) for x in _l(row.get("must_preserve_refs")) if _t(x)]})
    ir = {"schema_version": SKELETON_SCHEMA, "scene_id": scene_id, "spine_fingerprint": spine_fingerprint, "nodes": nodes}
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "ir": ir, "topology_fingerprint": fingerprint(ir)}

def validate_skeleton(skeleton: dict[str, Any], *, spine: dict[str, Any], scene: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    errors = []; warnings = []; nodes = _l(skeleton.get("nodes")); spine_segments = {_t(s.get("segment_key")) for s in _l(spine.get("segments"))}; segment_phases = {_t(s.get("segment_key")): {_t(p) for p in _l(s.get("phase_ids"))} for s in _l(spine.get("segments"))}; beats = {_ref(_d(b).get("beat_id")) for b in _l(scene.get("beats")) if _t(_d(b).get("beat_id"))}; phases = {_t(p.get("phase_id")) for p in _l(strategy.get("scene_phases")) if isinstance(p, dict)}; character_ids = {_t(_d(c).get("character_id")) for c in _l(_d(scene.get("characters")).get("records"))}; seen = set(); prior_beats = []
    for index, node in enumerate(nodes, 1):
        key = _t(_d(node).get("node_key"));
        if key in seen: errors.append({"code": "DUPLICATE_NODE_KEY", "node_key": key})
        seen.add(key)
        if _t(_d(node).get("segment_key")) not in spine_segments: errors.append({"code": "UNKNOWN_SPINE_SEGMENT", "node_key": key})
        if _t(_d(node).get("phase_id")) not in phases: errors.append({"code": "UNKNOWN_PHASE", "node_key": key})
        elif _t(_d(node).get("phase_id")) not in segment_phases.get(_t(_d(node).get("segment_key")), set()): errors.append({"code": "SKELETON_PHASE_MEMBERSHIP_INVALID", "node_key": key})
        refs = _l(_d(node).get("beat_refs")); unknown = sorted(set(refs) - beats); errors += [{"code": "UNKNOWN_BEAT_REFERENCE", "node_key": key, "reference": x} for x in unknown]
        role = _t(_d(node).get("primary_role")); second = _d(node).get("secondary_role")
        if role not in ROLE_ENUM: errors.append({"code": "TOPOLOGY_ROLE_INVALID", "node_key": key})
        if second is not None and _t(second) not in ROLE_ENUM: errors.append({"code": "TOPOLOGY_SECONDARY_ROLE_INVALID", "node_key": key})
        if not any(_t(_d(node).get(x)) for x in ("dramatic_reason", "performance_reason", "information_reason", "spatial_reason", "editorial_reason")): errors.append({"code": "NODE_EXISTENCE_REASON_MISSING", "node_key": key})
        for ref in _l(_d(node).get("subjects")) + _l(_d(node).get("reaction_subjects")):
            text = _t(ref)
            if text.startswith("character:") and text.split(":", 1)[1] not in character_ids:
                errors.append({"code": "SKELETON_IDENTITY_BINDING_INVALID", "node_key": key, "reference": text})
        if role == "REACTION" and not (_l(_d(node).get("stimulus_beat_refs")) or _t(_d(node).get("stimulus_event_key")) or _l(_d(node).get("stimulus_event_keys"))): errors.append({"code": "REACTION_SEMANTIC_STIMULUS_MISSING", "node_key": key})
        prior_beats += refs
    if len(nodes) > 0 and not seen: errors.append({"code": "SKELETON_EMPTY"})
    covered = set(x for n in nodes for x in _l(_d(n).get("beat_refs"))); errors += [{"code": "SKELETON_ORPHAN_BEAT", "reference": x} for x in sorted(beats - covered)]
    return {"status": "PASS" if not errors else "FAIL", "hard_errors": errors, "warnings": warnings, "node_count": len(nodes), "covered_beats": sorted(covered), "missing_beats": sorted(beats - covered)}

def compile_skeleton(raw, *, scene_id, spine, scene, strategy):
    normalized = normalize_skeleton(raw, scene_id=scene_id, spine_fingerprint=fingerprint(spine)); validation = validate_skeleton(normalized.get("ir") or {}, spine=spine, scene=scene, strategy=strategy) if normalized.get("ir") else {"status": "FAIL", "hard_errors": normalized.get("errors", [])}; return {**normalized, "validation": validation, "status": "PASS" if normalized.get("status") == "PASS" and validation.get("status") == "PASS" else "FAIL"}
