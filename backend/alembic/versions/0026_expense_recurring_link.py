"""expenses: recurring_template_id, and a best-effort link for past recurring expenses

Remembers which recurring template posted an expense, so committed spending (rent,
subscriptions) can be told apart from everyday spending. Not a foreign key on purpose:
deleting a template must not turn the payments it already made back into everyday spending.

Idempotent: a fresh database already got the column and its index from 0001 (built from the
models). The backfill is a heuristic; see app/db/recurring_link_cleanup.py.

Revision ID: 0026_expense_recurring_link
Revises: 0025_fill_bill_total_shops
Create Date: 2026-10-20
"""
import sqlalchemy as sa

from alembic import op

revision = "0026_expense_recurring_link"
down_revision = "0025_fill_bill_total_shops"
branch_labels = None
depends_on = None

_INDEX = "ix_expenses_recurring_template_id"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "recurring_template_id" not in {c["name"] for c in insp.get_columns("expenses")}:
        op.add_column("expenses", sa.Column("recurring_template_id", sa.Integer(), nullable=True))
    if _INDEX not in {i["name"] for i in insp.get_indexes("expenses")}:
        op.create_index(_INDEX, "expenses", ["recurring_template_id"])

    from app.db.recurring_link_cleanup import link_recurring_expenses

    link_recurring_expenses(bind)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "recurring_template_id" not in {c["name"] for c in insp.get_columns("expenses")}:
        return
    with op.batch_alter_table("expenses") as batch_op:
        if _INDEX in {i["name"] for i in insp.get_indexes("expenses")}:
            batch_op.drop_index(_INDEX)
        batch_op.drop_column("recurring_template_id")
