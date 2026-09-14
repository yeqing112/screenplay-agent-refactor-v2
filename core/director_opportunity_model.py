"""Evidence-backed creative opportunity and outcome contracts.

Phase B separates *whether a scene contains a directing opportunity* from
whether a planner elects to act on it.  This module is deliberately provider-
free: it only normalizes and validates the small records exchanged by the
detector, planner, evaluator, and tail-repair stages.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


OPPORTUNITY_SCHEMA_VERSION = "director_creative_opportunity_v1"
OPPORTUNITY_OUTCOME_SCHEMA_VERSION = "director_creative_opportunity_outcome_v1"

OPPORTUNITY_TYPES = (
    "OPP_EMOTION_TURN",
    "OPP_REACTION",
    "OPP_INFORMATION_WITHHOLD",
    "OPP_INFORMATION_REVEAL",
    "OPP_POWER_SHIFT",
    "OPP_RHYTHM_CHANGE",
    "OPP_PROP_EMPHASIS",
    "OPP_SPATIAL_ISOLATION",
    "OPP_CHARACTER_ENTRANCE",
    "OPP_CHARACTER_EXIT",
    "OPP_VISUAL_REVEAL",
    "OPP_SILENCE_HOLD",
    "OPP_DIALOGUE_PRESSURE",
    "OPP_ACTION_ACCELERATION",
    "OPP_SCENE_BUTTON",
)
OPPORTUNITY_PRIORITIES = ("low", "medium", "high")
PLANNER_DECISIONS = ("ACT", "SKIP_WITH_REASON", "NOT_APPLICABLE")
OUTCOME_STATUSES = (
    "USEFUL_ACCEPTED",
    "ACCEPTED_NO_MEASURABLE_VALUE",
    "REJECTED_CONTRACT",
    "REJECTED_QUALITY",
    "SKIPPED_VALID_REASON",
    "MISSED_OPPORTUNITY",
    "FALLBACK_BASELINE",
)
DIRECTING_DIMENSIONS = (
    "performance_direction",
    "edit_strategy",
    "emotion_arc",
    "information_strategy",
    "shot_motivation",
    "camera_language",
    "spatial_clarity",
    "visual_storytelling",
    "power_dynamics",
    "shot_diversity",
)

_OPPORTUNITY_KEYS = {
    "schema_version",
    "opportunity_id",
    "type",
    "scene_id",
    "beat_id",
    "subjects",
    "reason",
    "evidence_refs",
    "priority",
    "eligible",
    "recommended_directing_dimensions",
}
_OUTCOME_KEYS = {
    "schema_version",
    "opportunity_id",
    "eligible",
    "planner_decision",
    "decision_reason",
    "accepted",
    "repaired",
    "fallback",
    "quality_delta",
    "dimension_deltas",
    "final_status",
    "evidence_fingerprint",
}


class OpportunityModelError(ValueError):
    """Raised when an opportunity or outcome violates its contract."""

    code = "DIRECTOR_OPPORTUNITY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def opportunity_fingerprint(value: Any) -> str:
    """Return a stable digest of a normalized opportunity or outcome."""

    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _string_list(value: Any, *, path: str, required: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise OpportunityModelError("value must be a list", path=path)
    result = [_text(item) for item in value]
    if any(not item for item in result):
        raise OpportunityModelError("list items must be non-empty strings", path=path)
    if required and not result:
        raise OpportunityModelError("list must not be empty", path=path)
    return result


def _evidence_refs(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise OpportunityModelError("evidence_refs must be a non-empty list", code="OPPORTUNITY_EVIDENCE_REQUIRED", path="evidence_refs")
    result: list[Any] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            if not _text(item):
                raise OpportunityModelError("evidence reference must not be empty", path=f"evidence_refs[{index}]")
            result.append(_text(item))
            continue
        if isinstance(item, dict):
            if not any(_text(item.get(key)) for key in ("source", "path", "ref", "quote")):
                raise OpportunityModelError("evidence object requires source/path/ref/quote", path=f"evidence_refs[{index}]")
            result.append(copy.deepcopy(item))
            continue
        raise OpportunityModelError("evidence reference must be a string or object", path=f"evidence_refs[{index}]")
    return result


def normalize_opportunity(raw: Any) -> dict[str, Any]:
    """Normalize one detector record without inventing evidence."""

    if not isinstance(raw, dict):
        raise OpportunityModelError("opportunity must be an object")
    unknown = sorted(set(raw) - _OPPORTUNITY_KEYS)
    if unknown:
        raise OpportunityModelError(f"opportunity contains forbidden fields: {', '.join(unknown)}", code="OPPORTUNITY_FIELD_FORBIDDEN")
    if _text(raw.get("schema_version")) not in {"", OPPORTUNITY_SCHEMA_VERSION}:
        raise OpportunityModelError(f"schema_version must be {OPPORTUNITY_SCHEMA_VERSION}", path="schema_version")
    opportunity_type = _text(raw.get("type"))
    if opportunity_type not in OPPORTUNITY_TYPES:
        raise OpportunityModelError("unknown opportunity type", path="type")
    priority = _text(raw.get("priority")).lower()
    if priority not in OPPORTUNITY_PRIORITIES:
        raise OpportunityModelError("priority must be low, medium, or high", path="priority")
    eligible = raw.get("eligible")
    if not isinstance(eligible, bool):
        raise OpportunityModelError("eligible must be boolean", path="eligible")
    dimensions = _string_list(raw.get("recommended_directing_dimensions"), path="recommended_directing_dimensions")
    invalid_dimensions = sorted(set(dimensions) - set(DIRECTING_DIMENSIONS))
    if invalid_dimensions:
        raise OpportunityModelError(f"unknown directing dimensions: {', '.join(invalid_dimensions)}", path="recommended_directing_dimensions")
    normalized = {
        "schema_version": OPPORTUNITY_SCHEMA_VERSION,
        "opportunity_id": _text(raw.get("opportunity_id")),
        "type": opportunity_type,
        "scene_id": _text(raw.get("scene_id")),
        "beat_id": _text(raw.get("beat_id")),
        "subjects": _string_list(raw.get("subjects"), path="subjects", required=False),
        "reason": _text(raw.get("reason")),
        "evidence_refs": _evidence_refs(raw.get("evidence_refs")),
        "priority": priority,
        "eligible": eligible,
        "recommended_directing_dimensions": dimensions,
    }
    for key in ("opportunity_id", "scene_id", "beat_id", "reason"):
        if not normalized[key]:
            raise OpportunityModelError("value must be a non-empty string", code="OPPORTUNITY_EVIDENCE_REQUIRED" if key in {"reason", "scene_id", "beat_id"} else None, path=key)
    return normalized


def validate_opportunity(raw: Any) -> dict[str, Any]:
    try:
        normalized = normalize_opportunity(raw)
    except OpportunityModelError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "opportunity": None}
    return {"status": "valid", "errors": [], "opportunity": normalized, "opportunity_fingerprint": opportunity_fingerprint(normalized)}


def build_opportunity_outcome(
    *,
    opportunity: dict[str, Any],
    planner_decision: str,
    decision_reason: str = "",
    accepted: bool = False,
    repaired: bool = False,
    fallback: bool = False,
    quality_delta: int | float = 0.0,
    dimension_deltas: dict[str, int | float] | None = None,
    final_status: str,
    evidence_fingerprint: str = "",
) -> dict[str, Any]:
    """Build an outcome while preserving the opportunity's eligibility fact."""

    normalized = normalize_opportunity(opportunity)
    outcome = {
        "schema_version": OPPORTUNITY_OUTCOME_SCHEMA_VERSION,
        "opportunity_id": normalized["opportunity_id"],
        "eligible": normalized["eligible"],
        "planner_decision": _text(planner_decision).upper(),
        "decision_reason": _text(decision_reason),
        "accepted": bool(accepted),
        "repaired": bool(repaired),
        "fallback": bool(fallback),
        "quality_delta": quality_delta,
        "dimension_deltas": copy.deepcopy(dimension_deltas or {}),
        "final_status": _text(final_status),
        "evidence_fingerprint": _text(evidence_fingerprint),
    }
    return normalize_opportunity_outcome(outcome)


def normalize_opportunity_outcome(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OpportunityModelError("outcome must be an object")
    unknown = sorted(set(raw) - _OUTCOME_KEYS)
    if unknown:
        raise OpportunityModelError(f"outcome contains forbidden fields: {', '.join(unknown)}", code="OPPORTUNITY_OUTCOME_FIELD_FORBIDDEN")
    if _text(raw.get("schema_version")) not in {"", OPPORTUNITY_OUTCOME_SCHEMA_VERSION}:
        raise OpportunityModelError(f"schema_version must be {OPPORTUNITY_OUTCOME_SCHEMA_VERSION}", path="schema_version")
    decision = _text(raw.get("planner_decision")).upper()
    if decision not in PLANNER_DECISIONS:
        raise OpportunityModelError("planner_decision must be ACT, SKIP_WITH_REASON, or NOT_APPLICABLE", path="planner_decision")
    eligible = raw.get("eligible")
    if not isinstance(eligible, bool):
        raise OpportunityModelError("eligible must be boolean", path="eligible")
    if eligible and decision == "NOT_APPLICABLE":
        raise OpportunityModelError("eligible opportunity cannot be NOT_APPLICABLE", path="planner_decision")
    if decision == "SKIP_WITH_REASON" and not _text(raw.get("decision_reason")):
        raise OpportunityModelError("SKIP_WITH_REASON requires decision_reason", code="OPPORTUNITY_SKIP_REASON_REQUIRED", path="decision_reason")
    status = _text(raw.get("final_status"))
    if status not in OUTCOME_STATUSES:
        raise OpportunityModelError("unknown final_status", path="final_status")
    quality_delta = raw.get("quality_delta")
    if isinstance(quality_delta, bool) or not isinstance(quality_delta, (int, float)):
        raise OpportunityModelError("quality_delta must be numeric", path="quality_delta")
    deltas = raw.get("dimension_deltas")
    if not isinstance(deltas, dict):
        raise OpportunityModelError("dimension_deltas must be an object", path="dimension_deltas")
    normalized_deltas: dict[str, float] = {}
    for key, value in deltas.items():
        if _text(key) not in DIRECTING_DIMENSIONS:
            raise OpportunityModelError("dimension_deltas contains unknown dimension", path=f"dimension_deltas.{key}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OpportunityModelError("dimension delta must be numeric", path=f"dimension_deltas.{key}")
        normalized_deltas[_text(key)] = float(value)
    normalized = {
        "schema_version": OPPORTUNITY_OUTCOME_SCHEMA_VERSION,
        "opportunity_id": _text(raw.get("opportunity_id")),
        "eligible": eligible,
        "planner_decision": decision,
        "decision_reason": _text(raw.get("decision_reason")),
        "accepted": bool(raw.get("accepted")),
        "repaired": bool(raw.get("repaired")),
        "fallback": bool(raw.get("fallback")),
        "quality_delta": float(quality_delta),
        "dimension_deltas": normalized_deltas,
        "final_status": status,
        "evidence_fingerprint": _text(raw.get("evidence_fingerprint")),
    }
    if not normalized["opportunity_id"]:
        raise OpportunityModelError("opportunity_id must be non-empty", path="opportunity_id")
    if normalized["accepted"] and decision != "ACT":
        raise OpportunityModelError("accepted outcome requires ACT", path="accepted")
    return normalized


def validate_opportunity_outcome(raw: Any) -> dict[str, Any]:
    try:
        normalized = normalize_opportunity_outcome(raw)
    except OpportunityModelError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "outcome": None}
    return {"status": "valid", "errors": [], "outcome": normalized, "outcome_fingerprint": opportunity_fingerprint(normalized)}


__all__ = [
    "OPPORTUNITY_SCHEMA_VERSION",
    "OPPORTUNITY_OUTCOME_SCHEMA_VERSION",
    "OPPORTUNITY_TYPES",
    "OPPORTUNITY_PRIORITIES",
    "PLANNER_DECISIONS",
    "OUTCOME_STATUSES",
    "DIRECTING_DIMENSIONS",
    "OpportunityModelError",
    "opportunity_fingerprint",
    "normalize_opportunity",
    "validate_opportunity",
    "build_opportunity_outcome",
    "normalize_opportunity_outcome",
    "validate_opportunity_outcome",
]
