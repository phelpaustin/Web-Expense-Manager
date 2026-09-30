"""add password reset token versioning

Revision ID: 0009_password_reset_version
Revises: 0008_numeric_money
Create Date: 2026-09-30
"""
import sqlalchemy as sa

from alembic import op

revision = "0009_password_reset_version"
down_revision = "0008_numeric_money"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "password_reset_version" not in columns:
        op.add_column(
            "users",
            sa.Column("password_reset_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("users") and "password_reset_version" in {
        column["name"] for column in inspector.get_columns("users")
    }:
        op.drop_column("users", "password_reset_version")