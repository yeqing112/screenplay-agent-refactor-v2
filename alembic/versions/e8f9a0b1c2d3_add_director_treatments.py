"""add independent DirectorTreatment creative layer"""

from alembic import op
import sqlalchemy as sa


revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "director_treatments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("scene_name", sa.String(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("source_script_revision", sa.String(), nullable=False, server_default=""),
        sa.Column("source_script_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("dramatic_objective", sa.Text(), nullable=False, server_default=""),
        sa.Column("audience_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("character_intents", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("beat_map", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("relationship_power_shift", sa.Text(), nullable=False, server_default=""),
        sa.Column("audience_emotion", sa.Text(), nullable=False, server_default=""),
        sa.Column("information_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("performance_direction", sa.Text(), nullable=False, server_default=""),
        sa.Column("visual_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("coverage_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("sound_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("edit_rhythm", sa.Text(), nullable=False, server_default=""),
        sa.Column("constraints", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unknowns", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("skill_id", sa.String(), nullable=False, server_default=""),
        sa.Column("skill_version", sa.String(), nullable=False, server_default=""),
        sa.Column("decision_packet_id", sa.Integer(), nullable=True),
        sa.Column("model_info", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("prompt_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_director_treatments_book_id", "director_treatments", ["book_id"])
    op.create_index("ix_director_treatments_episode", "director_treatments", ["episode"])


def downgrade() -> None:
    op.drop_index("ix_director_treatments_episode", table_name="director_treatments")
    op.drop_index("ix_director_treatments_book_id", table_name="director_treatments")
    op.drop_table("director_treatments")
