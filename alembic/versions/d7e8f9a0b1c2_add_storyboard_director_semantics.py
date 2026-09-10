"""persist storyboard director semantics

Revision ID: d7e8f9a0b1c2
Revises: c6f7a8b9c0d1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import json


revision = "d7e8f9a0b1c2"
down_revision = "c6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "storyboard_shots" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("storyboard_shots")}
    if "camera_speed" not in columns:
        op.add_column(
            "storyboard_shots",
            sa.Column("camera_speed", sa.String(), nullable=False, server_default="slow"),
        )
    if "shot_purpose" not in columns:
        op.add_column(
            "storyboard_shots",
            sa.Column("shot_purpose", sa.String(), nullable=False, server_default="emotion"),
        )
    if "emotion_arc" not in columns:
        op.add_column(
            "storyboard_shots",
            sa.Column("emotion_arc", sa.Text(), nullable=False, server_default="{}"),
        )

    # Preserve semantics already written into the legacy structured_shot JSON.
    # This is deliberately a data-preserving backfill: existing non-default
    # column values remain authoritative and malformed JSON is ignored.
    rows = op.get_bind().execute(
        sa.text("SELECT id, meta_info, camera_speed, shot_purpose, emotion_arc FROM storyboard_shots")
    ).mappings()
    for row in rows:
        try:
            meta = json.loads(row["meta_info"] or "{}")
            structured = meta.get("structured_shot", {}) if isinstance(meta, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(structured, dict):
            continue
        values = {}
        if (not row["camera_speed"] or row["camera_speed"] == "slow") and structured.get("camera_speed"):
            values["camera_speed"] = str(structured["camera_speed"]).strip()
        if (not row["shot_purpose"] or row["shot_purpose"] == "emotion") and structured.get("shot_purpose"):
            values["shot_purpose"] = str(structured["shot_purpose"]).strip()
        if (not row["emotion_arc"] or row["emotion_arc"] == "{}") and isinstance(structured.get("emotion_arc"), dict):
            values["emotion_arc"] = json.dumps(structured["emotion_arc"], ensure_ascii=False)
        if values:
            assignments = ", ".join(f":{key} = :{key}" for key in values)
            params = {"id": row["id"], **values}
            op.get_bind().execute(
                sa.text(f"UPDATE storyboard_shots SET {', '.join(f'{key} = :{key}' for key in values)} WHERE id = :id"),
                params,
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "storyboard_shots" not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns("storyboard_shots")}
    for name in ("emotion_arc", "shot_purpose", "camera_speed"):
        if name in columns:
            op.drop_column("storyboard_shots", name)
