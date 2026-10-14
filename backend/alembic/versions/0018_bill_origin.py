"""bills made from expenses: origin + origin_key

Every expense should show up on the Bills page however it was entered. Expenses that are not
part of a bill yet are adopted into "derived" bills (origin = 'expenses') when the Bills or
Expenses page loads, which also covers all existing expenses. This migration only adds the
columns and the index that makes adopting safe under concurrent requests; no data is touched.

Downgrade removes the derived bills again (their expenses are kept, just unlinked), except
derived bills that have a receipt attached: those stay as ordinary bills so no receipt is lost.

Revision ID: 0018_bill_origin
Revises: 0017_bill_status_links
Create Date: 2026-10-11
"""
import sqlalchemy as sa

from alembic import op

revision = "0018_bill_origin"
down_revision = "0017_bill_status_links"
branch_labels = None
depends_on = None

_INDEX = "uq_pending_bills_origin_key"


def _columns(insp) -> set:
    return {c["name"] for c in insp.get_columns("pending_bills")} if insp.has_table("pending_bills") else set()


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("pending_bills"):
        return
    cols = _columns(insp)
    if "origin" not in cols:
        op.add_column("pending_bills", sa.Column("origin", sa.String(), nullable=True))
    if "origin_key" not in cols:
        op.add_column("pending_bills", sa.Column("origin_key", sa.String(), nullable=True))
    if _INDEX not in {i["name"] for i in insp.get_indexes("pending_bills")}:
        op.create_index(
            _INDEX,
            "pending_bills",
            ["user_id", "origin_key"],
            unique=True,
            sqlite_where=sa.text("origin_key IS NOT NULL"),
            postgresql_where=sa.text("origin_key IS NOT NULL"),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = _columns(insp)
    if "origin" in cols:
        doomed = (
            "SELECT id FROM pending_bills WHERE origin = 'expenses' "
            "AND id NOT IN (SELECT pending_bill_id FROM receipts)"
        )
        op.execute(sa.text(f"UPDATE expenses SET source_bill_id = NULL WHERE source_bill_id IN ({doomed})"))
        op.execute(sa.text(f"DELETE FROM pending_bills WHERE id IN ({doomed})"))
    if _INDEX in {i["name"] for i in insp.get_indexes("pending_bills")}:
        op.drop_index(_INDEX, table_name="pending_bills")
    for col in ("origin_key", "origin"):
        if col in cols:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("pending_bills") as batch_op:
                    batch_op.drop_column(col)
            else:
                op.drop_column("pending_bills", col)
