"""Character identity, reference and shot binding runtime.

This module composes the existing CharacterProfile, production asset
authority and production prompt lineage records.  It does not create media,
call a provider, rewrite source PromptIR, or maintain a second asset store.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence

from models import (
    CharacterProfile,
    CharacterReferenceAsset,
    ShotCharacterBinding,
    StoryboardShot,
    VisualReferenceAsset,
)


REFERENCE_TYPES = {"portrait", "full_body", "costume", "expression"}


class CharacterConsistencyError(ValueError):
    status_code = 409
    code = "CHARACTER_CONSISTENCY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, diagnostics: Sequence[Mapping[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.diagnostics = [dict(item) for item in (diagnostics or ())]

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_object(value: Any, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return dict(default or {})


def _json_array(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, list):
            return parsed
    return []


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _identity_dict(row: CharacterProfile) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "book_id": int(row.book_id),
        "name": row.name,
        "description": row.description or row.identity or "",
        "attributes": _json_object(row.attributes),
        "appearance_profile": _json_object(row.appearance_profile),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _reference_dict(row: CharacterReferenceAsset) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "character_id": int(row.character_id),
        "asset_id": row.asset_id,
        "reference_type": row.reference_type,
        "priority": int(row.priority),
        "visual_reference_asset_id": row.visual_reference_asset_id,
        "asset_version_id": row.asset_version_id,
        "constraint_snapshot": _json_object(row.constraint_snapshot),
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _binding_dict(session: Any, row: ShotCharacterBinding) -> dict[str, Any]:
    identity = session.query(CharacterProfile).filter_by(id=row.character_id).one_or_none()
    return {
        "id": int(row.id),
        "shot_id": int(row.storyboard_shot_id),
        "storyboard_shot_id": int(row.storyboard_shot_id),
        "character_id": int(row.character_id),
        "character": _identity_dict(identity) if identity else None,
        "role": row.role,
        "reference_asset_ids": [str(value) for value in _json_array(row.reference_asset_ids)],
        "appearance_rules": _json_object(row.appearance_rules),
        "constraint_snapshot": _json_object(row.constraint_snapshot),
        "asset_authority_id": row.asset_authority_id,
        "asset_version_id": row.asset_version_id,
        "binding_fingerprint": row.binding_fingerprint,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def get_character_identity(session: Any, character_id: int) -> CharacterProfile:
    row = session.query(CharacterProfile).filter_by(id=int(character_id)).one_or_none()
    if row is None:
        raise CharacterConsistencyError("character identity does not exist", code="CHARACTER_IDENTITY_NOT_FOUND")
    return row


def create_character_identity(
    session: Any,
    *,
    book_id: int,
    name: str,
    description: str = "",
    attributes: Mapping[str, Any] | None = None,
    appearance_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise CharacterConsistencyError("character name is required", code="CHARACTER_NAME_REQUIRED")
    existing = session.query(CharacterProfile).filter_by(book_id=int(book_id), name=normalized_name).order_by(CharacterProfile.id.asc()).first()
    if existing is not None:
        return _identity_dict(existing)
    row = CharacterProfile(
        book_id=int(book_id),
        name=normalized_name,
        description=str(description or ""),
        identity=str(description or ""),
        attributes=_canonical(dict(attributes or {})),
        appearance_profile=_canonical(dict(appearance_profile or {})),
    )
    session.add(row)
    session.flush()
    return _identity_dict(row)


def serialize_character_identity(session: Any, character_id: int) -> dict[str, Any]:
    row = get_character_identity(session, character_id)
    references = session.query(CharacterReferenceAsset).filter_by(character_id=row.id, status="ACTIVE").order_by(CharacterReferenceAsset.priority.asc(), CharacterReferenceAsset.id.asc()).all()
    bindings = session.query(ShotCharacterBinding).filter_by(character_id=row.id, status="ACTIVE").order_by(ShotCharacterBinding.id.asc()).all()
    return {**_identity_dict(row), "references": [_reference_dict(item) for item in references], "bindings": [_binding_dict(session, item) for item in bindings]}


def add_character_reference_asset(
    session: Any,
    *,
    character_id: int,
    asset_id: str,
    reference_type: str = "portrait",
    priority: int = 0,
    visual_reference_asset_id: int | None = None,
    asset_version_id: str | None = None,
    constraint_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    character = get_character_identity(session, character_id)
    kind = str(reference_type or "").strip().lower()
    if kind not in REFERENCE_TYPES:
        raise CharacterConsistencyError("reference_type is unsupported", code="CHARACTER_REFERENCE_TYPE_INVALID")
    asset_key = str(asset_id or "").strip()
    if not asset_key:
        raise CharacterConsistencyError("asset_id is required", code="CHARACTER_REFERENCE_ASSET_REQUIRED")
    if int(priority) < 0:
        raise CharacterConsistencyError("priority must be non-negative", code="CHARACTER_REFERENCE_PRIORITY_INVALID")
    if visual_reference_asset_id is not None:
        visual = session.query(VisualReferenceAsset).filter_by(id=int(visual_reference_asset_id)).one_or_none()
        if visual is None:
            raise CharacterConsistencyError("visual reference asset does not exist", code="CHARACTER_REFERENCE_ASSET_NOT_FOUND")
    existing = session.query(CharacterReferenceAsset).filter_by(character_id=character.id, asset_id=asset_key, reference_type=kind).one_or_none()
    if existing is None:
        existing = CharacterReferenceAsset(
            character_id=character.id,
            asset_id=asset_key,
            reference_type=kind,
            priority=int(priority),
            visual_reference_asset_id=visual_reference_asset_id,
            asset_version_id=str(asset_version_id or "") or None,
            constraint_snapshot=_canonical(dict(constraint_snapshot or {})),
            status="ACTIVE",
        )
        session.add(existing)
    else:
        existing.priority = int(priority)
        existing.visual_reference_asset_id = visual_reference_asset_id
        existing.asset_version_id = str(asset_version_id or "") or None
        existing.constraint_snapshot = _canonical(dict(constraint_snapshot or {}))
        existing.status = "ACTIVE"
        existing.updated_at = datetime.utcnow()
    session.flush()
    return _reference_dict(existing)


def list_character_references(session: Any, character_id: int) -> list[dict[str, Any]]:
    character = get_character_identity(session, character_id)
    rows = session.query(CharacterReferenceAsset).filter_by(character_id=character.id, status="ACTIVE").order_by(CharacterReferenceAsset.priority.asc(), CharacterReferenceAsset.id.asc()).all()
    return [_reference_dict(row) for row in rows]


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise CharacterConsistencyError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def bind_shot_character(
    session: Any,
    *,
    shot_id: int,
    character_id: int,
    role: str = "supporting",
    reference_asset_ids: Sequence[int | str] | None = None,
    appearance_rules: Mapping[str, Any] | None = None,
    constraint_snapshot: Mapping[str, Any] | None = None,
    asset_authority_id: str | None = None,
    asset_version_id: str | None = None,
) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    character = get_character_identity(session, character_id)
    role_value = str(role or "supporting").strip()
    if not role_value:
        raise CharacterConsistencyError("character role is required", code="CHARACTER_ROLE_REQUIRED")
    requested_refs = [str(value) for value in (reference_asset_ids or ())]
    refs = session.query(CharacterReferenceAsset).filter(CharacterReferenceAsset.character_id == character.id, CharacterReferenceAsset.status == "ACTIVE").all()
    by_id = {str(row.id): row for row in refs}
    by_asset = {str(row.asset_id): row for row in refs}
    selected = []
    for value in requested_refs:
        row = by_id.get(value) or by_asset.get(value)
        if row is None:
            raise CharacterConsistencyError("reference asset is not bound to the character", code="CHARACTER_REFERENCE_BINDING_INVALID", diagnostics=[{"reference_asset_id": value, "character_id": character.id}])
        # Persist the stable asset identity rather than the relation row id so
        # prompt constraints remain portable across database replays.
        selected.append(str(row.asset_id))
    selected = list(dict.fromkeys(selected))
    if not selected and refs:
        selected = [str(row.asset_id) for row in sorted(refs, key=lambda item: (int(item.priority), int(item.id)))]
    identity_constraints = {"description": character.description or character.identity or "", "attributes": _json_object(character.attributes), "appearance_profile": _json_object(character.appearance_profile)}
    appearance = dict(appearance_rules or {})
    snapshot = dict(constraint_snapshot or {})
    snapshot.setdefault("character_identity", identity_constraints)
    snapshot.setdefault("reference_asset_ids", selected)
    basis = {"shot_id": int(shot.id), "character_id": int(character.id), "role": role_value, "reference_asset_ids": selected, "appearance_rules": appearance, "constraint_snapshot": snapshot, "asset_authority_id": asset_authority_id or "", "asset_version_id": asset_version_id or ""}
    fingerprint = _fingerprint(basis)
    row = session.query(ShotCharacterBinding).filter_by(storyboard_shot_id=shot.id, character_id=character.id, role=role_value).one_or_none()
    if row is None:
        row = ShotCharacterBinding(storyboard_shot_id=shot.id, character_id=character.id, role=role_value, reference_asset_ids=_canonical(selected), appearance_rules=_canonical(appearance), constraint_snapshot=_canonical(snapshot), asset_authority_id=str(asset_authority_id or "") or None, asset_version_id=str(asset_version_id or "") or None, binding_fingerprint=fingerprint, status="ACTIVE")
        session.add(row)
    else:
        row.reference_asset_ids = _canonical(selected)
        row.appearance_rules = _canonical(appearance)
        row.constraint_snapshot = _canonical(snapshot)
        row.asset_authority_id = str(asset_authority_id or "") or None
        row.asset_version_id = str(asset_version_id or "") or None
        row.binding_fingerprint = fingerprint
        row.status = "ACTIVE"
        row.updated_at = datetime.utcnow()
    session.flush()
    return _binding_dict(session, row)


def validate_shot_character_consistency(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    rows = session.query(ShotCharacterBinding).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").order_by(ShotCharacterBinding.id.asc()).all()
    errors: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for row in rows:
        identity = session.query(CharacterProfile).filter_by(id=row.character_id).one_or_none()
        if identity is None:
            errors.append({"code": "CHARACTER_IDENTITY_MISSING", "binding_id": row.id, "character_id": row.character_id})
            continue
        refs = session.query(CharacterReferenceAsset).filter_by(character_id=identity.id, status="ACTIVE").all()
        selected = _json_array(row.reference_asset_ids)
        available_ids = {str(item.id) for item in refs} | {str(item.asset_id) for item in refs}
        if not refs:
            errors.append({"code": "CHARACTER_REFERENCE_ASSET_MISSING", "binding_id": row.id, "character_id": identity.id})
        missing = [str(item) for item in selected if str(item) not in available_ids]
        if missing:
            errors.append({"code": "CHARACTER_REFERENCE_BINDING_INVALID", "binding_id": row.id, "missing_reference_asset_ids": missing})
        if not (identity.description or identity.identity or _json_object(identity.attributes) or _json_object(identity.appearance_profile)):
            errors.append({"code": "CHARACTER_CONSTRAINTS_MISSING", "binding_id": row.id, "character_id": identity.id})
        resolved.append(_binding_dict(session, row))
    if not rows:
        errors.append({"code": "CHARACTER_BINDING_MISSING", "shot_id": int(shot.id)})
    return {"shot_id": int(shot.id), "status": "PASS" if not errors else "BLOCKED", "binding_count": len(rows), "bindings": resolved, "errors": errors, "checks": {"character_bound": bool(rows), "reference_asset_present": bool(rows) and not any(item["code"] == "CHARACTER_REFERENCE_ASSET_MISSING" for item in errors), "constraints_present": not any(item["code"] == "CHARACTER_CONSTRAINTS_MISSING" for item in errors)}}


def build_character_constraint_block(session: Any, *, shot_id: int) -> dict[str, Any]:
    validation = validate_shot_character_consistency(session, shot_id=shot_id)
    if validation["status"] != "PASS":
        raise CharacterConsistencyError("shot character consistency validation failed", code="CHARACTER_CONSISTENCY_BLOCKED", diagnostics=validation["errors"])
    blocks = []
    for binding in validation["bindings"]:
        character = binding["character"] or {}
        references = session.query(CharacterReferenceAsset).filter_by(character_id=binding["character_id"], status="ACTIVE").order_by(CharacterReferenceAsset.priority.asc(), CharacterReferenceAsset.id.asc()).all()
        selected = set(str(item) for item in binding["reference_asset_ids"])
        reference_constraints = [
            {"asset_id": row.asset_id, "reference_type": row.reference_type, "priority": int(row.priority), "constraint_snapshot": _json_object(row.constraint_snapshot)}
            for row in references
            if not selected or str(row.asset_id) in selected
        ]
        blocks.append({"character_id": binding["character_id"], "name": character.get("name", ""), "role": binding["role"], "identity": character.get("description", ""), "attributes": character.get("attributes", {}), "appearance_profile": character.get("appearance_profile", {}), "reference_asset_ids": binding["reference_asset_ids"], "appearance_rules": binding["appearance_rules"]})
        blocks[-1]["reference_constraints"] = reference_constraints
    return {"schema_version": "character_consistency_constraints_v1", "shot_id": int(validation["shot_id"]), "characters": blocks, "validation": validation}


def inject_character_constraints(session: Any, *, shot_id: int, original_prompt: str) -> dict[str, Any]:
    """Derive a prompt candidate while returning the original prompt intact."""
    source = str(original_prompt or "")
    if not source.strip():
        raise CharacterConsistencyError("original prompt is required", code="ORIGINAL_PROMPT_REQUIRED")
    block = build_character_constraint_block(session, shot_id=shot_id)
    lines = [source, "", "Character consistency constraints:"]
    for character in block["characters"]:
        lines.append(f"- {character['name']} ({character['role']}): {character['identity']}")
        if character["attributes"]:
            lines.append(f"  attributes: {_canonical(character['attributes'])}")
        if character["appearance_profile"]:
            lines.append(f"  appearance rules: {_canonical(character['appearance_profile'])}")
        if character["reference_asset_ids"]:
            lines.append(f"  reference assets: {', '.join(map(str, character['reference_asset_ids']))}")
        if character.get("reference_constraints"):
            lines.append(f"  reference constraints: {_canonical(character['reference_constraints'])}")
        if character["appearance_rules"]:
            lines.append(f"  shot rules: {_canonical(character['appearance_rules'])}")
    injected = "\n".join(lines)
    return {"original_prompt": source, "injected_prompt": injected, "prompt_text": injected, "prompt_was_mutated": False, "constraint_block": block, "prompt_structure": {"source_prompt": source, "character_constraints": block}}


def create_character_constrained_prompt_version(
    session: Any,
    *,
    prompt_id: str,
    shot_id: int,
    original_prompt: str,
    prompt_structure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append an immutable production prompt version with character constraints.

    The source prompt is retained in ``prompt_structure.source_prompt`` and is
    never overwritten in place.  The created row therefore remains compatible
    with ``ProductionPromptLineage`` and its append-only version contract.
    """
    from core.production_prompt_lineage import create_production_prompt_version

    prompt = create_production_prompt_version(
        session,
        prompt_id=prompt_id,
        prompt_text=original_prompt,
        prompt_structure=dict(prompt_structure or {}),
        created_from="CHARACTER_CONSISTENCY",
        shot_id=shot_id,
    )
    injected = inject_character_constraints(session, shot_id=shot_id, original_prompt=original_prompt)
    return {"prompt_version": prompt, "original_prompt": injected["original_prompt"], "injected_prompt": injected["injected_prompt"], "prompt_was_mutated": False, "constraint_block": injected["constraint_block"]}


__all__ = [
    "REFERENCE_TYPES",
    "CharacterConsistencyError",
    "create_character_identity",
    "get_character_identity",
    "serialize_character_identity",
    "add_character_reference_asset",
    "list_character_references",
    "bind_shot_character",
    "validate_shot_character_consistency",
    "build_character_constraint_block",
    "inject_character_constraints",
    "create_character_constrained_prompt_version",
]
