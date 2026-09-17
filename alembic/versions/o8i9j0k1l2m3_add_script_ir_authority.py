"""add ScriptIR production authority envelope fields"""

from alembic import op
import sqlalchemy as sa

revision = "o8i9j0k1l2m3"
down_revision = "n7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("script_ir_versions", sa.Column("authority_envelope_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("script_ir_versions", sa.Column("qualification_state", sa.String(), nullable=False, server_default="STRUCTURALLY_VALID"))
    op.add_column("script_ir_versions", sa.Column("stale_status", sa.String(), nullable=False, server_default="UNKNOWN"))
    op.add_column("script_ir_versions", sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("script_ir_versions", "stale_reasons")
    op.drop_column("script_ir_versions", "stale_status")
    op.drop_column("script_ir_versions", "qualification_state")
    op.drop_column("script_ir_versions", "authority_envelope_json")
