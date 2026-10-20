"""import_profiles: saved bank-statement mappings

A person's own "this is how my bank's file maps" record, found again by the file's header layout.

Idempotent: a fresh database already got the table from 0001 (built from the models).

Revision ID: 0027_import_profiles
Revises: 0026_expense_recurring_link
Create Date: 2026-10-20
"""
import sqlalchemy as sa

from alembic import op

revision = "0027_import_profiles"
down_revision = "0026_expense_recurring_link"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("import_profiles"):
        return
    op.create_table(
        "import_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_import_profile_user_name"),
    )
    op.create_index("ix_import_profiles_id", "import_profiles", ["id"])
    op.create_index("ix_import_profiles_user_id", "import_profiles", ["user_id"])
    op.create_index("ix_import_profiles_signature", "import_profiles", ["signature"])


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("import_profiles"):
        op.drop_table("import_profiles")
