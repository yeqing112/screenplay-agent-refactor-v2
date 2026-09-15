"""Deterministic resolver from semantic topology to canonical graph edges."""
from __future__ import annotations
import hashlib, json
from typing import Any

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def fingerprint(v): return hashlib.sha256(_canon(v).encode()).hexdigest()

def _refs(node, key): return {_t(x) for x in _l(_d(node).get(key)) if _t(x)}

def bind_topology(skeleton: dict[str, Any], *, semantic_events: dict[str, Any] | None = None) -> dict[str, Any]:
    nodes = _l(skeleton.get("nodes")); bound_nodes = []
    for index, source in enumerate(nodes, 1):
        node = dict(source); node_id = f"ST{index:02d}"; node["node_id"] = node_id; node.pop("node_key", None); bound_nodes.append(node)
    edges = []; errors = []
    events = { _t(e.get("event_key")): e for e in _l(_d(semantic_events).get("events")) }
    for index, node in enumerate(bound_nodes):
        if _t(node.get("primary_role")) != "REACTION": continue
        beat_refs = _refs(node, "stimulus_beat_refs"); event_key = _t(node.get("stimulus_event_key")); candidates = []
        for prior_index, prior in enumerate(bound_nodes[:index]):
            if beat_refs & _refs(prior, "beat_refs"): candidates.append(prior["node_id"])
            if event_key and event_key in events and _t(events[event_key].get("beat_ref")) in _refs(prior, "beat_refs"): candidates.append(prior["node_id"])
        candidates = list(dict.fromkeys(candidates))
        if len(candidates) == 1:
            edge = {"edge_type": "REACTION_TO", "from_node_id": node["node_id"], "to_node_id": candidates[0], "bound_node_id": candidates[0], "binding_status": "BOUND", "source_type": "BEAT" if beat_refs else "EVENT", "source_ref": sorted(beat_refs)[0] if beat_refs else event_key}; node["stimulus_binding"] = edge; edges.append(edge)
        elif len(candidates) > 1:
            errors.append({"code": "GRAPH_BINDING_AMBIGUOUS", "node_id": node["node_id"], "candidate_node_ids": candidates}); node["stimulus_binding"] = {"binding_status": "AMBIGUOUS", "candidate_node_ids": candidates}
        else:
            future = []
            for future_node in bound_nodes[index + 1:]:
                if beat_refs & _refs(future_node, "beat_refs"): future.append(future_node["node_id"])
            code = "GRAPH_BINDING_ORDER_INVALID" if future else "GRAPH_BINDING_TARGET_MISSING"
            errors.append({"code": code, "node_id": node["node_id"], "candidate_node_ids": future}); node["stimulus_binding"] = {"binding_status": code.replace("GRAPH_BINDING_", ""), "candidate_node_ids": future}
    # A self edge is never legal, even if a malformed fixture attempts one.
    errors.extend(validate_bound_edges(edges))
    result = {"schema_version": "bound_shot_topology_v1", "scene_id": _t(skeleton.get("scene_id")), "spine_fingerprint": _t(skeleton.get("spine_fingerprint")), "topology_fingerprint": fingerprint(skeleton), "nodes": bound_nodes, "edges": edges, "errors": errors, "binding_status": "PASS" if not errors else "FAIL"}
    result["bound_topology_fingerprint"] = fingerprint({k: v for k, v in result.items() if k not in {"bound_topology_fingerprint", "errors"}})
    return result


def validate_bound_edges(edges: Any) -> list[dict[str, Any]]:
    """Validate program-owned graph edges without inventing semantics.

    This small, side-effect-free validator is also used by replay/negative
    fixtures to prove that a malformed bound graph fails closed.  The binder
    itself never creates a self edge because only prior nodes are candidates,
    but persisted or hand-edited results must be guarded as well.
    """
    errors: list[dict[str, Any]] = []
    for edge in _l(edges):
        row = _d(edge)
        source = _t(row.get("from_node_id")); target = _t(row.get("to_node_id"))
        if source and target and source == target:
            errors.append({"code": "GRAPH_SELF_EDGE_INVALID", "node_id": source})
        if _t(row.get("edge_type")) not in {"REACTION_TO", "EVIDENCE_RESPONSE", "REVEAL_DEPENDENCY", "INFORMATION_PRECONDITION"}:
            errors.append({"code": "GRAPH_EDGE_TYPE_INVALID", "edge_type": row.get("edge_type")})
        if not source or not target:
            errors.append({"code": "GRAPH_EDGE_ENDPOINT_MISSING", "edge": row})
    return errors
