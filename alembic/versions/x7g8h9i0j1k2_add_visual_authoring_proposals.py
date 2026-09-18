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
down_revision: Union[str, Sequence[str], None] = ("w6f7g8h9i0j1", "p0q1r2s3t4u5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    def ensure_columns(table: str, columns: list[sa.Column]) -> None:
        if table not in tables:
            return
        existing = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)

    if "visual_authoring_proposals" not in tables:
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
            sa.UniqueConstraint("request_id", "provider_request_fingerprint", name="uq_visual_authoring_proposal_request_fingerprint"),
        )
        tables.add("visual_authoring_proposals")

    # The historical Canary table used the same logical rows but shorter
    # column names.  Preserve those columns and add the canonical names.
    ensure_columns("visual_authoring_proposals", [
        sa.Column("scope_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("source_constraint_refs_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("validator_diagnostics_json", sa.Text(), nullable=True, server_default="{}"),
    ])
    ensure_columns("visual_authoring_decision_requests", [
        sa.Column("missing_field", sa.String(), nullable=True, server_default=""),
        sa.Column("source_constraints_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("free_authoring_space_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("forbidden_contradictions_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("scope_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("required_by_stage", sa.String(), nullable=True, server_default="PromptIR"),
        sa.Column("resolution_json", sa.Text(), nullable=True, server_default="{}"),
    ])
    ensure_columns("visual_authoring_decisions", [
        sa.Column("field", sa.String(), nullable=True, server_default=""),
        sa.Column("value_json", sa.Text(), nullable=True, server_default="null"),
        sa.Column("scope_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("authority_class", sa.String(), nullable=True, server_default="PRODUCTION_VISUAL_AUTHORING_DECISION"),
        sa.Column("source_constraint_refs_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("author", sa.String(), nullable=True, server_default="human"),
        sa.Column("authoring_policy", sa.String(), nullable=True, server_default="visual_authoring_policy_v1"),
        sa.Column("provenance_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=True, server_default="1"),
    ])
    ensure_columns("visual_asset_versions", [
        sa.Column("asset_type", sa.String(), nullable=True, server_default=""),
        sa.Column("canonical_id", sa.String(), nullable=True, server_default=""),
        sa.Column("canonical_identity_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("scope_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("payload_hash", sa.String(), nullable=True, server_default=""),
        sa.Column("source_constraints_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("authoring_decisions_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("variant_binding_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("source_constraint_fingerprint", sa.String(), nullable=True, server_default=""),
        sa.Column("authoring_decision_fingerprint", sa.String(), nullable=True, server_default=""),
        sa.Column("variant_fingerprint", sa.String(), nullable=True, server_default=""),
        sa.Column("authority_status", sa.String(), nullable=True, server_default="SPEC_DRAFT"),
        sa.Column("stale_status", sa.String(), nullable=True, server_default="FRESH"),
        sa.Column("stale_reasons", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ])
    ensure_columns("visual_asset_pointers", [
        sa.Column("asset_type", sa.String(), nullable=True, server_default=""),
        sa.Column("scope_key", sa.String(), nullable=True, server_default=""),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("payload_hash", sa.String(), nullable=True, server_default=""),
        sa.Column("authority_status", sa.String(), nullable=True, server_default="SPEC_APPROVED"),
        sa.Column("stale_status", sa.String(), nullable=True, server_default="FRESH"),
        sa.Column("stale_reasons", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    ])
    ensure_columns("visual_reference_authorities", [
        sa.Column("visual_reference_asset_id", sa.Integer(), nullable=True),
        sa.Column("asset_version_id", sa.Integer(), nullable=True),
        sa.Column("asset_version_fingerprint", sa.String(), nullable=True, server_default=""),
        sa.Column("reference_scope_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("image_identity", sa.String(), nullable=True, server_default=""),
        sa.Column("checksum", sa.String(), nullable=True, server_default=""),
        sa.Column("storage_reference_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("generation_provenance_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("reference_token_mapping_json", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("lock_revision", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("authority_fingerprint", sa.String(), nullable=True, server_default=""),
        sa.Column("stale_status", sa.String(), nullable=True, server_default="FRESH"),
        sa.Column("stale_reasons", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ])
    ensure_columns("visual_reference_assets", [
        sa.Column("asset_key", sa.String(), nullable=True, server_default=""),
        sa.Column("asset_version_id", sa.Integer(), nullable=True),
        sa.Column("authority_status", sa.String(), nullable=True, server_default="CANDIDATE"),
        sa.Column("reference_scope", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("image_identity", sa.String(), nullable=True, server_default=""),
        sa.Column("checksum", sa.String(), nullable=True, server_default=""),
        sa.Column("generation_provenance", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("reference_token_mapping", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("lock_revision", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("stale_status", sa.String(), nullable=True, server_default="FRESH"),
        sa.Column("stale_reasons", sa.Text(), nullable=True, server_default="[]"),
    ])
    ensure_columns("visual_makeups", [sa.Column("asset_key", sa.String(), nullable=True, server_default="")])
    ensure_columns("visual_locations", [sa.Column("asset_key", sa.String(), nullable=True, server_default=""), sa.Column("scene_id", sa.String(), nullable=True, server_default="")])
    ensure_columns("visual_props", [sa.Column("asset_key", sa.String(), nullable=True, server_default="")])

    bind = op.get_bind()
    # Backfill only obvious lineage aliases; no row is deleted or overwritten.
    if "visual_asset_versions" in tables:
        version_columns = {item["name"] for item in inspect(bind).get_columns("visual_asset_versions")}
        if "version" in version_columns:
            bind.execute(sa.text("UPDATE visual_asset_versions SET revision=version WHERE revision IS NULL AND version IS NOT NULL"))
    if "visual_authoring_decision_requests" in tables:
        request_columns = {item["name"] for item in inspect(bind).get_columns("visual_authoring_decision_requests")}
        if {"source_constraints", "source_constraints_json"}.issubset(request_columns):
            bind.execute(sa.text("UPDATE visual_authoring_decision_requests SET source_constraints_json=source_constraints WHERE (source_constraints_json IS NULL OR source_constraints_json='[]') AND source_constraints IS NOT NULL"))
        if {"free_authoring_space", "free_authoring_space_json"}.issubset(request_columns):
            bind.execute(sa.text("UPDATE visual_authoring_decision_requests SET free_authoring_space_json=free_authoring_space WHERE (free_authoring_space_json IS NULL OR free_authoring_space_json='[]') AND free_authoring_space IS NOT NULL"))
        if {"scope", "scope_json"}.issubset(request_columns):
            bind.execute(sa.text("UPDATE visual_authoring_decision_requests SET scope_json=scope WHERE (scope_json IS NULL OR scope_json='{}') AND scope IS NOT NULL"))
    if "visual_authoring_proposals" in tables:
        proposal_columns = {item["name"] for item in inspect(bind).get_columns("visual_authoring_proposals")}
        if {"scope", "scope_json"}.issubset(proposal_columns):
            bind.execute(sa.text("UPDATE visual_authoring_proposals SET scope_json=scope WHERE (scope_json IS NULL OR scope_json='{}') AND scope IS NOT NULL"))
        if {"source_constraint_refs", "source_constraint_refs_json"}.issubset(proposal_columns):
            bind.execute(sa.text("UPDATE visual_authoring_proposals SET source_constraint_refs_json=source_constraint_refs WHERE (source_constraint_refs_json IS NULL OR source_constraint_refs_json='[]') AND source_constraint_refs IS NOT NULL"))
        if {"validator_diagnostics", "validator_diagnostics_json"}.issubset(proposal_columns):
            bind.execute(sa.text("UPDATE visual_authoring_proposals SET validator_diagnostics_json=validator_diagnostics WHERE (validator_diagnostics_json IS NULL OR validator_diagnostics='{}') AND validator_diagnostics IS NOT NULL"))
    if "visual_asset_pointers" in tables:
        pointer_columns = {item["name"] for item in inspect(bind).get_columns("visual_asset_pointers")}
        if {"version_id", "current_version_id"}.issubset(pointer_columns):
            bind.execute(sa.text("UPDATE visual_asset_pointers SET current_version_id=version_id WHERE current_version_id IS NULL AND version_id IS NOT NULL"))
        if "scope_key" in pointer_columns:
            bind.execute(sa.text("UPDATE visual_asset_pointers SET scope_key=asset_key || '@canonical' WHERE (scope_key IS NULL OR scope_key='') AND asset_key IS NOT NULL"))


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
