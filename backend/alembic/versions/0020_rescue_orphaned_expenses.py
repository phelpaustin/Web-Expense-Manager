"""return orphaned expenses to their owners

Before this release, leaving (or being removed from) a space or trip left the person's
expenses tagged to it. They could no longer edit or delete them, and a trip's settlement
counted them with no payer. Going forward those expenses move back to personal on leave;
this migration does the same for the ones already stranded: any expense tagged to a group
its owner is not a member of is made personal again.

Downgrade is a no-op (the old tags are not recoverable, and restoring them would
re-create the problem).

Revision ID: 0020_rescue_orphaned_expenses
Revises: 0019_lowercase_emails
Create Date: 2026-10-15
"""
import sqlalchemy as sa

from alembic import op

revision = "0020_rescue_orphaned_expenses"
down_revision = "0019_lowercase_emails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not (insp.has_table("expenses") and insp.has_table("group_members")):
        return
    bind.execute(
        sa.text(
            "UPDATE expenses SET group_id = NULL "
            "WHERE group_id IS NOT NULL AND user_id IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM group_members gm "
            "  WHERE gm.group_id = expenses.group_id AND gm.user_id = expenses.user_id)"
        )
    )


def downgrade() -> None:
    pass
