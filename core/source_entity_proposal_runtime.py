"""Provider-free binding and existing-entity audit for V7.7.6 proposals."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .provider_structured_output_qualification import (
    QUALIFICATION_VERSION,
    fingerprint,
    provider_identity,
    qualification_fingerprint,
)
from .source_entity_proposal import ENTITY_KINDS


def build_existing_canonical_registry(
    *,
    base_registry: Mapping[str, Any],
    script_ir: Mapping[str, Any],
    source_units: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Enrich runtime refs from their upstream declarations, without inference."""
    registry: dict[str, dict[str, Any]] = {}
    for ref, raw in base_registry.items():
        row = dict(raw) if isinstance(raw, Mapping) else {}
        registry[str(ref)] = {
            "ref": str(ref),
            "kind": str(row.get("kind") or "UNKNOWN_ENTITY"),
            "source": str(row.get("source") or "runtime"),
            "display_forms": [str(ref)],
            "evidence_refs": [],
            "evidence_identities": [],
        }

    for scene in script_ir.get("scenes", []) if isinstance(script_ir.get("scenes"), list) else []:
        if not isinstance(scene, Mapping):
            continue
        scene_ref = str(scene.get("scene_id") or "")
        if scene_ref and scene_ref in registry:
            display_forms = [scene.get(key) for key in ("display_name", "name", "location_name")]
            registry[scene_ref]["display_forms"] = sorted({str(value) for value in display_forms if isinstance(value, str) and value.strip()} | {scene_ref})
            registry[scene_ref]["source_evidence_refs"] = [str(row.get("evidence_id")) for row in scene.get("source_identity_evidence", []) if isinstance(row, Mapping) and row.get("evidence_id")]
            registry[scene_ref]["evidence_refs"] = list(registry[scene_ref]["source_evidence_refs"])
            registry[scene_ref]["evidence_identities"] = [str(row.get("sha256")) for row in scene.get("source_identity_evidence", []) if isinstance(row, Mapping) and row.get("sha256")]

        participants = scene.get("participants") if isinstance(scene.get("participants"), list) else []
        for participant in participants:
            if not isinstance(participant, Mapping):
                continue
            ref = str(participant.get("character_id") or participant.get("id") or "")
            if not ref or ref not in registry:
                continue
            forms = {ref}
            for key in ("name", "display_name", "character_name"):
                value = participant.get(key)
                if isinstance(value, str) and value.strip():
                    forms.add(value)
            registry[ref]["display_forms"] = sorted(forms)
            evidence_rows = participant.get("evidence") if isinstance(participant.get("evidence"), list) else []
            registry[ref]["evidence_refs"] = sorted({str(row.get("evidence_id")) for row in evidence_rows if isinstance(row, Mapping) and row.get("evidence_id")})
            registry[ref]["evidence_identities"] = sorted({str(row.get("sha256")) for row in evidence_rows if isinstance(row, Mapping) and row.get("sha256")})

    for unit in source_units:
        if not isinstance(unit, Mapping) or unit.get("source_type") != "SOURCE_DIALOGUE":
            continue
        ref = str(unit.get("unit_id") or "")
        if ref and ref in registry:
            evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
            registry[ref]["display_forms"] = [str(unit.get("source_ref") or ref)]
            registry[ref]["evidence_refs"] = [str(item) for item in unit.get("source_evidence_refs", [])]
            registry[ref]["evidence_identities"] = [str(evidence.get("sha256"))] if evidence.get("sha256") else []

    return {"schema_version": "source_canonical_entity_registry_snapshot_v1", "authority": "CANONICAL_RUNTIME", "entities": registry}


def validate_entity_evidence_binding(
    candidate: Mapping[str, Any],
    *,
    evidence_index: Mapping[str, Any],
    source_fingerprint: str,
    source_package_id: str,
) -> dict[str, Any]:
    evidence_refs = candidate.get("evidence_refs") if isinstance(candidate.get("evidence_refs"), list) else []
    source_unit_refs = candidate.get("source_unit_refs") if isinstance(candidate.get("source_unit_refs"), list) else []
    anchors = {str(row.get("anchor_ref")): row for row in evidence_index.get("anchors", []) if isinstance(row, Mapping) and row.get("anchor_ref")}
    errors: list[str] = []
    resolved: list[dict[str, Any]] = []
    for ref in evidence_refs:
        key = str(ref)
        anchor = anchors.get(key)
        if not anchor:
            errors.append(f"EVIDENCE_REF_MISSING:{key}")
            continue
        anchor_fingerprint = str(anchor.get("source_fingerprint") or "")
        if anchor_fingerprint and source_fingerprint and anchor_fingerprint != source_fingerprint:
            errors.append(f"EVIDENCE_STALE:{key}")
        anchor_package = str(anchor.get("source_package_id") or "")
        if anchor_package and source_package_id and anchor_package != source_package_id:
            errors.append(f"EVIDENCE_PACKAGE_MISMATCH:{key}")
        owner = str(anchor.get("unit_id") or "")
        if owner not in {str(item) for item in source_unit_refs}:
            errors.append(f"EVIDENCE_NOT_BOUND_TO_SOURCE_UNIT:{key}")
        resolved.append({"evidence_ref": key, "source_unit_id": owner, "sha256": str(anchor.get("sha256") or ""), "source_fingerprint": anchor_fingerprint, "source_package_id": anchor_package})
    if not evidence_refs:
        errors.append("EVIDENCE_REFS_EMPTY")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "resolved": resolved}


def validate_entity_source_unit_binding(candidate: Mapping[str, Any], *, unit_evidence_map: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    refs = candidate.get("source_unit_refs") if isinstance(candidate.get("source_unit_refs"), list) else []
    evidence_refs = candidate.get("evidence_refs") if isinstance(candidate.get("evidence_refs"), list) else []
    errors: list[str] = []
    for ref in refs:
        if str(ref) not in unit_evidence_map:
            errors.append(f"SOURCE_UNIT_REF_MISSING:{ref}")
    owners: list[str] = []
    for evidence_ref in evidence_refs:
        owner = next((str(unit_id) for unit_id, owned in unit_evidence_map.items() if str(evidence_ref) in {str(item) for item in owned}), None)
        if owner is None:
            errors.append(f"EVIDENCE_OWNER_UNKNOWN:{evidence_ref}")
        elif owner not in {str(item) for item in refs}:
            errors.append(f"EVIDENCE_NOT_BOUND_TO_SOURCE_UNIT:{evidence_ref}")
        else:
            owners.append(owner)
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "resolved_source_unit_ids": sorted(set(owners))}


def validate_entity_surface_binding(candidate: Mapping[str, Any], *, evidence_index: Mapping[str, Any], unit_evidence_map: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    refs = {str(item) for item in candidate.get("evidence_refs", [])} if isinstance(candidate.get("evidence_refs"), list) else set()
    declared_units = {str(item) for item in candidate.get("source_unit_refs", [])} if isinstance(candidate.get("source_unit_refs"), list) else set()
    anchors = {str(row.get("anchor_ref")): row for row in evidence_index.get("anchors", []) if isinstance(row, Mapping) and row.get("anchor_ref")}
    surface = candidate.get("surface_form")
    if not isinstance(surface, str) or not surface:
        return {"status": "BLOCKED", "errors": ["SURFACE_FORM_INVALID"], "matched_evidence_refs": []}
    matched: list[str] = []
    for ref in refs:
        anchor = anchors.get(ref)
        if not anchor or str(anchor.get("unit_id") or "") not in declared_units:
            continue
        owned = {str(item) for item in unit_evidence_map.get(str(anchor.get("unit_id") or ""), [])}
        if ref not in owned:
            continue
        evidence_text = anchor.get("text")
        if isinstance(evidence_text, str) and surface in evidence_text:
            matched.append(ref)
    errors = [] if matched else ["SURFACE_FORM_NOT_IN_ANY_BOUND_EVIDENCE"]
    return {"status": "PASS" if matched else "BLOCKED", "errors": errors, "matched_evidence_refs": sorted(set(matched))}


def exact_existing_entity_duplicate(candidate: Mapping[str, Any], *, canonical_registry: Mapping[str, Any], evidence_index: Mapping[str, Any]) -> dict[str, Any]:
    entities = canonical_registry.get("entities", {}) if isinstance(canonical_registry.get("entities"), Mapping) else {}
    candidate_kind = str(candidate.get("kind") or "")
    surface = candidate.get("surface_form")
    refs = {str(item) for item in candidate.get("evidence_refs", [])} if isinstance(candidate.get("evidence_refs"), list) else set()
    anchor_by_ref = {str(row.get("anchor_ref")): row for row in evidence_index.get("anchors", []) if isinstance(row, Mapping)}
    candidate_sha = {str(anchor_by_ref[ref].get("sha256")) for ref in refs if ref in anchor_by_ref and anchor_by_ref[ref].get("sha256")}
    matches: list[dict[str, Any]] = []
    for ref, entity in entities.items():
        if not isinstance(entity, Mapping) or str(entity.get("kind") or "") != candidate_kind:
            continue
        forms = {str(item) for item in entity.get("display_forms", []) if isinstance(item, str)}
        canonical_evidence_refs = {str(item) for item in entity.get("evidence_refs", [])}
        canonical_sha = {str(item) for item in entity.get("evidence_identities", [])}
        display_match = isinstance(surface, str) and surface in forms
        evidence_id_match = bool(refs & canonical_evidence_refs)
        evidence_hash_match = bool(candidate_sha & canonical_sha)
        if display_match:
            matches.append({"canonical_ref": str(ref), "kind": candidate_kind, "match_basis": "EXACT_KIND_AND_DISPLAY", "evidence_identity_match": evidence_id_match or evidence_hash_match, "authority": "CANONICAL_RUNTIME"})
    return {"status": "ALREADY_CANONICAL_ENTITY" if matches else "NOT_CANONICAL_DUPLICATE", "matches": matches, "promotion_allowed": False if matches else None, "fuzzy_match_used": False}


def validate_proposal_kind(value: Any) -> bool:
    return value in ENTITY_KINDS


def qualification_freshness_gate(*, profile_identity: Mapping[str, Any], qualification: Mapping[str, Any], expected_qualification_fingerprint: str) -> dict[str, Any]:
    current_identity = provider_identity(
        profile_id=str(profile_identity.get("profile_id") or ""),
        provider=str(profile_identity.get("provider") or ""),
        model=str(profile_identity.get("model") or ""),
        base_host=str(profile_identity.get("base_host") or ""),
    )
    recomputed = qualification_fingerprint(
        identity=current_identity,
        capability=str(qualification.get("capability") or ""),
        probe_schema_fingerprint=str(qualification.get("probe_schema_fingerprint") or ""),
        request_fingerprint=str(qualification.get("request_fingerprint") or ""),
        raw_response_sha256=str(qualification.get("raw_response_sha256") or ""),
        qualified=qualification.get("qualified") is True,
    )
    checks = {
        "qualification_schema_version": qualification.get("schema_version") == QUALIFICATION_VERSION,
        "profile_id": current_identity.get("profile_id") == qualification.get("profile_id"),
        "provider": current_identity.get("provider") == qualification.get("provider"),
        "model": current_identity.get("model") == qualification.get("model"),
        "base_host": current_identity.get("base_host") == qualification.get("base_host"),
        "provider_identity_fingerprint": current_identity.get("provider_identity_fingerprint") == qualification.get("provider_identity_fingerprint"),
        "strict_capability": qualification.get("capability") == "JSON_SCHEMA_STRICT_SUPPORTED",
        "qualified": qualification.get("qualified") is True,
        "qualification_fingerprint_recomputed": recomputed.get("qualification_fingerprint") == qualification.get("qualification_fingerprint") == expected_qualification_fingerprint,
    }
    return {"status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks, "failed_checks": [key for key, value in checks.items() if not value], "current_identity": current_identity, "qualification_fingerprint": qualification.get("qualification_fingerprint")}


def classify_entity_proposal_result(*, candidate_count: int, valid_count: int) -> str:
    if candidate_count <= 0:
        return "SOURCE_ENTITY_PROPOSAL_EMPTY_REVIEW_REQUIRED"
    if valid_count <= 0:
        return "SOURCE_ENTITY_PROPOSAL_BINDING_BLOCKED"
    return "SOURCE_ENTITY_PROPOSAL_VALIDATED"


__all__ = ["build_existing_canonical_registry", "validate_entity_evidence_binding", "validate_entity_source_unit_binding", "validate_entity_surface_binding", "exact_existing_entity_duplicate", "validate_proposal_kind", "qualification_freshness_gate", "classify_entity_proposal_result"]
