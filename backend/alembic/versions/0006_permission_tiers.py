"""Permission tiers: group_invites.role, and migrate legacy 'member' -> 'editor' (idempotent).

Revision ID: 0006_permission_tiers
Revises: 0005_nested_trip_spaces
Create Date: 2026-08-29
"""
import sqlalchemy as sa

from alembic import op

revision = "0006_permission_tiers"
down_revision = "0005_nested_trip_spaces"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("group_invites") and "role" not in _columns(insp, "group_invites"):
        op.add_column(
            "group_invites",
            sa.Column("role", sa.String(), nullable=False, server_default=sa.text("'editor'")),
        )

    # The old binary owner/member model used the literal role "member"; promote
    # those to "editor" (write access), matching what they could already do.
    if insp.has_table("group_members"):
        bind.execute(sa.text("UPDATE group_members SET role = 'editor' WHERE role = 'member'"))


def downgrade():
    pass
