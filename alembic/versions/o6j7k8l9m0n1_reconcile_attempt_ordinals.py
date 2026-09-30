"""Reconcile Retry and Regenerate business ordinals and uniqueness."""

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "o6j7k8l9m0n1"
down_revision = "n5i6j7k8l9m0"
branch_labels = None
depends_on = None


def _fingerprint(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _regenerate_key(row) -> str:
    return _fingerprint({
        "schema_version": "regenerate_variant_key_v1",
        "book_id": int(row["book_id"]), "episode": int(row["episode"]),
        "storyboard_shot_id": int(row["storyboard_shot_id"]),
        "target_media": str(row["target_media"] or "").upper(),
        "variant_index": int(row["variant_index"]),
    })


def _retry_key(row) -> str:
    return _fingerprint({
        "schema_version": "retry_attempt_key_v1",
        "root_execution_id": str(row["root_execution_id"]),
        "attempt_number": int(row["attempt_number"]),
    })


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    table = "generation_execution_attempt_lineages"
    if table not in tables:
        raise RuntimeError(f"required table is missing: {table}")
    columns = {item["name"] for item in inspector.get_columns(table)}
    if "regenerate_variant_key" not in columns:
        op.add_column(table, sa.Column("regenerate_variant_key", sa.String(), nullable=True))
    if "retry_attempt_key" not in columns:
        op.add_column(table, sa.Column("retry_attempt_key", sa.String(), nullable=True))

    # This is a deterministic semantic correction, not a fabricated history:
    # old Retry rows already represent business retries and their variant lane
    # must be zero.  Identity, lineage ID, and confirmation hashes are kept.
    op.execute(text("UPDATE generation_execution_attempt_lineages SET variant_index = 0 WHERE operation_kind = 'RETRY' AND variant_index <> 0"))

    rows = bind.execute(text(
        "SELECT id, operation_kind, book_id, episode, storyboard_shot_id, target_media, "
        "root_execution_id, attempt_number, variant_index FROM generation_execution_attempt_lineages ORDER BY id"
    )).mappings().all()
    regenerate_keys: dict[str, int] = {}
    retry_keys: dict[str, int] = {}
    updates: list[tuple[int, str | None, str | None]] = []
    for row in rows:
        kind = str(row["operation_kind"] or "").upper()
        regenerate_key = _regenerate_key(row) if kind == "REGENERATE" else None
        retry_key = _retry_key(row) if kind == "RETRY" else None
        if regenerate_key:
            if regenerate_key in regenerate_keys:
                raise RuntimeError(f"duplicate regenerate variant sequence: rows {regenerate_keys[regenerate_key]} and {row['id']}")
            regenerate_keys[regenerate_key] = int(row["id"])
        if retry_key:
            if retry_key in retry_keys:
                raise RuntimeError(f"duplicate retry ordinal sequence: rows {retry_keys[retry_key]} and {row['id']}")
            retry_keys[retry_key] = int(row["id"])
        updates.append((int(row["id"]), regenerate_key, retry_key))
    for row_id, regenerate_key, retry_key in updates:
        bind.execute(text(
            "UPDATE generation_execution_attempt_lineages "
            "SET regenerate_variant_key = :regenerate_key, retry_attempt_key = :retry_key WHERE id = :id"
        ), {"id": row_id, "regenerate_key": regenerate_key, "retry_key": retry_key})

    # Nullable unique indexes allow unlimited Retry/Regenerate NULL lanes for
    # the other operation kind while protecting every populated business key.
    inspector = inspect(bind)
    index_names = {item["name"] for item in inspector.get_indexes(table)}
    if "uq_generation_attempt_regenerate_variant_key" not in index_names:
        op.create_index("uq_generation_attempt_regenerate_variant_key", table, ["regenerate_variant_key"], unique=True)
    if "uq_generation_attempt_retry_attempt_key" not in index_names:
        op.create_index("uq_generation_attempt_retry_attempt_key", table, ["retry_attempt_key"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    table = "generation_execution_attempt_lineages"
    if table not in set(inspect(bind).get_table_names()):
        return
    indexes = {item["name"] for item in inspect(bind).get_indexes(table)}
    if "uq_generation_attempt_retry_attempt_key" in indexes:
        op.drop_index("uq_generation_attempt_retry_attempt_key", table_name=table)
    if "uq_generation_attempt_regenerate_variant_key" in indexes:
        op.drop_index("uq_generation_attempt_regenerate_variant_key", table_name=table)
    columns = {item["name"] for item in inspect(bind).get_columns(table)}
    if "retry_attempt_key" in columns:
        op.drop_column(table, "retry_attempt_key")
    if "regenerate_variant_key" in columns:
        op.drop_column(table, "regenerate_variant_key")
