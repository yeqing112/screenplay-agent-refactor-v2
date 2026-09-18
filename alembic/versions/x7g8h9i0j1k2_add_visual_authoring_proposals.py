"""Add provider-only visual authoring proposals.

This is an additive reconciliation migration.  The canonical Authority
tables are created by ``v5e6f7g8h9i0`` and are deliberately not recreated or
altered here.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "x7g8h9i0j1k2"
down_revision: Union[str, Sequence[str], None] = "w6f7g8h9i0j1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "visual_authoring_proposals" in inspector.get_table_names():
        return
    op.create_table(
        "visual_authoring_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("proposed_fields_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("explanation_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_constraint_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("provider_profile_id", sa.String(), nullable=False),
        sa.Column("provider_model", sa.String(), nullable=False, server_default=""),
        sa.Column("provider_vendor_host", sa.String(), nullable=False, server_default=""),
        sa.Column("provider_request_fingerprint", sa.String(), nullable=False),
        sa.Column("provider_response_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("proposal_payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("validator_status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("validator_diagnostics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("audit_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="CANDIDATE"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("proposal_id", name="uq_visual_authoring_proposals_proposal_id"),
        sa.UniqueConstraint(
            "request_id",
            "provider_request_fingerprint",
            name="uq_visual_authoring_proposal_request_fingerprint",
        ),
    )
    op.create_index("ix_visual_authoring_proposals_request_id", "visual_authoring_proposals", ["request_id"])
    op.create_index("ix_visual_authoring_proposals_book_id", "visual_authoring_proposals", ["book_id"])
    op.create_index("ix_visual_authoring_proposals_asset_key", "visual_authoring_proposals", ["asset_key"])
    op.create_index("ix_visual_authoring_proposals_provider_request_fingerprint", "visual_authoring_proposals", ["provider_request_fingerprint"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "visual_authoring_proposals" not in inspector.get_table_names():
        return
    for name in (
        "ix_visual_authoring_proposals_provider_request_fingerprint",
        "ix_visual_authoring_proposals_asset_key",
        "ix_visual_authoring_proposals_book_id",
        "ix_visual_authoring_proposals_request_id",
    ):
        op.drop_index(name, table_name="visual_authoring_proposals")
    op.drop_table("visual_authoring_proposals")
