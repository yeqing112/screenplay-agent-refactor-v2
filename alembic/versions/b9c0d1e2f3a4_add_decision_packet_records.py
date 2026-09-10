"""add decision packet records

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "decision_packet_records" in inspect(op.get_bind()).get_table_names(): return
    op.create_table("decision_packet_records",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False), sa.Column("scope", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("packet_fingerprint", sa.String(), nullable=False, unique=True), sa.Column("evidence", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unknowns", sa.Text(), nullable=False, server_default="[]"), sa.Column("conflicts", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allowed_operations", sa.Text(), nullable=False, server_default="[]"), sa.Column("proposal", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"), sa.Column("model_info", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), nullable=True), sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_decision_packet_book_domain", "decision_packet_records", ["book_id", "domain"])

def downgrade() -> None:
    if "decision_packet_records" in inspect(op.get_bind()).get_table_names(): op.drop_table("decision_packet_records")
