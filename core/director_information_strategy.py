"""Structured Information Strategy V2 and reveal-order diagnostics."""

from __future__ import annotations

import copy
from typing import Any, Iterable


INFORMATION_STRATEGY_SCHEMA_VERSION = "director_information_strategy_v2"
INFORMATION_ISSUES = (
    "INFORMATION_STRATEGY_MISSING",
    "EARLY_REVEAL",
    "LATE_REVEAL",
    "REVEAL_WITHOUT_SETUP",
    "MISSING_REACTION_TO_REVEAL",
    "AUDIENCE_FOCUS_CONFLICT",
    "REDUNDANT_INFORMATION_REPEAT",
)


class InformationStrategyError(ValueError):
    code = "INFORMATION_STRATEGY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any, *, path: str) -> list[str]:
    if not isinstance(value, list) or any(not _text(item) for item in value):
        raise InformationStrategyError("value must be a list of non-empty strings", path=path)
    return [_text(item) for item in value]


def normalize_information_strategy(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InformationStrategyError("information strategy must be an object", code="INFORMATION_STRATEGY_MISSING")
    unknown = sorted(set(raw) - {"schema_version", "known_to_audience", "withheld_from_audience", "reveal_plan", "reaction_priority", "audience_focus"})
    if unknown:
        raise InformationStrategyError(f"information strategy contains forbidden fields: {', '.join(unknown)}", code="INFORMATION_STRATEGY_FIELD_FORBIDDEN")
    version = _text(raw.get("schema_version"))
    if version and version != INFORMATION_STRATEGY_SCHEMA_VERSION:
        raise InformationStrategyError(f"schema_version must be {INFORMATION_STRATEGY_SCHEMA_VERSION}", path="schema_version")
    reveal_plan_raw = raw.get("reveal_plan")
    if not isinstance(reveal_plan_raw, list):
        raise InformationStrategyError("reveal_plan must be a list", path="reveal_plan")
    reveal_plan: list[dict[str, Any]] = []
    seen_beats: set[str] = set()
    for index, item in enumerate(reveal_plan_raw):
        if not isinstance(item, dict):
            raise InformationStrategyError("reveal plan item must be an object", path=f"reveal_plan[{index}]")
        unknown_item = sorted(set(item) - {"beat_id", "reveals", "withholds", "audience_should_notice", "audience_should_not_yet_know"})
        if unknown_item:
            raise InformationStrategyError(f"reveal plan item contains forbidden fields: {', '.join(unknown_item)}", path=f"reveal_plan[{index}]")
        beat_id = _text(item.get("beat_id"))
        if not beat_id or beat_id in seen_beats:
            raise InformationStrategyError("reveal_plan beat_id must be unique and non-empty", path=f"reveal_plan[{index}].beat_id")
        seen_beats.add(beat_id)
        reveals = _strings(item.get("reveals", []), path=f"reveal_plan[{index}].reveals")
        withholds = _strings(item.get("withholds", []), path=f"reveal_plan[{index}].withholds")
        notice = _text(item.get("audience_should_notice"))
        not_yet = _text(item.get("audience_should_not_yet_know"))
        if not (reveals or withholds or notice or not_yet):
            raise InformationStrategyError("reveal plan item needs an information intention", path=f"reveal_plan[{index}]")
        reveal_plan.append({"beat_id": beat_id, "reveals": reveals, "withholds": withholds, "audience_should_notice": notice, "audience_should_not_yet_know": not_yet})
    focus = raw.get("audience_focus", [])
    if isinstance(focus, str):
        focus = [focus] if _text(focus) else []
    normalized = {
        "schema_version": INFORMATION_STRATEGY_SCHEMA_VERSION,
        "known_to_audience": _strings(raw.get("known_to_audience", []), path="known_to_audience"),
        "withheld_from_audience": _strings(raw.get("withheld_from_audience", []), path="withheld_from_audience"),
        "reveal_plan": reveal_plan,
        "reaction_priority": _strings(raw.get("reaction_priority", []), path="reaction_priority"),
        "audience_focus": _strings(focus, path="audience_focus"),
    }
    return normalized


def validate_information_strategy(raw: Any) -> dict[str, Any]:
    try:
        value = normalize_information_strategy(raw)
    except InformationStrategyError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "information_strategy": None}
    return {"status": "valid", "errors": [], "information_strategy": value}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _issue(code: str, message: str, *, beat_id: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"code": code, "issue_code": code, "severity": "warning", "blocking": False, "message": message}
    if beat_id:
        value["beat_id"] = beat_id
    if details:
        value["details"] = copy.deepcopy(details)
    return value


def evaluate_information_strategy(
    strategy: Any, *, shots: Iterable[dict[str, Any]] = (), beat_map: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    try:
        normalized = normalize_information_strategy(strategy)
    except InformationStrategyError as exc:
        return {"schema_version": INFORMATION_STRATEGY_SCHEMA_VERSION, "issues": [_issue(exc.code, str(exc))], "coverage": None, "blocking": False}
    beat_ids = [_text(item.get("beat_id")) for item in beat_map if isinstance(item, dict) and _text(item.get("beat_id"))]
    beat_order = {beat_id: index for index, beat_id in enumerate(beat_ids)}
    by_beat = {_text(item.get("beat_id")): item for item in shots if isinstance(item, dict) and _text(item.get("beat_id"))}
    issues: list[dict[str, Any]] = []
    withheld = set(normalized["withheld_from_audience"])
    reveal_entries = normalized["reveal_plan"]
    reveal_positions: dict[str, int] = {}
    for index, entry in enumerate(reveal_entries):
        beat_id = entry["beat_id"]
        if beat_ids and beat_id not in beat_order:
            issues.append(_issue("REVEAL_WITHOUT_SETUP", "reveal_plan 引用了未知 beat", beat_id=beat_id))
        for fact in entry["reveals"]:
            if fact in reveal_positions:
                issues.append(_issue("REDUNDANT_INFORMATION_REPEAT", "同一信息在 reveal_plan 中重复揭示", beat_id=beat_id, details={"fact": fact, "first_index": reveal_positions[fact]}))
            reveal_positions.setdefault(fact, beat_order.get(beat_id, index))
            if fact not in withheld and fact not in normalized["known_to_audience"]:
                issues.append(_issue("REVEAL_WITHOUT_SETUP", "信息没有已知或隐藏声明作为铺垫", beat_id=beat_id, details={"fact": fact}))
    covered = 0
    for entry in reveal_entries:
        beat_id = entry["beat_id"]
        shot = by_beat.get(beat_id, {})
        info = _dict(shot.get("information_strategy"))
        observed = {_text(item) for item in info.get("reveals", []) if _text(item)}
        expected = set(entry["reveals"])
        if expected:
            if expected & observed:
                covered += 1
            elif shot:
                issues.append(_issue("LATE_REVEAL", "计划揭示的 beat 没有在对应镜头呈现", beat_id=beat_id, details={"expected": sorted(expected)}))
            performance = shot.get("performance_direction")
            if expected & observed and (not isinstance(performance, list) or not any(isinstance(item, dict) and _text(item.get("visible_behavior")) for item in performance)):
                issues.append(_issue("MISSING_REACTION_TO_REVEAL", "信息揭示后没有可观察反应支撑", beat_id=beat_id))
        early_facts = observed & withheld
        if early_facts and beat_id != reveal_entries[-1]["beat_id"]:
            issues.append(_issue("EARLY_REVEAL", "镜头提前揭示了仍处于 withheld 集合的信息", beat_id=beat_id, details={"facts": sorted(early_facts)}))
    return {
        "schema_version": INFORMATION_STRATEGY_SCHEMA_VERSION,
        "issues": issues,
        "coverage": round(covered / len([item for item in reveal_entries if item["reveals"]]), 4) if any(item["reveals"] for item in reveal_entries) else None,
        "reveal_plan_count": len(reveal_entries),
        "blocking": False,
    }


__all__ = ["INFORMATION_STRATEGY_SCHEMA_VERSION", "INFORMATION_ISSUES", "InformationStrategyError", "normalize_information_strategy", "validate_information_strategy", "evaluate_information_strategy"]
