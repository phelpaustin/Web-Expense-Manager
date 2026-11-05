"""drop_count_bills_as_spending

New bills now always count as spending straight away, so the per-user switch is gone.

Idempotent: a fresh database built from the models never had the column.

Revision ID: 0032_drop_count_bills
Revises: 0031_dismissed_duplicates
Create Date: 2026-11-05
"""
import sqlalchemy as sa

from alembic import op

revision = "0032_drop_count_bills"
down_revision = "0031_dismissed_duplicates"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    insp = sa.inspect(op.get_bind())
    return insp.has_table("user_options") and any(c["name"] == "count_bills_as_spending" for c in insp.get_columns("user_options"))


def upgrade():
    if _has_column():
        with op.batch_alter_table("user_options") as batch_op:
            batch_op.drop_column("count_bills_as_spending")


def downgrade():
    if not _has_column():
        with op.batch_alter_table("user_options") as batch_op:
            batch_op.add_column(
                sa.Column("count_bills_as_spending", sa.Boolean(), nullable=False, server_default=sa.true())
            )
