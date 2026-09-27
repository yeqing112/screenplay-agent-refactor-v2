"""Add Scene Continuity Runtime relations over VisualLocation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e2f3a4b5c6d7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {item["name"] for item in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "visual_locations" in _tables(bind):
        existing = _columns(bind, "visual_locations")
        for name, column in (
            ("attributes", sa.Column("attributes", sa.Text(), nullable=False, server_default=sa.text("'{}'"))),
            ("environment_profile", sa.Column("environment_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'"))),
        ):
            if name not in existing:
                op.add_column("visual_locations", column)

    if "scene_reference_assets" not in _tables(bind):
        op.create_table(
            "scene_reference_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scene_id", sa.Integer(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("reference_type", sa.String(), nullable=False, server_default=sa.text("'overview'")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("visual_reference_asset_id", sa.Integer(), nullable=True),
            sa.Column("asset_version_id", sa.String(), nullable=True),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["scene_id"], ["visual_locations.id"], name="fk_scene_reference_scene", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["visual_reference_asset_id"], ["visual_reference_assets.id"], name="fk_scene_reference_visual_asset", ondelete="RESTRICT"),
            sa.UniqueConstraint("scene_id", "asset_id", "reference_type", name="uq_scene_reference_asset_identity"),
            sa.CheckConstraint("reference_type IN ('overview','layout','lighting','detail','prop')", name="ck_scene_reference_asset_type"),
            sa.CheckConstraint("priority >= 0", name="ck_scene_reference_asset_priority"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_scene_reference_asset_status"),
        )
        for name, fields in {
            "ix_scene_reference_assets_scene": ["scene_id"],
            "ix_scene_reference_assets_asset": ["asset_id"],
            "ix_scene_reference_assets_version": ["asset_version_id"],
            "ix_scene_reference_assets_status": ["status"],
        }.items():
            op.create_index(name, "scene_reference_assets", fields)

    if "shot_scene_bindings" not in _tables(bind):
        op.create_table(
            "shot_scene_bindings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.Integer(), nullable=False),
            sa.Column("reference_asset_ids", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("environment_rules", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("asset_authority_id", sa.String(), nullable=True),
            sa.Column("asset_version_id", sa.String(), nullable=True),
            sa.Column("binding_fingerprint", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_shot_scene_binding_shot", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["scene_id"], ["visual_locations.id"], name="fk_shot_scene_binding_scene", ondelete="RESTRICT"),
            sa.UniqueConstraint("binding_fingerprint", name="uq_shot_scene_binding_fingerprint"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_scene_binding_status"),
        )
        for name, fields in {
            "ix_shot_scene_bindings_shot": ["storyboard_shot_id"],
            "ix_shot_scene_bindings_scene": ["scene_id"],
            "ix_shot_scene_bindings_status": ["status"],
            "ix_shot_scene_bindings_version": ["asset_version_id"],
        }.items():
            op.create_index(name, "shot_scene_bindings", fields)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "shot_scene_bindings" in tables:
        op.drop_table("shot_scene_bindings")
    if "scene_reference_assets" in tables:
        op.drop_table("scene_reference_assets")
    if "visual_locations" in tables:
        existing = _columns(bind, "visual_locations")
        for name in ("environment_profile", "attributes"):
            if name in existing:
                op.drop_column("visual_locations", name)
