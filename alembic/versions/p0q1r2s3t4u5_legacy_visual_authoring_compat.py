"""Compatibility marker for databases left at the historical Canary revision.

The old Canary migration is intentionally not restored.  This no-op revision
only lets Alembic resolve an existing ``alembic_version`` value so the
canonical reconciliation migration can add missing columns in place.
"""

from typing import Sequence, Union


revision: str = "p0q1r2s3t4u5"
down_revision: Union[str, Sequence[str], None] = "w6f7g8h9i0j1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
