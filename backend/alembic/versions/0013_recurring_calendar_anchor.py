"""preserve calendar anchors for recurring schedules

Revision ID: 0013_recurring_calendar_anchor
Revises: 0012_email_verification
Create Date: 2026-10-06
"""
import sqlalchemy as sa

from alembic import op

revision = "0013_recurring_calendar_anchor"
down_revision = "0012_email_verification"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("recurring_templates"):
        return

    columns = {column["name"] for column in inspector.get_columns("recurring_templates")}
    if "schedule_anchor" not in columns:
        op.add_column("recurring_templates", sa.Column("schedule_anchor", sa.Date(), nullable=True))
        bind.execute(
            sa.text(
                "UPDATE recurring_templates "
                "SET schedule_anchor = last_applied "
                "WHERE schedule_anchor IS NULL AND last_applied IS NOT NULL"
            )
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("recurring_templates"):
        return
    columns = {column["name"] for column in inspector.get_columns("recurring_templates")}
    if "schedule_anchor" in columns:
        op.drop_column("recurring_templates", "schedule_anchor")
