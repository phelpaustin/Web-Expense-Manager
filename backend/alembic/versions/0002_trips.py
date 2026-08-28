"""add trips table + expenses.trip_id (idempotent)

Revision ID: 0002_trips
Revises: 0001_baseline
Create Date: 2026-08-28
"""
import sqlalchemy as sa

from alembic import op

revision = "0002_trips"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()

    # Creates the new "trips" table if missing; no-op for tables that already exist.
    from app.db.database import Base
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=bind)

    insp = sa.inspect(bind)
    if insp.has_table("expenses") and "trip_id" not in _columns(insp, "expenses"):
        op.add_column("expenses", sa.Column("trip_id", sa.Integer(), nullable=True))


def downgrade():
    pass
