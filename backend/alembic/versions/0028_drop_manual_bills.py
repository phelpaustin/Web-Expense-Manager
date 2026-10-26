"""drop manual_bills: the old manual ledger has no screen and no API any more

Manual ledger bills were copied into the Bills list by 0017 and the ledger has had no screen since.
The table is dropped only when it is EMPTY. If any row is left (for example one created through the
API after 0017 copied the rest), the table is kept as it is and a warning is logged, so nothing is
ever deleted that somebody might still want.

Idempotent: a fresh database no longer creates the table (it is not a model any more).

Revision ID: 0028_drop_manual_bills
Revises: 0027_import_profiles
Create Date: 2026-10-26
"""
import sys

import sqlalchemy as sa

from alembic import op

revision = "0028_drop_manual_bills"
down_revision = "0027_import_profiles"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("manual_bills"):
        return
    rows = bind.execute(sa.text("SELECT count(*) FROM manual_bills")).scalar()
    if rows:
        # Printed, not logged: alembic's logging is not configured here, and this must be seen.
        print(
            f"manual_bills still has {rows} row(s), so the table was kept. Look at them with "
            "`select * from manual_bills;` and drop the table by hand once they are not needed.",
            file=sys.stderr,
        )
        return
    op.drop_table("manual_bills")


def downgrade():
    if sa.inspect(op.get_bind()).has_table("manual_bills"):
        return
    op.create_table(
        "manual_bills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shop", sa.String(), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        sa.Column("currency", sa.String(), nullable=False),
    )
    op.create_index("ix_manual_bills_id", "manual_bills", ["id"])
    op.create_index("ix_manual_bills_user_id", "manual_bills", ["user_id"])
    op.create_index("ix_manual_bills_date", "manual_bills", ["date"])
