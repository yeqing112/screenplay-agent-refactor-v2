"""Violation Log — Agent 违规追踪模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text

from models.base import Base


class AgentViolationLog(Base):
    """Agent 违规日志表"""
    __tablename__ = "agent_violation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_type = Column(String(32), nullable=False, index=True)       # 'screenwriter' / 'storyboard' / 'compiler'
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=True)
    scene_name = Column(String(128), nullable=True)
    shot_id = Column(Integer, nullable=True)

    violation_id = Column(String(64), nullable=False, index=True)     # e.g. 'CAMERA_INVALID_ENUM'
    field = Column(String(64), nullable=False)                         # e.g. 'camera_movement'
    actual_value = Column(String(256), nullable=True)                  # e.g. 'orbit'
    expected_source = Column(String(64), nullable=True)                # e.g. 'CAMERA_LIBRARY'
    severity = Column(String(16), nullable=False)                      # 'block' / 'warn' / 'penalty'

    repair_strategy = Column(String(16), nullable=True)                # 'programmatic' / 'hybrid' / 'llm' / 'none'
    repair_result = Column(String(16), nullable=True)                  # 'auto_fixed' / 'llm_fixed' / 'rejected' / 'accepted_with_warning'
    fix_details = Column(Text, nullable=True)                          # JSON: what was changed
    regression = Column(Integer, default=0)                            # 1 if repair introduced new violations

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<AgentViolationLog {self.violation_id} agent={self.agent_type} book={self.book_id}>"
