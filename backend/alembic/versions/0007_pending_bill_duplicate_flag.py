"""Add pending_bills.possible_duplicate for bulk-import duplicate flagging.

Revision ID: 0007_pending_bill_duplicate_flag
Revises: 0006_permission_tiers
Create Date: 2026-09-06
"""
import sqlalchemy as sa

from alembic import op

revision = "0007_pending_bill_duplicate_flag"
down_revision = "0006_permission_tiers"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("pending_bills") and "possible_duplicate" not in _columns(insp, "pending_bills"):
        op.add_column(
            "pending_bills",
            sa.Column("possible_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    op.drop_column("pending_bills", "possible_duplicate")
