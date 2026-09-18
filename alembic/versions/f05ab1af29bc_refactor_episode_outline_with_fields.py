"""refactor_episode_outline_with_fields

Revision ID: f05ab1af29bc
Revises: c84a783f96d7
Create Date: 2026-06-14 21:35:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "f05ab1af29bc"
down_revision: Union[str, Sequence[str], None] = "c84a783f96d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add outline fields without destroying legacy ``content`` rows.

    ``f05`` was originally generated as a drop-and-recreate migration.  That
    is unsafe both on a fresh database (the table may not exist yet) and on a
    legacy database (the old content is lost).  This implementation is
    deliberately additive and can safely be replayed against either shape.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    target_columns = {
        "genre": sa.Column("genre", sa.String(length=50), nullable=True, server_default="short_drama"),
        "episode": sa.Column("episode", sa.Integer(), nullable=False, server_default="0"),
        "title": sa.Column("title", sa.String(), nullable=True, server_default=""),
        "core_event": sa.Column("core_event", sa.Text(), nullable=True, server_default=""),
        "opening_hook": sa.Column("opening_hook", sa.Text(), nullable=True, server_default=""),
        "core_conflict": sa.Column("core_conflict", sa.Text(), nullable=True, server_default=""),
        "climax": sa.Column("climax", sa.Text(), nullable=True, server_default=""),
        "ending_hook": sa.Column("ending_hook", sa.Text(), nullable=True, server_default=""),
        "characters": sa.Column("characters", sa.Text(), nullable=True, server_default=""),
        "scenes": sa.Column("scenes", sa.Text(), nullable=True, server_default=""),
        "is_fixed": sa.Column("is_fixed", sa.Integer(), nullable=False, server_default="0", comment="是否为改编方案锁定的固定纲次"),
        "raw_content": sa.Column("raw_content", sa.Text(), nullable=True, server_default=""),
    }

    if "episode_outlines" not in tables:
        op.create_table(
            "episode_outlines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("book_id", sa.Integer(), nullable=False),
            *target_columns.values(),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        return

    existing = {column["name"] for column in inspect(bind).get_columns("episode_outlines")}
    had_legacy_content = "content" in existing
    for name, column in target_columns.items():
        if name not in existing:
            op.add_column("episode_outlines", column)

    # Keep the legacy column for compatibility, and copy its payload into the
    # explicit raw_content field.  The predicate makes a replay idempotent and
    # never overwrites an already curated raw_content value.
    if had_legacy_content and "raw_content" not in existing:
        bind.execute(text(
            "UPDATE episode_outlines "
            "SET raw_content = content "
            "WHERE (raw_content IS NULL OR raw_content = '') "
            "AND content IS NOT NULL"
        ))


def downgrade() -> None:
    # Removing the structured fields would be lossy for upgraded legacy rows.
    # Keep the data intact and make the policy explicit to callers.
    raise NotImplementedError(
        "f05ab1af29bc downgrade is intentionally unsupported: it would lose "
        "structured outline fields and cannot be made lossless."
    )
