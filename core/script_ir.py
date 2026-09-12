"""Deterministic ScriptIR normalization, validation and legacy reconstruction."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "script_ir_v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def script_ir_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_script_ir(payload: Any, *, book_id: int, episode: int, fact_snapshot_id: str = "", source_outline_revision: str = "") -> dict[str, Any]:
    """Normalize a structured script payload into ScriptIR v1."""
    source = payload if isinstance(payload, dict) else {}
    raw_scenes = source.get("scenes") if isinstance(source.get("scenes"), list) else []
    scenes: list[dict[str, Any]] = []
    for scene_index, raw_scene in enumerate(raw_scenes, start=1):
        if not isinstance(raw_scene, dict):
            continue
        name = _text(raw_scene.get("name") or raw_scene.get("scene_name")) or f"未命名场景{scene_index}"
        scene_id = _text(raw_scene.get("scene_id")) or f"E{int(episode):02d}_SC{scene_index:03d}"
        raw_beats = raw_scene.get("beats") if isinstance(raw_scene.get("beats"), list) else []
        beats = []
        for beat_index, raw_beat in enumerate(raw_beats, start=1):
            if isinstance(raw_beat, dict):
                beats.append({
                    "beat_id": _text(raw_beat.get("beat_id") or raw_beat.get("id")) or f"{scene_id}_B{beat_index:02d}",
                    "type": _text(raw_beat.get("type")),
                    "event": _text(raw_beat.get("event") or raw_beat.get("description") or raw_beat.get("content")),
                    "dramatic_function": _text(raw_beat.get("dramatic_function")),
                    "information_change": _text(raw_beat.get("information_change")),
                    "emotion_change": _text(raw_beat.get("emotion_change")),
                })
            elif _text(raw_beat):
                beats.append({"beat_id": f"{scene_id}_B{beat_index:02d}", "type": "action", "event": _text(raw_beat), "dramatic_function": "", "information_change": "", "emotion_change": ""})
        scenes.append({
            "scene_id": scene_id,
            "name": name,
            "location_id": _text(raw_scene.get("location_id")),
            "location_name": _text(raw_scene.get("location_name") or name),
            "time_of_day": _text(raw_scene.get("time_of_day")),
            "weather": _text(raw_scene.get("weather")),
            "participants": raw_scene.get("participants") if isinstance(raw_scene.get("participants"), list) else [],
            "beats": beats,
            "actions": raw_scene.get("actions") if isinstance(raw_scene.get("actions"), list) else [],
            "dialogues": raw_scene.get("dialogues") if isinstance(raw_scene.get("dialogues"), list) else [],
            "state_in": raw_scene.get("state_in") if isinstance(raw_scene.get("state_in"), dict) else {},
            "state_out": raw_scene.get("state_out") if isinstance(raw_scene.get("state_out"), dict) else {},
            "required_visual_proofs": raw_scene.get("required_visual_proofs") if isinstance(raw_scene.get("required_visual_proofs"), list) else [],
            "blocking_hints": raw_scene.get("blocking_hints") if isinstance(raw_scene.get("blocking_hints"), list) else [],
            "asset_mentions": raw_scene.get("asset_mentions") if isinstance(raw_scene.get("asset_mentions"), list) else [],
        })
    result = {
        "schema_version": SCHEMA_VERSION,
        "book_id": int(book_id),
        "episode": int(episode),
        "fact_snapshot_id": _text(fact_snapshot_id),
        "title": _text(source.get("title")),
        "episode_objective": _text(source.get("episode_objective")),
        "characters": source.get("characters") if isinstance(source.get("characters"), list) else [],
        "scenes": scenes,
    }
    result["payload_hash"] = script_ir_hash(result)
    return result


def legacy_markdown_to_script_ir(markdown: str, *, book_id: int, episode: int) -> dict[str, Any]:
    """Best-effort one-time reconstruction; callers must mark needs_review."""
    scenes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in str(markdown or "").splitlines():
        text = line.strip()
        heading = re.match(r"^#{2,4}\s+(.+?)\s*$", text)
        if heading:
            current = {"name": heading.group(1).strip(), "beats": []}
            scenes.append(current)
        elif text and current is not None and not text.startswith("#"):
            current.setdefault("beats", []).append({"type": "action", "event": text})
    return build_script_ir({"scenes": scenes}, book_id=book_id, episode=episode)


def validate_script_ir(payload: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "SCHEMA_VERSION_INVALID", "message": "ScriptIR schema_version must be script_ir_v1."})
        return {"status": "invalid", "errors": errors, "warnings": warnings}
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append({"code": "SCENES_REQUIRED", "message": "ScriptIR must contain at least one scene."})
    seen_ids: set[str] = set()
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_OBJECT_INVALID", "message": "Each scene must be an object."})
            continue
        scene_id = _text(scene.get("scene_id"))
        name = _text(scene.get("name"))
        if not scene_id or scene_id in seen_ids:
            errors.append({"code": "SCENE_ID_INVALID", "message": "Scene IDs must be present and unique."})
        seen_ids.add(scene_id)
        if not name:
            errors.append({"code": "SCENE_NAME_REQUIRED", "message": f"{scene_id or 'scene'} requires a name."})
        beats = scene.get("beats")
        if not isinstance(beats, list) or not beats:
            warnings.append({"code": "SCENE_BEATS_EMPTY", "message": f"{scene_id or name} has no beats."})
    return {"status": "qualified" if not errors else "needs_review", "errors": errors, "warnings": warnings}


def resolve_script_payload(session: Any, script_row: Any, *, workflow_profile: str = "creative_draft") -> dict[str, Any]:
    """Resolve the machine source for downstream director stages.

    Production is fail-closed: it may only consume a qualified ScriptIR.  The
    creative-draft compatibility path may still read the legacy Script.content
    payload while migration is in progress.
    """
    from fastapi import HTTPException

    profile = str(workflow_profile or "creative_draft").strip().lower()
    if profile == "production":
        from models import ScriptIRVersion

        version = None
        current_id = getattr(script_row, "current_script_ir_version_id", None)
        if current_id:
            version = session.query(ScriptIRVersion).filter_by(id=current_id, book_id=script_row.book_id, episode=script_row.episode, status="qualified").first()
        if version is None:
            version = session.query(ScriptIRVersion).filter_by(book_id=script_row.book_id, episode=script_row.episode, status="qualified").order_by(ScriptIRVersion.revision.desc(), ScriptIRVersion.id.desc()).first()
        if version is None:
            raise HTTPException(status_code=409, detail="Production workflow requires a qualified ScriptIR version.")
        try:
            payload = json.loads(version.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Qualified ScriptIR payload is invalid.") from exc
        return payload if isinstance(payload, dict) else {"scenes": []}
    try:
        parsed = json.loads(script_row.content or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"raw_content": str(script_row.content or "")}
    return parsed if isinstance(parsed, dict) else {"raw_content": str(script_row.content or "")}
