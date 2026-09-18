"""add versioned PromptIR authority and current pointer"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "u4d5e6f7g8h9"
down_revision = "t3c4d5e6f7g8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "prompt_ir_versions" not in tables:
        op.create_table(
            "prompt_ir_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("materialization_set_id", sa.Integer(), nullable=False),
            sa.Column("plan_shot_id", sa.String(), nullable=False),
            sa.Column("schema_version", sa.String(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("compiler_version", sa.String(), nullable=False),
            sa.Column("compiler_policy_version", sa.String(), nullable=False),
            sa.Column("retention_policy_version", sa.String(), nullable=False),
            sa.Column("authority_envelope_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="STRUCTURALLY_VALID"),
            sa.Column("asset_reference_state", sa.String(), nullable=False, server_default="ASSET_REFERENCE_PENDING"),
            sa.Column("model_generation_ready", sa.String(), nullable=False, server_default="false"),
            sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"),
            sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        for name, cols in (("book_episode", ["book_id", "episode"]), ("scene", ["scene_id"]), ("shot", ["storyboard_shot_id"]), ("materialization", ["materialization_set_id"]), ("payload", ["payload_hash"])):
            op.create_index(f"ix_prompt_ir_versions_{name}", "prompt_ir_versions", cols)

    inspector = inspect(op.get_bind())
    if "prompt_ir_authorities" not in set(inspector.get_table_names()):
        op.create_table(
            "prompt_ir_authorities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("prompt_ir_version_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("envelope_fingerprint", sa.String(), nullable=False, unique=True),
            sa.Column("envelope_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="PROMPT_IR_QUALIFIED"),
            sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"),
            sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_prompt_ir_authorities_book_episode", "prompt_ir_authorities", ["book_id", "episode"])
        op.create_index("ix_prompt_ir_authorities_shot", "prompt_ir_authorities", ["storyboard_shot_id"])

    inspector = inspect(op.get_bind())
    if "prompt_ir_pointers" not in set(inspector.get_table_names()):
        op.create_table(
            "prompt_ir_pointers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("prompt_ir_version_id", sa.Integer(), nullable=False),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="PROMPT_IR_QUALIFIED"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_prompt_ir_pointers_book_episode", "prompt_ir_pointers", ["book_id", "episode"])
        op.create_index("ix_prompt_ir_pointers_shot", "prompt_ir_pointers", ["storyboard_shot_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table in ("prompt_ir_pointers", "prompt_ir_authorities", "prompt_ir_versions"):
        if table in set(inspector.get_table_names()):
            op.drop_table(table)
