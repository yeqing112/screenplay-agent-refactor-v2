"""Provider-only visual authoring contract.

The provider may suggest bounded visual fields, but this module never writes
canonical versions, pointers, references, or PromptIR.  The returned status
is always review material until a human creates field-level authority
decisions through the canonical Authority API.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from core.prompt_cache import canonical_json


VISUAL_AUTHORING_PROVIDER_CONTRACT_VERSION = "visual_authoring_provider_contract_v2"
VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION = "visual_authoring_proposal_v2"

ALLOWED_FIELDS = {
    "character": {
        "face", "facial_structure", "apparent_age", "body_type", "skin",
        "baseline_hairstyle", "persistent_features", "canonical_temperament",
        "wardrobe", "hairstyle", "makeup", "injury", "dirt_blood_wetness",
        "accessories", "age_stage", "expression",
    },
    "scene": {
        "material", "texture", "architecture_style", "color_palette",
        "lighting_look", "fixed_fixtures", "atmosphere", "visual_condition",
        "state", "weather", "time_of_day", "dressing", "lighting_variant",
    },
    "prop": {
        "basic_form", "material", "color", "distinctive_features", "open_closed",
        "condition", "holder", "position", "story_state",
    },
}

FORBIDDEN_FIELDS = {
    "source_facts", "source_constraints", "authority_status", "approved", "confirmed",
    "status", "version_id", "visual_asset_version_id", "pointer", "reference_authority",
    "checksum", "asset_authority_fingerprint", "geometry", "geometry_mutation",
    "continuity", "continuity_mutation", "media_url", "image_reference", "prompt_ir",
    "prompt_ir_version", "prompt", "visual_prompt_zh", "visual_prompt_en", "asset_id",
    "character_id", "scene_id", "prop_id", "canonical_id", "asset_key",
}


def proposal_payload_fingerprint(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _field_value(item: Any) -> tuple[str, Any]:
    item = _as_dict(item)
    field = str(item.get("field") or item.get("predicate") or item.get("key") or "").strip()
    value = item.get("value", item.get("fact_value", item.get("content")))
    return field, value


def _constraint_map(items: Iterable[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        field, value = _field_value(item)
        if field:
            result[field] = value
    return result


def _normal(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_forbidden(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_name = str(key).strip().lower()
            current = f"{path}.{key}" if path else str(key)
            # ``asset_key`` is required at the envelope root; it is forbidden
            # only when a provider attempts to smuggle it into a proposal or
            # nested authority payload.
            if key_name in FORBIDDEN_FIELDS and not (not path and key_name == "asset_key"):
                found.append(current)
            found.extend(_contains_forbidden(child, current))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_contains_forbidden(child, f"{path}[{index}]"))
    return found


def build_visual_authoring_provider_context(*, request: dict, authoritative_context: dict | None = None) -> dict:
    req = _as_dict(request)
    return {
        "contract_version": VISUAL_AUTHORING_PROVIDER_CONTRACT_VERSION,
        "request_id": str(req.get("request_id") or ""),
        "book_id": req.get("book_id"),
        "asset_key": str(req.get("asset_key") or ""),
        "asset_type": str(req.get("asset_type") or ""),
        "scope": _as_dict(req.get("scope")),
        "source_constraints": _as_list(req.get("source_constraints")),
        "free_authoring_space": [str(value).strip() for value in _as_list(req.get("free_authoring_space")) if str(value).strip()],
        "forbidden_contradictions": _as_list(req.get("forbidden_contradictions")),
        "evidence": _as_dict(authoritative_context),
    }


def build_visual_authoring_provider_prompt(context: dict) -> tuple[str, str]:
    system = (
        "You are a conservative visual authoring assistant. Return exactly one JSON object. "
        "Suggest only fields in free_authoring_space. Never output authority, approval, version, "
        "pointer, reference, media, prompt, geometry, or continuity mutation fields. Preserve "
        "unknowns instead of inventing facts. Required top-level keys are schema_version, "
        "request_id, asset_key, proposals, unknowns, review_notes. Copy request_id and asset_key "
        "exactly from the evidence packet."
    )
    user = canonical_json({
        "schema_version": VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
        "evidence_packet": context,
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


def validate_visual_authoring_proposal(raw: Any, *, request: dict, context: dict | None = None) -> dict:
    diagnostics: list[dict[str, Any]] = []
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
    proposals = payload.get("proposals")
    if not isinstance(proposals, list):
        diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "message": "proposals must be a list"})
        proposals = []
    asset_type = str(req.get("asset_type") or "")
    allowed = set(_as_list(req.get("free_authoring_space"))) or ALLOWED_FIELDS.get(asset_type, set())
    source = _constraint_map(_as_list(req.get("source_constraints")))
    forbidden_constraints = {field for field, _ in (_field_value(item) for item in _as_list(req.get("forbidden_contradictions"))) if field}
    seen: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(proposals):
        if not isinstance(item, dict) or not {"field", "value", "scope", "design_intent", "constraint_refs"}.issubset(item):
            diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "index": index, "message": "proposal item fields incomplete"})
            continue
        field = str(item.get("field") or "").strip()
        if not field or field.lower() in FORBIDDEN_FIELDS or field not in allowed:
            diagnostics.append({"code": "PROPOSAL_FIELD_OUT_OF_SCOPE", "field": field})
        if field in source and _normal(item.get("value")) != _normal(source[field]):
            diagnostics.append({"code": "SOURCE_VISUAL_CONSTRAINT_CONFLICT", "field": field})
        if field in forbidden_constraints:
            diagnostics.append({"code": "SOURCE_VISUAL_CONSTRAINT_CONFLICT", "field": field, "message": "forbidden contradiction"})
        encoded = canonical_json(item.get("value"))
        if field in seen and seen[field] != encoded:
            diagnostics.append({"code": "PROPOSAL_DUPLICATE_CONFLICT", "field": field})
        seen[field] = encoded
        normalized.append({
            "field": field,
            "value": item.get("value"),
            "scope": _as_dict(item.get("scope")),
            "design_intent": str(item.get("design_intent") or ""),
            "constraint_refs": [str(ref) for ref in _as_list(item.get("constraint_refs"))],
        })
    unknowns = payload.get("unknowns", [])
    if not isinstance(unknowns, list) or any(not isinstance(item, str) for item in unknowns):
        diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "message": "unknowns must be a list of strings"})
        unknowns = []
    review_notes = payload.get("review_notes", [])
    if not isinstance(review_notes, list) or any(not isinstance(item, str) for item in review_notes):
        diagnostics.append({"code": "PROPOSAL_SCHEMA_INVALID", "message": "review_notes must be a list of strings"})
        review_notes = []
    reason_codes = list(dict.fromkeys(item["code"] for item in diagnostics))
    return {
        "ok": not reason_codes,
        "status": "REVIEW_REQUIRED" if not reason_codes else "REJECTED",
        "reason_codes": reason_codes,
        "diagnostics": diagnostics,
        "normalized": {
            "schema_version": VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
            "request_id": str(payload.get("request_id") or ""),
            "asset_key": str(payload.get("asset_key") or ""),
            "asset_type": asset_type,
            "proposals": normalized,
            "unknowns": [str(item) for item in unknowns],
            "review_notes": [str(item) for item in review_notes],
        },
    }
