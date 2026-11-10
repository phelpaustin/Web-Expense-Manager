"""ignored_subscriptions

Names the user marked "not a subscription" in the subscription finder.

Idempotent: a fresh database already got the table from 0001 (built from the models).

Revision ID: 0034_ignored_subscriptions
Revises: 0033_sign_in_events
Create Date: 2026-11-10
"""
import sqlalchemy as sa

from alembic import op

revision = "0034_ignored_subscriptions"
down_revision = "0033_sign_in_events"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("ignored_subscriptions"):
        return
    op.create_table(
        "ignored_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_ignored_subscription_user_key"),
    )
    op.create_index("ix_ignored_subscriptions_id", "ignored_subscriptions", ["id"])
    op.create_index("ix_ignored_subscriptions_user_id", "ignored_subscriptions", ["user_id"])


def downgrade():
    if sa.inspect(op.get_bind()).has_table("ignored_subscriptions"):
        op.drop_table("ignored_subscriptions")
