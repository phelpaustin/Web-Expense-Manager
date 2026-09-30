"""add server-side access-session versioning

Revision ID: 0010_session_version
Revises: 0009_password_reset_version
Create Date: 2026-09-30
"""
import sqlalchemy as sa

from alembic import op

revision = "0010_session_version"
down_revision = "0009_password_reset_version"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "session_version" not in columns:
        op.add_column(
            "users",
            sa.Column("session_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("users") and "session_version" in {
        column["name"] for column in inspector.get_columns("users")
    }:
        op.drop_column("users", "session_version")