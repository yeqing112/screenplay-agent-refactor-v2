"""Schema-first scene directing strategy for Director Quality V2.1.

The strategy is a scene-level creative brief.  It references approved beats
and characters but cannot rewrite them.  This module performs deterministic
normalization/validation only; provider calls belong to the planner boundary
and are intentionally absent here.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


SCENE_DIRECTING_STRATEGY_SCHEMA_VERSION = "scene_directing_strategy_v1"
SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION = "scene_directing_strategy_v2"
STRATEGY_KEYS = {
    "schema_version",
    "scene_objective",
    "visual_strategy",
    "emotional_curve",
    "information_strategy",
    "power_curve",
    "rhythm_strategy",
    "camera_language",
    "forbidden_tendencies",
    "strategy_fingerprint",
}
INFORMATION_KEYS = {"reveal_order", "withhold_until", "audience_focus"}
CAMERA_KEYS = {"base_style", "movement_rule", "closeup_rule", "reaction_rule"}
STRATEGY_V2_KEYS = STRATEGY_KEYS | {
    "performance_arc",
    "rhythm_curve",
    "emotion_curve",
    "information_plan",
}
PERFORMANCE_ARC_KEYS = {"beat_id", "character_id", "objective", "internal_shift", "visible_behavior", "subtext"}
RHYTHM_CURVE_KEYS = {"beat_id", "pace", "cut_strategy", "target_duration_range", "hold_reason"}
EMOTION_CURVE_KEYS = {"beat_id", "character_id", "state", "intensity"}
INFORMATION_PLAN_KEYS = {"beat_id", "audience_should_know", "audience_should_not_know_yet", "reveal_trigger", "reaction_priority"}


class SceneDirectingStrategyError(ValueError):
    code = "DIRECTOR_STRATEGY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def strategy_fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _beat_map(contract: dict[str, Any]) -> dict[str, Any]:
    value = _dict(contract).get("source_beat_map")
    return value if isinstance(value, dict) else {}


def _known_characters(contract: dict[str, Any]) -> set[str]:
    facts = _dict(_dict(contract).get("immutable_projection")).get("facts")
    values = _list(_dict(facts).get("participants"))
    result: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("character_id") or value.get("id") or value.get("name")
        if _text(value):
            result.add(_text(value))
    return result


def _require_text(value: Any, *, path: str) -> str:
    text = _text(value)
    if not text:
        raise SceneDirectingStrategyError("value must be a non-empty string", path=path)
    return text


def _validate_curve(raw: Any, *, path: str, beat_map: dict[str, Any], power: bool = False, known_characters: set[str] | None = None) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise SceneDirectingStrategyError("curve must be a list", path=path)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            raise SceneDirectingStrategyError("curve item must be an object", path=item_path)
        allowed = {"beat_id", "intensity"} if not power else {"beat_id", "dominant_character"}
        forbidden = sorted(set(item) - allowed)
        if forbidden:
            raise SceneDirectingStrategyError(f"curve item contains forbidden fields: {', '.join(forbidden)}", path=item_path)
        beat_id = _require_text(item.get("beat_id"), path=f"{item_path}.beat_id")
        if beat_id not in beat_map:
            raise SceneDirectingStrategyError("curve references an unknown source beat", code="DIRECTOR_STRATEGY_UNBOUND_BEAT", path=f"{item_path}.beat_id")
        if beat_id in seen:
            raise SceneDirectingStrategyError("each beat may appear once in a curve", path=f"{item_path}.beat_id")
        seen.add(beat_id)
        if power:
            character = _require_text(item.get("dominant_character"), path=f"{item_path}.dominant_character")
            if known_characters and character not in known_characters:
                raise SceneDirectingStrategyError("dominant_character is not present in approved evidence", code="INVALID_CHARACTER_REFERENCE", path=f"{item_path}.dominant_character")
            result.append({"beat_id": beat_id, "dominant_character": character})
        else:
            intensity = item.get("intensity")
            if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or not 0 <= float(intensity) <= 10:
                raise SceneDirectingStrategyError("intensity must be between 0 and 10", path=f"{item_path}.intensity")
            result.append({"beat_id": beat_id, "intensity": float(intensity) if isinstance(intensity, float) else int(intensity)})
    return result


def parse_scene_directing_strategy(raw: Any, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strictly parse a strategy and verify all references are authoritative."""

    if not isinstance(raw, dict):
        raise SceneDirectingStrategyError("scene directing strategy must be an object")
    if _text(raw.get("schema_version")) == SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION:
        return parse_scene_directing_strategy_v2(raw, contract)
    forbidden = sorted(set(raw) - STRATEGY_KEYS)
    if forbidden:
        raise SceneDirectingStrategyError(f"strategy contains forbidden fields: {', '.join(forbidden)}", code="DIRECTOR_STRATEGY_FIELD_FORBIDDEN")
    if _text(raw.get("schema_version")) != SCENE_DIRECTING_STRATEGY_SCHEMA_VERSION:
        raise SceneDirectingStrategyError(
            f"schema_version must be {SCENE_DIRECTING_STRATEGY_SCHEMA_VERSION}",
            code="DIRECTOR_STRATEGY_SCHEMA_VERSION_INVALID",
            path="schema_version",
        )
    contract_obj = _dict(contract)
    beats = _beat_map(contract_obj)
    if not beats:
        raise SceneDirectingStrategyError("strategy requires a non-empty source beat map", code="DIRECTOR_STRATEGY_MISSING_EVIDENCE", path="source_beat_map")
    emotional = _validate_curve(raw.get("emotional_curve"), path="emotional_curve", beat_map=beats)
    power = _validate_curve(raw.get("power_curve"), path="power_curve", beat_map=beats, power=True, known_characters=_known_characters(contract_obj))
    information = raw.get("information_strategy")
    if not isinstance(information, dict):
        raise SceneDirectingStrategyError("information_strategy must be an object", path="information_strategy")
    info_forbidden = sorted(set(information) - INFORMATION_KEYS)
    if info_forbidden:
        raise SceneDirectingStrategyError(f"information_strategy contains forbidden fields: {', '.join(info_forbidden)}", code="DIRECTOR_STRATEGY_FIELD_FORBIDDEN", path="information_strategy")
    normalized_info: dict[str, list[str]] = {}
    for key in INFORMATION_KEYS:
        value = information.get(key, [])
        if not isinstance(value, list) or any(not _text(item) for item in value):
            raise SceneDirectingStrategyError(f"{key} must be a list of non-empty strings", path=f"information_strategy.{key}")
        normalized_info[key] = [_text(item) for item in value]
    camera = raw.get("camera_language")
    if not isinstance(camera, dict):
        raise SceneDirectingStrategyError("camera_language must be an object", path="camera_language")
    camera_forbidden = sorted(set(camera) - CAMERA_KEYS)
    if camera_forbidden:
        raise SceneDirectingStrategyError(f"camera_language contains forbidden fields: {', '.join(camera_forbidden)}", code="DIRECTOR_STRATEGY_FIELD_FORBIDDEN", path="camera_language")
    normalized_camera = {key: _require_text(camera.get(key), path=f"camera_language.{key}") for key in CAMERA_KEYS}
    tendencies = raw.get("forbidden_tendencies")
    if not isinstance(tendencies, list) or any(not _text(item) for item in tendencies):
        raise SceneDirectingStrategyError("forbidden_tendencies must be a list of non-empty strings", path="forbidden_tendencies")
    normalized = {
        "schema_version": SCENE_DIRECTING_STRATEGY_SCHEMA_VERSION,
        "scene_objective": _require_text(raw.get("scene_objective"), path="scene_objective"),
        "visual_strategy": _require_text(raw.get("visual_strategy"), path="visual_strategy"),
        "emotional_curve": emotional,
        "information_strategy": normalized_info,
        "power_curve": power,
        "rhythm_strategy": _require_text(raw.get("rhythm_strategy"), path="rhythm_strategy"),
        "camera_language": normalized_camera,
        "forbidden_tendencies": [_text(item) for item in tendencies],
    }
    expected_fingerprint = strategy_fingerprint(normalized)
    supplied_fingerprint = _text(raw.get("strategy_fingerprint"))
    if supplied_fingerprint and supplied_fingerprint != expected_fingerprint:
        raise SceneDirectingStrategyError(
            "strategy_fingerprint does not match the normalized strategy",
            code="DIRECTOR_STRATEGY_FINGERPRINT_MISMATCH",
            path="strategy_fingerprint",
        )
    normalized["strategy_fingerprint"] = expected_fingerprint
    return normalized


def build_scene_directing_strategy(
    *,
    treatment: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    structural_shot_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a conservative deterministic strategy from approved evidence."""

    treatment_obj = _dict(treatment)
    contract_obj = _dict(contract)
    beats = _beat_map(contract_obj)
    if not beats:
        # Keep the function fail-closed rather than inventing beats.  Callers
        # should build the immutable contract before requesting a strategy.
        raise SceneDirectingStrategyError("cannot build strategy without source beats", code="DIRECTOR_STRATEGY_MISSING_EVIDENCE")
    beat_ids = list(beats)
    participants = sorted(_known_characters(contract_obj))
    default_character = participants[0] if participants else "主体角色"
    visual = _text(treatment_obj.get("visual_strategy")) or "优先呈现已批准的空间关系、动作节拍和关键反应。"
    objective = _text(treatment_obj.get("scene_objective")) or _text(treatment_obj.get("dramatic_function")) or "让观众清楚理解本场节拍变化。"
    strategy = {
        "schema_version": SCENE_DIRECTING_STRATEGY_SCHEMA_VERSION,
        "scene_objective": objective,
        "visual_strategy": visual,
        "emotional_curve": [{"beat_id": beat_id, "intensity": 5} for beat_id in beat_ids],
        "information_strategy": {
            "reveal_order": beat_ids,
            "withhold_until": [],
            "audience_focus": [],
        },
        "power_curve": [{"beat_id": beat_id, "dominant_character": default_character} for beat_id in beat_ids],
        "rhythm_strategy": _text(treatment_obj.get("rhythm_strategy")) or "按节拍变化剪辑，避免无动机的加速与停留。",
        "camera_language": {
            "base_style": "自然透视、空间关系优先",
            "movement_rule": "只有在动作或信息变化需要时移动镜头",
            "closeup_rule": "特写服务于已批准的反应或关键道具信息",
            "reaction_rule": "先完成可观察反应，再切换视线或景别",
        },
        "forbidden_tendencies": ["gratuitous_camera_movement", "random_shot_scale_changes"],
    }
    return parse_scene_directing_strategy(strategy, contract_obj)


def _v2_beat_entries(contract: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(str(key), value if isinstance(value, dict) else {}) for key, value in _beat_map(contract).items()]


def _v2_intensity(index: int, beat: dict[str, Any]) -> int:
    """Derive a bounded creative curve from declared beat semantics only."""

    value = min(8, max(2, 3 + index))
    beat_type = _text(beat.get("type")).lower()
    if beat_type in {"reveal", "decision", "power_shift", "turn"}:
        value = min(10, value + 2)
    return value


def _v2_pace(beat: dict[str, Any]) -> str:
    beat_type = _text(beat.get("type")).lower()
    if beat_type in {"action", "obstacle", "chase"}:
        return "accelerate"
    if beat_type in {"reveal", "decision", "power_shift", "reaction"}:
        return "hold"
    return "normal"


def _validate_v2_items(raw: Any, *, path: str, allowed: set[str], beat_map: dict[str, Any], known_characters: set[str], required_fields: tuple[str, ...], unique_key: tuple[str, ...] = ("beat_id",)) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise SceneDirectingStrategyError("value must be a list", path=path)
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for index, item in enumerate(raw):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            raise SceneDirectingStrategyError("item must be an object", path=item_path)
        forbidden = sorted(set(item) - allowed)
        if forbidden:
            raise SceneDirectingStrategyError(f"item contains forbidden fields: {', '.join(forbidden)}", code="DIRECTOR_STRATEGY_FIELD_FORBIDDEN", path=item_path)
        for field in required_fields:
            _require_text(item.get(field), path=f"{item_path}.{field}")
        beat_id = _require_text(item.get("beat_id"), path=f"{item_path}.beat_id")
        if beat_id not in beat_map:
            raise SceneDirectingStrategyError("item references an unknown source beat", code="DIRECTOR_STRATEGY_UNBOUND_BEAT", path=f"{item_path}.beat_id")
        character = _text(item.get("character_id"))
        if character and known_characters and character not in known_characters:
            raise SceneDirectingStrategyError("character_id is not present in approved evidence", code="INVALID_CHARACTER_REFERENCE", path=f"{item_path}.character_id")
        key = tuple(_text(item.get(field)) for field in unique_key)
        if key in seen:
            raise SceneDirectingStrategyError("duplicate beat/character strategy entry", path=item_path)
        seen.add(key)
        result.append(copy.deepcopy(item))
    return result


def parse_scene_directing_strategy_v2(raw: Any, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse the beat-bound Strategy V2 without widening fact authority."""

    if not isinstance(raw, dict):
        raise SceneDirectingStrategyError("scene directing strategy must be an object")
    forbidden = sorted(set(raw) - STRATEGY_V2_KEYS)
    if forbidden:
        raise SceneDirectingStrategyError(f"strategy contains forbidden fields: {', '.join(forbidden)}", code="DIRECTOR_STRATEGY_FIELD_FORBIDDEN")
    if _text(raw.get("schema_version")) != SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION:
        raise SceneDirectingStrategyError(f"schema_version must be {SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION}", code="DIRECTOR_STRATEGY_SCHEMA_VERSION_INVALID", path="schema_version")
    contract_obj = _dict(contract)
    beats = _beat_map(contract_obj)
    if not beats:
        raise SceneDirectingStrategyError("strategy requires a non-empty source beat map", code="DIRECTOR_STRATEGY_MISSING_EVIDENCE", path="source_beat_map")
    known_characters = _known_characters(contract_obj)
    performance = _validate_v2_items(raw.get("performance_arc"), path="performance_arc", allowed=PERFORMANCE_ARC_KEYS, beat_map=beats, known_characters=known_characters, required_fields=("character_id", "objective", "internal_shift", "visible_behavior"), unique_key=("beat_id", "character_id"))
    rhythm = _validate_v2_items(raw.get("rhythm_curve"), path="rhythm_curve", allowed=RHYTHM_CURVE_KEYS, beat_map=beats, known_characters=known_characters, required_fields=("pace", "cut_strategy", "hold_reason"))
    for index, item in enumerate(rhythm):
        if item.get("pace") not in {"hold", "normal", "accelerate"}:
            raise SceneDirectingStrategyError("pace must be hold, normal, or accelerate", path=f"rhythm_curve[{index}].pace")
        duration = item.get("target_duration_range")
        if not isinstance(duration, list) or len(duration) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0 for value in duration) or float(duration[0]) > float(duration[1]):
            raise SceneDirectingStrategyError("target_duration_range must be an ascending positive pair", path=f"rhythm_curve[{index}].target_duration_range")
        item["target_duration_range"] = [float(duration[0]), float(duration[1])]
    emotion = _validate_v2_items(raw.get("emotion_curve"), path="emotion_curve", allowed=EMOTION_CURVE_KEYS, beat_map=beats, known_characters=known_characters, required_fields=("character_id", "state", "intensity"), unique_key=("beat_id", "character_id"))
    for index, item in enumerate(emotion):
        intensity = item.get("intensity")
        if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or not 0 <= float(intensity) <= 10:
            raise SceneDirectingStrategyError("intensity must be between 0 and 10", path=f"emotion_curve[{index}].intensity")
        item["intensity"] = float(intensity) if isinstance(intensity, float) else int(intensity)
    information = _validate_v2_items(raw.get("information_plan"), path="information_plan", allowed=INFORMATION_PLAN_KEYS, beat_map=beats, known_characters=known_characters, required_fields=("reveal_trigger", "reaction_priority"))
    for index, item in enumerate(information):
        for key in ("audience_should_know", "audience_should_not_know_yet"):
            values = item.get(key, [])
            if not isinstance(values, list) or any(not _text(value) for value in values):
                raise SceneDirectingStrategyError(f"{key} must be a list of non-empty strings", path=f"information_plan[{index}].{key}")
            item[key] = [_text(value) for value in values]
    camera = raw.get("camera_language")
    if not isinstance(camera, dict):
        raise SceneDirectingStrategyError("camera_language must be an object", path="camera_language")
    camera_forbidden = sorted(set(camera) - CAMERA_KEYS)
    if camera_forbidden:
        raise SceneDirectingStrategyError(f"camera_language contains forbidden fields: {', '.join(camera_forbidden)}", code="DIRECTOR_STRATEGY_FIELD_FORBIDDEN", path="camera_language")
    normalized_camera = {key: _require_text(camera.get(key), path=f"camera_language.{key}") for key in CAMERA_KEYS}
    tendencies = raw.get("forbidden_tendencies")
    if not isinstance(tendencies, list) or any(not _text(item) for item in tendencies):
        raise SceneDirectingStrategyError("forbidden_tendencies must be a list of non-empty strings", path="forbidden_tendencies")
    normalized = {
        "schema_version": SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION,
        "scene_objective": _require_text(raw.get("scene_objective"), path="scene_objective"),
        "visual_strategy": _require_text(raw.get("visual_strategy"), path="visual_strategy"),
        "performance_arc": performance,
        "rhythm_curve": rhythm,
        "emotion_curve": emotion,
        "information_plan": information,
        "camera_language": normalized_camera,
        "forbidden_tendencies": [_text(item) for item in tendencies],
    }
    # Keep the old scene-level fields optional and lossless for readers that
    # still render V2.1 strategy summaries.  They are not used as V2 signal
    # evidence when the beat-bound arrays are present.
    for key in ("emotional_curve", "information_strategy", "power_curve", "rhythm_strategy"):
        if key in raw:
            normalized[key] = copy.deepcopy(raw[key])
    expected_fingerprint = strategy_fingerprint(normalized)
    supplied = _text(raw.get("strategy_fingerprint"))
    if supplied and supplied != expected_fingerprint:
        raise SceneDirectingStrategyError("strategy_fingerprint does not match the normalized strategy", code="DIRECTOR_STRATEGY_FINGERPRINT_MISMATCH", path="strategy_fingerprint")
    normalized["strategy_fingerprint"] = expected_fingerprint
    return normalized


def build_scene_directing_strategy_v2(
    *,
    treatment: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    structural_shot_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a beat-bound Strategy V2 from approved evidence only."""

    treatment_obj = _dict(treatment)
    contract_obj = _dict(contract)
    entries = _v2_beat_entries(contract_obj)
    if not entries:
        raise SceneDirectingStrategyError("cannot build strategy without source beats", code="DIRECTOR_STRATEGY_MISSING_EVIDENCE")
    participants = sorted(_known_characters(contract_obj))
    if not participants:
        raise SceneDirectingStrategyError("Strategy V2 requires an approved character reference", code="DIRECTOR_STRATEGY_MISSING_EVIDENCE", path="participants")
    performance: list[dict[str, Any]] = []
    rhythm: list[dict[str, Any]] = []
    emotion: list[dict[str, Any]] = []
    information: list[dict[str, Any]] = []
    for index, (beat_id, beat) in enumerate(entries):
        character = participants[index % len(participants)]
        event = _text(beat.get("event"))
        info_change = _text(beat.get("information_change"))
        emotion_change = _text(beat.get("emotion_change"))
        performance.append({"beat_id": beat_id, "character_id": character, "objective": "推进已批准节拍", "internal_shift": emotion_change or "回应当前节拍并保持可见状态变化", "visible_behavior": "通过可观察的目光、姿态或动作呈现节拍", "subtext": ""})
        pace = _v2_pace(beat)
        target = [2.5, 4.0] if pace == "accelerate" else ([3.5, 5.5] if pace == "hold" else [3.0, 4.5])
        rhythm.append({"beat_id": beat_id, "pace": pace, "cut_strategy": "动作完成后切" if pace == "accelerate" else ("反应完成后切" if pace == "hold" else "节拍变化时切"), "target_duration_range": target, "hold_reason": "保留观众读取当前节拍所需的最小停留"})
        emotion.append({"beat_id": beat_id, "character_id": character, "state": emotion_change or ("信息压力上升" if _text(beat.get("type")).lower() in {"reveal", "decision", "power_shift"} else "保持并呈现当前状态"), "intensity": _v2_intensity(index, beat)})
        information.append({"beat_id": beat_id, "audience_should_know": [event] if event else [], "audience_should_not_know_yet": [info_change] if info_change else [], "reveal_trigger": info_change or event or "节拍完成", "reaction_priority": "人物可见反应"})
    strategy = {
        "schema_version": SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION,
        "scene_objective": _text(treatment_obj.get("scene_objective")) or _text(treatment_obj.get("dramatic_function")) or "让观众清楚理解本场节拍变化。",
        "visual_strategy": _text(treatment_obj.get("visual_strategy")) or "优先呈现已批准的空间关系、动作节拍和关键反应。",
        "performance_arc": performance,
        "rhythm_curve": rhythm,
        "emotion_curve": emotion,
        "information_plan": information,
        "camera_language": {"base_style": "自然透视、空间关系优先", "movement_rule": "只有在动作或信息变化需要时移动镜头", "closeup_rule": "特写服务于已批准的反应或关键道具信息", "reaction_rule": "先完成可观察反应，再切换视线或景别"},
        "forbidden_tendencies": ["gratuitous_camera_movement", "random_shot_scale_changes"],
    }
    return parse_scene_directing_strategy_v2(strategy, contract_obj)


def validate_scene_directing_strategy(raw: Any, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        normalized = parse_scene_directing_strategy(raw, contract)
    except SceneDirectingStrategyError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "strategy": None}
    return {"status": "valid", "errors": [], "strategy": normalized, "strategy_fingerprint": normalized["strategy_fingerprint"]}


# Friendly aliases for integration callers.
normalize_scene_directing_strategy = parse_scene_directing_strategy
validate_directing_strategy = validate_scene_directing_strategy


__all__ = [
    "SCENE_DIRECTING_STRATEGY_SCHEMA_VERSION",
    "SCENE_DIRECTING_STRATEGY_V2_SCHEMA_VERSION",
    "STRATEGY_KEYS",
    "STRATEGY_V2_KEYS",
    "SceneDirectingStrategyError",
    "strategy_fingerprint",
    "parse_scene_directing_strategy",
    "normalize_scene_directing_strategy",
    "build_scene_directing_strategy",
    "parse_scene_directing_strategy_v2",
    "build_scene_directing_strategy_v2",
    "validate_scene_directing_strategy",
    "validate_directing_strategy",
]
