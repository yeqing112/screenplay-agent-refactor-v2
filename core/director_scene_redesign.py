"""Schema-only Scene Redesign protocol.

Redesign is the future topology-changing lane.  This foundation defines its
request/validation boundary but never executes a redesign or writes a plan.
"""
from __future__ import annotations

import copy
from typing import Any


REDESIGN_SCHEMA_VERSION = "director_scene_redesign_request_v1"
TOPOLOGY_OPERATIONS = {"add", "delete", "split", "merge", "reorder", "change_camera_structure", "change_reveal_placement", "add_reaction", "add_insert", "add_establishing"}
IMMUTABLE_AUTHORITY = {"source_facts", "dialogue_facts", "event_results", "character_identity", "asset_facts", "time_space_facts", "continuity_source_truth"}


class SceneRedesignError(ValueError):
    code = "SCENE_REDESIGN_INVALID"


def build_scene_redesign_request(*, scene_strategy: dict[str, Any], draft_shot_plan: dict[str, Any], qa_findings: list[dict[str, Any]], immutable_facts: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, assets: dict[str, Any] | None = None, allowed_topology_freedom: list[str] | None = None) -> dict[str, Any]:
    operations = sorted(set(allowed_topology_freedom or {"add", "delete", "split", "merge", "reorder"}) & TOPOLOGY_OPERATIONS)
    return {"schema_version": REDESIGN_SCHEMA_VERSION, "scene_strategy_fingerprint": str(scene_strategy.get("strategy_fingerprint") or ""), "draft_shot_plan_fingerprint": _fingerprint(draft_shot_plan), "qa_findings": copy.deepcopy(qa_findings), "immutable_facts": copy.deepcopy(immutable_facts or {}), "blocking": copy.deepcopy(blocking or {}), "assets": copy.deepcopy(assets or {}), "allowed_topology_operations": operations, "forbidden_authority_mutations": sorted(IMMUTABLE_AUTHORITY), "execution_status": "interface_only", "provider_calls": 0}


def _fingerprint(value: Any) -> str:
    import hashlib, json
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def validate_scene_redesign_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["request must be an object"]}
    errors = []
    if raw.get("schema_version") != REDESIGN_SCHEMA_VERSION: errors.append("invalid schema_version")
    if raw.get("execution_status") != "interface_only": errors.append("redesign execution is not enabled in Foundation")
    operations = raw.get("allowed_topology_operations")
    if not isinstance(operations, list) or any(str(item) not in TOPOLOGY_OPERATIONS for item in operations): errors.append("unknown topology operation")
    if set(raw.get("forbidden_authority_mutations") or []) != IMMUTABLE_AUTHORITY: errors.append("immutable authority boundary is incomplete")
    return {"valid": not errors, "errors": errors}


__all__ = ["REDESIGN_SCHEMA_VERSION", "TOPOLOGY_OPERATIONS", "IMMUTABLE_AUTHORITY", "SceneRedesignError", "build_scene_redesign_request", "validate_scene_redesign_request"]
