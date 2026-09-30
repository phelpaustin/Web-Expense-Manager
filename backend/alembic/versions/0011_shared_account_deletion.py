"""allow shared records to survive account deletion

Revision ID: 0011_shared_account_deletion
Revises: 0010_session_version
Create Date: 2026-09-30
"""
import sqlalchemy as sa

from alembic import op

revision = "0011_shared_account_deletion"
down_revision = "0010_session_version"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("expenses"):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("expenses") as batch_op:
                batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        else:
            op.alter_column("expenses", "user_id", existing_type=sa.Integer(), nullable=True)

    if inspector.has_table("groups"):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("groups") as batch_op:
                batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=True)
        else:
            op.alter_column("groups", "owner_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("groups"):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("groups") as batch_op:
                batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        else:
            op.alter_column("groups", "owner_id", existing_type=sa.Integer(), nullable=False)

    if inspector.has_table("expenses"):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("expenses") as batch_op:
                batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        else:
            op.alter_column("expenses", "user_id", existing_type=sa.Integer(), nullable=False)