"""Violation Logger — 违规日志记录工具。"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from core.constraint_engine import Violation, RepairStrategy

logger = logging.getLogger(__name__)


def log_violation(
    agent_type: str,
    book_id: int,
    violation: Violation,
    episode: int | None = None,
    scene_name: str | None = None,
    shot_id: int | None = None,
    repair_result: str | None = None,
    fix_details: dict | None = None,
    regression: bool = False,
) -> None:
    """记录违规到数据库"""
    try:
        from models import Session, AgentViolationLog

        with Session() as s:
            log = AgentViolationLog(
                agent_type=agent_type,
                book_id=book_id,
                episode=episode,
                scene_name=scene_name,
                shot_id=shot_id,
                violation_id=violation.constraint_id,
                field=violation.field,
                actual_value=str(violation.actual_value)[:256] if violation.actual_value else None,
                expected_source=violation.source,
                severity=violation.severity.value if hasattr(violation.severity, 'value') else str(violation.severity),
                repair_strategy=violation.repair_strategy.value if hasattr(violation.repair_strategy, 'value') else str(violation.repair_strategy),
                repair_result=repair_result,
                fix_details=json.dumps(fix_details, ensure_ascii=False) if fix_details else None,
                regression=1 if regression else 0,
                created_at=datetime.utcnow(),
            )
            s.add(log)
            s.commit()
    except Exception as e:
        logger.warning("Failed to log violation: %s", e)


def log_violations_batch(
    agent_type: str,
    book_id: int,
    violations: list[Violation],
    episode: int | None = None,
    scene_name: str | None = None,
    shot_id: int | None = None,
    repair_results: dict[str, str] | None = None,
) -> None:
    """批量记录违规"""
    for violation in violations:
        repair_result = (repair_results or {}).get(violation.constraint_id)
        log_violation(
            agent_type=agent_type,
            book_id=book_id,
            violation=violation,
            episode=episode,
            scene_name=scene_name,
            shot_id=shot_id,
            repair_result=repair_result,
        )
