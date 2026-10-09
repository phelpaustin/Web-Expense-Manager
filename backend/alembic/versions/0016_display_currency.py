"""per-user display currency

Adds a nullable `display_currency` to user_options. NULL means "follow the base
currency", so existing users see no change and nothing needs backfilling.

Idempotent: on a fresh database 0001 already created the column from the
current models.

Revision ID: 0016_display_currency
Revises: 0015_currency_columns
Create Date: 2026-10-09
"""
import sqlalchemy as sa

from alembic import op

revision = "0016_display_currency"
down_revision = "0015_currency_columns"
branch_labels = None
depends_on = None


def _columns(insp) -> set:
    return {c["name"] for c in insp.get_columns("user_options")} if insp.has_table("user_options") else set()


def upgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("user_options") and "display_currency" not in _columns(insp):
        op.add_column("user_options", sa.Column("display_currency", sa.String(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "display_currency" not in _columns(insp):
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("user_options") as batch_op:
            batch_op.drop_column("display_currency")
    else:
        op.drop_column("user_options", "display_currency")
