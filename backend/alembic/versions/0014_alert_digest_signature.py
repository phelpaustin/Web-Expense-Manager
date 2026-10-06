"""remember the last successfully sent alert digest

Revision ID: 0014_alert_digest_signature
Revises: 0013_recurring_calendar_anchor
Create Date: 2026-10-06
"""
import sqlalchemy as sa

from alembic import op

revision = "0014_alert_digest_signature"
down_revision = "0013_recurring_calendar_anchor"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "alert_digest_signature" not in columns:
        op.add_column("users", sa.Column("alert_digest_signature", sa.String(length=64), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "alert_digest_signature" in columns:
        op.drop_column("users", "alert_digest_signature")
