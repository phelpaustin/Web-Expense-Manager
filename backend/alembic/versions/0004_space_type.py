"""add groups.space_type (idempotent)

Revision ID: 0004_space_type
Revises: 0003_groups
Create Date: 2026-08-29
"""
import sqlalchemy as sa

from alembic import op

revision = "0004_space_type"
down_revision = "0003_groups"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("groups") and "space_type" not in _columns(insp, "groups"):
        op.add_column(
            "groups",
            sa.Column("space_type", sa.String(), nullable=False, server_default=sa.text("'custom'")),
        )


def downgrade():
    pass
