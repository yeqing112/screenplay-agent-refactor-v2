"""Allow the same canonical entity key in more than one Book.

Production Asset authority ids and fingerprints include ``book_id``.  The
entity key is therefore scoped by its authority and cannot be globally unique
when two disposable projects use the same scene or character ids.
"""

from alembic import op


revision = "p1q2r3s4t5u6"
down_revision = "o6j7k8l9m0n1"
branch_labels = None
depends_on = None


_TABLE_CONSTRAINTS = {
    "character_asset_authorities": "uq_character_asset_authority_entity",
    "character_asset_pointers": "uq_character_asset_pointer_entity",
    "scene_asset_authorities": "uq_scene_asset_authority_entity",
    "scene_asset_pointers": "uq_scene_asset_pointer_entity",
    "prop_asset_authorities": "uq_prop_asset_authority_entity",
    "prop_asset_pointers": "uq_prop_asset_pointer_entity",
}


def upgrade() -> None:
    # SQLite recreates the table in batch mode, preserving the FK graph while
    # removing only the entity-level unique constraint.  Authority and
    # fingerprint uniqueness remain canonical identity guards.
    for table, constraint in _TABLE_CONSTRAINTS.items():
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(constraint, type_="unique")


def downgrade() -> None:
    for table, constraint in _TABLE_CONSTRAINTS.items():
        with op.batch_alter_table(table, recreate="always") as batch:
            columns = {
                "character_asset_authorities": "character_id",
                "character_asset_pointers": "character_id",
                "scene_asset_authorities": "scene_id",
                "scene_asset_pointers": "scene_id",
                "prop_asset_authorities": "prop_id",
                "prop_asset_pointers": "prop_id",
            }
            batch.create_unique_constraint(constraint, [columns[table]])
