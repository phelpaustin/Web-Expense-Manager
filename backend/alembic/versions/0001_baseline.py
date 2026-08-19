"""baseline schema (idempotent): create missing tables, add missing columns

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-19
"""
import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()

    # Create any tables that don't exist yet (safe on an already-populated DB).
    from app.db.database import Base
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=bind)

    # Bring older databases up to date by adding any columns they're missing.
    insp = sa.inspect(bind)
    additions = [
        ("users", "name", sa.String(), "''"),
        ("expenses", "subcategory", sa.String(), "''"),
        ("expenses", "quantity", sa.Float(), "1"),
        ("expenses", "unit", sa.String(), "'Count'"),
        ("expenses", "shop", sa.String(), "''"),
        ("expenses", "brand", sa.String(), "''"),
        ("expenses", "currency", sa.String(), "'SEK'"),
        ("expenses", "price_per_unit", sa.Float(), "0"),
        ("user_options", "base_currency", sa.String(), "'SEK'"),
        ("user_options", "shops", sa.JSON(), "'[]'"),
        ("user_options", "budget_period", sa.String(), "'Monthly'"),
        ("user_options", "budget_rollover", sa.Boolean(), "false"),
    ]
    for table, col, coltype, default in additions:
        if insp.has_table(table) and col not in _columns(insp, table):
            op.add_column(
                table,
                sa.Column(col, coltype, nullable=False, server_default=sa.text(default)),
            )


def downgrade():
    pass
