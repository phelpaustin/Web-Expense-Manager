"""expenses: covers_from / covers_to, the days of a trip an expense covers

A stay paid on one day can span several trip days; these two dates say which, so the Trips page
can show the cost day by day. Both null means "the day it was paid".

Idempotent: a fresh database already got the columns from 0001 (built from the models).

Revision ID: 0029_expense_trip_days
Revises: 0028_drop_manual_bills
Create Date: 2026-10-27
"""
import sqlalchemy as sa

from alembic import op

revision = "0029_expense_trip_days"
down_revision = "0028_drop_manual_bills"
branch_labels = None
depends_on = None

_COLUMNS = ("covers_from", "covers_to")


def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("expenses")}
    for name in _COLUMNS:
        if name not in existing:
            op.add_column("expenses", sa.Column(name, sa.Date(), nullable=True))


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("expenses")}
    present = [n for n in _COLUMNS if n in existing]
    if present:
        with op.batch_alter_table("expenses") as batch_op:
            for name in present:
                batch_op.drop_column(name)
