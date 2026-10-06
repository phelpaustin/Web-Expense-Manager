"""require verified email ownership for new password sign-ups

Revision ID: 0012_email_verification
Revises: 0011_shared_account_deletion
Create Date: 2026-10-06
"""
import sqlalchemy as sa

from alembic import op

revision = "0012_email_verification"
down_revision = "0011_shared_account_deletion"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "email_verified" not in columns:
        op.add_column(
            "users",
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "email_verification_version" not in columns:
        op.add_column(
            "users",
            sa.Column("email_verification_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "email_verification_version" in columns:
        op.drop_column("users", "email_verification_version")
    if "email_verified" in columns:
        op.drop_column("users", "email_verified")
