"""per-user budget-alert digest opt-out

Adds `alert_digest_enabled` (default true) to user_options so a user can unsubscribe
from the daily digest email. Existing users keep getting it until they opt out.

Idempotent: on a fresh database 0001 already created the column from the models.

Revision ID: 0021_alert_digest_enabled
Revises: 0020_rescue_orphaned_expenses
Create Date: 2026-10-15
"""
import sqlalchemy as sa

from alembic import op

revision = "0021_alert_digest_enabled"
down_revision = "0020_rescue_orphaned_expenses"
branch_labels = None
depends_on = None


def _columns(insp) -> set:
    return {c["name"] for c in insp.get_columns("user_options")} if insp.has_table("user_options") else set()


def upgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("user_options") and "alert_digest_enabled" not in _columns(insp):
        op.add_column(
            "user_options",
            sa.Column("alert_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "alert_digest_enabled" not in _columns(insp):
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("user_options") as batch_op:
            batch_op.drop_column("alert_digest_enabled")
    else:
        op.drop_column("user_options", "alert_digest_enabled")
