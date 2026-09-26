"""Add media-scoped PromptIR current pointers.

The pointer scope is derived from the immutable PromptIR payload.  This
migration intentionally does not add target_media to PromptIRVersion or
PromptIRAuthority and does not touch any execution/media tables.
"""

from __future__ import annotations

import json
import hashlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _prompt_ir_payload_basis(prompt_ir: dict) -> dict:
    payload = dict(prompt_ir) if isinstance(prompt_ir, dict) else {}
    payload.pop("prompt_ir_payload_fingerprint", None)
    payload.pop("payload_hash", None)
    return payload


def fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

TABLE = "prompt_ir_pointers"
CHECK_NAME = "ck_prompt_ir_pointer_target_media"
UNIQUE_NAME = "uq_prompt_ir_pointer_media_scope"
OLD_DOWNGRADE_CODE = "PROMPT_IR_POINTER_DOWNGRADE_CARDINALITY_CONFLICT"

REVIEW_STATE_SQL = "'GENERATED','NORMALIZED','AI_VALIDATED','HUMAN_REVIEW_PENDING','HUMAN_APPROVED','PRODUCTION_READY','ARCHIVED','REJECTED','REQUEST_CHANGE'"
REVIEWER_TYPE_SQL = "'DIRECTOR','ART_DIRECTOR','PRODUCER','SYSTEM'"
REVIEW_DECISION_SQL = "'APPROVE','REJECT','REQUEST_CHANGE'"


def _timestamp(name: str):
    return sa.Column(name, sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))


def _create_review_tables(bind) -> None:
    """Create the append-only human review layer at the canonical head.

    This remains in the existing canonical head migration so databases and
    historical tests that intentionally pin ``b2c3d4e5f6g7`` receive the new
    governance tables without changing the established migration identity.
    """
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "production_asset_reviews" not in tables:
        op.create_table(
            "production_asset_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("review_id", sa.String(), nullable=False),
            sa.Column("asset_type", sa.String(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("asset_version_id", sa.String(), nullable=False),
            sa.Column("prompt_lineage_id", sa.String(), nullable=True),
            sa.Column("review_state", sa.String(), nullable=False),
            sa.Column("reviewer_type", sa.String(), nullable=False),
            sa.Column("decision", sa.String(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("version_fingerprint", sa.String(), nullable=True),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.ForeignKeyConstraint(["asset_version_id"], ["production_asset_version_registry.version_id"], name="fk_production_asset_review_version", ondelete="RESTRICT"),
            sa.UniqueConstraint("review_id", name="uq_production_asset_review_id"),
            sa.CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_production_asset_review_asset_type"),
            sa.CheckConstraint(f"review_state IN ({REVIEW_STATE_SQL})", name="ck_production_asset_review_state"),
            sa.CheckConstraint(f"reviewer_type IN ({REVIEWER_TYPE_SQL})", name="ck_production_asset_review_reviewer_type"),
            sa.CheckConstraint(f"decision IS NULL OR decision IN ({REVIEW_DECISION_SQL})", name="ck_production_asset_review_decision"),
        )
        op.create_index("ix_production_asset_reviews_review_id", "production_asset_reviews", ["review_id"], unique=True)
        op.create_index("ix_production_asset_reviews_asset_type", "production_asset_reviews", ["asset_type"])
        op.create_index("ix_production_asset_reviews_asset_id", "production_asset_reviews", ["asset_id"])
        op.create_index("ix_production_asset_reviews_asset_version_id", "production_asset_reviews", ["asset_version_id"])
        op.create_index("ix_production_asset_reviews_review_state", "production_asset_reviews", ["review_state"])
    if "production_asset_review_history" not in tables:
        op.create_table(
            "production_asset_review_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("history_id", sa.String(), nullable=False),
            sa.Column("review_id", sa.String(), nullable=False),
            sa.Column("asset_version_id", sa.String(), nullable=False),
            sa.Column("from_state", sa.String(), nullable=True),
            sa.Column("to_state", sa.String(), nullable=False),
            sa.Column("actor", sa.String(), nullable=False),
            sa.Column("decision", sa.String(), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            _timestamp("created_at"),
            sa.ForeignKeyConstraint(["review_id"], ["production_asset_reviews.review_id"], name="fk_production_asset_review_history_review", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["asset_version_id"], ["production_asset_version_registry.version_id"], name="fk_production_asset_review_history_version", ondelete="RESTRICT"),
            sa.UniqueConstraint("history_id", name="uq_production_asset_review_history_id"),
            sa.CheckConstraint(f"from_state IS NULL OR from_state IN ({REVIEW_STATE_SQL})", name="ck_production_asset_review_history_from_state"),
            sa.CheckConstraint(f"to_state IN ({REVIEW_STATE_SQL})", name="ck_production_asset_review_history_to_state"),
            sa.CheckConstraint(f"actor IN ({REVIEWER_TYPE_SQL})", name="ck_production_asset_review_history_actor"),
            sa.CheckConstraint(f"decision IS NULL OR decision IN ({REVIEW_DECISION_SQL})", name="ck_production_asset_review_history_decision"),
        )
        op.create_index("ix_production_asset_review_history_history_id", "production_asset_review_history", ["history_id"], unique=True)
        op.create_index("ix_production_asset_review_history_review_id", "production_asset_review_history", ["review_id"])
        op.create_index("ix_production_asset_review_history_asset_version_id", "production_asset_review_history", ["asset_version_id"])


def _drop_review_tables(bind) -> None:
    tables = set(inspect(bind).get_table_names())
    if "production_asset_review_history" in tables:
        op.drop_table("production_asset_review_history")
    if "production_asset_reviews" in tables:
        op.drop_table("production_asset_reviews")


def _create_prompt_lineage_tables(bind) -> None:
    """Create the append-only Prompt -> Intent -> Asset lineage layer."""
    tables = set(inspect(bind).get_table_names())
    if "production_prompt_versions" not in tables:
        op.create_table(
            "production_prompt_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("prompt_version_id", sa.String(), nullable=False),
            sa.Column("prompt_id", sa.String(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("prompt_text", sa.Text(), nullable=False),
            sa.Column("prompt_structure", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("prompt_fingerprint", sa.String(), nullable=False),
            sa.Column("created_from", sa.String(), nullable=False),
            _timestamp("created_at"),
            sa.UniqueConstraint("prompt_version_id", name="uq_production_prompt_version_id"),
            sa.UniqueConstraint("prompt_id", "version_number", name="uq_production_prompt_version_number"),
            sa.CheckConstraint("version_number > 0", name="ck_production_prompt_version_positive"),
        )
        op.create_index("ix_production_prompt_versions_prompt_version_id", "production_prompt_versions", ["prompt_version_id"], unique=True)
        op.create_index("ix_production_prompt_versions_prompt_id", "production_prompt_versions", ["prompt_id"])
        op.create_index("ix_production_prompt_versions_prompt_fingerprint", "production_prompt_versions", ["prompt_fingerprint"])
    if "production_generation_intents" not in tables:
        op.create_table(
            "production_generation_intents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("generation_intent_id", sa.String(), nullable=False),
            sa.Column("shot_id", sa.Integer(), nullable=False),
            sa.Column("character_requirements", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("scene_requirements", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("camera_requirements", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("style_requirements", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("constraint_snapshot", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("shot_requirement_snapshot", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("shot_requirement_fingerprint", sa.String(), nullable=False),
            _timestamp("created_at"),
            sa.ForeignKeyConstraint(["shot_id"], ["storyboard_shots.id"], name="fk_production_generation_intent_shot", ondelete="RESTRICT"),
            sa.UniqueConstraint("generation_intent_id", name="uq_production_generation_intent_id"),
        )
        op.create_index("ix_production_generation_intents_generation_intent_id", "production_generation_intents", ["generation_intent_id"], unique=True)
        op.create_index("ix_production_generation_intents_shot_id", "production_generation_intents", ["shot_id"])
        op.create_index("ix_production_generation_intents_shot_requirement_fingerprint", "production_generation_intents", ["shot_requirement_fingerprint"])
    if "production_prompt_lineages" not in tables:
        op.create_table(
            "production_prompt_lineages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("prompt_lineage_id", sa.String(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("asset_version_id", sa.String(), nullable=False),
            sa.Column("shot_id", sa.Integer(), nullable=False),
            sa.Column("prompt_version_id", sa.String(), nullable=False),
            sa.Column("generation_intent_id", sa.String(), nullable=False),
            sa.Column("prompt_fingerprint", sa.String(), nullable=False),
            _timestamp("created_at"),
            sa.ForeignKeyConstraint(["asset_version_id"], ["production_asset_version_registry.version_id"], name="fk_production_prompt_lineage_asset_version", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["shot_id"], ["storyboard_shots.id"], name="fk_production_prompt_lineage_shot", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["prompt_version_id"], ["production_prompt_versions.prompt_version_id"], name="fk_production_prompt_lineage_prompt_version", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["generation_intent_id"], ["production_generation_intents.generation_intent_id"], name="fk_production_prompt_lineage_intent", ondelete="RESTRICT"),
            sa.UniqueConstraint("prompt_lineage_id", name="uq_production_prompt_lineage_id"),
            sa.UniqueConstraint("asset_version_id", "prompt_version_id", "generation_intent_id", name="uq_production_prompt_lineage_edge"),
        )
        for name, column in (
            ("prompt_lineage_id", "prompt_lineage_id"),
            ("asset_id", "asset_id"),
            ("asset_version_id", "asset_version_id"),
            ("shot_id", "shot_id"),
            ("prompt_version_id", "prompt_version_id"),
            ("generation_intent_id", "generation_intent_id"),
            ("prompt_fingerprint", "prompt_fingerprint"),
        ):
            op.create_index(f"ix_production_prompt_lineages_{name}", "production_prompt_lineages", [column], unique=(name == "prompt_lineage_id"))


def _drop_prompt_lineage_tables(bind) -> None:
    tables = set(inspect(bind).get_table_names())
    if "production_prompt_lineages" in tables:
        op.drop_table("production_prompt_lineages")
    if "production_generation_intents" in tables:
        op.drop_table("production_generation_intents")
    if "production_prompt_versions" in tables:
        op.drop_table("production_prompt_versions")


def _columns(*, include_target: bool, legacy_unique: bool = False) -> sa.Table:
    metadata = sa.MetaData()
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("storyboard_shot_id", sa.Integer(), nullable=False, unique=legacy_unique),
    ]
    if include_target:
        columns.append(sa.Column("target_media", sa.String(), nullable=False))
    columns.extend(
        [
            sa.Column("prompt_ir_version_id", sa.Integer(), nullable=False),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="PROMPT_IR_QUALIFIED"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        ]
    )
    table = sa.Table(TABLE, metadata, *columns)
    if include_target:
        table.append_constraint(sa.CheckConstraint("target_media IN ('IMAGE','VIDEO')", name=CHECK_NAME))
        table.append_constraint(
            sa.UniqueConstraint("book_id", "episode", "storyboard_shot_id", "target_media", name=UNIQUE_NAME)
        )
    sa.Index("ix_prompt_ir_pointers_book_episode", table.c.book_id, table.c.episode)
    sa.Index("ix_prompt_ir_pointers_shot", table.c.storyboard_shot_id)
    return table


def _preflight(bind) -> list[dict[str, object]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT p.id, p.book_id, p.episode, p.storyboard_shot_id,
                   p.prompt_ir_version_id, p.payload_hash AS pointer_payload_hash,
                   v.book_id AS version_book_id, v.episode AS version_episode,
                   v.storyboard_shot_id AS version_shot_id,
                   v.payload_json, v.payload_hash AS version_payload_hash
              FROM prompt_ir_pointers AS p
              LEFT JOIN prompt_ir_versions AS v ON v.id = p.prompt_ir_version_id
             ORDER BY p.id
            """
        )
    ).mappings().all()
    derived: list[dict[str, object]] = []
    seen: set[tuple[int, int, int, str]] = set()
    for row in rows:
        prefix = f"pointer_id={row['id']}"
        if row["version_book_id"] is None:
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: {prefix} pointed PromptIRVersion is missing")
        identity = (int(row["book_id"]), int(row["episode"]), int(row["storyboard_shot_id"]))
        version_identity = (int(row["version_book_id"]), int(row["version_episode"]), int(row["version_shot_id"]))
        if identity != version_identity:
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: {prefix} pointer/version scope mismatch")
        if str(row["pointer_payload_hash"] or "") != str(row["version_payload_hash"] or ""):
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: {prefix} pointer/version payload hash mismatch")
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: {prefix} payload JSON is invalid") from exc
        if not isinstance(payload, dict) or fingerprint(_prompt_ir_payload_basis(payload)) != str(row["version_payload_hash"] or ""):
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: {prefix} PromptIR payload hash is invalid")
        policy = payload.get("generation_policy")
        target = policy.get("target_media") if isinstance(policy, dict) else None
        if target not in {"IMAGE", "VIDEO"}:
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: {prefix} generation_policy.target_media must be IMAGE or VIDEO")
        scope = (*identity, str(target))
        if scope in seen:
            raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_BLOCKED: duplicate derived scope {scope!r}")
        seen.add(scope)
        derived.append({"id": int(row["id"]), "target_media": str(target)})
    return derived


def _verify_upgrade(bind, expected_count: int) -> None:
    inspector = inspect(bind)
    columns = {item["name"]: item for item in inspector.get_columns(TABLE)}
    if "target_media" not in columns or bool(columns["target_media"].get("nullable")):
        raise RuntimeError("PROMPT_IR_POINTER_MIGRATION_VERIFY_FAILED: target_media is not NOT NULL")
    unique_names = {item.get("name") for item in inspector.get_unique_constraints(TABLE)}
    if UNIQUE_NAME not in unique_names:
        raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_VERIFY_FAILED: missing {UNIQUE_NAME}")
    index_names = {item.get("name") for item in inspector.get_indexes(TABLE)}
    if not {"ix_prompt_ir_pointers_book_episode", "ix_prompt_ir_pointers_shot"}.issubset(index_names):
        raise RuntimeError("PROMPT_IR_POINTER_MIGRATION_VERIFY_FAILED: required pointer indexes are missing")
    count = int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one())
    if count != expected_count:
        raise RuntimeError(f"PROMPT_IR_POINTER_MIGRATION_VERIFY_FAILED: row count changed {expected_count} -> {count}")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in set(inspector.get_table_names()):
        return

    # Validate every row before any DDL.  Raising here leaves the old schema
    # untouched even on SQLite.
    derived = _preflight(bind)
    before_count = len(derived)
    op.add_column(TABLE, sa.Column("target_media", sa.String(), nullable=True))
    for item in derived:
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET target_media = :target_media WHERE id = :id"),
            {"target_media": item["target_media"], "id": item["id"]},
        )

    # Recreate the table because the old storyboard_shot_id unique is an
    # unnamed SQLite autoindex and cannot be dropped by constraint name.
    copy = _columns(include_target=True)
    with op.batch_alter_table(TABLE, recreate="always", copy_from=copy):
        pass
    _verify_upgrade(bind, before_count)
    _create_review_tables(bind)
    _create_prompt_lineage_tables(bind)


def _verify_downgrade(bind, expected_count: int) -> None:
    inspector = inspect(bind)
    if "target_media" in {item["name"] for item in inspector.get_columns(TABLE)}:
        raise RuntimeError("PROMPT_IR_POINTER_DOWNGRADE_VERIFY_FAILED: target_media remains")
    count = int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one())
    if count != expected_count:
        raise RuntimeError(f"PROMPT_IR_POINTER_DOWNGRADE_VERIFY_FAILED: row count changed {expected_count} -> {count}")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in set(inspector.get_table_names()):
        return

    # This preflight must happen before any drop/rebuild operation.
    conflicts = bind.execute(
        sa.text(
            f"SELECT book_id, episode, storyboard_shot_id, COUNT(*) AS pointer_count "
            f"FROM {TABLE} GROUP BY book_id, episode, storyboard_shot_id HAVING COUNT(*) > 1"
        )
    ).mappings().all()
    if conflicts:
        raise RuntimeError(f"{OLD_DOWNGRADE_CODE}: {conflicts!r}")
    before_count = int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one())
    copy = _columns(include_target=False, legacy_unique=True)
    with op.batch_alter_table(TABLE, recreate="always", copy_from=copy):
        pass
    _verify_downgrade(bind, before_count)
    _drop_prompt_lineage_tables(bind)
    _drop_review_tables(bind)
