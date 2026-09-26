"""Add the Character Consistency Runtime relations.

The existing ``character_profiles`` table remains the single character
identity authority.  New rows only describe typed references and shot role
bindings; media and Prompt lineage continue to use the existing authority
tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e1f2a3b4c5d6"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {item["name"] for item in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "character_profiles" in _tables(bind):
        existing = _columns(bind, "character_profiles")
        for name, column in (
            ("description", sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''"))),
            ("attributes", sa.Column("attributes", sa.Text(), nullable=False, server_default=sa.text("'{}'"))),
            ("appearance_profile", sa.Column("appearance_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'"))),
        ):
            if name not in existing:
                op.add_column("character_profiles", column)

    tables = _tables(bind)
    if "character_reference_assets" not in tables:
        op.create_table(
            "character_reference_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("character_id", sa.Integer(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("reference_type", sa.String(), nullable=False, server_default=sa.text("'portrait'")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("visual_reference_asset_id", sa.Integer(), nullable=True),
            sa.Column("asset_version_id", sa.String(), nullable=True),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["character_id"], ["character_profiles.id"], name="fk_character_reference_character", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["visual_reference_asset_id"], ["visual_reference_assets.id"], name="fk_character_reference_visual_asset", ondelete="RESTRICT"),
            sa.UniqueConstraint("character_id", "asset_id", "reference_type", name="uq_character_reference_asset_identity"),
            sa.CheckConstraint("reference_type IN ('portrait','full_body','costume','expression')", name="ck_character_reference_asset_type"),
            sa.CheckConstraint("priority >= 0", name="ck_character_reference_asset_priority"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_character_reference_asset_status"),
        )
        op.create_index("ix_character_reference_assets_character", "character_reference_assets", ["character_id"])
        op.create_index("ix_character_reference_assets_asset", "character_reference_assets", ["asset_id"])
        op.create_index("ix_character_reference_assets_version", "character_reference_assets", ["asset_version_id"])
        op.create_index("ix_character_reference_assets_status", "character_reference_assets", ["status"])

    tables = _tables(bind)
    if "shot_character_bindings" not in tables:
        op.create_table(
            "shot_character_bindings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("character_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(), nullable=False, server_default=sa.text("'supporting'")),
            sa.Column("reference_asset_ids", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("appearance_rules", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("asset_authority_id", sa.String(), nullable=True),
            sa.Column("asset_version_id", sa.String(), nullable=True),
            sa.Column("binding_fingerprint", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_shot_character_binding_shot", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["character_id"], ["character_profiles.id"], name="fk_shot_character_binding_character", ondelete="RESTRICT"),
            sa.UniqueConstraint("storyboard_shot_id", "character_id", "role", name="uq_shot_character_binding_role"),
            sa.UniqueConstraint("binding_fingerprint", name="uq_shot_character_binding_fingerprint"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_character_binding_status"),
        )
        op.create_index("ix_shot_character_bindings_shot", "shot_character_bindings", ["storyboard_shot_id"])
        op.create_index("ix_shot_character_bindings_character", "shot_character_bindings", ["character_id"])
        op.create_index("ix_shot_character_bindings_status", "shot_character_bindings", ["status"])
        op.create_index("ix_shot_character_bindings_version", "shot_character_bindings", ["asset_version_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "shot_character_bindings" in tables:
        op.drop_table("shot_character_bindings")
    if "character_reference_assets" in tables:
        op.drop_table("character_reference_assets")
    if "character_profiles" in tables:
        existing = _columns(bind, "character_profiles")
        for name in ("appearance_profile", "attributes", "description"):
            if name in existing:
                op.drop_column("character_profiles", name)
