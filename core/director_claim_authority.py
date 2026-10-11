"""Versioned authority rules for Director ClaimIR.

The matrix is deliberately declarative.  It does not inspect phrase text and
therefore cannot grow a one-off exception for a historical response.
"""
from __future__ import annotations

from typing import Any, Mapping

from .director_claim_ir import AUTHORITIES, CLAIM_TYPES


AUTHORITY_MATRIX_VERSION = "director_claim_authority_matrix_v1"

SOURCE_AUTHORITY = {
    "SOURCE_EVENT", "CHARACTER_ACTION", "CHARACTER_KNOWLEDGE", "CHARACTER_EMOTION",
    "CHARACTER_RELATIONSHIP", "CHARACTER_BACKSTORY", "OBJECT_EXISTENCE", "OBJECT_PROPERTY",
    "OBJECT_OWNERSHIP", "OBJECT_PROVENANCE", "OBJECT_POSSESSION", "ENVIRONMENT_STATE",
    "SENSORY_FACT", "UNCERTAINTY", "CERTAINTY_ASSERTION", "INFORMATION_REVEAL",
    "INFORMATION_WITHHOLD",
}
STAGE_A_OWNED = {"DRAMATIC_GROUPING", "DRAMATIC_OBJECTIVE", "DRAMATIC_QUESTION", "AUDIENCE_INTERPRETATION"}
STAGE_B_OWNED = {
    "PERFORMANCE_DIRECTION", "PERFORMANCE_OPTION", "AUDIENCE_EFFECT", "AUDIENCE_INTERPRETATION",
    "INFORMATION_REVEAL", "INFORMATION_WITHHOLD", "INFORMATION_STRATEGY", "RHYTHM_INTENT",
    "VISUAL_PRIORITY", "META_COMPLIANCE", "AUTHORITY_DELEGATION", "PROHIBITION",
}
DOWNSTREAM_FORBIDDEN = {"SPATIAL_BLOCKING", "SHOT_EXECUTION"}
SOURCE_REQUIRED_CANONICAL = {
    "SOURCE_EVENT", "CHARACTER_ACTION", "CHARACTER_KNOWLEDGE", "CHARACTER_INTENT", "CHARACTER_EMOTION",
    "CHARACTER_RELATIONSHIP", "CHARACTER_BACKSTORY", "OBJECT_EXISTENCE", "OBJECT_PROPERTY",
    "OBJECT_OWNERSHIP", "OBJECT_PROVENANCE", "OBJECT_POSSESSION", "ENVIRONMENT_STATE", "SENSORY_FACT",
    "SPATIAL_BLOCKING", "SHOT_EXECUTION", "CERTAINTY_ASSERTION", "UNCERTAINTY",
}


def authority_matrix() -> dict[str, Any]:
    return {
        "schema_version": AUTHORITY_MATRIX_VERSION,
        "principle": "Stage A may organize Source facts but may not promote unsupported interpretation into source-equivalent authority.",
        "precedence": ["SOURCE", "STAGE_A", "STAGE_B", "NONE"],
        "origins": {
            "SOURCE": {"allowed_claim_types": sorted(SOURCE_AUTHORITY), "authority_role": "canonical_source_fact"},
            "STAGE_A": {"allowed_claim_types": sorted(STAGE_A_OWNED), "source_support_required_for": sorted(SOURCE_REQUIRED_CANONICAL), "authority_role": "dramatic_organization_only"},
            "STAGE_B": {"allowed_claim_types": sorted(STAGE_B_OWNED), "source_support_required_for": sorted(SOURCE_REQUIRED_CANONICAL), "forbidden_claim_types": sorted(DOWNSTREAM_FORBIDDEN), "authority_role": "creative_presentation_only"},
            "COMPILED": {"allowed_claim_types": sorted(CLAIM_TYPES), "inherits_upstream_support": True, "authority_role": "derived_projection_not_new_authority"},
        },
        "non_canonical_safe": ["PERFORMANCE_OPTION", "AUDIENCE_EFFECT", "AUDIENCE_INTERPRETATION", "AUTHORITY_DELEGATION", "META_COMPLIANCE", "PROHIBITION"],
        "no_phrase_exceptions": True,
    }


def authority_requirement(claim: Mapping[str, Any]) -> dict[str, Any]:
    origin = str(claim.get("origin") or "")
    claim_type = str(claim.get("claim_type") or "")
    canonicality = str(claim.get("canonicality") or "")
    if claim_type not in CLAIM_TYPES:
        return {"status": "BLOCKED", "authority_required": "SOURCE", "reason": "UNKNOWN_CLAIM_TYPE"}
    if claim_type == "AUTHORITY_DELEGATION" or claim_type == "META_COMPLIANCE" or canonicality == "META":
        return {"status": "META_SAFE", "authority_required": "NONE", "reason": "metadata_or_delegation_does_not_assert_story_fact"}
    if canonicality == "NON_CANONICAL_PERFORMANCE_OPTION" or str(claim.get("modality")) == "PLAYABLE_OPTION":
        return {"status": "NON_CANONICAL_OPTION", "authority_required": "STAGE_B", "reason": "explicit_playable_non_canonical_option"}
    if origin == "SOURCE":
        return {"status": "SOURCE_AUTHORITY", "authority_required": "SOURCE", "reason": "source_authoring_unit_is_canonical_input"}
    if origin == "STAGE_A":
        if claim_type in STAGE_A_OWNED:
            return {"status": "STAGE_A_AUTHORITY", "authority_required": "STAGE_A", "reason": "stage_a_dramatic_organization"}
        return {"status": "SOURCE_SUPPORT_REQUIRED", "authority_required": "SOURCE", "reason": "stage_a_cannot_bootstrap_canonical_fact"}
    if origin in {"STAGE_B", "COMPILED"}:
        if claim_type in DOWNSTREAM_FORBIDDEN:
            return {"status": "DOWNSTREAM_FORBIDDEN", "authority_required": "NONE", "reason": "claim belongs to SceneBlocking or ShotPlan"}
        if claim_type in STAGE_B_OWNED:
            return {"status": "STAGE_B_AUTHORITY", "authority_required": "STAGE_B", "reason": "creative_presentation_claim"}
        return {"status": "SOURCE_SUPPORT_REQUIRED", "authority_required": "SOURCE", "reason": "stage_b cannot create a new canonical fact"}
    return {"status": "BLOCKED", "authority_required": "SOURCE", "reason": "UNKNOWN_ORIGIN"}


def validate_authority_matrix() -> dict[str, Any]:
    matrix = authority_matrix()
    errors = []
    if "SPATIAL_BLOCKING" not in matrix["origins"]["STAGE_B"]["forbidden_claim_types"]:
        errors.append("STAGE_B_SPATIAL_BLOCKING_NOT_FORBIDDEN")
    if "SHOT_EXECUTION" not in matrix["origins"]["STAGE_B"]["forbidden_claim_types"]:
        errors.append("STAGE_B_SHOT_EXECUTION_NOT_FORBIDDEN")
    if "DRAMATIC_OBJECTIVE" not in matrix["origins"]["STAGE_A"]["allowed_claim_types"]:
        errors.append("STAGE_A_OBJECTIVE_NOT_ALLOWED")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "schema_version": AUTHORITY_MATRIX_VERSION}


__all__ = ["AUTHORITY_MATRIX_VERSION", "SOURCE_AUTHORITY", "STAGE_A_OWNED", "STAGE_B_OWNED", "DOWNSTREAM_FORBIDDEN", "authority_matrix", "authority_requirement", "validate_authority_matrix"]
