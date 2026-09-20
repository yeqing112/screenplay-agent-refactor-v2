"""Provider-free visual asset authority and authoring contracts.

This module deliberately separates source facts, production authoring, visual
variants and reference media.  Mutable legacy cards may feed an audit, but they
never become production authority without an immutable version and pointer.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable


VISUAL_ASSET_AUTHORITY_CONTRACT_VERSION = "visual_asset_authority_contract_v1"
VISUAL_ASSET_AUTHORITY_ENVELOPE_VERSION = "visual_asset_authority_envelope_v1"
REFERENCE_REQUIREMENT_POLICY_VERSION = "reference_requirement_policy_v1"
REFERENCE_GENERATION_REQUEST_VERSION = "visual_reference_generation_request_v1"

SOURCE_VISUAL_CONSTRAINT = "SOURCE_VISUAL_CONSTRAINT"
PRODUCTION_VISUAL_AUTHORING_DECISION = "PRODUCTION_VISUAL_AUTHORING_DECISION"
VISUAL_VARIANT_DECISION = "VISUAL_VARIANT_DECISION"
DERIVED_VISUAL_CONSTRAINT = "DERIVED_VISUAL_CONSTRAINT"
REFERENCE_MEDIA_AUTHORITY = "REFERENCE_MEDIA_AUTHORITY"
ADVISORY_VISUAL_CONTEXT = "ADVISORY_VISUAL_CONTEXT"
AUTHORING_PENDING = "AUTHORING_PENDING"
UNKNOWN = "UNKNOWN"

IDENTITY_REGISTERED = "IDENTITY_REGISTERED"
SPEC_DRAFT = "SPEC_DRAFT"
SPEC_APPROVED = "SPEC_APPROVED"
REFERENCE_PENDING = "REFERENCE_PENDING"
REFERENCE_SELECTED = "REFERENCE_SELECTED"
REFERENCE_LOCKED = "REFERENCE_LOCKED"
PRODUCTION_READY = "PRODUCTION_READY"
STALE = "STALE"

ASSET_TYPES = ("character", "scene", "prop")
REFERENCE_STATUSES = ("CANDIDATE", "SELECTED", "LOCKED", "STALE", "SUPERSEDED")
AUTHORING_REQUEST_STATUSES = ("PENDING", "PROPOSED", "REVIEW_REQUIRED", "APPROVED", "SUPERSEDED")


class VisualAssetAuthorityError(ValueError):
    def __init__(self, code: str, message: str, *, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or [{"code": code, "message": message, "severity": "blocked"}]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _slug(value: Any) -> str:
    value = _text(value)
    value = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_:")
    return value


def build_asset_key(*, book_id: int | str, asset_type: str, canonical_id: str) -> str:
    """Build a stable identity key; display names are not accepted as IDs."""
    kind = _text(asset_type).lower()
    if kind not in ASSET_TYPES:
        raise VisualAssetAuthorityError("ASSET_TYPE_INVALID", f"Unsupported visual asset type: {asset_type!r}.")
    canonical = _slug(canonical_id)
    if not canonical:
        raise VisualAssetAuthorityError("CANONICAL_ID_REQUIRED", "Production asset identity requires a stable canonical ID, not a display name.")
    return f"book:{_slug(book_id)}:{kind}:{canonical}"


def scope_key(*, asset_key: str, scope: dict[str, Any] | None = None) -> str:
    scope = _dict(scope)
    normalized = {key: scope[key] for key in ("episode", "scene_id", "shot_id", "story_stage") if scope.get(key) not in (None, "")}
    return f"{_text(asset_key)}@{fingerprint(normalized)[:16]}" if normalized else f"{_text(asset_key)}@canonical"


def _field_value(item: dict[str, Any]) -> tuple[str, Any]:
    field = _text(item.get("field") or item.get("predicate") or item.get("key"))
    value = item.get("value", item.get("fact_value", item.get("content")))
    return field, value


def _constraint_map(items: Iterable[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        field, value = _field_value(raw)
        if field:
            result[field] = {"field": field, "value": value, **raw}
    return result


def visual_asset_authority_contract() -> dict[str, Any]:
    common = {
        "identity": {"required": ["asset_key", "asset_type", "canonical_id", "scope"], "authority_class": DERIVED_VISUAL_CONSTRAINT},
        "source_constraints": {"authority_class": SOURCE_VISUAL_CONSTRAINT, "immutable": True},
        "authoring_decisions": {"authority_class": PRODUCTION_VISUAL_AUTHORING_DECISION, "requires_confirmation": True},
        "variants": {"authority_class": VISUAL_VARIANT_DECISION, "scoped": True},
        "reference_media": {"authority_class": REFERENCE_MEDIA_AUTHORITY, "requires_version_lineage": True},
        "legacy_prompt_text": {"authority_class": ADVISORY_VISUAL_CONTEXT, "production_authority": False},
        "unknown": {"authority_class": UNKNOWN, "production_authority": False},
    }
    schemas = {
        "character": {
            "canonical_fields": ["identity", "face", "facial_structure", "apparent_age", "body_type", "skin", "baseline_hairstyle", "persistent_features", "canonical_temperament"],
            "variant_fields": ["wardrobe", "hairstyle", "makeup", "injury", "dirt_blood_wetness", "accessories", "age_stage", "expression"],
            "required_identity": ["character_id"],
        },
        "scene": {
            "canonical_fields": ["material", "texture", "architecture_style", "color_palette", "lighting_look", "fixed_fixtures", "atmosphere", "visual_condition"],
            "variant_fields": ["state", "weather", "time_of_day", "dressing", "lighting_variant"],
            "required_identity": ["scene_id"],
            "geometry_dependency": "SceneBlocking",
            "geometry_override": False,
        },
        "prop": {
            "canonical_fields": ["basic_form", "material", "color", "distinctive_features"],
            "variant_fields": ["open_closed", "condition", "holder", "position", "story_state"],
            "required_identity": ["prop_id"],
            "continuity_dependency": "ShotPlan",
        },
    }
    return {
        "schema_version": VISUAL_ASSET_AUTHORITY_CONTRACT_VERSION,
        "authority_classes": common,
        "asset_types": schemas,
        "lifecycle": [IDENTITY_REGISTERED, AUTHORING_PENDING, SPEC_DRAFT, SPEC_APPROVED, REFERENCE_PENDING, REFERENCE_SELECTED, REFERENCE_LOCKED, PRODUCTION_READY, STALE],
        "production_rules": [
            "mutable_visual_rows_are_not_production_authority",
            "name_is_display_or_legacy_lookup_only",
            "source_constraints_are_immutable",
            "reference_does_not_mutate_visual_spec",
            "scene_visual_spec_cannot_override_scene_blocking_geometry",
            "prop_variant_cannot_override_shot_plan_state",
            "legacy_prompt_text_is_derived_or_advisory_only",
        ],
        "reference_requirement_policy_version": REFERENCE_REQUIREMENT_POLICY_VERSION,
    }


def compile_visual_asset_spec(*, asset_type: str, asset_key: str, canonical_identity: dict[str, Any], source_constraints: list[dict[str, Any]] | None = None, authoring_decisions: list[dict[str, Any]] | None = None, variant_decisions: list[dict[str, Any]] | None = None, scope: dict[str, Any] | None = None, geometry_authority: dict[str, Any] | None = None, continuity_authority: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministically merge approved decisions without overwriting source facts."""
    kind = _text(asset_type).lower()
    if kind not in ASSET_TYPES:
        raise VisualAssetAuthorityError("ASSET_TYPE_INVALID", "asset_type must be character, scene or prop.")
    if not _text(asset_key):
        raise VisualAssetAuthorityError("ASSET_KEY_REQUIRED", "asset_key is required.")
    canonical_identity = _dict(canonical_identity)
    source = _constraint_map(source_constraints or [])
    decisions = _constraint_map(authoring_decisions or [])
    variants = _constraint_map(variant_decisions or [])
    conflicts = []
    for field, decision in decisions.items():
        if field in source and _canonical(source[field].get("value")) != _canonical(decision.get("value")):
            conflicts.append({"field": field, "source": source[field].get("value"), "decision": decision.get("value"), "code": "SOURCE_AUTHORING_CONFLICT"})
    if conflicts:
        raise VisualAssetAuthorityError("SOURCE_AUTHORING_CONFLICT", "Authoring decisions contradict immutable source visual constraints.", diagnostics=conflicts)
    if kind == "scene" and _dict(geometry_authority).get("conflicts"):
        raise VisualAssetAuthorityError("SCENE_GEOMETRY_CONFLICT", "Scene visual design conflicts with authoritative SceneBlocking geometry.", diagnostics=_list(_dict(geometry_authority).get("conflicts")))
    if kind == "prop" and _dict(continuity_authority).get("conflicts"):
        raise VisualAssetAuthorityError("PROP_CONTINUITY_CONFLICT", "Prop visual variant conflicts with authoritative ShotPlan continuity state.", diagnostics=_list(_dict(continuity_authority).get("conflicts")))
    spec = {
        "schema_version": VISUAL_ASSET_AUTHORITY_CONTRACT_VERSION,
        "asset_key": asset_key,
        "asset_type": kind,
        "canonical_identity": canonical_identity,
        "scope": _dict(scope),
        "canonical_spec": {field: item.get("value") for field, item in source.items()},
        "authoring_spec": {field: item.get("value") for field, item in decisions.items()},
        "variant_spec": {field: item.get("value") for field, item in variants.items()},
        "provenance": {
            "source_constraint_ids": sorted(_text(item.get("source_ref") or item.get("fact_id")) for item in source.values() if _text(item.get("source_ref") or item.get("fact_id"))),
            "authoring_decision_ids": sorted(_text(item.get("decision_id")) for item in decisions.values() if _text(item.get("decision_id"))),
            "variant_decision_ids": sorted(_text(item.get("decision_id")) for item in variants.values() if _text(item.get("decision_id"))),
            "geometry_authority": _dict(geometry_authority).get("fingerprint", "") if geometry_authority else "",
            "continuity_authority": _dict(continuity_authority).get("fingerprint", "") if continuity_authority else "",
        },
    }
    spec["source_constraint_fingerprint"] = fingerprint(source)
    spec["authoring_decision_fingerprint"] = fingerprint(decisions)
    spec["variant_fingerprint"] = fingerprint(variants)
    spec["payload_hash"] = fingerprint(spec)
    return spec


def reference_requirement_policy(*, asset_type: str, identity_importance: str = "normal", target_capability: dict[str, Any] | None = None, production_profile: str = "production") -> dict[str, Any]:
    target = _dict(target_capability)
    required = _text(target.get("reference_requirement")).upper()
    if required not in {"REQUIRED", "OPTIONAL", "NOT_REQUIRED"}:
        if _text(asset_type).lower() == "character" and _text(identity_importance).lower() in {"critical", "high"}:
            required = "REQUIRED"
        elif _text(asset_type).lower() == "scene" and target.get("spatial_consistency"):
            required = "REQUIRED"
        else:
            required = "OPTIONAL"
    return {"schema_version": REFERENCE_REQUIREMENT_POLICY_VERSION, "asset_type": _text(asset_type).lower(), "identity_importance": _text(identity_importance) or "normal", "production_profile": _text(production_profile) or "production", "requirement": required, "provider_specific_execution": False, "fingerprint": fingerprint({"asset_type": asset_type, "identity_importance": identity_importance, "target": target, "production_profile": production_profile})}


def build_reference_media_authority(*, asset_key: str, asset_version_id: int | str, asset_version_fingerprint: str, reference_scope: dict[str, Any], image_identity: str, checksum: str, storage_reference: dict[str, Any] | None = None, generation_provenance: dict[str, Any] | None = None, reference_token_mapping: dict[str, Any] | None = None, lock_revision: int = 1, status: str = "LOCKED") -> dict[str, Any]:
    normalized_status = _text(status).upper()
    if normalized_status not in REFERENCE_STATUSES:
        raise VisualAssetAuthorityError("REFERENCE_STATUS_INVALID", f"Unsupported reference status: {status!r}.")
    missing = [name for name, value in (("asset_key", asset_key), ("asset_version_id", asset_version_id), ("asset_version_fingerprint", asset_version_fingerprint), ("image_identity", image_identity), ("checksum", checksum)) if not _text(value)]
    if missing:
        raise VisualAssetAuthorityError("REFERENCE_LINEAGE_REQUIRED", "Reference media authority is missing lineage fields.", diagnostics=[{"code": "REFERENCE_LINEAGE_FIELD_MISSING", "field": field, "severity": "blocked"} for field in missing])
    payload = {"schema_version": "reference_media_authority_v1", "asset_key": asset_key, "asset_version_id": asset_version_id, "asset_version_fingerprint": asset_version_fingerprint, "reference_scope": _dict(reference_scope), "image_identity": image_identity, "checksum": checksum, "storage_reference": _dict(storage_reference), "generation_provenance": _dict(generation_provenance), "reference_token_mapping": _dict(reference_token_mapping), "lock_revision": int(lock_revision), "status": normalized_status}
    payload["authority_fingerprint"] = fingerprint(payload)
    return payload


def classify_reference_asset(reference: dict[str, Any], *, current_asset_version: dict[str, Any] | None = None) -> dict[str, Any]:
    current = _dict(current_asset_version)
    missing = [field for field in ("asset_key", "asset_version_id", "asset_version_fingerprint", "image_identity", "checksum") if not _text(reference.get(field))]
    if missing:
        return {"classification": "LEGACY_LOCKED_UNBOUND" if _text(reference.get("status")).upper() == "LOCKED" else "INVALID", "status": "LEGACY_REFERENCE_MIGRATION_REQUIRED", "missing": missing}
    if current and (_text(reference.get("asset_version_fingerprint")) != _text(current.get("payload_hash") or current.get("asset_version_fingerprint"))):
        return {"classification": "STALE", "status": "STALE", "missing": [], "reason": "ASSET_VERSION_CHANGED"}
    status = _text(reference.get("status")).upper()
    if status == "LOCKED":
        return {"classification": "AUTHORITY_BINDABLE", "status": REFERENCE_LOCKED, "missing": []}
    if status in REFERENCE_STATUSES:
        return {"classification": "AUTHORITY_BINDABLE", "status": status, "missing": []}
    return {"classification": "INVALID", "status": "INVALID", "missing": []}


def reference_stale_reasons(reference: dict[str, Any], *, current_asset_version: dict[str, Any] | None = None, expected_checksum: str = "", expected_token_mapping: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    current = _dict(current_asset_version)
    if current and _text(reference.get("asset_version_fingerprint")) != _text(current.get("payload_hash") or current.get("asset_version_fingerprint")):
        reasons.append("ASSET_VERSION_CHANGED")
    if expected_checksum and _text(reference.get("checksum")) != _text(expected_checksum):
        reasons.append("IMAGE_CHECKSUM_CHANGED")
    if expected_token_mapping is not None and _canonical(reference.get("reference_token_mapping") or {}) != _canonical(expected_token_mapping):
        reasons.append("REFERENCE_TOKEN_MAPPING_CHANGED")
    if _text(reference.get("status")).upper() == "STALE":
        reasons.append("REFERENCE_MARKED_STALE")
    return sorted(set(reasons))


def build_visual_asset_authority_envelope(*, version: dict[str, Any], pointer: dict[str, Any], reference: dict[str, Any] | None = None, stale_status: str = "FRESH", stale_reasons: list[str] | None = None) -> dict[str, Any]:
    envelope = {"schema_version": VISUAL_ASSET_AUTHORITY_ENVELOPE_VERSION, "identity": {key: version.get(key) for key in ("asset_key", "asset_type", "canonical_identity", "scope")}, "source": {"constraint_fingerprint": version.get("source_constraint_fingerprint"), "source_constraints": version.get("source_constraints", [])}, "authoring": {"decision_fingerprint": version.get("authoring_decision_fingerprint"), "decision_ids": version.get("authoring_decision_ids", [])}, "variant": {"fingerprint": version.get("variant_fingerprint"), "scope": version.get("scope", {})}, "payload": {"version_id": version.get("id"), "revision": version.get("revision"), "payload_hash": version.get("payload_hash")}, "reference": reference or {}, "state": {"authority_status": version.get("authority_status"), "stale_status": stale_status, "stale_reasons": sorted(set(stale_reasons or []))}, "pointer": pointer}
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    return envelope


def mark_visual_asset_stale(*, version: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    normalized = sorted({_text(reason) for reason in reasons if _text(reason)})
    return {**version, "stale_status": STALE, "stale_reasons": normalized, "authority_status": STALE}


def build_reference_generation_request_draft(*, version: dict[str, Any], reference_purpose: str, aspect_layout_requirement: dict[str, Any], board_type: str, required_source_constraints: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    draft = {"schema_version": REFERENCE_GENERATION_REQUEST_VERSION, "asset_version_id": version.get("id"), "asset_key": version.get("asset_key"), "variant_id": version.get("variant_id") or "", "reference_purpose": _text(reference_purpose), "structured_visual_spec_snapshot": version.get("payload") or version, "required_source_constraints": _list(required_source_constraints), "allowed_authoring_fields": version.get("allowed_authoring_fields", []), "aspect_layout_requirement": _dict(aspect_layout_requirement), "reference_board_type": _text(board_type), "status": "READY_FOR_PROVIDER_CANARY", "provider_not_called": True}
    draft["request_fingerprint"] = fingerprint(draft)
    return draft


def propagate_visual_asset_staleness(session: Any, *, asset_key: str, reason: str) -> dict[str, int]:
    """Precisely stale bound versions/references/PromptIR, never the whole book."""
    from models import PromptIRAuthority, PromptIRVersion, VisualAssetPointer, VisualAssetVersion, VisualReferenceAsset, VisualReferenceAuthority
    versions = session.query(VisualAssetVersion).filter_by(asset_key=asset_key).all()
    for version in versions:
        version.stale_status = STALE
        version.authority_status = STALE
        try:
            previous_reasons = json.loads(version.stale_reasons or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            previous_reasons = []
        version.stale_reasons = json.dumps(sorted(set(_list(previous_reasons) + [_text(reason)])), ensure_ascii=False)
        version.updated_at = datetime.now()
    pointers = session.query(VisualAssetPointer).filter_by(asset_key=asset_key).all()
    for pointer in pointers:
        pointer.stale_status = STALE
        pointer.stale_reasons = json.dumps([_text(reason)], ensure_ascii=False)
        pointer.updated_at = datetime.now()
    refs = session.query(VisualReferenceAuthority).filter_by(asset_key=asset_key).all()
    for ref in refs:
        ref.stale_status = STALE
        ref.stale_reasons = json.dumps([_text(reason)], ensure_ascii=False)
        ref.status = "STALE"
        ref.updated_at = datetime.now()
    legacy_refs = session.query(VisualReferenceAsset).filter_by(asset_key=asset_key).all()
    for ref in legacy_refs:
        ref.stale_status = STALE
        ref.stale_reasons = json.dumps([_text(reason)], ensure_ascii=False)
        ref.authority_status = "STALE"
        ref.updated_at = datetime.now()
    prompt_count = 0
    for prompt in session.query(PromptIRVersion).all():
        try:
            payload = json.loads(prompt.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        # V1 stored bindings under ``assets``; Phase E v2 stores them under
        # ``asset_authority_bindings``.  Both are lineage-bearing references.
        lineage_payload = {"assets": payload.get("assets", {}), "asset_authority_bindings": payload.get("asset_authority_bindings", {})}
        if asset_key in json.dumps(lineage_payload, ensure_ascii=False):
            prompt.stale_status = "STALE"
            try:
                previous_reasons = json.loads(prompt.stale_reasons or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                previous_reasons = []
            prompt.stale_reasons = json.dumps(sorted(set(_list(previous_reasons) + [f"VISUAL_ASSET_CHANGED:{asset_key}"])), ensure_ascii=False)
            prompt.updated_at = datetime.now()
            authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=prompt.id).first()
            if authority:
                authority.stale_status = "STALE"
                authority.stale_reasons = prompt.stale_reasons
            prompt_count += 1
    return {"versions_staled": len(versions), "pointers_staled": len(pointers), "references_staled": len(refs) + len(legacy_refs), "prompt_ir_staled": prompt_count}


def propagate_visual_reference_staleness(session: Any, *, authority_fingerprint: str, reason: str) -> dict[str, int]:
    """Stale one concrete reference authority and PromptIR rows bound to it."""
    from models import PromptIRAuthority, PromptIRVersion, VisualReferenceAuthority
    refs = session.query(VisualReferenceAuthority).filter_by(authority_fingerprint=authority_fingerprint).all()
    for ref in refs:
        ref.stale_status = STALE
        ref.status = "STALE"
        ref.stale_reasons = json.dumps([_text(reason)], ensure_ascii=False)
        ref.updated_at = datetime.now()
    prompt_count = 0
    for prompt in session.query(PromptIRVersion).all():
        try:
            payload = json.loads(prompt.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        bindings = _dict(payload.get("asset_authority_bindings"))
        if authority_fingerprint not in json.dumps(bindings, ensure_ascii=False):
            continue
        prompt.stale_status = STALE
        prompt.stale_reasons = json.dumps([f"VISUAL_REFERENCE_CHANGED:{authority_fingerprint}", _text(reason)], ensure_ascii=False)
        prompt.updated_at = datetime.now()
        authority = session.query(PromptIRAuthority).filter_by(prompt_ir_version_id=prompt.id).first()
        if authority:
            authority.stale_status = STALE
            authority.stale_reasons = prompt.stale_reasons
            authority.updated_at = datetime.now()
        prompt_count += 1
    return {"references_staled": len(refs), "prompt_ir_staled": prompt_count}


def resolve_current_visual_asset_authority(session: Any, *, book_id: int, asset_key: str, expected_asset_type: str = "", expected_scope_key: str = "") -> dict[str, Any]:
    """Resolve and validate one current VisualAssetPointer/Version chain."""
    from models import VisualAssetPointer, VisualAssetVersion
    pointers = session.query(VisualAssetPointer).filter_by(book_id=book_id, asset_key=asset_key).all()
    if not pointers:
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_INVALID", "No current VisualAssetPointer exists for the required asset.", diagnostics=[{"asset_key": asset_key}])
    if expected_scope_key:
        pointers = [item for item in pointers if str(item.scope_key or "") == str(expected_scope_key)]
    elif len(pointers) > 1:
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_AMBIGUOUS", "Current VisualAssetPointer scope is ambiguous; an exact scope is required.", diagnostics=[{"asset_key": asset_key, "pointer_count": len(pointers)}])
    if len(pointers) != 1:
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_AMBIGUOUS", "Current VisualAssetPointer scope is ambiguous.", diagnostics=[{"asset_key": asset_key, "pointer_count": len(pointers)}])
    pointer = pointers[0]
    if _text(pointer.stale_status).upper() != "FRESH":
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_STALE", "Current VisualAssetPointer is stale.", diagnostics=[{"asset_key": asset_key}])
    if not pointer.current_version_id:
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_INVALID", "Current VisualAssetPointer has no current_version_id.")
    version = session.query(VisualAssetVersion).filter_by(id=pointer.current_version_id).first()
    if version is None:
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_INVALID", "Current VisualAssetPointer points to a missing VisualAssetVersion.")
    if str(version.book_id) != str(pointer.book_id) or str(version.asset_key) != str(pointer.asset_key) or (expected_asset_type and str(version.asset_type) != str(expected_asset_type)):
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_TAMPERED", "VisualAssetPointer and VisualAssetVersion identity does not match.")
    if _text(version.stale_status).upper() != "FRESH":
        raise VisualAssetAuthorityError("VISUAL_ASSET_VERSION_STALE", "Current VisualAssetVersion is stale.")
    if _text(pointer.payload_hash) != _text(version.payload_hash):
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_TAMPERED", "VisualAssetPointer payload_hash does not match the current version.")
    if _text(pointer.authority_status) != _text(version.authority_status):
        raise VisualAssetAuthorityError("VISUAL_ASSET_POINTER_TAMPERED", "VisualAssetPointer authority_status does not match the current version.")
    if _text(version.authority_status).upper() not in {SPEC_APPROVED, PRODUCTION_READY, "LOCKED", "QUALIFIED", "PRODUCTION_AUTHORITATIVE"}:
        raise VisualAssetAuthorityError("VISUAL_ASSET_AUTHORITY_NOT_QUALIFIED", "Current VisualAssetVersion is not production qualified.")
    return {"pointer": pointer, "version": version, "integrity_valid": True, "asset_key": asset_key}


def asset_readiness(*, identity_ready: bool, authoring_status: str, spec_approved: bool, reference_required: bool, reference_locked: bool) -> dict[str, Any]:
    if not identity_ready:
        return {"identity_ready": False, "visual_spec_ready": False, "reference_ready": False, "media_ready": False, "status": "ASSET_IDENTITY_PENDING", "blocking_reason": "IDENTITY_PENDING"}
    if _text(authoring_status).upper() in {AUTHORING_PENDING, "PENDING", "REVIEW_REQUIRED"} or not spec_approved:
        return {"identity_ready": True, "visual_spec_ready": False, "reference_ready": False, "media_ready": False, "status": "ASSET_AUTHORING_PENDING", "blocking_reason": "AUTHORING_PENDING"}
    if reference_required and not reference_locked:
        return {"identity_ready": True, "visual_spec_ready": True, "reference_ready": False, "media_ready": False, "status": "ASSET_REFERENCE_PENDING", "blocking_reason": "REFERENCE_PENDING"}
    return {"identity_ready": True, "visual_spec_ready": True, "reference_ready": bool(reference_locked or not reference_required), "media_ready": False, "status": "ASSET_REFERENCE_READY", "blocking_reason": ""}


def production_asset_binding(*, asset_key: str, asset_type: str, asset_name: str = "", version: dict[str, Any] | None = None, reference: dict[str, Any] | None = None, reference_required: bool = True) -> dict[str, Any]:
    """Project one current version/pointer into the PromptIR binding shape."""
    version = _dict(version)
    reference = _dict(reference)
    payload = _dict(version.get("payload"))
    ready = bool(version and _text(version.get("authority_status")) in {SPEC_APPROVED, PRODUCTION_READY} and _text(version.get("stale_status")) != STALE)
    ref_ready = bool(reference and _text(reference.get("status")).upper() in {"LOCKED", REFERENCE_LOCKED} and _text(reference.get("stale_status") or "FRESH") == "FRESH")
    spec = _dict(payload.get("canonical_spec"))
    authoring = _dict(payload.get("authoring_spec"))
    variant = _dict(payload.get("variant_spec"))
    facts = [{"fact_key": key, "value": value, "authority_class": DERIVED_VISUAL_CONSTRAINT} for source in (spec, authoring, variant) for key, value in source.items() if value not in (None, "", [], {})]
    status = _text(version.get("authority_status")) if ready else AUTHORING_PENDING
    reference_authority = dict(reference) if isinstance(reference, dict) else {}
    return {"asset_type": asset_type, "canonical_asset_id": asset_key.rsplit(":", 1)[-1], "asset_key": asset_key, "asset_name": asset_name, "asset_revision": version.get("revision"), "asset_version_id": version.get("id"), "asset_version_fingerprint": _text(version.get("payload_hash")), "authority_status": status, "stale_status": _text(version.get("stale_status") or "FRESH"), "variant_scope": payload.get("scope", {}), "variant_id": payload.get("variant_id", ""), "reference_status": "REFERENCE_READY" if ref_ready else "REFERENCE_PENDING", "reference_token": _text(reference.get("reference_token") or reference.get("reference_name")) if ref_ready else "", "authority_fingerprint": _text(version.get("payload_hash")), "reference_authority": reference_authority, "visual_facts": facts, "media_readiness": "READY" if ref_ready or not reference_required else "PENDING", "readiness": asset_readiness(identity_ready=True, authoring_status="APPROVED" if ready else AUTHORING_PENDING, spec_approved=ready, reference_required=reference_required, reference_locked=ref_ready)}


__all__ = [name for name in globals() if not name.startswith("_")]
