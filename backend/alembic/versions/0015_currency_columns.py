"""per-record currencies + historical FX rate cache

Adds a `currency` column to budgets, income, recurring_templates, pending_bills
and manual_bills (backfilled from the owner's base currency), sets the currency
of existing non-trip spaces to their owner's base currency, and creates the
`fx_rates` cache table.

Idempotent: on a fresh database 0001 already created everything from the
current models, so every step checks before acting.

Revision ID: 0015_currency_columns
Revises: 0014_alert_digest_signature
Create Date: 2026-10-08
"""
import sqlalchemy as sa

from alembic import op

revision = "0015_currency_columns"
down_revision = "0014_alert_digest_signature"
branch_labels = None
depends_on = None

_TABLES = ["budgets", "income", "recurring_templates", "pending_bills", "manual_bills"]


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    first_run = not insp.has_table("fx_rates")

    if first_run:
        op.create_table(
            "fx_rates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rate_date", sa.Date(), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("rate", sa.Numeric(20, 8), nullable=False),
            sa.UniqueConstraint("rate_date", "currency", name="uq_fx_date_currency"),
        )
        op.create_index("ix_fx_rates_id", "fx_rates", ["id"])

    for table in _TABLES:
        if not insp.has_table(table) or "currency" in _columns(insp, table):
            continue
        # Temporary default so the NOT NULL column can be added to populated tables.
        op.add_column(
            table,
            sa.Column("currency", sa.String(), nullable=False, server_default=sa.text("'SEK'")),
        )
        op.execute(
            sa.text(
                f"UPDATE {table} SET currency = COALESCE("
                f"(SELECT base_currency FROM user_options WHERE user_options.user_id = {table}.user_id), "
                "'SEK')"
            )
        )
        # Drop the temporary default so a writer that forgets currency fails loudly.
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(
                    "currency", existing_type=sa.String(), existing_nullable=False, server_default=None
                )
        else:
            op.alter_column(table, "currency", existing_type=sa.String(), server_default=None)

    # Non-trip spaces had the generic 'SEK' column default; use the owner's base currency.
    if first_run and insp.has_table("groups") and "currency" in _columns(insp, "groups"):
        op.execute(
            sa.text(
                'UPDATE "groups" SET currency = COALESCE('
                '(SELECT base_currency FROM user_options WHERE user_options.user_id = "groups".owner_id), '
                "'SEK') WHERE space_type <> 'trip'"
            )
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _TABLES:
        if "currency" not in _columns(insp, table):
            continue
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column("currency")
        else:
            op.drop_column(table, "currency")
    if insp.has_table("fx_rates"):
        op.drop_table("fx_rates")
