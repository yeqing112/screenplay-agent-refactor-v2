"""add agent session plan and audit log

Revision ID: c2d3e4f5a6b7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-06 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c2d3e4f5a6b7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "agent_sessions" not in tables:
        op.create_table(
            "agent_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("user_prompt", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("skill_id", sa.String(), nullable=False, server_default=""),
            sa.Column("skill_version", sa.String(), nullable=False, server_default=""),
            sa.Column("evidence_fingerprint", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_agent_sessions_book", "agent_sessions", ["book_id"])
        op.create_index("ix_agent_sessions_evidence", "agent_sessions", ["evidence_fingerprint"])

    if "agent_plans" not in tables:
        op.create_table(
            "agent_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("plan_fingerprint", sa.String(), nullable=False, server_default=""),
            sa.Column("objective", sa.Text(), nullable=False, server_default=""),
            sa.Column("scope", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("evidence_snapshot", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("steps", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("preconditions", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("blocking_issues", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("approval_policy", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("cost_envelope", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("rollback_anchor", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_agent_plans_session", "agent_plans", ["session_id"])
        op.create_index("ix_agent_plans_fingerprint", "agent_plans", ["plan_fingerprint"])

    if "agent_audit_logs" not in tables:
        op.create_table(
            "agent_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=True),
            sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("operation", sa.String(), nullable=False, server_default=""),
            sa.Column("tool_tier", sa.String(), nullable=False, server_default="A"),
            sa.Column("evidence_fingerprint", sa.String(), nullable=False, server_default=""),
            sa.Column("plan_fingerprint", sa.String(), nullable=False, server_default=""),
            sa.Column("model_info", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("request_payload", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("response_payload", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confirmation_user", sa.String(), nullable=False, server_default=""),
            sa.Column("confirmation_at", sa.DateTime(), nullable=True),
            sa.Column("result_status", sa.String(), nullable=False, server_default=""),
            sa.Column("result_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_agent_audit_session", "agent_audit_logs", ["session_id"])
        op.create_index("ix_agent_audit_plan", "agent_audit_logs", ["plan_id"])
        op.create_index("ix_agent_audit_evidence", "agent_audit_logs", ["evidence_fingerprint"])
        op.create_index("ix_agent_audit_plan_fingerprint", "agent_audit_logs", ["plan_fingerprint"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    for name in ("agent_audit_logs", "agent_plans", "agent_sessions"):
        if name in tables:
            op.drop_table(name)