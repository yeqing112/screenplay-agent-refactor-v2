"""add additive SceneBlocking V2 payload and runtime repair ledger"""

from alembic import op
import sqlalchemy as sa


revision = "n7h8i9j0k1l2"
down_revision = "m6g7h8i9j0k1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, default in (
        ("schema_version", "scene_blocking_v1"),
        ("spatial_model", "{}"),
        ("source_spatial_facts", "[]"),
        ("creative_decisions", "[]"),
        ("derived_constraints", "{}"),
        ("unresolved_facts", "[]"),
        ("camera_axis", "{}"),
        ("validation", "{}"),
    ):
        op.add_column("scene_blockings", sa.Column(name, sa.Text() if name != "schema_version" else sa.String(), nullable=False, server_default=default))
    op.create_table(
        "repair_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_code", sa.String(), nullable=False, server_default=""),
        sa.Column("target_layer", sa.String(), nullable=False, server_default=""),
        sa.Column("target_id", sa.String(), nullable=False, server_default=""),
        sa.Column("book_id", sa.Integer(), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("scene_id", sa.String(), nullable=True, server_default=""),
        sa.Column("shot_id", sa.String(), nullable=True, server_default=""),
        sa.Column("before_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("repair_operation", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revalidation_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("revalidation_details", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("model", sa.String(), nullable=False, server_default=""),
        sa.Column("prompt_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_repair_attempts_book_id", "repair_attempts", ["book_id"])
    op.create_index("ix_repair_attempts_episode", "repair_attempts", ["episode"])


def downgrade() -> None:
    op.drop_index("ix_repair_attempts_episode", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_book_id", table_name="repair_attempts")
    op.drop_table("repair_attempts")
    for name in ("validation", "camera_axis", "unresolved_facts", "derived_constraints", "creative_decisions", "source_spatial_facts", "spatial_model", "schema_version"):
        op.drop_column("scene_blockings", name)
