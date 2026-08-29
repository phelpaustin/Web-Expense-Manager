"""add groups, group_members, group_invites + expenses.group_id (idempotent)

Revision ID: 0003_groups
Revises: 0002_trips
Create Date: 2026-08-29
"""
import sqlalchemy as sa

from alembic import op

revision = "0003_groups"
down_revision = "0002_trips"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()

    # Creates the new group tables if missing; no-op for tables that already exist.
    from app.db.database import Base
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=bind)

    insp = sa.inspect(bind)
    if insp.has_table("expenses") and "group_id" not in _columns(insp, "expenses"):
        op.add_column("expenses", sa.Column("group_id", sa.Integer(), nullable=True))


def downgrade():
    pass
