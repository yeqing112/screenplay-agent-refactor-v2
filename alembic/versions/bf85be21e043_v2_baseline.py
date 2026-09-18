"""v2 baseline

Revision ID: bf85be21e043
Revises: 
Create Date: 2026-06-12 15:48:21.668494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf85be21e043"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the schema that existed at the baseline revision.

    This migration is intentionally self contained.  It must not import the
    current ORM package: doing so would make a historical revision depend on
    today's model metadata and could silently change a fresh install after a
    future model edit.
    """
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("chapter_count", sa.Integer(), nullable=True),
        sa.Column("total_words", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("character_table", sa.Text(), nullable=True),
        sa.Column("events", sa.Text(), nullable=True),
        sa.Column("scenes", sa.Text(), nullable=True),
        sa.Column("foreshadowing", sa.Text(), nullable=True),
        sa.Column("appearance_fragments", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "book_bibles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id"),
    )
    op.create_table(
        "character_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("age_range", sa.String(length=50), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("identity", sa.String(length=200), nullable=True),
        sa.Column("face_shape", sa.String(length=50), nullable=True),
        sa.Column("facial_features", sa.Text(), nullable=True),
        sa.Column("body_type", sa.String(length=100), nullable=True),
        sa.Column("skin_tone", sa.String(length=50), nullable=True),
        sa.Column("distinguishing_marks", sa.Text(), nullable=True),
        sa.Column("nationality", sa.String(length=50), nullable=True),
        sa.Column("precise_age", sa.Integer(), nullable=True),
        sa.Column("style_era", sa.String(length=100), nullable=True),
        sa.Column("signature_outfit", sa.Text(), nullable=True),
        sa.Column("accessories", sa.Text(), nullable=True),
        sa.Column("hairstyle", sa.Text(), nullable=True),
        sa.Column("temperament", sa.Text(), nullable=True),
        sa.Column("vibe", sa.String(length=100), nullable=True),
        sa.Column("color_palette", sa.Text(), nullable=True),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("speech_style", sa.Text(), nullable=True),
        sa.Column("body_language", sa.Text(), nullable=True),
        sa.Column("relationships", sa.Text(), nullable=True),
        sa.Column("visual_prompt_en", sa.Text(), nullable=True),
        sa.Column("visual_prompt_zh", sa.Text(), nullable=True),
        sa.Column("core_prompt_en", sa.Text(), nullable=True),
        sa.Column("core_prompt_zh", sa.Text(), nullable=True),
        sa.Column("outfit_prompt_en", sa.Text(), nullable=True),
        sa.Column("outfit_prompt_zh", sa.Text(), nullable=True),
        sa.Column("scene_prompt_en", sa.Text(), nullable=True),
        sa.Column("scene_prompt_zh", sa.Text(), nullable=True),
        sa.Column("chapter_range", sa.String(length=255), nullable=True),
        sa.Column("importance", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "character_stages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("character_name", sa.String(length=100), nullable=False),
        sa.Column("stage_name", sa.String(length=100), nullable=False),
        sa.Column("chapter_start", sa.Integer(), nullable=False),
        sa.Column("chapter_end", sa.Integer(), nullable=False),
        sa.Column("timeline", sa.String(length=100), nullable=True),
        sa.Column("identity", sa.String(length=200), nullable=True),
        sa.Column("age_description", sa.String(length=100), nullable=True),
        sa.Column("face_shape", sa.String(length=50), nullable=True),
        sa.Column("facial_features", sa.Text(), nullable=True),
        sa.Column("body_type", sa.String(length=100), nullable=True),
        sa.Column("skin_tone", sa.String(length=50), nullable=True),
        sa.Column("distinguishing_marks", sa.Text(), nullable=True),
        sa.Column("signature_outfit", sa.Text(), nullable=True),
        sa.Column("accessories", sa.Text(), nullable=True),
        sa.Column("hair_style", sa.Text(), nullable=True),
        sa.Column("makeup_spec", sa.Text(), nullable=True),
        sa.Column("temperament", sa.Text(), nullable=True),
        sa.Column("vibe", sa.String(length=100), nullable=True),
        sa.Column("color_palette", sa.Text(), nullable=True),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("speech_style", sa.Text(), nullable=True),
        sa.Column("body_language", sa.Text(), nullable=True),
        sa.Column("visual_prompt_en", sa.Text(), nullable=True),
        sa.Column("visual_prompt_zh", sa.Text(), nullable=True),
        sa.Column("core_prompt_en", sa.Text(), nullable=True),
        sa.Column("core_prompt_zh", sa.Text(), nullable=True),
        sa.Column("outfit_prompt_en", sa.Text(), nullable=True),
        sa.Column("outfit_prompt_zh", sa.Text(), nullable=True),
        sa.Column("scene_prompt_en", sa.Text(), nullable=True),
        sa.Column("scene_prompt_zh", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # f05ab1af29bc is the historical episode-outline refactor.  The baseline
    # deliberately keeps the pre-refactor content column so the refactor can
    # migrate legacy rows without data loss.
    op.create_table(
        "episode_outlines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scripts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("genre", sa.String(length=50), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "qa_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "kv",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "storyboard_shots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("scene_name", sa.String(), nullable=False),
        sa.Column("shot_id", sa.Integer(), nullable=False),
        sa.Column("dialogue", sa.Text(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("camera_angle", sa.String(), nullable=True),
        sa.Column("camera_movement", sa.String(), nullable=True),
        sa.Column("transition", sa.String(), nullable=True),
        sa.Column("lighting", sa.Text(), nullable=True),
        sa.Column("sound_effects", sa.Text(), nullable=True),
        sa.Column("bgm_mood", sa.String(), nullable=True),
        sa.Column("start_state", sa.Text(), nullable=True),
        sa.Column("action_process", sa.Text(), nullable=True),
        sa.Column("end_state", sa.Text(), nullable=True),
        sa.Column("visual_prompt_static", sa.Text(), nullable=True),
        sa.Column("visual_prompt_motion", sa.Text(), nullable=True),
        sa.Column("visual_prompt_final", sa.Text(), nullable=True),
        sa.Column("asset_links", sa.Text(), nullable=True),
        sa.Column("asset_status", sa.String(), nullable=True),
        sa.Column("meta_info", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop only the tables owned by this baseline revision."""
    for table in (
        "storyboard_shots",
        "kv",
        "qa_results",
        "scripts",
        "episode_outlines",
        "character_stages",
        "character_profiles",
        "book_bibles",
        "chapters",
        "books",
    ):
        op.drop_table(table)
