"""Visual style identity, reference binding, validation and prompt injection."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence

from models import ShotStyleBinding, StoryboardShot, StyleReferenceAsset, VisualReferenceAsset, VisualStyleProfile


REFERENCE_TYPES = {"color", "camera", "lighting", "composition", "mood"}
SCOPES = {"EPISODE_DEFAULT", "SHOT_OVERRIDE"}


class VisualStyleConsistencyError(ValueError):
    status_code = 409
    code = "VISUAL_STYLE_CONSISTENCY_INVALID"

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


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _array(value: Any) -> list[Any]:
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


def _value(value: Any) -> Any:
    if isinstance(value, (Mapping, list, tuple)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return value
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _style_dict(row: VisualStyleProfile) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "book_id": int(row.book_id),
        "name": row.name,
        "description": row.description or "",
        "camera_profile": _value(row.camera_profile),
        "lighting_profile": _value(row.lighting_profile),
        "color_profile": _value(row.color_profile),
        "composition_profile": _value(row.composition_profile),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _reference_dict(row: StyleReferenceAsset) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "style_id": int(row.style_id),
        "asset_id": row.asset_id,
        "reference_type": row.reference_type,
        "priority": int(row.priority),
        "visual_reference_asset_id": row.visual_reference_asset_id,
        "asset_version_id": row.asset_version_id,
        "constraint_snapshot": _obj(row.constraint_snapshot),
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _binding_dict(session: Any, row: ShotStyleBinding) -> dict[str, Any]:
    style = session.query(VisualStyleProfile).filter_by(id=row.style_id).one_or_none()
    return {
        "id": int(row.id),
        "shot_id": int(row.storyboard_shot_id) if row.storyboard_shot_id is not None else None,
        "storyboard_shot_id": int(row.storyboard_shot_id) if row.storyboard_shot_id is not None else None,
        "book_id": int(row.book_id),
        "episode": int(row.episode),
        "style_id": int(row.style_id),
        "style": _style_dict(style) if style else None,
        "scope": row.scope,
        "reference_asset_ids": [str(item) for item in _array(row.reference_asset_ids)],
        "style_rules": _obj(row.style_rules),
        "constraint_snapshot": _obj(row.constraint_snapshot),
        "asset_authority_id": row.asset_authority_id,
        "asset_version_id": row.asset_version_id,
        "binding_fingerprint": row.binding_fingerprint,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def get_visual_style_profile(session: Any, style_id: int | str) -> VisualStyleProfile:
    value = str(style_id or "").strip()
    row = session.query(VisualStyleProfile).filter_by(id=int(value)).one_or_none() if value.isdigit() else None
    if row is None and value:
        row = session.query(VisualStyleProfile).filter_by(name=value).order_by(VisualStyleProfile.id.asc()).first()
    if row is None:
        raise VisualStyleConsistencyError("visual style profile does not exist", code="STYLE_PROFILE_NOT_FOUND")
    return row


def create_visual_style_profile(
    session: Any,
    *,
    book_id: int,
    name: str,
    description: str = "",
    camera_profile: Mapping[str, Any] | None = None,
    lighting_profile: Mapping[str, Any] | None = None,
    color_profile: Mapping[str, Any] | None = None,
    composition_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise VisualStyleConsistencyError("style name is required", code="STYLE_NAME_REQUIRED")
    existing = session.query(VisualStyleProfile).filter_by(book_id=int(book_id), name=normalized_name).order_by(VisualStyleProfile.id.asc()).first()
    if existing is not None:
        return _style_dict(existing)
    row = VisualStyleProfile(
        book_id=int(book_id),
        name=normalized_name,
        description=str(description or ""),
        camera_profile=_canonical(dict(camera_profile or {})),
        lighting_profile=_canonical(dict(lighting_profile or {})),
        color_profile=_canonical(dict(color_profile or {})),
        composition_profile=_canonical(dict(composition_profile or {})),
    )
    session.add(row)
    session.flush()
    return _style_dict(row)


def serialize_visual_style_profile(session: Any, style_id: int | str) -> dict[str, Any]:
    row = get_visual_style_profile(session, style_id)
    references = session.query(StyleReferenceAsset).filter_by(style_id=row.id, status="ACTIVE").order_by(StyleReferenceAsset.priority.asc(), StyleReferenceAsset.id.asc()).all()
    bindings = session.query(ShotStyleBinding).filter_by(style_id=row.id, status="ACTIVE").order_by(ShotStyleBinding.id.asc()).all()
    return {**_style_dict(row), "references": [_reference_dict(item) for item in references], "bindings": [_binding_dict(session, item) for item in bindings]}


def add_style_reference_asset(
    session: Any,
    *,
    style_id: int | str,
    asset_id: str,
    reference_type: str = "mood",
    priority: int = 0,
    visual_reference_asset_id: int | None = None,
    asset_version_id: str | None = None,
    constraint_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    style = get_visual_style_profile(session, style_id)
    kind = str(reference_type or "").strip().lower()
    if kind not in REFERENCE_TYPES:
        raise VisualStyleConsistencyError("reference_type is unsupported", code="STYLE_REFERENCE_TYPE_INVALID")
    asset_key = str(asset_id or "").strip()
    if not asset_key:
        raise VisualStyleConsistencyError("asset_id is required", code="STYLE_REFERENCE_ASSET_REQUIRED")
    if int(priority) < 0:
        raise VisualStyleConsistencyError("priority must be non-negative", code="STYLE_REFERENCE_PRIORITY_INVALID")
    if visual_reference_asset_id is not None and session.query(VisualReferenceAsset).filter_by(id=int(visual_reference_asset_id)).one_or_none() is None:
        raise VisualStyleConsistencyError("visual reference asset does not exist", code="STYLE_REFERENCE_ASSET_NOT_FOUND")
    row = session.query(StyleReferenceAsset).filter_by(style_id=style.id, asset_id=asset_key, reference_type=kind).one_or_none()
    if row is None:
        row = StyleReferenceAsset(style_id=style.id, asset_id=asset_key, reference_type=kind, priority=int(priority), visual_reference_asset_id=visual_reference_asset_id, asset_version_id=str(asset_version_id or "") or None, constraint_snapshot=_canonical(dict(constraint_snapshot or {})), status="ACTIVE")
        session.add(row)
    else:
        row.priority = int(priority)
        row.visual_reference_asset_id = visual_reference_asset_id
        row.asset_version_id = str(asset_version_id or "") or None
        row.constraint_snapshot = _canonical(dict(constraint_snapshot or {}))
        row.status = "ACTIVE"
        row.updated_at = datetime.utcnow()
    session.flush()
    return _reference_dict(row)


def list_style_references(session: Any, style_id: int | str) -> list[dict[str, Any]]:
    style = get_visual_style_profile(session, style_id)
    rows = session.query(StyleReferenceAsset).filter_by(style_id=style.id, status="ACTIVE").order_by(StyleReferenceAsset.priority.asc(), StyleReferenceAsset.id.asc()).all()
    return [_reference_dict(row) for row in rows]


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise VisualStyleConsistencyError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def _select_reference_assets(session: Any, style: VisualStyleProfile, requested: Sequence[int | str] | None) -> list[str]:
    refs = session.query(StyleReferenceAsset).filter_by(style_id=style.id, status="ACTIVE").all()
    by_id = {str(row.id): row for row in refs}
    by_asset = {str(row.asset_id): row for row in refs}
    selected: list[str] = []
    for value in (requested or ()):
        row = by_id.get(str(value)) or by_asset.get(str(value))
        if row is None:
            raise VisualStyleConsistencyError("reference asset is not bound to the style", code="STYLE_REFERENCE_BINDING_INVALID", diagnostics=[{"reference_asset_id": str(value), "style_id": style.id}])
        selected.append(str(row.asset_id))
    if not selected and refs:
        selected = [str(row.asset_id) for row in sorted(refs, key=lambda item: (int(item.priority), int(item.id)))]
    return list(dict.fromkeys(selected))


def _bind_style(
    session: Any,
    *,
    style_id: int | str,
    book_id: int,
    episode: int,
    scope: str,
    storyboard_shot_id: int | None,
    reference_asset_ids: Sequence[int | str] | None,
    style_rules: Mapping[str, Any] | None,
    constraint_snapshot: Mapping[str, Any] | None,
    asset_authority_id: str | None,
    asset_version_id: str | None,
) -> dict[str, Any]:
    if scope not in SCOPES:
        raise VisualStyleConsistencyError("style binding scope is unsupported", code="STYLE_BINDING_SCOPE_INVALID")
    style = get_visual_style_profile(session, style_id)
    selected = _select_reference_assets(session, style, reference_asset_ids)
    rules = dict(style_rules or {})
    snapshot = dict(constraint_snapshot or {})
    snapshot.setdefault("style_profile", _style_dict(style))
    snapshot.setdefault("reference_asset_ids", selected)
    basis = {"book_id": int(book_id), "episode": int(episode), "storyboard_shot_id": storyboard_shot_id, "style_id": int(style.id), "scope": scope, "reference_asset_ids": selected, "style_rules": rules, "constraint_snapshot": snapshot, "asset_authority_id": asset_authority_id or "", "asset_version_id": asset_version_id or ""}
    fingerprint = _fingerprint(basis)
    query = session.query(ShotStyleBinding).filter_by(scope=scope, status="ACTIVE")
    if scope == "SHOT_OVERRIDE":
        query = query.filter_by(storyboard_shot_id=int(storyboard_shot_id))
    else:
        query = query.filter_by(book_id=int(book_id), episode=int(episode))
    query.update({"status": "STALE", "updated_at": datetime.utcnow()}, synchronize_session=False)
    row = ShotStyleBinding(storyboard_shot_id=storyboard_shot_id, book_id=int(book_id), episode=int(episode), style_id=style.id, scope=scope, reference_asset_ids=_canonical(selected), style_rules=_canonical(rules), constraint_snapshot=_canonical(snapshot), asset_authority_id=str(asset_authority_id or "") or None, asset_version_id=str(asset_version_id or "") or None, binding_fingerprint=fingerprint, status="ACTIVE")
    session.add(row)
    session.flush()
    return _binding_dict(session, row)


def bind_shot_style(session: Any, *, shot_id: int, style_id: int | str, reference_asset_ids: Sequence[int | str] | None = None, style_rules: Mapping[str, Any] | None = None, constraint_snapshot: Mapping[str, Any] | None = None, asset_authority_id: str | None = None, asset_version_id: str | None = None) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    return _bind_style(session, style_id=style_id, book_id=shot.book_id, episode=shot.episode, scope="SHOT_OVERRIDE", storyboard_shot_id=shot.id, reference_asset_ids=reference_asset_ids, style_rules=style_rules, constraint_snapshot=constraint_snapshot, asset_authority_id=asset_authority_id, asset_version_id=asset_version_id)


def bind_episode_style(session: Any, *, book_id: int, episode: int, style_id: int | str, reference_asset_ids: Sequence[int | str] | None = None, style_rules: Mapping[str, Any] | None = None, constraint_snapshot: Mapping[str, Any] | None = None, asset_authority_id: str | None = None, asset_version_id: str | None = None) -> dict[str, Any]:
    return _bind_style(session, style_id=style_id, book_id=int(book_id), episode=int(episode), scope="EPISODE_DEFAULT", storyboard_shot_id=None, reference_asset_ids=reference_asset_ids, style_rules=style_rules, constraint_snapshot=constraint_snapshot, asset_authority_id=asset_authority_id, asset_version_id=asset_version_id)


def _effective_binding(session: Any, shot: StoryboardShot) -> ShotStyleBinding | None:
    override = session.query(ShotStyleBinding).filter_by(storyboard_shot_id=shot.id, scope="SHOT_OVERRIDE", status="ACTIVE").order_by(ShotStyleBinding.id.desc()).first()
    if override is not None:
        return override
    return session.query(ShotStyleBinding).filter_by(book_id=shot.book_id, episode=shot.episode, scope="EPISODE_DEFAULT", status="ACTIVE").order_by(ShotStyleBinding.id.desc()).first()


def validate_shot_style_consistency(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    row = _effective_binding(session, shot)
    errors: list[dict[str, Any]] = []
    if row is None:
        errors.append({"code": "STYLE_BINDING_MISSING", "shot_id": int(shot.id)})
        return {"shot_id": int(shot.id), "status": "BLOCKED", "binding_count": 0, "binding": None, "errors": errors, "checks": {"style_bound": False, "reference_asset_present": False, "constraints_present": False}}
    style = session.query(VisualStyleProfile).filter_by(id=row.style_id).one_or_none()
    if style is None:
        errors.append({"code": "STYLE_PROFILE_MISSING", "binding_id": row.id, "style_id": row.style_id})
        return {"shot_id": int(shot.id), "status": "BLOCKED", "binding_count": 1, "binding": _binding_dict(session, row), "errors": errors, "checks": {"style_bound": False, "reference_asset_present": False, "constraints_present": False}}
    refs = session.query(StyleReferenceAsset).filter_by(style_id=style.id, status="ACTIVE").all()
    selected = [str(item) for item in _array(row.reference_asset_ids)]
    available = {str(item.id) for item in refs} | {str(item.asset_id) for item in refs}
    if not refs:
        errors.append({"code": "STYLE_REFERENCE_ASSET_MISSING", "binding_id": row.id, "style_id": style.id})
    missing = [item for item in selected if item not in available]
    if missing:
        errors.append({"code": "STYLE_REFERENCE_BINDING_INVALID", "binding_id": row.id, "missing_reference_asset_ids": missing})
    profile_fields = ("camera_profile", "lighting_profile", "color_profile", "composition_profile")
    missing_constraints = [field for field in profile_fields if not str(getattr(style, field) or "").strip() or _value(getattr(style, field)) in ({}, [], None, "")]
    if missing_constraints:
        errors.append({"code": "STYLE_CONSTRAINTS_MISSING", "binding_id": row.id, "style_id": style.id, "missing_fields": missing_constraints})
    binding = _binding_dict(session, row)
    return {"shot_id": int(shot.id), "status": "PASS" if not errors else "BLOCKED", "binding_count": 1, "binding": binding, "errors": errors, "checks": {"style_bound": True, "reference_asset_present": bool(refs) and not any(item["code"] == "STYLE_REFERENCE_ASSET_MISSING" for item in errors), "constraints_present": not any(item["code"] == "STYLE_CONSTRAINTS_MISSING" for item in errors), "scope": row.scope}}


def build_style_constraint_block(session: Any, *, shot_id: int | None = None, style_id: int | str | None = None) -> dict[str, Any]:
    binding = None
    if shot_id is not None:
        validation = validate_shot_style_consistency(session, shot_id=shot_id)
        if validation["status"] != "PASS":
            raise VisualStyleConsistencyError("shot visual style validation failed", code="VISUAL_STYLE_CONSISTENCY_BLOCKED", diagnostics=validation["errors"])
        binding = validation["binding"]
    else:
        style = get_visual_style_profile(session, style_id or "")
        refs = list_style_references(session, style.id)
        if not refs:
            raise VisualStyleConsistencyError("style has no reference assets", code="STYLE_REFERENCE_ASSET_MISSING")
        binding = {"style_id": style.id, "reference_asset_ids": [item["asset_id"] for item in refs], "style_rules": {}}
    style = get_visual_style_profile(session, binding["style_id"])
    refs = session.query(StyleReferenceAsset).filter_by(style_id=style.id, status="ACTIVE").order_by(StyleReferenceAsset.priority.asc(), StyleReferenceAsset.id.asc()).all()
    selected = set(str(item) for item in binding["reference_asset_ids"])
    constraints = [{"asset_id": row.asset_id, "reference_type": row.reference_type, "priority": int(row.priority), "constraint_snapshot": _obj(row.constraint_snapshot)} for row in refs if not selected or str(row.asset_id) in selected]
    return {"schema_version": "visual_style_consistency_constraints_v1", "style_id": int(style.id), "style": _style_dict(style), "scope": binding.get("scope"), "style_rules": binding.get("style_rules", {}), "reference_constraints": constraints}


def inject_style_constraints(session: Any, *, original_prompt: str, shot_id: int | None = None, style_id: int | str | None = None) -> dict[str, Any]:
    source = str(original_prompt or "")
    if not source.strip():
        raise VisualStyleConsistencyError("original prompt is required", code="ORIGINAL_PROMPT_REQUIRED")
    block = build_style_constraint_block(session, shot_id=shot_id, style_id=style_id)
    style = block["style"] or {}
    lines = [source, "", "Visual style consistency constraints:", f"- style: {style.get('name', '')}: {style.get('description', '')}", f"- Camera Rules: {_canonical(style.get('camera_profile', {}))}", f"- Lighting Rules: {_canonical(style.get('lighting_profile', {}))}", f"- Color Rules: {_canonical(style.get('color_profile', {}))}", f"- Composition Rules: {_canonical(style.get('composition_profile', {}))}"]
    if block["style_rules"]:
        lines.append(f"- Shot style rules: {_canonical(block['style_rules'])}")
    if block["reference_constraints"]:
        lines.append(f"- Reference constraints: {_canonical(block['reference_constraints'])}")
    injected = "\n".join(lines)
    return {"original_prompt": source, "injected_prompt": injected, "prompt_text": injected, "prompt_was_mutated": False, "constraint_block": block, "prompt_structure": {"source_prompt": source, "style_constraints": block}}


def create_style_constrained_prompt_version(session: Any, *, prompt_id: str, shot_id: int, original_prompt: str, prompt_structure: Mapping[str, Any] | None = None) -> dict[str, Any]:
    injected = inject_style_constraints(session, shot_id=shot_id, original_prompt=original_prompt)
    from core.production_prompt_lineage import create_production_prompt_version

    prompt = create_production_prompt_version(session, prompt_id=prompt_id, prompt_text=original_prompt, prompt_structure=dict(prompt_structure or {}), created_from="VISUAL_STYLE_CONSISTENCY", style_shot_id=shot_id)
    return {"prompt_version": prompt, "original_prompt": injected["original_prompt"], "injected_prompt": injected["injected_prompt"], "prompt_was_mutated": False, "constraint_block": injected["constraint_block"]}


__all__ = [
    "REFERENCE_TYPES",
    "SCOPES",
    "VisualStyleConsistencyError",
    "create_visual_style_profile",
    "get_visual_style_profile",
    "serialize_visual_style_profile",
    "add_style_reference_asset",
    "list_style_references",
    "bind_shot_style",
    "bind_episode_style",
    "validate_shot_style_consistency",
    "build_style_constraint_block",
    "inject_style_constraints",
    "create_style_constrained_prompt_version",
]
