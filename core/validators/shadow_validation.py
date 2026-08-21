"""Shadow validation hooks for production paths.

These helpers record validator findings without blocking, repairing, or mutating
the generated artifact. They are intended for measuring real-world violation
rates before stricter enforcement is enabled.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from core.validators.storyboard_validator import StoryboardValidator
from core.validators.violation_logger import log_violation_to_session

logger = logging.getLogger(__name__)


def shadow_validate_storyboard_shots(
    book_id: int,
    episode: int,
    shots: list[dict[str, Any]],
    session,
    agent_type: str = "storyboard",
) -> int:
    """Validate storyboard shots in shadow mode and log violations.

    Returns the number of log rows queued in the provided session.
    """
    if not shots:
        return 0

    try:
        validator = StoryboardValidator()
        logged = 0
        for scene_name, scene_shots in _group_shots_by_scene(shots).items():
            result = validator.validate_scene(scene_shots)
            for violation in result.violations:
                shot = _shot_for_violation(scene_shots, violation.location)
                log_violation_to_session(
                    session,
                    agent_type=agent_type,
                    book_id=book_id,
                    violation=violation,
                    episode=episode,
                    scene_name=scene_name,
                    shot_id=_coerce_int(shot.get("shot_id")) if shot else None,
                    repair_result="shadow_logged",
                    fix_details={
                        "mode": "shadow",
                        "location": violation.location,
                        "passed": result.passed,
                    },
                )
                logged += 1
        return logged
    except Exception as exc:
        logger.warning("Storyboard shadow validation skipped: %s", exc)
        return 0


def _group_shots_by_scene(shots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shot in shots:
        scene_name = str(shot.get("scene_name") or "unknown").strip() or "unknown"
        grouped[scene_name].append(_normalize_shot_for_validation(shot))
    return dict(grouped)


def _normalize_shot_for_validation(shot: dict[str, Any]) -> dict[str, Any]:
    metadata = shot.get("metadata") if isinstance(shot.get("metadata"), dict) else {}
    structured = metadata.get("structured_shot") if isinstance(metadata.get("structured_shot"), dict) else {}
    normalized = dict(shot)
    for field in (
        "shot_purpose",
        "camera_speed",
        "emotion",
        "camera_angle_detail",
        "transition",
        "duration",
        "camera_angle",
        "camera_movement",
    ):
        if not normalized.get(field) and structured.get(field):
            normalized[field] = structured.get(field)
    return normalized


def _shot_for_violation(shots: list[dict[str, Any]], location: str) -> dict[str, Any] | None:
    if location.startswith("shot_"):
        try:
            idx = int(location.split("_", 1)[1].split("/", 1)[0])
            if 0 <= idx < len(shots):
                return shots[idx]
        except (TypeError, ValueError):
            return None
    return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
