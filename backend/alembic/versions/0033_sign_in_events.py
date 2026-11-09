"""sign_in_events

A short history of sign-ins and failed password attempts per account, shown in Settings.

Idempotent: a fresh database already got the table from 0001 (built from the models).

Revision ID: 0033_sign_in_events
Revises: 0032_drop_count_bills
Create Date: 2026-11-08
"""
import sqlalchemy as sa

from alembic import op

revision = "0033_sign_in_events"
down_revision = "0032_drop_count_bills"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("sign_in_events"):
        return
    op.create_table(
        "sign_in_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=300), nullable=False, server_default=""),
    )
    op.create_index("ix_sign_in_events_id", "sign_in_events", ["id"])
    op.create_index("ix_sign_in_events_user_id", "sign_in_events", ["user_id"])
    op.create_index("ix_sign_in_events_at", "sign_in_events", ["at"])


def downgrade():
    if sa.inspect(op.get_bind()).has_table("sign_in_events"):
        op.drop_table("sign_in_events")
