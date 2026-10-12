"""Versioned, type-level relation compatibility for claim-aware authoring.

The registry contains ontology relations only.  It has no story names, scene
identifiers, raw text cues, or attempt-specific exceptions.
"""
from __future__ import annotations

from typing import Any, Mapping


RELATION_REGISTRY_VERSION = "director_claim_relation_registry_v1"

RELATION_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {
    "CHARACTER_ACTION": {
        "enter_guided": {
            "compatible_predicates": ["enter_guided", "lead_into", "guide_into"],
            "qualifier_keys": ["destination"],
        },
        "receive_object": {
            "compatible_predicates": ["receive_object", "take_possession"],
            "qualifier_keys": ["transfer_source"],
        },
    },
    "OBJECT_PROPERTY": {
        "typed_property": {
            "compatible_predicates": ["has_property", "property_value", "typed_property"],
            "qualifier_keys": ["property_domain"],
        },
    },
    "OBJECT_PROVENANCE": {
        "authorship": {
            "compatible_predicates": ["authored_by", "created_by"],
            "qualifier_keys": [],
        },
        "custody_origin": {
            "compatible_predicates": ["left_by", "inherited_from", "originated_from"],
            "qualifier_keys": ["ownership"],
        },
    },
    "OBJECT_POSSESSION": {
        "transfer": {
            "compatible_predicates": ["received_by", "possessed_by", "take_possession"],
            "qualifier_keys": ["transfer_source", "possession"],
        },
    },
    "ENVIRONMENT_STATE": {
        "state_value": {
            "compatible_predicates": ["state_value", "has_state", "light_state"],
            "qualifier_keys": ["state_domain", "light_state"],
        },
    },
    # Generic ontology classes required by the source semantic proposal
    # boundary.  These entries intentionally contain no story names or
    # scene-specific exceptions; they only describe predicate capabilities.
    "OBJECT_EXISTENCE": {
        "existence": {
            "compatible_predicates": ["scene_existence", "object_existence", "exists"],
            "qualifier_keys": [],
        },
    },
    "KNOWLEDGE_STATE": {
        "knowledge": {
            "compatible_predicates": ["knows", "knows_about", "knowledge_state"],
            "qualifier_keys": [],
        },
    },
    "SPEECH_ACT": {
        "speech": {
            "compatible_predicates": ["speech_act", "utters", "asks", "asserts"],
            "qualifier_keys": ["speaker_binding"],
        },
    },
    "UNCERTAINTY": {
        "uncertainty": {
            "compatible_predicates": ["uncertainty", "uncertain_about", "possible"],
            "qualifier_keys": [],
        },
    },
    "PROVENANCE": {
        "provenance": {
            "compatible_predicates": ["left_by", "authored_by", "created_by", "provenance"],
            "qualifier_keys": ["ownership"],
        },
    },
    "SOURCE_EVENT": {
        "source_event": {
            "compatible_predicates": ["scene_identity_evidence", "source_event"],
            "qualifier_keys": [],
        },
    },
}


def relation_registry() -> dict[str, Any]:
    return {
        "schema_version": RELATION_REGISTRY_VERSION,
        "relations": RELATION_REGISTRY,
        "matching": "claim_type plus typed subject/object refs plus registered predicate compatibility and typed qualifiers",
        "raw_text_is_semantically_ignored": True,
    }


def _ref(value: Any) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        return "", ""
    return str(value.get("kind") or ""), str(value.get("ref") or "")


def relation_compatible(candidate: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    """Check a registered relation without consulting prose."""
    claim_type = str(candidate.get("claim_type") or "")
    if claim_type != str(source.get("claim_type") or ""):
        return False
    if _ref(candidate.get("subject")) != _ref(source.get("subject")):
        return False
    if _ref(candidate.get("object")) != _ref(source.get("object")):
        return False
    candidate_predicate = str(candidate.get("predicate") or "")
    source_predicate = str(source.get("predicate") or "")
    if candidate_predicate == source_predicate:
        return True
    for relation in RELATION_REGISTRY.get(claim_type, {}).values():
        predicates = set(str(item) for item in relation.get("compatible_predicates", []))
        if candidate_predicate in predicates and source_predicate in predicates:
            qualifier_keys = set(str(item) for item in relation.get("qualifier_keys", []))
            for key in qualifier_keys:
                left = (candidate.get("qualifiers") or {}).get(key)
                right = (source.get("qualifiers") or {}).get(key)
                if left is not None and right is not None and left != right:
                    return False
            return True
    return False


def validate_relation_registry() -> dict[str, Any]:
    errors: list[str] = []
    for claim_type, relations in RELATION_REGISTRY.items():
        if not relations:
            errors.append(f"EMPTY_RELATION_GROUP:{claim_type}")
        for name, relation in relations.items():
            if not str(name).strip():
                errors.append("EMPTY_RELATION_NAME")
            if not relation.get("compatible_predicates"):
                errors.append(f"MISSING_PREDICATES:{claim_type}:{name}")
    return {"schema_version": RELATION_REGISTRY_VERSION, "status": "PASS" if not errors else "BLOCKED", "errors": errors}


__all__ = ["RELATION_REGISTRY_VERSION", "RELATION_REGISTRY", "relation_registry", "relation_compatible", "validate_relation_registry"]
