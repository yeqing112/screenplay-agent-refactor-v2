"""Provider-free keyframe authoring runtime over StoryboardShot and ShotDirection."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from models import Keyframe, KeyframeAssetBinding, KeyframeSequence, ProductionPromptVersion, StoryboardShot
from core.production_asset_authority import resolve_current_production_asset_binding


FRAME_TYPES = {"start", "middle", "end"}
MOTION_FIELDS = ("camera_motion", "character_motion", "environment_motion", "emotion_transition")


class KeyframeAuthoringError(ValueError):
    status_code = 409
    code = "KEYFRAME_AUTHORING_INVALID"

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


def _keyframe_binding_fingerprint(*, keyframe_id: int, storyboard_shot_id: int, asset_type: str, authority_fingerprint: str, version_fingerprint: str, pointer_fingerprint: str) -> str:
    """Return a unique binding identity for one keyframe-to-asset edge.

    Production asset bindings are shot-scoped, while keyframe bindings are
    edges from an individual frame to an existing authoritative asset.  The
    frame identity must therefore participate in the fingerprint so that the
    same scene/character asset can be used by both the start and end frames.
    """
    return _fingerprint({
        "schema": "keyframe_asset_binding_v1",
        "keyframe_id": int(keyframe_id),
        "storyboard_shot_id": int(storyboard_shot_id),
        "asset_type": str(asset_type).upper(),
        "authority_fingerprint": authority_fingerprint,
        "version_fingerprint": version_fingerprint,
        "pointer_fingerprint": pointer_fingerprint,
    })


def _obj(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        return list(parsed) if isinstance(parsed, list) else []
    return []


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise KeyframeAuthoringError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def _resolve_sequence(session: Any, shot_id: int, *, active_only: bool = True) -> KeyframeSequence:
    shot = _resolve_shot(session, shot_id)
    query = session.query(KeyframeSequence).filter_by(storyboard_shot_id=shot.id)
    if active_only:
        query = query.filter(KeyframeSequence.status == "ACTIVE")
    row = query.order_by(KeyframeSequence.revision.desc(), KeyframeSequence.id.desc()).first()
    if row is None:
        raise KeyframeAuthoringError("keyframe sequence does not exist", code="KEYFRAME_SEQUENCE_NOT_FOUND")
    return row


def _normalize_frame(raw: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise KeyframeAuthoringError("each keyframe must be an object", code="KEYFRAME_INVALID", diagnostics=[{"index": index, "reason": "object_required"}])
    frame_type = str(raw.get("type") or raw.get("frame_type") or "").strip().lower()
    if frame_type not in FRAME_TYPES:
        raise KeyframeAuthoringError("keyframe type must be start, middle, or end", code="KEYFRAME_TYPE_INVALID", diagnostics=[{"index": index, "value": frame_type}])
    try:
        time_seconds = float(raw.get("time") if raw.get("time") is not None else raw.get("time_seconds"))
    except (TypeError, ValueError):
        raise KeyframeAuthoringError("keyframe time must be numeric", code="KEYFRAME_TIME_INVALID", diagnostics=[{"index": index}]) from None
    if time_seconds < 0:
        raise KeyframeAuthoringError("keyframe time must be non-negative", code="KEYFRAME_TIME_INVALID", diagnostics=[{"index": index, "time": time_seconds}])
    description = str(raw.get("description") or "").strip()
    if not description:
        raise KeyframeAuthoringError("keyframe description is required", code="KEYFRAME_DESCRIPTION_REQUIRED", diagnostics=[{"index": index}])
    frame = {
        "type": frame_type,
        "time": time_seconds,
        "description": description,
        "camera_state": _obj(raw.get("camera_state", raw.get("cameraState"))),
        "character_state": _obj(raw.get("character_state", raw.get("characterState"))),
        "scene_state": _obj(raw.get("scene_state", raw.get("sceneState"))),
        "emotion_state": _obj(raw.get("emotion_state", raw.get("emotionState"))),
    }
    for field in MOTION_FIELDS:
        camel = "".join([field.split("_")[0], *[part.title() for part in field.split("_")[1:]]])
        frame[field] = str(raw.get(field, raw.get(camel, "")) or "").strip()
    return frame


def _validate_frames(duration: float, frames: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(frames):
        try:
            normalized.append(_normalize_frame(raw, index=index))
        except KeyframeAuthoringError as exc:
            diagnostics.extend(exc.diagnostics or [{"index": index, "code": exc.code}])
    if not normalized:
        diagnostics.append({"code": "KEYFRAME_LIST_EMPTY"})
        return normalized, diagnostics
    ordered = sorted(normalized, key=lambda item: item["time"])
    if len({item["time"] for item in ordered}) != len(ordered):
        diagnostics.append({"code": "KEYFRAME_TIME_DUPLICATE"})
    for left, right in zip(ordered, ordered[1:]):
        if right["time"] <= left["time"]:
            diagnostics.append({"code": "KEYFRAME_ORDER_INVALID"})
            break
    starts = [item for item in ordered if item["type"] == "start"]
    ends = [item for item in ordered if item["type"] == "end"]
    if len(starts) != 1:
        diagnostics.append({"code": "KEYFRAME_START_REQUIRED", "count": len(starts)})
    if len(ends) != 1:
        diagnostics.append({"code": "KEYFRAME_END_REQUIRED", "count": len(ends)})
    if starts and abs(starts[0]["time"]) > 1e-6:
        diagnostics.append({"code": "KEYFRAME_START_TIME_INVALID", "expected": 0, "actual": starts[0]["time"]})
    if ends and abs(ends[0]["time"] - duration) > 1e-6:
        diagnostics.append({"code": "KEYFRAME_END_TIME_INVALID", "expected": duration, "actual": ends[0]["time"]})
    for item in ordered:
        if item["time"] > duration:
            diagnostics.append({"code": "KEYFRAME_TIME_OUT_OF_RANGE", "time": item["time"], "duration": duration})
    return ordered, diagnostics


def _frame_dict(row: Keyframe) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "keyframe_sequence_id": int(row.keyframe_sequence_id),
        "type": row.frame_type,
        "frame_type": row.frame_type,
        "time": float(row.time_seconds),
        "time_seconds": float(row.time_seconds),
        "order_index": int(row.order_index),
        "description": row.description,
        "camera_state": _obj(row.camera_state),
        "character_state": _obj(row.character_state),
        "scene_state": _obj(row.scene_state),
        "emotion_state": _obj(row.emotion_state),
        "camera_motion": row.camera_motion,
        "character_motion": row.character_motion,
        "environment_motion": row.environment_motion,
        "emotion_transition": row.emotion_transition,
        "frame_fingerprint": row.frame_fingerprint,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _binding_dict(row: KeyframeAssetBinding) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "keyframe_id": int(row.keyframe_id),
        "shot_id": int(row.storyboard_shot_id),
        "storyboard_shot_id": int(row.storyboard_shot_id),
        "asset_type": row.asset_type,
        "authority_id": row.authority_id,
        "version_id": row.version_id,
        "binding_fingerprint": row.binding_fingerprint,
        "is_primary": bool(row.is_primary),
        "status": row.status,
        "created_at": _iso(row.created_at),
    }


def _sequence_dict(session: Any, row: KeyframeSequence) -> dict[str, Any]:
    frames = session.query(Keyframe).filter_by(keyframe_sequence_id=row.id, status="ACTIVE").order_by(Keyframe.time_seconds.asc(), Keyframe.id.asc()).all()
    assets = session.query(KeyframeAssetBinding).filter_by(status="ACTIVE").filter(KeyframeAssetBinding.keyframe_id.in_([item.id for item in frames] or [-1])).order_by(KeyframeAssetBinding.keyframe_id.asc(), KeyframeAssetBinding.id.asc()).all()
    return {
        "id": int(row.id),
        "shot_id": int(row.storyboard_shot_id),
        "storyboard_shot_id": int(row.storyboard_shot_id),
        "duration": float(row.duration),
        "status": row.status,
        "frame_plan": _obj(row.frame_plan),
        "revision": int(row.revision),
        "sequence_fingerprint": row.sequence_fingerprint,
        "frames": [_frame_dict(item) for item in frames],
        "asset_bindings": [_binding_dict(item) for item in assets],
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _frame_fingerprint(sequence_id: int, frame: Mapping[str, Any], *, revision: int) -> str:
    return _fingerprint({"schema": "keyframe_v1", "sequence_id": int(sequence_id), "revision": int(revision), "frame": dict(frame)})


def _sequence_fingerprint(shot_id: int, revision: int, duration: float, frame_plan: Mapping[str, Any], frames: Sequence[Mapping[str, Any]]) -> str:
    return _fingerprint({"schema": "keyframe_sequence_v1", "shot_id": int(shot_id), "revision": int(revision), "duration": duration, "frame_plan": dict(frame_plan), "frames": [dict(item) for item in frames]})


def create_keyframe_sequence(session: Any, *, shot_id: int, duration: float, frame_plan: Mapping[str, Any] | None, frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    try:
        duration_value = float(duration)
    except (TypeError, ValueError):
        raise KeyframeAuthoringError("duration must be numeric", code="KEYFRAME_DURATION_INVALID") from None
    if duration_value <= 0:
        raise KeyframeAuthoringError("duration must be positive", code="KEYFRAME_DURATION_INVALID")
    normalized, diagnostics = _validate_frames(duration_value, frames)
    if diagnostics:
        raise KeyframeAuthoringError("keyframe sequence validation failed", code="KEYFRAME_SEQUENCE_INVALID", diagnostics=diagnostics)
    plan = dict(frame_plan or {})
    previous = session.query(KeyframeSequence).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").order_by(KeyframeSequence.revision.desc()).first()
    revision = int(previous.revision) + 1 if previous else 1
    if previous is not None:
        previous.status = "STALE"
        previous.updated_at = datetime.utcnow()
    row = KeyframeSequence(storyboard_shot_id=shot.id, duration=duration_value, status="ACTIVE", frame_plan=_canonical(plan), revision=revision, sequence_fingerprint=_sequence_fingerprint(shot.id, revision, duration_value, plan, normalized))
    session.add(row)
    session.flush()
    for index, frame in enumerate(normalized):
        session.add(Keyframe(keyframe_sequence_id=row.id, frame_type=frame["type"], time_seconds=frame["time"], order_index=index, description=frame["description"], camera_state=_canonical(frame["camera_state"]), character_state=_canonical(frame["character_state"]), scene_state=_canonical(frame["scene_state"]), emotion_state=_canonical(frame["emotion_state"]), camera_motion=frame["camera_motion"], character_motion=frame["character_motion"], environment_motion=frame["environment_motion"], emotion_transition=frame["emotion_transition"], frame_fingerprint=_frame_fingerprint(row.id, frame, revision=1), status="ACTIVE"))
    session.flush()
    return _sequence_dict(session, row)


def get_keyframe_sequence(session: Any, *, shot_id: int) -> dict[str, Any]:
    return _sequence_dict(session, _resolve_sequence(session, shot_id))


def validate_keyframe_sequence(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    sequence = session.query(KeyframeSequence).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").order_by(KeyframeSequence.revision.desc()).first()
    if sequence is None:
        return {"shot_id": int(shot.id), "status": "BLOCKED", "sequence": None, "errors": [{"code": "KEYFRAME_SEQUENCE_MISSING"}], "checks": {"shot_exists": True, "sequence_present": False, "order_valid": False, "start_end_complete": False, "prompt_lineage_present": False, "asset_binding_correct": False}}
    frames = session.query(Keyframe).filter_by(keyframe_sequence_id=sequence.id, status="ACTIVE").order_by(Keyframe.time_seconds.asc(), Keyframe.id.asc()).all()
    payloads = [_frame_dict(item) for item in frames]
    _, diagnostics = _validate_frames(float(sequence.duration), payloads)
    order_codes = {"KEYFRAME_ORDER_INVALID", "KEYFRAME_TIME_DUPLICATE", "KEYFRAME_TIME_OUT_OF_RANGE"}
    boundary_codes = {"KEYFRAME_START_REQUIRED", "KEYFRAME_END_REQUIRED", "KEYFRAME_START_TIME_INVALID", "KEYFRAME_END_TIME_INVALID"}
    lineage_present = False
    for prompt_row in session.query(ProductionPromptVersion).all():
        structure = _obj(prompt_row.prompt_structure)
        keyframe = structure.get("keyframe")
        if "KEYFRAME_AUTHORING" in str(prompt_row.created_from or "") and isinstance(keyframe, Mapping) and int(keyframe.get("sequence_id", -1)) == int(sequence.id):
            lineage_present = True
            break
    active_assets = session.query(KeyframeAssetBinding).filter_by(status="ACTIVE").filter(KeyframeAssetBinding.keyframe_id.in_([item.id for item in frames] or [-1])).all()
    asset_binding_correct = bool(frames) and all(item.status == "ACTIVE" and item.keyframe_id in {frame.id for frame in frames} and item.storyboard_shot_id == shot.id for item in active_assets) and any(item.is_primary for item in active_assets if item.keyframe_id == frames[0].id)
    errors = [{"code": item.get("code", "KEYFRAME_INVALID"), **item} for item in diagnostics]
    if not lineage_present:
        errors.append({"code": "KEYFRAME_PROMPT_LINEAGE_MISSING"})
    if not asset_binding_correct:
        errors.append({"code": "KEYFRAME_ASSET_BINDING_MISSING"})
    return {"shot_id": int(shot.id), "status": "PASS" if not errors else "BLOCKED", "sequence": _sequence_dict(session, sequence), "errors": errors, "checks": {"shot_exists": True, "sequence_present": True, "order_valid": not any(item.get("code") in order_codes for item in diagnostics), "start_end_complete": not any(item.get("code") in boundary_codes for item in diagnostics), "prompt_lineage_present": lineage_present, "asset_binding_correct": asset_binding_correct}}


def update_keyframe(session: Any, *, keyframe_id: int, values: Mapping[str, Any]) -> dict[str, Any]:
    row = session.query(Keyframe).filter_by(id=int(keyframe_id), status="ACTIVE").one_or_none()
    if row is None:
        raise KeyframeAuthoringError("keyframe does not exist", code="KEYFRAME_NOT_FOUND")
    sequence = session.query(KeyframeSequence).filter_by(id=row.keyframe_sequence_id, status="ACTIVE").one_or_none()
    if sequence is None:
        raise KeyframeAuthoringError("keyframe sequence does not exist", code="KEYFRAME_SEQUENCE_NOT_FOUND")
    current = _frame_dict(row)
    merged = {**current, **dict(values)}
    normalized, diagnostics = _validate_frames(float(sequence.duration), [merged if item.id == row.id else _frame_dict(item) for item in session.query(Keyframe).filter_by(keyframe_sequence_id=sequence.id, status="ACTIVE").all()])
    if diagnostics:
        raise KeyframeAuthoringError("keyframe update validation failed", code="KEYFRAME_INVALID", diagnostics=diagnostics)
    target = next(item for item in normalized if item["time"] == float(merged.get("time", merged.get("time_seconds"))))
    row.frame_type = target["type"]
    row.time_seconds = target["time"]
    row.order_index = next(index for index, item in enumerate(normalized) if item is target)
    row.description = target["description"]
    row.camera_state = _canonical(target["camera_state"])
    row.character_state = _canonical(target["character_state"])
    row.scene_state = _canonical(target["scene_state"])
    row.emotion_state = _canonical(target["emotion_state"])
    for field in MOTION_FIELDS:
        setattr(row, field, target[field])
    row.frame_fingerprint = _frame_fingerprint(sequence.id, target, revision=int(sequence.revision) + 1)
    row.updated_at = datetime.utcnow()
    sequence.revision = int(sequence.revision) + 1
    sequence.updated_at = datetime.utcnow()
    frames = [item for item in normalized]
    sequence.sequence_fingerprint = _sequence_fingerprint(sequence.storyboard_shot_id, sequence.revision, float(sequence.duration), _obj(sequence.frame_plan), frames)
    session.flush()
    return _frame_dict(row)


def inject_keyframe_constraints(session: Any, *, keyframe_id: int, original_prompt: str) -> dict[str, Any]:
    source = str(original_prompt or "")
    if not source.strip():
        raise KeyframeAuthoringError("original prompt is required", code="ORIGINAL_PROMPT_REQUIRED")
    row = session.query(Keyframe).filter_by(id=int(keyframe_id), status="ACTIVE").one_or_none()
    if row is None:
        raise KeyframeAuthoringError("keyframe does not exist", code="KEYFRAME_NOT_FOUND")
    sequence = session.query(KeyframeSequence).filter_by(id=row.keyframe_sequence_id, status="ACTIVE").one_or_none()
    if sequence is None:
        raise KeyframeAuthoringError("keyframe sequence does not exist", code="KEYFRAME_SEQUENCE_NOT_FOUND")
    from core.shot_direction import inject_shot_direction

    if "Shot direction constraints:" in source:
        direction = {"injected_prompt": source}
    else:
        direction = inject_shot_direction(session, shot_id=sequence.storyboard_shot_id, original_prompt=source)
    frame = _frame_dict(row)
    block = {"schema_version": "keyframe_constraints_v1", "keyframe_id": int(row.id), "sequence_id": int(sequence.id), "frame_type": row.frame_type, "time_seconds": float(row.time_seconds), "description": row.description, "camera_state": frame["camera_state"], "character_state": frame["character_state"], "scene_state": frame["scene_state"], "emotion_state": frame["emotion_state"], "motion_intent": {field: frame[field] for field in MOTION_FIELDS}}
    injected = "\n".join([direction["injected_prompt"], "", "Frame State:", f"- { _canonical({key: block[key] for key in ('frame_type','time_seconds','description','camera_state','character_state','scene_state','emotion_state')}) }", "Motion Preparation:", f"- {_canonical(block['motion_intent'])}"])
    return {"original_prompt": source, "injected_prompt": injected, "prompt_text": injected, "prompt_was_mutated": False, "constraint_block": block, "prompt_structure": {"keyframe": block}}


def create_keyframe_prompt_version(session: Any, *, keyframe_id: int, prompt_id: str, original_prompt: str, prompt_structure: Mapping[str, Any] | None = None) -> dict[str, Any]:
    injected = inject_keyframe_constraints(session, keyframe_id=keyframe_id, original_prompt=original_prompt)
    row = session.query(Keyframe).filter_by(id=int(keyframe_id), status="ACTIVE").one()
    sequence = session.query(KeyframeSequence).filter_by(id=row.keyframe_sequence_id, status="ACTIVE").one()
    from core.production_prompt_lineage import create_production_prompt_version

    prompt = create_production_prompt_version(session, prompt_id=prompt_id, prompt_text=original_prompt, prompt_structure={**dict(prompt_structure or {}), **injected["prompt_structure"]}, created_from="KEYFRAME_AUTHORING", direction_shot_id=sequence.storyboard_shot_id, keyframe_id=row.id)
    return {"prompt_version": prompt, "original_prompt": injected["original_prompt"], "injected_prompt": injected["injected_prompt"], "prompt_was_mutated": False, "constraint_block": injected["constraint_block"]}


def bind_keyframe_asset(session: Any, *, keyframe_id: int, asset_type: str, authority_id: str, version_id: str, is_primary: bool = False) -> dict[str, Any]:
    row = session.query(Keyframe).filter_by(id=int(keyframe_id), status="ACTIVE").one_or_none()
    if row is None:
        raise KeyframeAuthoringError("keyframe does not exist", code="KEYFRAME_NOT_FOUND")
    sequence = session.query(KeyframeSequence).filter_by(id=row.keyframe_sequence_id, status="ACTIVE").one_or_none()
    if sequence is None:
        raise KeyframeAuthoringError("keyframe sequence does not exist", code="KEYFRAME_SEQUENCE_NOT_FOUND")
    kind = str(asset_type or "").strip().upper()
    if kind not in {"CHARACTER", "SCENE", "PROP"}:
        raise KeyframeAuthoringError("asset_type is unsupported", code="KEYFRAME_ASSET_TYPE_INVALID")
    existing = session.query(KeyframeAssetBinding).filter_by(keyframe_id=row.id, asset_type=kind, authority_id=str(authority_id), version_id=str(version_id)).one_or_none()
    if existing is None:
        existing = KeyframeAssetBinding(keyframe_id=row.id, storyboard_shot_id=sequence.storyboard_shot_id, asset_type=kind, authority_id=str(authority_id), version_id=str(version_id), binding_fingerprint="pending", is_primary=bool(is_primary), status="ACTIVE")
        session.add(existing)
        session.flush()
    result = resolve_current_production_asset_binding(session, existing)
    failed = [item for item in result.get("failed_checks", []) if item != "binding_fingerprint"]
    if failed or not result.get("binding_fingerprint"):
        if existing.id and existing.binding_fingerprint == "pending":
            session.delete(existing)
            session.flush()
        raise KeyframeAuthoringError("keyframe asset binding is not current", code="KEYFRAME_ASSET_BINDING_INVALID", diagnostics=[{"check": item} for item in failed or ["asset_resolution"]])
    existing.binding_fingerprint = _keyframe_binding_fingerprint(
        keyframe_id=int(row.id),
        storyboard_shot_id=int(sequence.storyboard_shot_id),
        asset_type=kind,
        authority_fingerprint=str(result.get("authority_fingerprint") or ""),
        version_fingerprint=str(result.get("version_fingerprint") or ""),
        pointer_fingerprint=str(result.get("pointer_fingerprint") or ""),
    )
    existing.is_primary = bool(is_primary)
    existing.status = "ACTIVE"
    if existing.is_primary:
        session.query(KeyframeAssetBinding).filter(KeyframeAssetBinding.keyframe_id == row.id, KeyframeAssetBinding.id != existing.id, KeyframeAssetBinding.status == "ACTIVE").update({"is_primary": False}, synchronize_session=False)
    session.flush()
    return _binding_dict(existing)


__all__ = ["KeyframeAuthoringError", "create_keyframe_sequence", "get_keyframe_sequence", "validate_keyframe_sequence", "update_keyframe", "inject_keyframe_constraints", "create_keyframe_prompt_version", "bind_keyframe_asset"]
