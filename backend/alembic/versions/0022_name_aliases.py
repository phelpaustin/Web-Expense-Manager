"""name_aliases table: user-defined item/shop name merges

Revision ID: 0022_name_aliases
Revises: 0021_alert_digest_enabled
Create Date: 2026-10-16
"""
from alembic import op

revision = "0022_name_aliases"
down_revision = "0021_alert_digest_enabled"
branch_labels = None
depends_on = None


def upgrade():
    # Creates the new table if it is missing; a no-op for tables that already exist
    # (a fresh database already got it from 0001, which builds from the models).
    from app.db import models  # noqa: F401
    from app.db.database import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    pass
