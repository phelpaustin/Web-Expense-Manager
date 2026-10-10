"""link expenses to the bills they came from; total-only bills; bill setting

* expenses.source_bill_id  - the bill an expense was created from (nullable, SET NULL on delete)
* expenses.bill_total_only - the single "Record total" placeholder expense of a bill
* user_options.count_bills_as_spending - record new bills as total-only straight away (default on)

Data steps, run once when the columns are first added:

* Old "Itemise" clicks created one "Bills" expense per bill and marked the bill itemised, with
  no link between them. Each such bill that matches exactly ONE expense (same user, date,
  amount, currency and description) is linked to it and becomes "total_only", so it can be
  itemised later. Ambiguous matches are left alone.
* Manual ledger bills (manual_bills) are copied into the unified bill list as "pending"
  bills, flagged as possible duplicates when an identical expense already exists. The
  manual_bills table itself is left untouched.

Idempotent: on a fresh database 0001 already created everything from the current models.

Revision ID: 0017_bill_status_links
Revises: 0016_display_currency
Create Date: 2026-10-10
"""
import sqlalchemy as sa

from alembic import op

revision = "0017_bill_status_links"
down_revision = "0016_display_currency"
branch_labels = None
depends_on = None


def _columns(insp, table) -> set:
    return {c["name"] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    first_run = "source_bill_id" not in _columns(insp, "expenses")

    if first_run:
        if bind.dialect.name == "sqlite":
            # SQLite can't ALTER in a foreign key (and doesn't enforce them by default),
            # so local databases get the plain column; Postgres gets the real constraint.
            op.add_column("expenses", sa.Column("source_bill_id", sa.Integer(), nullable=True))
        else:
            op.add_column(
                "expenses",
                sa.Column(
                    "source_bill_id",
                    sa.Integer(),
                    sa.ForeignKey("pending_bills.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        op.create_index("ix_expenses_source_bill_id", "expenses", ["source_bill_id"])
    if "bill_total_only" not in _columns(insp, "expenses"):
        op.add_column(
            "expenses",
            sa.Column("bill_total_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if insp.has_table("user_options") and "count_bills_as_spending" not in _columns(insp, "user_options"):
        op.add_column(
            "user_options",
            sa.Column("count_bills_as_spending", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    if first_run:
        _link_old_total_only_expenses(bind)
        _copy_manual_bills(bind)


def _link_old_total_only_expenses(bind):
    bills = bind.execute(
        sa.text("SELECT id, user_id, date, amount, currency, shop FROM pending_bills WHERE status = 'itemised'")
    ).fetchall()
    claimed: set[int] = set()
    for b in bills:
        matches = bind.execute(
            sa.text(
                "SELECT id FROM expenses WHERE user_id = :u AND date = :d AND amount = :a AND currency = :c "
                "AND description = :s AND category = 'Bills' AND source_bill_id IS NULL"
            ),
            {"u": b.user_id, "d": b.date, "a": b.amount, "c": b.currency, "s": b.shop},
        ).fetchall()
        if len(matches) != 1 or matches[0].id in claimed:
            continue  # nothing to link, or ambiguous: leave it alone
        claimed.add(matches[0].id)
        bind.execute(
            sa.text("UPDATE expenses SET source_bill_id = :b, bill_total_only = :t WHERE id = :e"),
            {"b": b.id, "t": True, "e": matches[0].id},
        )
        bind.execute(sa.text("UPDATE pending_bills SET status = 'total_only' WHERE id = :b"), {"b": b.id})


def _copy_manual_bills(bind):
    insp = sa.inspect(bind)
    if not insp.has_table("manual_bills"):
        return
    manual = bind.execute(
        sa.text("SELECT user_id, date, shop, amount, note, currency FROM manual_bills")
    ).fetchall()
    for m in manual:
        has_twin = bind.execute(
            sa.text(
                "SELECT 1 FROM expenses WHERE user_id = :u AND date = :d AND amount = :a AND currency = :c LIMIT 1"
            ),
            {"u": m.user_id, "d": m.date, "a": m.amount, "c": m.currency},
        ).first()
        bind.execute(
            sa.text(
                "INSERT INTO pending_bills (user_id, date, shop, amount, note, status, possible_duplicate, currency) "
                "VALUES (:u, :d, :s, :a, :n, 'pending', :dup, :c)"
            ),
            {
                "u": m.user_id, "d": m.date, "s": m.shop, "a": m.amount,
                "n": m.note or "Manual entry", "dup": bool(has_twin), "c": m.currency,
            },
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "count_bills_as_spending" in _columns(insp, "user_options"):
        _drop_column("user_options", "count_bills_as_spending", bind)
    if "bill_total_only" in _columns(insp, "expenses"):
        _drop_column("expenses", "bill_total_only", bind)
    if "source_bill_id" in _columns(insp, "expenses"):
        op.drop_index("ix_expenses_source_bill_id", table_name="expenses")
        _drop_column("expenses", "source_bill_id", bind)


def _drop_column(table, column, bind):
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column(column)
    else:
        op.drop_column(table, column)
