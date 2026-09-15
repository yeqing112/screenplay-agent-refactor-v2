"""Deterministic upstream authority and provider-readiness gates."""
from __future__ import annotations

from typing import Any

from core.director_contract_ssot import schema_fingerprint

PRESERVE_KINDS = {
    "CHARACTER_ACTION", "CHARACTER_REACTION", "PROP_STATE", "PROP_INTERACTION",
    "SPATIAL_RELATION", "INFORMATION_REVEAL", "INFORMATION_WITHHOLD",
    "VISUAL_EVENT", "ENTRY_EXIT", "CONTINUITY_REQUIREMENT",
}


def _d(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _l(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _t(value: Any) -> str: return str(value or "").strip()


def _refs(scene: dict[str, Any], key: str, prefix: str) -> set[str]:
    out: set[str] = set()
    for item in _l(scene.get(key)):
        row = _d(item); value = _t(row.get(f"{prefix}_id") or row.get("id") or row.get("character_id") or row.get("prop_id") or row.get("location_id"))
        if value: out.add(value if ":" in value else f"{prefix}:{value}")
    return out


def valid_scene_refs(scene: dict[str, Any], semantic_events: dict[str, Any] | None = None) -> dict[str, set[str]]:
    beats = {_t(_d(item).get("beat_id")) for item in _l(scene.get("beats")) if _t(_d(item).get("beat_id"))}
    beats = {value if ":" in value else f"beat:{value[1:] if value.upper().startswith('B') else value}" for value in beats}
    characters = _refs(scene, "characters", "character") | {_t(_d(item).get("character_id")) for item in _l(scene.get("participants")) if _t(_d(item).get("character_id"))}
    characters = {value if ":" in value else f"character:{value}" for value in characters}
    props = _refs(scene, "props", "prop")
    locations = _refs(scene, "locations", "location")
    events = {_t(_d(item).get("event_key")) for item in _l(_d(semantic_events).get("events")) if _t(_d(item).get("event_key"))} if semantic_events else set()
    facts = {_t(_d(item).get("fact_id") or _d(item).get("id")) for item in _l(scene.get("facts")) if _t(_d(item).get("fact_id") or _d(item).get("id"))}
    facts = {value if ":" in value else f"fact:{value}" for value in facts}
    return {"beat": beats, "character": characters, "prop": props, "location": locations, "event": events, "fact": facts, "source": beats | events | facts}


def normalize_structured_preserve_constraints(value: Any, *, scene: dict[str, Any], semantic_events: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate machine authority without fuzzy mapping or ID invention by LLM."""
    valid = valid_scene_refs(scene, semantic_events); rows = _l(value); normalized = []; errors = []
    for index, raw in enumerate(rows, 1):
        row = _d(raw); constraint_id = f"MP{index:02d}"
        kind = _t(row.get("kind")); description = _t(row.get("description"))
        beat_refs = [_t(x) for x in _l(row.get("beat_refs")) if _t(x)]; event_refs = [_t(x) for x in _l(row.get("event_refs")) if _t(x)]; source_refs = [_t(x) for x in _l(row.get("source_refs")) if _t(x)]
        anchors = beat_refs + event_refs + source_refs
        if not description or kind not in PRESERVE_KINDS: errors.append({"code": "PRESERVE_CONSTRAINT_INVALID", "constraint_id": constraint_id})
        if not anchors: errors.append({"code": "PRESERVE_AUTHORITY_UNRESOLVED", "constraint_id": constraint_id})
        if any(ref not in valid["beat"] for ref in beat_refs): errors.append({"code": "PRESERVE_CONSTRAINT_UNKNOWN_BEAT", "constraint_id": constraint_id})
        if any(ref not in valid["event"] for ref in event_refs): errors.append({"code": "PRESERVE_CONSTRAINT_UNKNOWN_EVENT", "constraint_id": constraint_id})
        if any(ref not in valid["source"] for ref in source_refs): errors.append({"code": "PRESERVE_CONSTRAINT_UNKNOWN_SOURCE", "constraint_id": constraint_id})
        if len(_l(row.get("binding_candidates"))) > 1: errors.append({"code": "PRESERVE_BINDING_AMBIGUOUS", "constraint_id": constraint_id})
        subjects = [_t(x) for x in _l(row.get("subject_refs")) if _t(x)]; objects = [_t(x) for x in _l(row.get("object_refs")) if _t(x)]
        if any(ref not in valid["character"] for ref in subjects): errors.append({"code": "PRESERVE_CONSTRAINT_UNKNOWN_CHARACTER", "constraint_id": constraint_id})
        if any(ref.startswith("prop:") and ref not in valid["prop"] for ref in objects): errors.append({"code": "PRESERVE_CONSTRAINT_UNKNOWN_PROP", "constraint_id": constraint_id})
        normalized.append({**row, "constraint_id": constraint_id, "kind": kind, "description": description, "subject_refs": subjects, "object_refs": objects, "beat_refs": beat_refs, "event_refs": event_refs, "source_refs": source_refs, "visibility_requirement": _t(row.get("visibility_requirement")) or "EXPLICIT", "preservation_scope": _t(row.get("preservation_scope")) or "SCENE"})
    return {"schema_version": "structured_preserve_constraint_v1", "constraints": normalized, "errors": errors, "status": "PASS" if not errors else "FAIL", "fingerprint": schema_fingerprint(normalized)}


def strategy_authority(strategy: dict[str, Any], *, scene: dict[str, Any], identity_projection: Any, semantic_events: dict[str, Any] | None = None) -> dict[str, Any]:
    structured = strategy.get("structured_preserve_constraints")
    if structured is None:
        legacy = _l(strategy.get("must_preserve")); structured = [{"kind": "VISUAL_EVENT", "description": _t(item)} for item in legacy]
    preserve = normalize_structured_preserve_constraints(structured, scene=scene, semantic_events=semantic_events)
    identity = _l(_d(identity_projection).get("records")) if isinstance(identity_projection, dict) else _l(identity_projection)
    identity_errors = [{"code": "IDENTITY_AUTHORITY_MISSING"}] if not identity else []
    return {"status": "PASS" if preserve["status"] == "PASS" and not identity_errors else "STRATEGY_AUTHORITY_INCOMPLETE", "strategy_fingerprint": _t(strategy.get("strategy_fingerprint")), "structured_preserve_constraints": preserve, "identity": {"status": "PASS" if not identity_errors else "FAIL", "record_count": len(identity), "errors": identity_errors}, "source_provenance": all(bool(_d(row).get("provenance")) for row in preserve["constraints"]) if preserve["constraints"] else True}


def provider_readiness_gate(*, authority: dict[str, Any], schema_parity: dict[str, Any], strategy_fingerprint_ok: bool = True) -> dict[str, Any]:
    checks = {"authority_complete": authority.get("status") == "PASS", "preserve_complete": _d(authority.get("structured_preserve_constraints")).get("status") == "PASS", "identity_complete": _d(authority.get("identity")).get("status") == "PASS", "schema_parity": schema_parity.get("status") == "PASS", "strategy_exact": strategy_fingerprint_ok, "no_unresolved_anchors": not any(_t(error.get("code")) == "PRESERVE_AUTHORITY_UNRESOLVED" for error in _l(_d(authority.get("structured_preserve_constraints")).get("errors")))}
    return {"schema_version": "provider_readiness_gate_v1", "status": "PASS" if all(checks.values()) else "FAIL", "provider_callable": all(checks.values()), "checks": checks, "errors": [] if all(checks.values()) else [key for key, value in checks.items() if not value]}


def strategy_approval_allowed(authority: dict[str, Any]) -> bool:
    """Approval is an upstream gate; unresolved machine authority is never approvable."""
    return authority.get("status") == "PASS"


def authority_completeness_gate(*, strategy: dict[str, Any], scene: dict[str, Any], identity_projection: Any, semantic_events: dict[str, Any] | None = None) -> dict[str, Any]:
    authority = strategy_authority(strategy, scene=scene, identity_projection=identity_projection, semantic_events=semantic_events)
    failed = authority.get("status") != "PASS" or not authority.get("source_provenance", False)
    return {"schema_version": "director_authority_completeness_gate_v1", "status": "AUTHORITY_COMPLETENESS_FAILED" if failed else "PASS", "provider_callable": not failed, "strategy_approval_allowed": not failed, "authority": authority, "errors": [{"code": "AUTHORITY_COMPLETENESS_FAILED"}] if failed else []}


def build_structured_preserve_constraints(value: Any, *, scene: dict[str, Any], semantic_events: dict[str, Any] | None = None) -> dict[str, Any]:
    return normalize_structured_preserve_constraints(value, scene=scene, semantic_events=semantic_events)
