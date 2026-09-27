"""Provider-free shot direction runtime over the existing StoryboardShot."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping

from models import ShotDirection, StoryboardShot


CAMERA_ANGLES = {"eye_level", "low_angle", "high_angle", "dutch", "overhead", "profile", "worm_eye"}
CAMERA_DISTANCES = {"extreme_wide", "wide", "medium", "medium shot", "medium_close_up", "medium close up", "close_up", "close up", "extreme_close_up", "extreme close up", "ms", "cu", "ecu", "ws", "ews"}
CAMERA_SPEEDS = {"slow", "medium", "fast"}
CAMERA_REQUIRED = ("lens", "angle", "distance", "movement", "speed")
COMPOSITION_REQUIRED = ("framing", "subject_position", "foreground", "background", "depth")
PERFORMANCE_REQUIRED = ("expression", "gesture", "body_motion", "eye_direction")


class ShotDirectionError(ValueError):
    status_code = 409
    code = "SHOT_DIRECTION_INVALID"

    def __init__(self, message: str, *, code: str | None = None, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.diagnostics = list(diagnostics or [])

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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _direction_dict(row: ShotDirection) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "shot_id": int(row.storyboard_shot_id),
        "storyboard_shot_id": int(row.storyboard_shot_id),
        "shot_type": row.shot_type,
        "camera_profile": _obj(row.camera_profile),
        "movement_profile": _obj(row.movement_profile),
        "composition_profile": _obj(row.composition_profile),
        "performance_profile": _obj(row.performance_profile),
        "emotion_profile": _obj(row.emotion_profile),
        "revision": int(row.revision),
        "direction_fingerprint": row.direction_fingerprint,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _resolve_shot(session: Any, shot_id: int) -> StoryboardShot:
    row = session.query(StoryboardShot).filter_by(id=int(shot_id)).one_or_none()
    if row is None:
        row = session.query(StoryboardShot).filter_by(shot_id=int(shot_id)).order_by(StoryboardShot.id.desc()).first()
    if row is None:
        raise ShotDirectionError("storyboard shot does not exist", code="SHOT_NOT_FOUND")
    return row


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _profile(value: Mapping[str, Any] | None, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ShotDirectionError(f"{field} must be an object", code="SHOT_DIRECTION_PROFILE_INVALID", diagnostics=[{"field": field, "expected": "object"}])
    return dict(value)


def _validate_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not str(payload.get("shot_type") or "").strip():
        errors.append({"code": "SHOT_TYPE_MISSING", "field": "shot_type"})
    camera = _obj(payload.get("camera_profile"))
    missing_camera = [field for field in CAMERA_REQUIRED if not str(camera.get(field) or "").strip()]
    if missing_camera:
        errors.append({"code": "CAMERA_PROFILE_INCOMPLETE", "field": "camera_profile", "missing": missing_camera})
    else:
        lens = camera.get("lens")
        lens_text = str(lens).strip().lower()
        if isinstance(lens, (int, float)):
            lens_valid = float(lens) > 0
        else:
            lens_valid = bool(re.fullmatch(r"\d+(?:\.\d+)?mm", lens_text))
        if not lens_valid:
            errors.append({"code": "CAMERA_LENS_INVALID", "field": "camera_profile.lens", "value": lens})
        angle = _normalize_key(camera.get("angle"))
        if angle not in CAMERA_ANGLES:
            errors.append({"code": "CAMERA_ANGLE_INVALID", "field": "camera_profile.angle", "value": camera.get("angle"), "allowed": sorted(CAMERA_ANGLES)})
        distance = str(camera.get("distance") or "").strip().lower()
        if distance not in CAMERA_DISTANCES:
            errors.append({"code": "CAMERA_DISTANCE_INVALID", "field": "camera_profile.distance", "value": camera.get("distance"), "allowed": sorted(CAMERA_DISTANCES)})
        speed = _normalize_key(camera.get("speed"))
        if speed not in CAMERA_SPEEDS:
            errors.append({"code": "CAMERA_SPEED_INVALID", "field": "camera_profile.speed", "value": camera.get("speed"), "allowed": sorted(CAMERA_SPEEDS)})
    movement = _obj(payload.get("movement_profile"))
    if not movement:
        errors.append({"code": "MOVEMENT_PROFILE_INCOMPLETE", "field": "movement_profile"})
    composition = _obj(payload.get("composition_profile"))
    missing_composition = [field for field in COMPOSITION_REQUIRED if not str(composition.get(field) or "").strip()]
    if missing_composition:
        errors.append({"code": "COMPOSITION_PROFILE_INCOMPLETE", "field": "composition_profile", "missing": missing_composition})
    performance = _obj(payload.get("performance_profile"))
    missing_performance = [field for field in PERFORMANCE_REQUIRED if not str(performance.get(field) or "").strip()]
    if missing_performance:
        errors.append({"code": "PERFORMANCE_PROFILE_INCOMPLETE", "field": "performance_profile", "missing": missing_performance})
    if not _obj(payload.get("emotion_profile")):
        errors.append({"code": "EMOTION_PROFILE_INCOMPLETE", "field": "emotion_profile"})
    return errors


def validate_shot_direction(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    row = session.query(ShotDirection).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").one_or_none()
    if row is None:
        errors = [{"code": "SHOT_DIRECTION_MISSING", "shot_id": int(shot.id)}]
        return {"shot_id": int(shot.id), "status": "BLOCKED", "direction": None, "errors": errors, "checks": {"shot_exists": True, "direction_present": False, "camera_valid": False, "complete": False}}
    payload = _direction_dict(row)
    errors = _validate_payload(payload)
    camera_errors = {"CAMERA_PROFILE_INCOMPLETE", "CAMERA_LENS_INVALID", "CAMERA_ANGLE_INVALID", "CAMERA_DISTANCE_INVALID", "CAMERA_SPEED_INVALID"}
    return {"shot_id": int(shot.id), "status": "PASS" if not errors else "BLOCKED", "direction": payload, "errors": errors, "checks": {"shot_exists": True, "direction_present": True, "camera_valid": not any(item["code"] in camera_errors for item in errors), "complete": not errors}}


def _persist_direction(session: Any, shot: StoryboardShot, payload: Mapping[str, Any], *, row: ShotDirection | None = None) -> dict[str, Any]:
    errors = _validate_payload(payload)
    if errors:
        raise ShotDirectionError("shot direction validation failed", code="SHOT_DIRECTION_INVALID", diagnostics=errors)
    if row is None:
        row = ShotDirection(storyboard_shot_id=shot.id, revision=1, status="ACTIVE")
        session.add(row)
    else:
        row.revision = int(row.revision) + 1
        row.updated_at = datetime.utcnow()
    row.shot_type = str(payload["shot_type"]).strip()
    row.camera_profile = _canonical(dict(payload["camera_profile"]))
    row.movement_profile = _canonical(dict(payload["movement_profile"]))
    row.composition_profile = _canonical(dict(payload["composition_profile"]))
    row.performance_profile = _canonical(dict(payload["performance_profile"]))
    row.emotion_profile = _canonical(dict(payload["emotion_profile"]))
    row.direction_fingerprint = _fingerprint({"shot_id": int(shot.id), "revision": int(row.revision), "shot_type": row.shot_type, "camera_profile": _obj(row.camera_profile), "movement_profile": _obj(row.movement_profile), "composition_profile": _obj(row.composition_profile), "performance_profile": _obj(row.performance_profile), "emotion_profile": _obj(row.emotion_profile)})
    row.status = "ACTIVE"
    session.flush()
    return _direction_dict(row)


def create_shot_direction(session: Any, *, shot_id: int, shot_type: str, camera_profile: Mapping[str, Any], movement_profile: Mapping[str, Any], composition_profile: Mapping[str, Any], performance_profile: Mapping[str, Any], emotion_profile: Mapping[str, Any]) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    existing = session.query(ShotDirection).filter_by(storyboard_shot_id=shot.id).one_or_none()
    payload = {"shot_type": shot_type, "camera_profile": _profile(camera_profile, "camera_profile"), "movement_profile": _profile(movement_profile, "movement_profile"), "composition_profile": _profile(composition_profile, "composition_profile"), "performance_profile": _profile(performance_profile, "performance_profile"), "emotion_profile": _profile(emotion_profile, "emotion_profile")}
    return _persist_direction(session, shot, payload, row=existing)


def update_shot_direction(session: Any, *, shot_id: int, shot_type: str | None = None, camera_profile: Mapping[str, Any] | None = None, movement_profile: Mapping[str, Any] | None = None, composition_profile: Mapping[str, Any] | None = None, performance_profile: Mapping[str, Any] | None = None, emotion_profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    row = session.query(ShotDirection).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").one_or_none()
    if row is None:
        raise ShotDirectionError("shot direction does not exist", code="SHOT_DIRECTION_NOT_FOUND")
    current = _direction_dict(row)
    payload = {"shot_type": current["shot_type"] if shot_type is None else shot_type, "camera_profile": current["camera_profile"] if camera_profile is None else _profile(camera_profile, "camera_profile"), "movement_profile": current["movement_profile"] if movement_profile is None else _profile(movement_profile, "movement_profile"), "composition_profile": current["composition_profile"] if composition_profile is None else _profile(composition_profile, "composition_profile"), "performance_profile": current["performance_profile"] if performance_profile is None else _profile(performance_profile, "performance_profile"), "emotion_profile": current["emotion_profile"] if emotion_profile is None else _profile(emotion_profile, "emotion_profile")}
    return _persist_direction(session, shot, payload, row=row)


def get_shot_direction(session: Any, *, shot_id: int) -> dict[str, Any]:
    shot = _resolve_shot(session, shot_id)
    row = session.query(ShotDirection).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").one_or_none()
    if row is None:
        raise ShotDirectionError("shot direction does not exist", code="SHOT_DIRECTION_NOT_FOUND")
    return _direction_dict(row)


def inject_shot_direction(session: Any, *, shot_id: int, original_prompt: str) -> dict[str, Any]:
    source = str(original_prompt or "")
    if not source.strip():
        raise ShotDirectionError("original prompt is required", code="ORIGINAL_PROMPT_REQUIRED")
    validation = validate_shot_direction(session, shot_id=shot_id)
    if validation["status"] != "PASS":
        raise ShotDirectionError("shot direction validation failed", code="SHOT_DIRECTION_BLOCKED", diagnostics=validation["errors"])
    direction = validation["direction"] or {}
    camera = direction["camera_profile"]
    composition = direction["composition_profile"]
    performance = direction["performance_profile"]
    emotion = direction["emotion_profile"]
    lines = [source, "", "Shot direction constraints:", f"- Camera Direction: {_canonical(camera)}", f"- Composition: {_canonical(composition)}", f"- Performance: {_canonical(performance)}", f"- Emotion: {_canonical(emotion)}", f"- Movement: {_canonical(direction['movement_profile'])}"]
    injected = "\n".join(lines)
    block = {"schema_version": "shot_direction_constraints_v1", "shot_id": int(validation["shot_id"]), "shot_type": direction["shot_type"], "camera_profile": camera, "movement_profile": direction["movement_profile"], "composition_profile": composition, "performance_profile": performance, "emotion_profile": emotion}
    return {"original_prompt": source, "injected_prompt": injected, "prompt_text": injected, "prompt_was_mutated": False, "constraint_block": block, "prompt_structure": {"source_prompt": source, "shot_direction": block}}


def create_shot_direction_prompt_version(session: Any, *, prompt_id: str, shot_id: int, original_prompt: str, prompt_structure: Mapping[str, Any] | None = None) -> dict[str, Any]:
    injected = inject_shot_direction(session, shot_id=shot_id, original_prompt=original_prompt)
    from core.production_prompt_lineage import create_production_prompt_version

    prompt = create_production_prompt_version(session, prompt_id=prompt_id, prompt_text=original_prompt, prompt_structure=dict(prompt_structure or {}), created_from="SHOT_DIRECTION", direction_shot_id=shot_id)
    return {"prompt_version": prompt, "original_prompt": injected["original_prompt"], "injected_prompt": injected["injected_prompt"], "prompt_was_mutated": False, "constraint_block": injected["constraint_block"]}


__all__ = ["ShotDirectionError", "create_shot_direction", "get_shot_direction", "update_shot_direction", "validate_shot_direction", "inject_shot_direction", "create_shot_direction_prompt_version"]
