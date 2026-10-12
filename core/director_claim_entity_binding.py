"""Runtime entity reference contract for claim-aware authoring."""
from __future__ import annotations

from typing import Any, Mapping


ENTITY_BINDING_VERSION = "director_claim_entity_binding_contract_v1"


def entity_binding_contract() -> dict[str, Any]:
    return {
        "schema_version": ENTITY_BINDING_VERSION,
        "ref_shape": {"kind": "string", "ref": "canonical runtime ref"},
        "identity_source": "DECLARED_PARTICIPANTS and upstream ScriptIR/entity registry",
        "display_text_is_not_identity": True,
        "unknown_ref_policy": "BLOCKED",
    }


def validate_entity_ref(value: Any, *, registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return {"status": "BLOCKED", "errors": ["ENTITY_REF_MUST_BE_OBJECT"]}
    kind = str(value.get("kind") or "").strip()
    ref = str(value.get("ref") or "").strip()
    if not kind:
        errors.append("ENTITY_KIND_REQUIRED")
    if not ref:
        errors.append("ENTITY_REF_REQUIRED")
    if registry is not None and ref and ref not in registry:
        errors.append("ENTITY_REF_NOT_IN_RUNTIME_REGISTRY")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "kind": kind, "ref": ref}


def validate_claim_entities(claim: Mapping[str, Any], *, registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for field in ("subject", "object"):
        value = claim.get(field)
        if isinstance(value, Mapping) and value.get("kind") and value.get("ref"):
            result = validate_entity_ref(value, registry=registry)
            if result["status"] != "PASS":
                errors.append({"field": field, "errors": result["errors"]})
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors}


__all__ = ["ENTITY_BINDING_VERSION", "entity_binding_contract", "validate_entity_ref", "validate_claim_entities"]
