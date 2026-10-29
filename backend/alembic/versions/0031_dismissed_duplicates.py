"""dismissed_duplicates

Groups of lookalike entries a user has said are not duplicates, so the "Entered twice?" list can
leave them out.

Idempotent: a fresh database already got the table from 0001 (built from the models).

Revision ID: 0031_dismissed_duplicates
Revises: 0030_savings_goals
Create Date: 2026-10-29
"""
import sqlalchemy as sa

from alembic import op

revision = "0031_dismissed_duplicates"
down_revision = "0030_savings_goals"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("dismissed_duplicates"):
        return
    op.create_table(
        "dismissed_duplicates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_dismissed_duplicate_user_key"),
    )
    op.create_index("ix_dismissed_duplicates_id", "dismissed_duplicates", ["id"])
    op.create_index("ix_dismissed_duplicates_user_id", "dismissed_duplicates", ["user_id"])


def downgrade():
    if sa.inspect(op.get_bind()).has_table("dismissed_duplicates"):
        op.drop_table("dismissed_duplicates")
