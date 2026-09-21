"""Create the Phase H2 Production Asset Authority schema.

Revision ID: a1b2c3d4e5f6
Revises: z0a1b2c3d4e5

The typed tables intentionally remain separate from VisualReferenceAuthority.
The two small registry tables provide a single FK target for the polymorphic
shot binding while keeping Character/Scene/Prop rows typed and empty until a
later ingestion phase.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "a1b2c3d4e5f6"
down_revision = "z0a1b2c3d4e5"
branch_labels = None
depends_on = None


AUTHORITY_TABLES = (
    "character_asset_authorities",
    "character_asset_versions",
    "character_asset_pointers",
    "scene_asset_authorities",
    "scene_asset_versions",
    "scene_asset_pointers",
    "prop_asset_authorities",
    "prop_asset_versions",
    "prop_asset_pointers",
)


def _table_names(bind) -> set[str]:
    return set(Inspector.from_engine(bind).get_table_names())


def _create_table(bind, name: str, *columns, constraints=(), indexes=()):
    if name in _table_names(bind):
        return
    op.create_table(name, *columns, *constraints)
    for index_name, fields, unique in indexes:
        op.create_index(index_name, name, fields, unique=unique)


def _drop_table(bind, name: str):
    if name in _table_names(bind):
        op.drop_table(name)


def _timestamp(name: str, *, nullable: bool = False):
    return sa.Column(name, sa.DateTime(), nullable=nullable, server_default=sa.text("CURRENT_TIMESTAMP"))


def upgrade() -> None:
    bind = op.get_bind()

    # These registries are an internal polymorphic FK bridge.  They contain no
    # rows during this migration; the future ingestion repository will insert a
    # typed authority/version and its registry row in one transaction.
    _create_table(
        bind,
        "production_asset_authority_registry",
        sa.Column("authority_id", sa.String(), primary_key=True),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("source_table", sa.String(), nullable=False),
        _timestamp("created_at"),
        constraints=(
            sa.CheckConstraint(
                "asset_type IN ('CHARACTER','SCENE','PROP')",
                name="ck_production_asset_authority_registry_type",
            ),
        ),
        indexes=(
            ("ix_production_asset_authority_registry_type", ["asset_type"], False),
        ),
    )
    _create_table(
        bind,
        "production_asset_version_registry",
        sa.Column("version_id", sa.String(), primary_key=True),
        sa.Column("authority_id", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        _timestamp("created_at"),
        constraints=(
            sa.ForeignKeyConstraint(
                ["authority_id"],
                ["production_asset_authority_registry.authority_id"],
                name="fk_production_asset_version_registry_authority",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "authority_id",
                "version_id",
                name="uq_production_asset_version_registry_authority_version",
            ),
            sa.CheckConstraint(
                "asset_type IN ('CHARACTER','SCENE','PROP')",
                name="ck_production_asset_version_registry_type",
            ),
        ),
        indexes=(
            ("ix_production_asset_version_registry_authority", ["authority_id"], False),
            ("ix_production_asset_version_registry_type", ["asset_type"], False),
        ),
    )

    # Version tables are created before authorities because authority.current_*
    # is an FK to the typed version identity.  Version authority ownership is
    # anchored to the registry; the validator enforces the typed pairing.
    version_columns = {
        "character_asset_versions": "CHARACTER",
        "scene_asset_versions": "SCENE",
        "prop_asset_versions": "PROP",
    }
    for name, asset_type in version_columns.items():
        entity = asset_type.lower()
        _create_table(
            bind,
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("version_id", sa.String(), nullable=False),
            sa.Column("authority_id", sa.String(), nullable=False),
            sa.Column(f"{entity}_id", sa.String(), nullable=False),
            sa.Column("visual_asset_version_id", sa.Integer(), nullable=True),
            sa.Column("storage_identity", sa.String(), nullable=True),
            sa.Column("checksum", sa.String(), nullable=True),
            sa.Column("metadata_hash", sa.String(), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="CURRENT"),
            _timestamp("created_at"),
            constraints=(
                sa.ForeignKeyConstraint(
                    ["authority_id", "version_id"],
                    ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
                    name=f"fk_{entity}_asset_version_registry_identity",
                    ondelete="RESTRICT",
                ),
                sa.ForeignKeyConstraint(
                    ["visual_asset_version_id"],
                    ["visual_asset_versions.id"],
                    name=f"fk_{entity}_asset_version_visual_lineage",
                    ondelete="RESTRICT",
                ),
                sa.UniqueConstraint("version_id", name=f"uq_{entity}_asset_version_identity"),
                sa.UniqueConstraint("authority_id", "version_id", name=f"uq_{entity}_asset_version_authority_identity"),
                sa.UniqueConstraint("authority_id", "revision", name=f"uq_{entity}_asset_version_revision"),
                sa.CheckConstraint("revision > 0", name=f"ck_{entity}_asset_version_revision_positive"),
                sa.CheckConstraint(
                    "status IN ('CURRENT','SUPERSEDED','STALE')",
                    name=f"ck_{entity}_asset_version_status",
                ),
            ),
            indexes=(
                (f"ix_{entity}_asset_versions_authority_revision", ["authority_id", "revision"], False),
                (f"ix_{entity}_asset_versions_status", ["status"], False),
                (f"ix_{entity}_asset_versions_checksum", ["checksum"], False),
            ),
        )

    authority_columns = {
        "character_asset_authorities": "CHARACTER",
        "scene_asset_authorities": "SCENE",
        "prop_asset_authorities": "PROP",
    }
    for name, asset_type in authority_columns.items():
        entity = asset_type.lower()
        _create_table(
            bind,
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("authority_id", sa.String(), nullable=False),
            sa.Column(f"{entity}_id", sa.String(), nullable=False),
            sa.Column("current_version_id", sa.String(), nullable=True),
            sa.Column("fingerprint", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            constraints=(
                sa.ForeignKeyConstraint(
                    ["authority_id"],
                    ["production_asset_authority_registry.authority_id"],
                    name=f"fk_{entity}_asset_authority_registry",
                    ondelete="RESTRICT",
                ),
                sa.ForeignKeyConstraint(
                    ["authority_id", "current_version_id"],
                    [f"{entity}_asset_versions.authority_id", f"{entity}_asset_versions.version_id"],
                    name=f"fk_{entity}_asset_authority_current_version",
                    ondelete="RESTRICT",
                ),
                sa.UniqueConstraint("authority_id", name=f"uq_{entity}_asset_authority_identity"),
                sa.UniqueConstraint(f"{entity}_id", name=f"uq_{entity}_asset_authority_entity"),
                sa.UniqueConstraint("fingerprint", name=f"uq_{entity}_asset_authority_fingerprint"),
                sa.CheckConstraint("status IN ('ACTIVE','STALE')", name=f"ck_{entity}_asset_authority_status"),
            ),
            indexes=(
                (f"ix_{entity}_asset_authorities_entity", [f"{entity}_id"], False),
                (f"ix_{entity}_asset_authorities_status", ["status"], False),
                (f"ix_{entity}_asset_authorities_current_version", ["current_version_id"], False),
            ),
        )

    pointer_columns = {
        "character_asset_pointers": "CHARACTER",
        "scene_asset_pointers": "SCENE",
        "prop_asset_pointers": "PROP",
    }
    for name, asset_type in pointer_columns.items():
        entity = asset_type.lower()
        _create_table(
            bind,
            name,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(f"{entity}_id", sa.String(), nullable=False),
            sa.Column("authority_id", sa.String(), nullable=False),
            sa.Column("version_id", sa.String(), nullable=False),
            sa.Column("fingerprint", sa.String(), nullable=False),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            constraints=(
                sa.ForeignKeyConstraint(
                    ["authority_id"],
                    [f"{entity}_asset_authorities.authority_id"],
                    name=f"fk_{entity}_asset_pointer_authority",
                    ondelete="RESTRICT",
                ),
                sa.ForeignKeyConstraint(
                    ["authority_id", "version_id"],
                    [f"{entity}_asset_versions.authority_id", f"{entity}_asset_versions.version_id"],
                    name=f"fk_{entity}_asset_pointer_version",
                    ondelete="RESTRICT",
                ),
                sa.UniqueConstraint(f"{entity}_id", name=f"uq_{entity}_asset_pointer_entity"),
                sa.UniqueConstraint("authority_id", name=f"uq_{entity}_asset_pointer_authority"),
            ),
            indexes=(
                (f"ix_{entity}_asset_pointers_authority", ["authority_id"], False),
                (f"ix_{entity}_asset_pointers_version", ["version_id"], False),
                (f"ix_{entity}_asset_pointers_fingerprint", ["fingerprint"], False),
            ),
        )

    _create_table(
        bind,
        "shot_asset_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("authority_id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("binding_fingerprint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        _timestamp("created_at"),
        constraints=(
            sa.ForeignKeyConstraint(
                ["storyboard_shot_id"],
                ["storyboard_shots.id"],
                name="fk_shot_asset_binding_storyboard_shot",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["authority_id"],
                ["production_asset_authority_registry.authority_id"],
                name="fk_shot_asset_binding_authority",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["authority_id", "version_id"],
                ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
                name="fk_shot_asset_binding_version",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "storyboard_shot_id",
                "asset_type",
                "authority_id",
                "version_id",
                name="uq_shot_asset_binding_identity",
            ),
            sa.UniqueConstraint("binding_fingerprint", name="uq_shot_asset_binding_fingerprint"),
            sa.CheckConstraint(
                "asset_type IN ('CHARACTER','SCENE','PROP')",
                name="ck_shot_asset_binding_type",
            ),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_asset_binding_status"),
        ),
        indexes=(
            ("ix_shot_asset_bindings_shot", ["storyboard_shot_id"], False),
            ("ix_shot_asset_bindings_authority", ["authority_id"], False),
            ("ix_shot_asset_bindings_version", ["version_id"], False),
            ("ix_shot_asset_bindings_type_status", ["asset_type", "status"], False),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Drop dependants first so PostgreSQL and SQLite enforce the same rollback
    # ordering.  No legacy/reference table is touched by this migration.
    for table in (
        "shot_asset_bindings",
        "character_asset_pointers",
        "scene_asset_pointers",
        "prop_asset_pointers",
        "character_asset_authorities",
        "scene_asset_authorities",
        "prop_asset_authorities",
        "character_asset_versions",
        "scene_asset_versions",
        "prop_asset_versions",
        "production_asset_version_registry",
        "production_asset_authority_registry",
    ):
        _drop_table(bind, table)
