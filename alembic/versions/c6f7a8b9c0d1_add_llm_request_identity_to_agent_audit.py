"""add request identity and usage telemetry to agent audits

Revision ID: c6f7a8b9c0d1
Revises: c5e6f7a8b9c0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c6f7a8b9c0d1"
down_revision = "c5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_audit_logs" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("agent_audit_logs")}
    if "request_fingerprint" not in columns:
        op.add_column("agent_audit_logs", sa.Column("request_fingerprint", sa.String(), nullable=False, server_default=""))
        op.create_index("ix_agent_audit_request_fingerprint", "agent_audit_logs", ["request_fingerprint"])
    if "llm_usage" not in columns:
        op.add_column("agent_audit_logs", sa.Column("llm_usage", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_audit_logs" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("agent_audit_logs")}
    if "llm_usage" in columns:
        op.drop_column("agent_audit_logs", "llm_usage")
    if "request_fingerprint" in columns:
        op.drop_index("ix_agent_audit_request_fingerprint", table_name="agent_audit_logs")
        op.drop_column("agent_audit_logs", "request_fingerprint")
