"""Provider-neutral helpers for the V7 first-order Claim V3 canary.

Executability is a type availability check only. This module never reads
source prose, entity display forms, evidence text, or story-specific values.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from .source_semantic_claim_v3 import (
    CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
    RELATION_SIGNATURE_REGISTRY_VERSION,
)


EXECUTABLE_PREDICATE_REGISTRY_VERSION = "source_claim_executable_predicate_registry_v1"
PROVIDER_ENTITY_VIEW_VERSION = "source_claim_provider_entity_view_v1"
PREDICATE_PROMPT_CONTRACT_VERSION = "source_claim_predicate_prompt_contract_v1"

_PREDICATE_DEFINITIONS = {
    "enter_guided": (
        "A character guides or escorts another person into a destination location. "
        "The current claim shape has no argument for the guided person. Omit an event "
        "when representing it would lose that participant; do not encode a person in a qualifier."
    ),
    "speech_act": (
        "A character is the speaker of one supplied dialogue-content entity. "
        "Use only the supplied character and dialogue-content references."
    ),
    "has_property": "An object has one typed property-value entity.",
    "state_value": "An environment has one typed state-value entity.",
    "received_by": "A character receives one object.",
    "left_by": "An object was left behind by one character.",
}


def claim_entity_kind_inventory(claim_input_entity_registry: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if claim_input_entity_registry.get("schema_version") != CLAIM_INPUT_ENTITY_REGISTRY_VERSION:
        errors.append("CLAIM_INPUT_ENTITY_REGISTRY_VERSION_INVALID")
    if claim_input_entity_registry.get("status") != "PASS":
        errors.append("CLAIM_INPUT_ENTITY_REGISTRY_NOT_READY")
    entities = claim_input_entity_registry.get("entities")
    if not isinstance(entities, Mapping):
        errors.append("CLAIM_INPUT_ENTITY_ROWS_INVALID")
        entities = {}
    counts: Counter[str] = Counter()
    for ref, row in entities.items():
        if not isinstance(row, Mapping) or not str(row.get("kind") or ""):
            errors.append(f"CLAIM_INPUT_ENTITY_KIND_INVALID:{ref}")
            continue
        counts[str(row["kind"])] += 1
    return {
        "schema_version": "source_claim_entity_kind_inventory_v1",
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "entity_count": sum(counts.values()),
        "kind_counts": dict(sorted(counts.items())),
        "registry_fingerprint": str(claim_input_entity_registry.get("fingerprint") or ""),
        "computed_from_entity_refs_and_kinds_only": True,
    }


def build_v7_7_8_1_forward_state_binding(
    *, baseline_commit: str, foundation_report: Mapping[str, Any],
    first_order_closure: Mapping[str, Any], second_order_closure: Mapping[str, Any],
) -> dict[str, Any]:
    checks = {
        "baseline_commit_exact": baseline_commit == "8fe2d0f7f6c5a0a5fcb1ce791a06b0bdb9196aee",
        "foundation_ready": foundation_report.get("foundation_state") == "SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY",
        "next_state_exact": foundation_report.get("next_state") == "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED",
        "first_order_unresolved_zero": first_order_closure.get("first_order_unresolved_count") == 0,
        "second_order_unresolved_zero": second_order_closure.get("second_order_unresolved_count") == 0,
        "second_order_execution_disabled": second_order_closure.get("execution_enabled") is False,
    }
    return {
        "schema_version": "v7_7_8_1_forward_state_binding_v1",
        "status": "PASS" if all(checks.values()) else "BLOCKED",
        "baseline_commit": baseline_commit,
        "foundation_state": str(foundation_report.get("foundation_state") or ""),
        "next_state": str(foundation_report.get("next_state") or ""),
        "first_order_unresolved_count": first_order_closure.get("first_order_unresolved_count"),
        "second_order_unresolved_count": second_order_closure.get("second_order_unresolved_count"),
        "second_order_execution_enabled": second_order_closure.get("execution_enabled"),
        "historical_recommended_next_action": "HISTORICAL_V7_7_8_ONLY",
        "historical_recommended_next_action_is_authorization_gate": False,
        "checks": checks,
        "failed_checks": [key for key, passed in checks.items() if not passed],
    }


def derive_executable_first_order_predicates(
    relation_signature_registry: Mapping[str, Any],
    claim_input_entity_registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Partition typed first-order predicates by available subject/object kinds.

    A predicate is executable if at least one allowed subject kind and at least
    one allowed object kind are present in the frozen entity registry. No text
    or predicate spelling is inspected to make this decision.
    """
    errors: list[str] = []
    if relation_signature_registry.get("schema_version") != RELATION_SIGNATURE_REGISTRY_VERSION:
        errors.append("RELATION_SIGNATURE_REGISTRY_VERSION_INVALID")
    signatures = relation_signature_registry.get("signatures")
    if not isinstance(signatures, Mapping):
        errors.append("RELATION_SIGNATURE_ROWS_INVALID")
        signatures = {}
    inventory = claim_entity_kind_inventory(claim_input_entity_registry)
    errors.extend(inventory.get("errors", []))
    kind_counts = inventory.get("kind_counts", {})

    executable: dict[str, dict[str, Any]] = {}
    dormant: dict[str, dict[str, Any]] = {}
    for predicate, raw_signature in sorted(signatures.items(), key=lambda item: str(item[0])):
        name = str(predicate)
        if not isinstance(raw_signature, Mapping):
            errors.append(f"RELATION_SIGNATURE_INVALID:{name}")
            continue
        subject_kinds = sorted({str(item) for item in raw_signature.get("allowed_subject_kinds", []) if str(item)})
        object_kinds = sorted({str(item) for item in raw_signature.get("allowed_object_kinds", []) if str(item)})
        if not subject_kinds or not object_kinds:
            errors.append(f"RELATION_KIND_DOMAIN_EMPTY:{name}")
            continue
        subject_counts = {kind: int(kind_counts.get(kind, 0)) for kind in subject_kinds}
        object_counts = {kind: int(kind_counts.get(kind, 0)) for kind in object_kinds}
        row = {
            **dict(raw_signature),
            "predicate": name,
            "available_subject_kind_counts": subject_counts,
            "available_object_kind_counts": object_counts,
            "execution_status": "EXECUTABLE" if any(subject_counts.values()) and any(object_counts.values()) else "TYPE_DEPENDENCY_UNAVAILABLE",
        }
        if row["execution_status"] == "EXECUTABLE":
            executable[name] = row
        else:
            dormant[name] = row
    return {
        "schema_version": EXECUTABLE_PREDICATE_REGISTRY_VERSION,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "predicates": executable,
        "dormant_predicates": dormant,
        "predicate_count": len(executable),
        "dormant_predicate_count": len(dormant),
        "unresolved_relation_count": len(errors),
        "semantics": "TYPE_EXECUTABLE != SOURCE_SUPPORTED",
        "source_prose_consulted": False,
        "surface_forms_consulted": False,
        "evidence_text_consulted": False,
        "predicate_name_semantics_inferred": False,
    }


def build_source_claim_provider_entity_view(
    claim_input_entity_registry: Mapping[str, Any],
    source_verified_entity_registry: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if claim_input_entity_registry.get("status") != "PASS":
        errors.append("CLAIM_INPUT_ENTITY_REGISTRY_NOT_READY")
    source_fingerprint = str(source_verified_entity_registry.get("fingerprint") or "")
    if source_fingerprint != str(claim_input_entity_registry.get("source_verified_entity_registry_fingerprint") or ""):
        errors.append("SOURCE_VERIFIED_ENTITY_REGISTRY_FINGERPRINT_MISMATCH")
    entities = claim_input_entity_registry.get("entities") if isinstance(claim_input_entity_registry.get("entities"), Mapping) else {}
    canonical = source_verified_entity_registry.get("canonical_runtime_entities") if isinstance(source_verified_entity_registry.get("canonical_runtime_entities"), Mapping) else {}
    proposals = source_verified_entity_registry.get("proposal_entities") if isinstance(source_verified_entity_registry.get("proposal_entities"), Mapping) else {}
    view: dict[str, dict[str, str]] = {}
    for ref, entity in sorted(entities.items(), key=lambda item: str(item[0])):
        if not isinstance(entity, Mapping):
            errors.append(f"CLAIM_INPUT_ENTITY_ROW_INVALID:{ref}")
            continue
        authority = str(entity.get("authority") or "")
        kind = str(entity.get("kind") or "")
        if authority == "CANONICAL_RUNTIME":
            source = canonical.get(ref)
            forms = source.get("display_forms") if isinstance(source, Mapping) else None
            if not isinstance(forms, list) or len(forms) != 1 or not isinstance(forms[0], str) or not forms[0]:
                errors.append(f"CANONICAL_DISPLAY_FORM_INVALID:{ref}")
                continue
            display_form = forms[0]
        elif authority == "SEMANTICALLY_VERIFIED_PROPOSAL":
            source = proposals.get(ref)
            display_form = str(source.get("surface_form") or "") if isinstance(source, Mapping) else ""
            if not display_form:
                errors.append(f"VERIFIED_PROPOSAL_SURFACE_FORM_INVALID:{ref}")
                continue
        else:
            errors.append(f"ENTITY_AUTHORITY_INVALID:{ref}")
            continue
        if isinstance(source, Mapping) and str(source.get("kind") or "") != kind:
            errors.append(f"ENTITY_KIND_FREEZE_MISMATCH:{ref}")
            continue
        view[str(ref)] = {
            "ref": str(ref),
            "kind": kind,
            "display_form": display_form,
            "authority": authority,
        }
    return {
        "schema_version": PROVIDER_ENTITY_VIEW_VERSION,
        "status": "PASS" if not errors and len(view) == len(entities) else "BLOCKED",
        "errors": sorted(set(errors)),
        "entities": view,
        "entity_count": len(view),
        "identity_authority": False,
        "provider_output_must_use_refs_only": True,
        "entity_identity_derived_from_display_form": False,
    }


def source_claim_predicate_prompt_contract(
    relation_signature_registry: Mapping[str, Any],
) -> dict[str, Any]:
    signatures = relation_signature_registry.get("signatures") if isinstance(relation_signature_registry.get("signatures"), Mapping) else {}
    errors: list[str] = []
    definitions: dict[str, dict[str, Any]] = {}
    for predicate, signature in sorted(signatures.items(), key=lambda item: str(item[0])):
        name = str(predicate)
        meaning = _PREDICATE_DEFINITIONS.get(name)
        if not isinstance(signature, Mapping) or not meaning:
            errors.append(f"PREDICATE_SEMANTIC_DEFINITION_MISSING:{name}")
            continue
        definitions[name] = {
            "predicate": name,
            "claim_type": str(signature.get("claim_type") or ""),
            "relation_class": str(signature.get("relation_class") or ""),
            "allowed_subject_kinds": list(signature.get("allowed_subject_kinds") or []),
            "allowed_object_kinds": list(signature.get("allowed_object_kinds") or []),
            "allowed_qualifier_keys": list(signature.get("allowed_qualifier_keys") or []),
            "required_qualifier_keys": list(signature.get("required_qualifier_keys") or []),
            "semantic_definition": meaning,
        }
    return {
        "schema_version": PREDICATE_PROMPT_CONTRACT_VERSION,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(errors),
        "predicates": definitions,
        "definitions_are_versioned_ontology": True,
        "story_specific_examples": False,
        "source_prose_used_to_define_predicates": False,
    }


def build_claim_v3_proposal_prompt(
    *,
    source_units: Sequence[Mapping[str, Any]],
    provider_entity_view: Mapping[str, Any],
    executable_predicate_registry: Mapping[str, Any],
    predicate_prompt_contract: Mapping[str, Any],
    qualifier_registry: Mapping[str, Any],
    polarities: Sequence[str],
    modalities: Sequence[str],
) -> tuple[str, str]:
    """Build a source-grounded proposal prompt from frozen, program-built views."""
    executable = executable_predicate_registry.get("predicates") if isinstance(executable_predicate_registry.get("predicates"), Mapping) else {}
    definitions = predicate_prompt_contract.get("predicates") if isinstance(predicate_prompt_contract.get("predicates"), Mapping) else {}
    predicate_view = {name: definitions[name] for name in sorted(executable) if name in definitions}
    qualifiers = qualifier_registry.get("qualifiers") if isinstance(qualifier_registry.get("qualifiers"), Mapping) else {}
    system = (
        "Propose zero or more atomic FIRST_ORDER source claims supported by the supplied immutable source evidence. "
        "Return exactly one JSON object matching the provided strict schema and no markdown. "
        "A source unit may produce zero or more claims. Propose only a fully expressible relation whose complete typed meaning is explicitly supported. "
        "Do not force source meaning into the closest available predicate. If the current relation has no argument needed to preserve a source participant or other meaning, omit that claim. "
        "Do not invent entities, values, participants, events, motives, or facts. Preserve polarity and modality. "
        "Use only entity refs from the supplied entity view; display_form is explanatory text and never establishes identity. "
        "Use only the executable predicates and their definitions below. Provider output contains refs, predicate, qualifiers, polarity, modality, evidence_refs, and source_unit_refs only. "
        "Do not return kinds, claim_type, relation_class, candidate IDs, claim IDs, authority, or canonical status."
    )
    evidence_rows: list[dict[str, Any]] = []
    for unit in source_units:
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        evidence_text = str(evidence.get("text") or "")
        source_row = {
            "source_unit_ref": str(unit.get("unit_id") or ""),
            "source_type": str(unit.get("source_type") or ""),
            "evidence": [{
                "evidence_ref": str(evidence.get("evidence_id") or ""),
                "text": evidence_text,
            }],
        }
        if isinstance(unit.get("speaker"), str) and unit["speaker"]:
            source_row["speaker_display_form"] = unit["speaker"]
        evidence_rows.append(source_row)
    user = (
        "Ontology and output instructions:\n"
        + "- SourceAuthoringUnit maps to zero or more claims.\n"
        + "- Every candidate is one typed relation. Never pack multiple facts into a qualifier or ref.\n"
        + "- If a relation cannot preserve all required source meaning, omit it.\n"
        + "- Type-executable means a compatible ref kind exists; it does not mean the source supports a claim.\n"
        + "- An empty claims array is valid when nothing is both supported and fully expressible.\n\n"
        + "Executable predicate definitions:\n"
        + __import__("json").dumps(predicate_view, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n\nAllowed qualifier definitions (wire values are strings):\n"
        + __import__("json").dumps(qualifiers, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n\nAllowed entity refs (display forms are explanatory only):\n"
        + __import__("json").dumps(provider_entity_view.get("entities", {}), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n\nAllowed polarity values:\n"
        + __import__("json").dumps(list(polarities), ensure_ascii=False)
        + "\n\nAllowed modality values:\n"
        + __import__("json").dumps(list(modalities), ensure_ascii=False)
        + "\n\nImmutable source units and exact evidence text:\n"
        + __import__("json").dumps(evidence_rows, ensure_ascii=False, sort_keys=True, indent=2)
    )
    return system, user


__all__ = [
    "EXECUTABLE_PREDICATE_REGISTRY_VERSION", "PROVIDER_ENTITY_VIEW_VERSION",
    "PREDICATE_PROMPT_CONTRACT_VERSION", "claim_entity_kind_inventory",
    "build_v7_7_8_1_forward_state_binding",
    "derive_executable_first_order_predicates", "build_source_claim_provider_entity_view",
    "source_claim_predicate_prompt_contract", "build_claim_v3_proposal_prompt",
]
