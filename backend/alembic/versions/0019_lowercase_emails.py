"""lowercase email addresses

Emails are now compared case-insensitively. This lowercases stored addresses so
"Alice@Example.com" and "alice@example.com" are one identity.

Accounts that already exist twice, differing only by case, cannot be merged
automatically (each may own data), so those rows are left unchanged; the app
still resolves them (lookups match on lower(email), oldest account first).
Downgrade is a no-op: the original capitalisation is not recoverable.

Revision ID: 0019_lowercase_emails
Revises: 0018_bill_origin
Create Date: 2026-10-15
"""
import sqlalchemy as sa

from alembic import op

revision = "0019_lowercase_emails"
down_revision = "0018_bill_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("users"):
        bind.execute(
            sa.text(
                "UPDATE users SET email = lower(email) "
                "WHERE email <> lower(email) AND lower(email) NOT IN ("
                "  SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1)"
            )
        )
    if insp.has_table("group_invites"):
        bind.execute(sa.text("UPDATE group_invites SET email = lower(email) WHERE email <> lower(email)"))


def downgrade() -> None:
    pass
