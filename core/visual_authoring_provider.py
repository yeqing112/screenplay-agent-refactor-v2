"""Deterministic contract and validator for visual authoring providers.

This module intentionally contains no provider transport and no database writes.
It is the hard boundary between a provider's creative suggestion and the
authority spine.  A valid result is still only a proposal for human review.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.prompt_cache import canonical_json


VISUAL_AUTHORING_PROVIDER_CONTRACT_VERSION = "visual_authoring_provider_contract_v1"
VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION = "visual_authoring_proposal_v1"
PROPOSAL_STATUSES = {"CANDIDATE", "VALIDATED", "REVIEW_REQUIRED", "REJECTED", "SUPERSEDED"}

ALLOWED_FIELDS = {
    "character": {
        "face", "facial_structure", "baseline_hairstyle", "body_type", "wardrobe",
        "accessories", "makeup", "color_palette", "visual_temperament", "silhouette",
    },
    "scene": {
        "architecture_style", "materials", "texture", "palette", "lighting_look",
        "set_dressing", "atmosphere", "surface_finish", "spatial_mood",
    },
    "prop": {
        "material", "finish", "color_palette", "wear_pattern", "style",
        "visual_detail", "silhouette", "surface_texture",
    },
}

# Names that may look useful to a model but are authority/production fields.
FORBIDDEN_FIELDS = {
    "source_facts", "source_constraints", "authority_status", "approved", "confirmed",
    "status", "version_id", "visual_asset_version_id", "pointer", "reference_authority",
    "checksum", "asset_authority_fingerprint", "geometry", "geometry_mutation",
    "continuity", "continuity_mutation", "media_url", "image_reference", "prompt_ir",
    "prompt_ir_version", "prompt", "visual_prompt_zh", "visual_prompt_en",
    "core_prompt_zh", "core_prompt_en", "outfit_prompt_zh", "outfit_prompt_en",
    "authority_prompt_raw", "asset_id", "character_id", "canonical_id",
}

REASON_CODES = {
    "PROVIDER_OUTPUT_FORBIDDEN_FIELD",
    "PROPOSAL_FIELD_OUT_OF_SCOPE",
    "SOURCE_VISUAL_CONSTRAINT_CONFLICT",
    "PROPOSAL_REQUEST_MISMATCH",
    "PROPOSAL_ASSET_MISMATCH",
    "PROPOSAL_SCOPE_MISMATCH",
    "PROPOSAL_SCHEMA_INVALID",
    "PROPOSAL_DUPLICATE_CONFLICT",
    "PROPOSAL_UNKNOWN_ALLOWED",
    "GEOMETRY_CONSTRAINT_CONFLICT",
    "CONTINUITY_CONSTRAINT_CONFLICT",
}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def proposal_payload_fingerprint(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _normal_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_forbidden(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_FIELDS:
                found.append(f"{path}.{key}" if path else str(key))
            found.extend(_contains_forbidden(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_contains_forbidden(item, f"{path}[{index}]"))
    return found


def _constraint_conflict(field: str, value: Any, constraints: dict) -> bool:
    """Compare only explicit structured constraints; silence is not a conflict."""
    if field not in constraints or constraints[field] in (None, "", [], {}):
        return False
    expected = constraints[field]
    if isinstance(expected, list):
        return _normal_text(value) not in {_normal_text(item) for item in expected}
    if isinstance(expected, dict):
        return _normal_text(value) != _normal_text(expected.get("value"))
    return _normal_text(value) != _normal_text(expected)


def build_visual_authoring_provider_context(
    *,
    request: dict,
    asset: dict | None = None,
    authoritative_context: dict | None = None,
) -> dict:
    """Build the smallest immutable task context sent to a provider.

    Legacy raw prompt fields are deliberately omitted even when present in
    ``asset``.  The caller may include a bounded ``advisory_legacy_context``
    explicitly, but it is never promoted to a constraint by this function.
    """
    req = _as_dict(request)
    asset_value = _as_dict(asset)
    authority = _as_dict(authoritative_context)
    source_constraints = _as_dict(req.get("source_constraints"))
    free_space = [str(item).strip() for item in _as_list(req.get("free_authoring_space")) if str(item).strip()]
    forbidden = [str(item).strip() for item in _as_list(req.get("forbidden_contradictions")) if str(item).strip()]
    structured_asset = {
        key: value for key, value in asset_value.items()
        if key not in FORBIDDEN_FIELDS and not key.endswith("_prompt_zh")
        and not key.endswith("_prompt_en") and not key.startswith("core_prompt")
        and not key.startswith("outfit_prompt") and key not in {"authority_prompt_raw", "media_url", "image_url"}
    }
    return {
        "contract_version": VISUAL_AUTHORING_PROVIDER_CONTRACT_VERSION,
        "request_id": str(req.get("request_id") or ""),
        "book_id": req.get("book_id"),
        "asset_key": str(req.get("asset_key") or ""),
        "asset_type": str(req.get("asset_type") or ""),
        "canonical_id": str(req.get("canonical_id") or ""),
        "scope": _as_dict(req.get("scope")),
        "source_constraints": source_constraints,
        "free_authoring_space": free_space,
        "forbidden_contradictions": forbidden,
        "structured_asset_context": structured_asset,
        "authoritative_context": authority,
        "advisory_legacy_context": _as_dict(req.get("advisory_legacy_context")),
    }


def build_visual_authoring_provider_prompt(context: dict) -> tuple[str, str]:
    system = (
        "You are a conservative visual authoring assistant. Return only one JSON object. "
        "You may PROPOSE design fields in the declared free_authoring_space only. "
        "Never return approval, authority, version, pointer, reference, prompt, media, geometry, "
        "or continuity mutation fields. Preserve unknowns instead of inventing facts."
    )
    user = canonical_json({
        "schema_version": VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
        "task_context": context,
        "output_contract": {
            "schema_version": VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
            "request_id": context.get("request_id"),
            "asset_key": context.get("asset_key"),
            "proposals": [{"field": "", "value": None, "scope": {}, "design_intent": "", "constraint_refs": []}],
            "unknowns": [],
            "review_notes": [],
        },
    })
    return system, user


def validate_visual_authoring_proposal(
    raw: Any,
    *,
    request: dict,
    context: dict | None = None,
) -> dict:
    """Validate provider output without mutating any authority artifact."""
    diagnostics: list[dict] = []
    payload = raw if isinstance(raw, dict) else None
    req = _as_dict(request)
    if payload is None:
        return {"ok": False, "status": "REJECTED", "reason_codes": ["PROPOSAL_SCHEMA_INVALID"], "diagnostics": [{"code": "PROPOSAL_SCHEMA_INVALID", "message": "output must be an object"}]}
    forbidden = _contains_forbidden(payload)
    if forbidden:
        diagnostics.append({"code": "PROVIDER_OUTPUT_FORBIDDEN_FIELD", "paths": forbidden})
    if payload.get("schema_version") != VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION:
        diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "message": "schema_version mismatch"})
    for identity, code in (("request_id", "PROPOSAL_REQUEST_MISMATCH"), ("asset_key", "PROPOSAL_ASSET_MISMATCH")):
        if str(payload.get(identity) or "") != str(req.get(identity) or ""):
            diagnostics.append({"code": code, "expected": req.get(identity), "actual": payload.get(identity)})
    if "asset_type" in payload and str(payload.get("asset_type")) != str(req.get("asset_type") or ""):
        diagnostics.append({"code": "PROPOSAL_SCOPE_MISMATCH", "message": "asset_type mismatch"})
    proposals = payload.get("proposals")
    if not isinstance(proposals, list):
        diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "message": "proposals must be a list"})
        proposals = []
    allowed = set(_as_list(req.get("free_authoring_space"))) or ALLOWED_FIELDS.get(str(req.get("asset_type") or ""), set())
    source_constraints = _as_dict(req.get("source_constraints"))
    forbidden_contradictions = {str(item).strip() for item in _as_list(req.get("forbidden_contradictions"))}
    authority = _as_dict(_as_dict(context).get("authoritative_context"))
    geometry_authority = _as_dict(authority.get("geometry"))
    continuity_authority = _as_dict(authority.get("continuity"))
    seen: dict[str, str] = {}
    normalized: list[dict] = []
    for index, item in enumerate(proposals):
        if not isinstance(item, dict):
            diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "index": index, "message": "proposal item must be an object"})
            continue
        field = str(item.get("field") or "").strip()
        if not field or not {"field", "value", "scope", "design_intent", "constraint_refs"}.issubset(item):
            diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "index": index, "message": "proposal item fields incomplete"})
            continue
        if field.lower() in FORBIDDEN_FIELDS or field not in allowed:
            diagnostics.append({"code": "PROPOSAL_FIELD_OUT_OF_SCOPE", "field": field})
        if _constraint_conflict(field, item.get("value"), source_constraints):
            diagnostics.append({"code": "SOURCE_VISUAL_CONSTRAINT_CONFLICT", "field": field})
        if field in forbidden_contradictions:
            diagnostics.append({"code": "SOURCE_VISUAL_CONSTRAINT_CONFLICT", "field": field, "message": "forbidden contradiction"})
        field_lower = field.lower()
        if geometry_authority and any(token in field_lower for token in ("geometry", "door", "window", "spatial", "blocking", "zone")):
            diagnostics.append({"code": "GEOMETRY_CONSTRAINT_CONFLICT", "field": field})
        if continuity_authority and any(token in field_lower for token in ("continuity", "holder", "position", "open_state", "closed_state", "damaged_state")):
            diagnostics.append({"code": "CONTINUITY_CONSTRAINT_CONFLICT", "field": field})
        value_key = canonical_json(item.get("value"))
        if field in seen and seen[field] != value_key:
            diagnostics.append({"code": "PROPOSAL_DUPLICATE_CONFLICT", "field": field})
        seen[field] = value_key
        normalized.append({
            "field": field,
            "value": item.get("value"),
            "scope": _as_dict(item.get("scope")),
            "design_intent": str(item.get("design_intent") or ""),
            "constraint_refs": [str(ref) for ref in _as_list(item.get("constraint_refs"))],
        })
    unknowns = payload.get("unknowns", [])
    if unknowns is None:
        unknowns = []
    if not isinstance(unknowns, list) or any(not isinstance(item, str) for item in unknowns):
        diagnostics.append({"code": "PROPOSAL_UNKNOWN_ALLOWED", "message": "unknowns must be a list of strings"})
        unknowns = []
    reason_codes = list(dict.fromkeys(item["code"] for item in diagnostics))
    ok = not reason_codes
    return {
        "ok": ok,
        "status": "REVIEW_REQUIRED" if ok else "REJECTED",
        "reason_codes": reason_codes,
        "diagnostics": diagnostics,
        "normalized": {
            "schema_version": VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
            "request_id": str(payload.get("request_id") or ""),
            "asset_key": str(payload.get("asset_key") or ""),
            "asset_type": str(req.get("asset_type") or ""),
            "proposals": normalized,
            "unknowns": [str(item) for item in unknowns],
            "review_notes": [str(item) for item in _as_list(payload.get("review_notes"))],
        },
    }
