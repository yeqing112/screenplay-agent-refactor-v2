"""Add versioned visual asset authority and reference lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "v5e6f7g8h9i0"
down_revision = "u4d5e6f7g8h9"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if table in inspector.get_table_names() and column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def _create_table(name: str, columns: list[sa.Column], indexes: list[tuple[str, list[str], bool]] = ()) -> None:
    inspector = inspect(op.get_bind())
    if name not in inspector.get_table_names():
        op.create_table(name, *columns)
        for index_name, fields, unique in indexes:
            op.create_index(index_name, name, fields, unique=unique)


def upgrade() -> None:
    for table in ("visual_props", "visual_locations", "visual_makeups"):
        _add_column(table, sa.Column("asset_key", sa.String(), nullable=True))
    for column in (
        sa.Column("asset_key", sa.String(), nullable=True),
        sa.Column("asset_version_id", sa.Integer(), nullable=True),
        sa.Column("authority_status", sa.String(), nullable=True, server_default="CANDIDATE"),
        sa.Column("reference_scope", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("image_identity", sa.String(), nullable=True, server_default=""),
        sa.Column("checksum", sa.String(), nullable=True, server_default=""),
        sa.Column("generation_provenance", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("lock_revision", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("stale_status", sa.String(), nullable=True, server_default="FRESH"),
        sa.Column("stale_reasons", sa.Text(), nullable=True, server_default="[]"),
    ):
        _add_column("visual_reference_assets", column)

    _create_table("visual_asset_versions", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_type", sa.String(), nullable=False), sa.Column("canonical_id", sa.String(), nullable=False), sa.Column("canonical_identity_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("scope_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("revision", sa.Integer(), nullable=False, server_default="1"), sa.Column("base_version_id", sa.Integer()), sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("payload_hash", sa.String(), nullable=False), sa.Column("source_constraints_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("authoring_decisions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("variant_binding_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("source_constraint_fingerprint", sa.String(), nullable=False, server_default=""), sa.Column("authoring_decision_fingerprint", sa.String(), nullable=False, server_default=""), sa.Column("variant_fingerprint", sa.String(), nullable=False, server_default=""), sa.Column("authority_status", sa.String(), nullable=False, server_default="SPEC_DRAFT"), sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"), sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_asset_versions_asset_key", ["asset_key"], False), ("ix_visual_asset_versions_book_type", ["book_id", "asset_type"], False), ("ix_visual_asset_versions_payload_hash", ["payload_hash"], False)])
    _create_table("visual_asset_pointers", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_type", sa.String(), nullable=False), sa.Column("scope_key", sa.String(), nullable=False), sa.Column("current_version_id", sa.Integer(), nullable=False, unique=True), sa.Column("payload_hash", sa.String(), nullable=False), sa.Column("authority_status", sa.String(), nullable=False, server_default="SPEC_APPROVED"), sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"), sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_asset_pointers_asset_scope", ["asset_key", "scope_key"], True), ("ix_visual_asset_pointers_book_type", ["book_id", "asset_type"], False)])
    _create_table("visual_authoring_decision_requests", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("request_id", sa.String(), nullable=False, unique=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_type", sa.String(), nullable=False), sa.Column("missing_field", sa.String(), nullable=False), sa.Column("source_constraints_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("free_authoring_space_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("forbidden_contradictions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("scope_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("required_by_stage", sa.String(), nullable=False, server_default="PromptIR"), sa.Column("status", sa.String(), nullable=False, server_default="PENDING"), sa.Column("resolution_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_authoring_requests_asset", ["asset_key"], False)])
    _create_table("visual_authoring_decisions", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("decision_id", sa.String(), nullable=False, unique=True), sa.Column("request_id", sa.String()), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_type", sa.String(), nullable=False), sa.Column("field", sa.String(), nullable=False), sa.Column("value_json", sa.Text(), nullable=False, server_default="null"), sa.Column("scope_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("authority_class", sa.String(), nullable=False, server_default="PRODUCTION_VISUAL_AUTHORING_DECISION"), sa.Column("source_constraint_refs_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("author", sa.String(), nullable=False, server_default="human"), sa.Column("authoring_policy", sa.String(), nullable=False, server_default="visual_authoring_policy_v1"), sa.Column("status", sa.String(), nullable=False, server_default="PROPOSED"), sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("revision", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_authoring_decisions_asset", ["asset_key"], False)])
    _create_table("visual_reference_authorities", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("visual_reference_asset_id", sa.Integer(), nullable=False), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_version_id", sa.Integer(), nullable=False), sa.Column("asset_version_fingerprint", sa.String(), nullable=False), sa.Column("reference_scope_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("image_identity", sa.String(), nullable=False), sa.Column("checksum", sa.String(), nullable=False), sa.Column("storage_reference_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("generation_provenance_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("reference_token_mapping_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("lock_revision", sa.Integer(), nullable=False, server_default="1"), sa.Column("status", sa.String(), nullable=False, server_default="CANDIDATE"), sa.Column("authority_fingerprint", sa.String(), nullable=False, unique=True), sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"), sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_reference_authorities_asset", ["asset_key"], False), ("ix_visual_reference_authorities_version", ["asset_version_id"], False)])
    _create_table("visual_reference_sets", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_version_id", sa.Integer(), nullable=False), sa.Column("set_type", sa.String(), nullable=False, server_default="single_hero_reference"), sa.Column("roles_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("status", sa.String(), nullable=False, server_default="CANDIDATE"), sa.Column("fingerprint", sa.String(), nullable=False, unique=True), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_reference_sets_asset", ["asset_key"], False)])
    _create_table("visual_reference_generation_requests", [
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("request_fingerprint", sa.String(), nullable=False, unique=True), sa.Column("asset_key", sa.String(), nullable=False), sa.Column("asset_version_id", sa.Integer(), nullable=False), sa.Column("variant_id", sa.String(), nullable=False, server_default=""), sa.Column("request_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("status", sa.String(), nullable=False, server_default="READY_FOR_PROVIDER_CANARY"), sa.Column("provider_not_called", sa.String(), nullable=False, server_default="true"), sa.Column("created_at", sa.DateTime()), sa.Column("updated_at", sa.DateTime()),
    ], [("ix_visual_reference_requests_asset", ["asset_key"], False)])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table in ("visual_reference_generation_requests", "visual_reference_sets", "visual_reference_authorities", "visual_authoring_decisions", "visual_authoring_decision_requests", "visual_asset_pointers", "visual_asset_versions"):
        if table in set(inspector.get_table_names()):
            op.drop_table(table)
