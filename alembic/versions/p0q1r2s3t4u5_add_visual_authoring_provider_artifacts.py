"""add visual authoring provider proposal and authority boundary artifacts"""

from alembic import op
import sqlalchemy as sa


revision = "p0q1r2s3t4u5"
down_revision = "n7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_authoring_decision_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("canonical_id", sa.String(128), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_constraints", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("free_authoring_space", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("forbidden_contradictions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("request_id", name="uq_visual_authoring_request_id"),
    )
    op.create_index("ix_visual_authoring_requests_book_id", "visual_authoring_decision_requests", ["book_id"])
    op.create_index("ix_visual_authoring_requests_asset_key", "visual_authoring_decision_requests", ["asset_key"])
    op.create_table(
        "visual_authoring_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("decision_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confirmed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="APPROVED"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("decision_id", name="uq_visual_authoring_decision_id"),
    )
    op.create_index("ix_visual_authoring_decisions_book_id", "visual_authoring_decisions", ["book_id"])
    op.create_index("ix_visual_authoring_decisions_request_id", "visual_authoring_decisions", ["request_id"])
    op.create_table(
        "visual_authoring_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("proposal_id", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("proposed_fields_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("explanation_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_constraint_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("provider_profile_id", sa.String(128), nullable=False),
        sa.Column("provider_model", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_vendor_host", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_request_fingerprint", sa.String(128), nullable=False),
        sa.Column("provider_response_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("proposal_payload_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("validator_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("validator_diagnostics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("audit_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="CANDIDATE"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("proposal_id", name="uq_visual_authoring_proposal_id"),
        sa.UniqueConstraint("request_id", "provider_request_fingerprint", name="uq_visual_authoring_proposal_request_fp"),
    )
    op.create_index("ix_visual_authoring_proposals_book_id", "visual_authoring_proposals", ["book_id"])
    op.create_index("ix_visual_authoring_proposals_request_id", "visual_authoring_proposals", ["request_id"])
    op.create_index("ix_visual_authoring_proposals_provider_request_fp", "visual_authoring_proposals", ["provider_request_fingerprint"])
    op.create_table(
        "visual_asset_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_visual_asset_versions_book_id", "visual_asset_versions", ["book_id"])
    op.create_index("ix_visual_asset_versions_asset_key", "visual_asset_versions", ["asset_key"])
    op.create_table(
        "visual_asset_pointers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(255), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("asset_key", name="uq_visual_asset_pointer_asset_key"),
    )
    op.create_index("ix_visual_asset_pointers_book_id", "visual_asset_pointers", ["book_id"])
    op.create_table(
        "visual_reference_authorities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.String(255), nullable=False),
        sa.Column("reference_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="CANDIDATE"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_visual_reference_authorities_book_id", "visual_reference_authorities", ["book_id"])
    op.create_index("ix_visual_reference_authorities_asset_key", "visual_reference_authorities", ["asset_key"])


def downgrade() -> None:
    for name in (
        "visual_reference_authorities",
        "visual_asset_pointers",
        "visual_asset_versions",
        "visual_authoring_proposals",
        "visual_authoring_decisions",
        "visual_authoring_decision_requests",
    ):
        op.drop_table(name)
