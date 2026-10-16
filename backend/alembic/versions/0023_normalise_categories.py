"""make category spelling consistent per user ("Milk"/"milk"/"MILK" -> one)

Revision ID: 0023_normalise_categories
Revises: 0022_name_aliases
Create Date: 2026-10-16
"""
from alembic import op

revision = "0023_normalise_categories"
down_revision = "0022_name_aliases"
branch_labels = None
depends_on = None


def upgrade():
    from app.db.category_cleanup import normalise_categories

    normalise_categories(op.get_bind())


def downgrade():
    # The old spellings are not recorded, so this cannot be undone.
    pass
