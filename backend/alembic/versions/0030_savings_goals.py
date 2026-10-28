"""savings_goals and savings_contributions

A goal (name, target amount, optional target date) and the deposits/withdrawals made towards it.

Idempotent: a fresh database already got the tables from 0001 (built from the models).

Revision ID: 0030_savings_goals
Revises: 0029_expense_trip_days
Create Date: 2026-10-28
"""
import sqlalchemy as sa

from alembic import op

revision = "0030_savings_goals"
down_revision = "0029_expense_trip_days"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("savings_goals"):
        op.create_table(
            "savings_goals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(), nullable=False),
            sa.Column("target_date", sa.Date(), nullable=True),
            sa.Column("note", sa.String(), nullable=False, server_default=""),
        )
        op.create_index("ix_savings_goals_id", "savings_goals", ["id"])
        op.create_index("ix_savings_goals_user_id", "savings_goals", ["user_id"])
    if not insp.has_table("savings_contributions"):
        op.create_table(
            "savings_contributions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("goal_id", sa.Integer(), sa.ForeignKey("savings_goals.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("note", sa.String(), nullable=False, server_default=""),
        )
        op.create_index("ix_savings_contributions_id", "savings_contributions", ["id"])
        op.create_index("ix_savings_contributions_goal_id", "savings_contributions", ["goal_id"])
        op.create_index("ix_savings_contributions_user_id", "savings_contributions", ["user_id"])


def downgrade():
    insp = sa.inspect(op.get_bind())
    for table in ("savings_contributions", "savings_goals"):    # the contributions point at the goals
        if insp.has_table(table):
            op.drop_table(table)
