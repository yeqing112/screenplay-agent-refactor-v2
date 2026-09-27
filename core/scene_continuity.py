"""Scene identity, reference, shot binding and continuity runtime."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence

from models import SceneReferenceAsset, ShotSceneBinding, StoryboardShot, VisualLocation, VisualReferenceAsset


REFERENCE_TYPES = {"overview", "layout", "lighting", "detail", "prop"}


class SceneContinuityError(ValueError):
    status_code = 409
    code = "SCENE_CONTINUITY_INVALID"

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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _scene_dict(row: VisualLocation) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "book_id": int(row.book_id),
        "scene_id": row.scene_id or str(row.id),
        "asset_key": row.asset_key or "",
        "name": row.name,
        "description": row.description or "",
        "attributes": _obj(row.attributes),
        "environment_profile": _obj(row.environment_profile),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _reference_dict(row: SceneReferenceAsset) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "scene_id": int(row.scene_id),
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


def _binding_dict(session: Any, row: ShotSceneBinding) -> dict[str, Any]:
    scene = session.query(VisualLocation).filter_by(id=row.scene_id).one_or_none()
    return {
        "id": int(row.id),
        "shot_id": int(row.storyboard_shot_id),
        "storyboard_shot_id": int(row.storyboard_shot_id),
        "scene_id": int(row.scene_id),
        "scene": _scene_dict(scene) if scene else None,
        "reference_asset_ids": [str(item) for item in _array(row.reference_asset_ids)],
        "environment_rules": _obj(row.environment_rules),
        "constraint_snapshot": _obj(row.constraint_snapshot),
        "asset_authority_id": row.asset_authority_id,
        "asset_version_id": row.asset_version_id,
        "binding_fingerprint": row.binding_fingerprint,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def get_scene_identity(session: Any, scene_id: int | str) -> VisualLocation:
    value = str(scene_id or "").strip()
    row = session.query(VisualLocation).filter_by(id=int(value)).one_or_none() if value.isdigit() else None
    if row is None and value:
        row = session.query(VisualLocation).filter_by(scene_id=value).order_by(VisualLocation.id.asc()).first()
    if row is None and value:
        row = session.query(VisualLocation).filter_by(asset_key=value).order_by(VisualLocation.id.asc()).first()
    if row is None:
        raise SceneContinuityError("scene identity does not exist", code="SCENE_IDENTITY_NOT_FOUND")
    return row


def create_scene_identity(
    session: Any,
    *,
    book_id: int,
    name: str,
    scene_id: str = "",
    description: str = "",
    attributes: Mapping[str, Any] | None = None,
    environment_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise SceneContinuityError("scene name is required", code="SCENE_NAME_REQUIRED")
    existing = session.query(VisualLocation).filter_by(book_id=int(book_id), name=normalized_name).order_by(VisualLocation.id.asc()).first()
    if existing is not None:
        return _scene_dict(existing)
    stable_id = str(scene_id or "").strip() or f"scene:{int(book_id)}:{normalized_name}"
    row = VisualLocation(book_id=int(book_id), scene_id=stable_id, name=normalized_name, description=str(description or ""), attributes=_canonical(dict(attributes or {})), environment_profile=_canonical(dict(environment_profile or {})))
    session.add(row)
    session.flush()
    return _scene_dict(row)


def serialize_scene_identity(session: Any, scene_id: int | str) -> dict[str, Any]:
    row = get_scene_identity(session, scene_id)
    references = session.query(SceneReferenceAsset).filter_by(scene_id=row.id, status="ACTIVE").order_by(SceneReferenceAsset.priority.asc(), SceneReferenceAsset.id.asc()).all()
    bindings = session.query(ShotSceneBinding).filter_by(scene_id=row.id, status="ACTIVE").order_by(ShotSceneBinding.id.asc()).all()
    return {**_scene_dict(row), "references": [_reference_dict(item) for item in references], "bindings": [_binding_dict(session, item) for item in bindings]}


def add_scene_reference_asset(
    session: Any,
    *,
    scene_id: int | str,
    asset_id: str,
    reference_type: str = "overview",
    priority: int = 0,
    visual_reference_asset_id: int | None = None,
    asset_version_id: str | None = None,
    constraint_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scene = get_scene_identity(session, scene_id)
    kind = str(reference_type or "").strip().lower()
    if kind not in REFERENCE_TYPES:
        raise SceneContinuityError("reference_type is unsupported", code="SCENE_REFERENCE_TYPE_INVALID")
    asset_key = str(asset_id or "").strip()
    if not asset_key:
        raise SceneContinuityError("asset_id is required", code="SCENE_REFERENCE_ASSET_REQUIRED")
    if int(priority) < 0:
        raise SceneContinuityError("priority must be non-negative", code="SCENE_REFERENCE_PRIORITY_INVALID")
    if visual_reference_asset_id is not None and session.query(VisualReferenceAsset).filter_by(id=int(visual_reference_asset_id)).one_or_none() is None:
        raise SceneContinuityError("visual reference asset does not exist", code="SCENE_REFERENCE_ASSET_NOT_FOUND")
    row = session.query(SceneReferenceAsset).filter_by(scene_id=scene.id, asset_id=asset_key, reference_type=kind).one_or_none()
    if row is None:
        row = SceneReferenceAsset(scene_id=scene.id, asset_id=asset_key, reference_type=kind, priority=int(priority), visual_reference_asset_id=visual_reference_asset_id, asset_version_id=str(asset_version_id or "") or None, constraint_snapshot=_canonical(dict(constraint_snapshot or {})), status="ACTIVE")
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


def list_scene_references(session: Any, scene_id: int | str) -> list[dict[str, Any]]:
    scene = get_scene_identity(session, scene_id)
    rows = session.query(SceneReferenceAsset).filter_by(scene_id=scene.id, status="ACTIVE").order_by(SceneReferenceAsset.priority.asc(), SceneReferenceAsset.id.asc()).all()
    return [_reference_dict(row) for row in rows]


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise SceneContinuityError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def bind_shot_scene(
    session: Any,
    *,
    shot_id: int,
    scene_id: int | str,
    reference_asset_ids: Sequence[int | str] | None = None,
    environment_rules: Mapping[str, Any] | None = None,
    constraint_snapshot: Mapping[str, Any] | None = None,
    asset_authority_id: str | None = None,
    asset_version_id: str | None = None,
) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    scene = get_scene_identity(session, scene_id)
    refs = session.query(SceneReferenceAsset).filter_by(scene_id=scene.id, status="ACTIVE").all()
    by_id = {str(row.id): row for row in refs}
    by_asset = {str(row.asset_id): row for row in refs}
    selected: list[str] = []
    for value in (reference_asset_ids or ()):
        row = by_id.get(str(value)) or by_asset.get(str(value))
        if row is None:
            raise SceneContinuityError("reference asset is not bound to the scene", code="SCENE_REFERENCE_BINDING_INVALID", diagnostics=[{"reference_asset_id": str(value), "scene_id": scene.id}])
        selected.append(str(row.asset_id))
    if not selected and refs:
        selected = [str(row.asset_id) for row in sorted(refs, key=lambda item: (int(item.priority), int(item.id)))]
    environment = dict(environment_rules or {})
    snapshot = dict(constraint_snapshot or {})
    snapshot.setdefault("scene_identity", {"description": scene.description or "", "attributes": _obj(scene.attributes), "environment_profile": _obj(scene.environment_profile)})
    snapshot.setdefault("reference_asset_ids", selected)
    basis = {"shot_id": int(shot.id), "scene_id": int(scene.id), "reference_asset_ids": selected, "environment_rules": environment, "constraint_snapshot": snapshot, "asset_authority_id": asset_authority_id or "", "asset_version_id": asset_version_id or ""}
    fingerprint = _fingerprint(basis)
    session.query(ShotSceneBinding).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").update({"status": "STALE", "updated_at": datetime.utcnow()}, synchronize_session=False)
    row = ShotSceneBinding(storyboard_shot_id=shot.id, scene_id=scene.id, reference_asset_ids=_canonical(selected), environment_rules=_canonical(environment), constraint_snapshot=_canonical(snapshot), asset_authority_id=str(asset_authority_id or "") or None, asset_version_id=str(asset_version_id or "") or None, binding_fingerprint=fingerprint, status="ACTIVE")
    session.add(row)
    session.flush()
    return _binding_dict(session, row)


def validate_scene_continuity(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    rows = session.query(ShotSceneBinding).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").order_by(ShotSceneBinding.id.asc()).all()
    errors: list[dict[str, Any]] = []
    if not rows:
        errors.append({"code": "SCENE_BINDING_MISSING", "shot_id": int(shot.id)})
    if len(rows) > 1:
        errors.append({"code": "SCENE_BINDING_MULTIPLE", "shot_id": int(shot.id), "binding_count": len(rows)})
    resolved = []
    for row in rows:
        scene = session.query(VisualLocation).filter_by(id=row.scene_id).one_or_none()
        if scene is None:
            errors.append({"code": "SCENE_IDENTITY_MISSING", "binding_id": row.id, "scene_id": row.scene_id})
            continue
        refs = session.query(SceneReferenceAsset).filter_by(scene_id=scene.id, status="ACTIVE").all()
        selected = [str(item) for item in _array(row.reference_asset_ids)]
        available = {str(item.id) for item in refs} | {str(item.asset_id) for item in refs}
        if not refs:
            errors.append({"code": "SCENE_REFERENCE_ASSET_MISSING", "binding_id": row.id, "scene_id": scene.id})
        missing = [item for item in selected if item not in available]
        if missing:
            errors.append({"code": "SCENE_REFERENCE_BINDING_INVALID", "binding_id": row.id, "missing_reference_asset_ids": missing})
        if not (scene.description or _obj(scene.attributes) or _obj(scene.environment_profile)):
            errors.append({"code": "SCENE_CONSTRAINTS_MISSING", "binding_id": row.id, "scene_id": scene.id})
        resolved.append(_binding_dict(session, row))
    return {"shot_id": int(shot.id), "status": "PASS" if not errors else "BLOCKED", "binding_count": len(rows), "bindings": resolved, "errors": errors, "checks": {"scene_bound": len(rows) == 1, "reference_asset_present": len(rows) == 1 and not any(item["code"] == "SCENE_REFERENCE_ASSET_MISSING" for item in errors), "constraints_present": not any(item["code"] == "SCENE_CONSTRAINTS_MISSING" for item in errors)}}


def build_scene_constraint_block(session: Any, *, shot_id: int | None = None, scene_id: int | str | None = None) -> dict[str, Any]:
    binding = None
    if shot_id is not None:
        validation = validate_scene_continuity(session, shot_id=shot_id)
        if validation["status"] != "PASS":
            raise SceneContinuityError("scene continuity validation failed", code="SCENE_CONTINUITY_BLOCKED", diagnostics=validation["errors"])
        binding = validation["bindings"][0]
        scene_payload = binding["scene"] or {}
    else:
        scene = get_scene_identity(session, scene_id or "")
        refs = list_scene_references(session, scene.id)
        if not refs:
            raise SceneContinuityError("scene has no reference assets", code="SCENE_REFERENCE_ASSET_MISSING")
        scene_payload = _scene_dict(scene)
        binding = {"scene_id": scene.id, "reference_asset_ids": [item["asset_id"] for item in refs], "environment_rules": {}}
    references = session.query(SceneReferenceAsset).filter_by(scene_id=int(binding["scene_id"]), status="ACTIVE").order_by(SceneReferenceAsset.priority.asc(), SceneReferenceAsset.id.asc()).all()
    selected = set(str(item) for item in binding["reference_asset_ids"])
    constraints = [{"asset_id": row.asset_id, "reference_type": row.reference_type, "priority": int(row.priority), "constraint_snapshot": _obj(row.constraint_snapshot)} for row in references if not selected or str(row.asset_id) in selected]
    return {"schema_version": "scene_continuity_constraints_v1", "scene_id": int(binding["scene_id"]), "scene": scene_payload, "environment_rules": binding.get("environment_rules", {}), "reference_constraints": constraints}


def inject_scene_constraints(session: Any, *, original_prompt: str, shot_id: int | None = None, scene_id: int | str | None = None) -> dict[str, Any]:
    source = str(original_prompt or "")
    if not source.strip():
        raise SceneContinuityError("original prompt is required", code="ORIGINAL_PROMPT_REQUIRED")
    block = build_scene_constraint_block(session, shot_id=shot_id, scene_id=scene_id)
    scene = block["scene"] or {}
    lines = [source, "", "Scene continuity constraints:", f"- {scene.get('name', '')}: {scene.get('description', '')}"]
    if scene.get("attributes"):
        lines.append(f"  attributes: {_canonical(scene['attributes'])}")
    if scene.get("environment_profile"):
        lines.append(f"  environment profile: {_canonical(scene['environment_profile'])}")
    if block["environment_rules"]:
        lines.append(f"  shot environment rules: {_canonical(block['environment_rules'])}")
    if block["reference_constraints"]:
        lines.append(f"  reference constraints: {_canonical(block['reference_constraints'])}")
    return {"original_prompt": source, "injected_prompt": "\n".join(lines), "prompt_text": "\n".join(lines), "prompt_was_mutated": False, "constraint_block": block, "prompt_structure": {"source_prompt": source, "scene_constraints": block}}


def create_scene_constrained_prompt_version(session: Any, *, prompt_id: str, shot_id: int, original_prompt: str, prompt_structure: Mapping[str, Any] | None = None) -> dict[str, Any]:
    injected = inject_scene_constraints(session, shot_id=shot_id, original_prompt=original_prompt)
    from core.production_prompt_lineage import create_production_prompt_version

    prompt = create_production_prompt_version(session, prompt_id=prompt_id, prompt_text=original_prompt, prompt_structure=dict(prompt_structure or {}), created_from="SCENE_CONTINUITY", scene_shot_id=shot_id)
    return {"prompt_version": prompt, "original_prompt": injected["original_prompt"], "injected_prompt": injected["injected_prompt"], "prompt_was_mutated": False, "constraint_block": injected["constraint_block"]}


__all__ = ["REFERENCE_TYPES", "SceneContinuityError", "create_scene_identity", "get_scene_identity", "serialize_scene_identity", "add_scene_reference_asset", "list_scene_references", "bind_shot_scene", "validate_scene_continuity", "build_scene_constraint_block", "inject_scene_constraints", "create_scene_constrained_prompt_version"]
