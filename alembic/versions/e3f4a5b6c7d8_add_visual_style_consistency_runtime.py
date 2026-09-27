"""Add Visual Style Consistency Runtime relations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e3f4a5b6c7d8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "visual_style_profiles" not in tables:
        op.create_table(
            "visual_style_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("camera_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("lighting_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("color_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("composition_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_visual_style_profiles_book", "visual_style_profiles", ["book_id"])

    tables = _tables(bind)
    if "style_reference_assets" not in tables:
        op.create_table(
            "style_reference_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("style_id", sa.Integer(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("reference_type", sa.String(), nullable=False, server_default=sa.text("'mood'")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("visual_reference_asset_id", sa.Integer(), nullable=True),
            sa.Column("asset_version_id", sa.String(), nullable=True),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["style_id"], ["visual_style_profiles.id"], name="fk_style_reference_style", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["visual_reference_asset_id"], ["visual_reference_assets.id"], name="fk_style_reference_visual_asset", ondelete="RESTRICT"),
            sa.UniqueConstraint("style_id", "asset_id", "reference_type", name="uq_style_reference_asset_identity"),
            sa.CheckConstraint("reference_type IN ('color','camera','lighting','composition','mood')", name="ck_style_reference_asset_type"),
            sa.CheckConstraint("priority >= 0", name="ck_style_reference_asset_priority"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_style_reference_asset_status"),
        )
        for name, fields in {
            "ix_style_reference_assets_style": ["style_id"],
            "ix_style_reference_assets_asset": ["asset_id"],
            "ix_style_reference_assets_version": ["asset_version_id"],
            "ix_style_reference_assets_status": ["status"],
        }.items():
            op.create_index(name, "style_reference_assets", fields)

    tables = _tables(bind)
    if "shot_style_bindings" not in tables:
        op.create_table(
            "shot_style_bindings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("style_id", sa.Integer(), nullable=False),
            sa.Column("scope", sa.String(), nullable=False, server_default=sa.text("'SHOT_OVERRIDE'")),
            sa.Column("reference_asset_ids", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("style_rules", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("asset_authority_id", sa.String(), nullable=True),
            sa.Column("asset_version_id", sa.String(), nullable=True),
            sa.Column("binding_fingerprint", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_shot_style_binding_shot", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["style_id"], ["visual_style_profiles.id"], name="fk_shot_style_binding_style", ondelete="RESTRICT"),
            sa.UniqueConstraint("binding_fingerprint", name="uq_shot_style_binding_fingerprint"),
            sa.CheckConstraint("scope IN ('EPISODE_DEFAULT','SHOT_OVERRIDE')", name="ck_shot_style_binding_scope"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_style_binding_status"),
        )
        for name, fields in {
            "ix_shot_style_bindings_shot": ["storyboard_shot_id"],
            "ix_shot_style_bindings_book": ["book_id"],
            "ix_shot_style_bindings_episode": ["episode"],
            "ix_shot_style_bindings_style": ["style_id"],
            "ix_shot_style_bindings_scope": ["scope"],
            "ix_shot_style_bindings_status": ["status"],
            "ix_shot_style_bindings_version": ["asset_version_id"],
        }.items():
            op.create_index(name, "shot_style_bindings", fields)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "shot_style_bindings" in tables:
        op.drop_table("shot_style_bindings")
    if "style_reference_assets" in tables:
        op.drop_table("style_reference_assets")
    if "visual_style_profiles" in tables:
        op.drop_table("visual_style_profiles")
