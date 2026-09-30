"""store monetary values as fixed-precision numerics

Revision ID: 0008_numeric_money
Revises: 0007_pending_bill_duplicate_flag
Create Date: 2026-09-30
"""
import sqlalchemy as sa

from alembic import op

revision = "0008_numeric_money"
down_revision = "0007_pending_bill_duplicate_flag"
branch_labels = None
depends_on = None


_MONEY_COLUMNS = {
    "expenses": {"amount": (12, 2), "price_per_unit": (12, 4)},
    "budgets": {"amount": (12, 2)},
    "income": {"amount": (12, 2)},
    "recurring_templates": {"amount": (12, 2)},
    "pending_bills": {"amount": (12, 2)},
    "manual_bills": {"amount": (12, 2)},
    "trips": {"budget": (12, 2)},
    "groups": {"budget": (12, 2)},
}


def _columns(insp, table) -> set:
    if not insp.has_table(table):
        return set()
    return {column["name"] for column in insp.get_columns(table)}


def _numeric(precision: int, scale: int) -> sa.Numeric:
    return sa.Numeric(precision, scale)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    for table, columns in _MONEY_COLUMNS.items():
        present = _columns(insp, table)
        columns_to_change = {name: scale for name, scale in columns.items() if name in present}
        if not columns_to_change:
            continue

        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                for name, (precision, scale) in columns_to_change.items():
                    batch_op.alter_column(
                        name,
                        existing_type=sa.Float(),
                        type_=_numeric(precision, scale),
                    )
        else:
            for name, (precision, scale) in columns_to_change.items():
                op.alter_column(
                    table,
                    name,
                    existing_type=sa.Float(),
                    type_=_numeric(precision, scale),
                    postgresql_using=f"{name}::numeric({precision},{scale})",
                )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    for table, columns in _MONEY_COLUMNS.items():
        present = _columns(insp, table)
        columns_to_change = {name: scale for name, scale in columns.items() if name in present}
        if not columns_to_change:
            continue

        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch_op:
                for name in columns_to_change:
                    batch_op.alter_column(name, existing_type=_numeric(*columns[name]), type_=sa.Float())
        else:
            for name in columns_to_change:
                precision, scale = columns[name]
                op.alter_column(
                    table,
                    name,
                    existing_type=_numeric(precision, scale),
                    type_=sa.Float(),
                    postgresql_using=f"{name}::double precision",
                )