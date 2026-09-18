"""add ScriptIR production authority envelope fields"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "o8i9j0k1l2m3"
down_revision = "n7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("script_ir_versions")}
    for name, type_, default in (
        ("authority_envelope_json", sa.Text(), "{}"),
        ("qualification_state", sa.String(), "STRUCTURALLY_VALID"),
        ("stale_status", sa.String(), "UNKNOWN"),
        ("stale_reasons", sa.Text(), "[]"),
    ):
        if name not in columns:
            op.add_column("script_ir_versions", sa.Column(name, type_, nullable=False, server_default=default))


def downgrade() -> None:
    op.drop_column("script_ir_versions", "stale_reasons")
    op.drop_column("script_ir_versions", "stale_status")
    op.drop_column("script_ir_versions", "qualification_state")
    op.drop_column("script_ir_versions", "authority_envelope_json")
