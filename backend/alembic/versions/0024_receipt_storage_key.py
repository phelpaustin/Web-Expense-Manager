"""receipts: storage_key, and data becomes optional

Receipt files can now live in object storage (Supabase Storage). `storage_key` names the object;
`data` stays for receipts that have not been moved yet (see app/scripts/migrate_receipts.py).

Idempotent: on a fresh database 0001 already built the table from the models.

Revision ID: 0024_receipt_storage_key
Revises: 0023_normalise_categories
Create Date: 2026-10-19
"""
import sqlalchemy as sa

from alembic import op

revision = "0024_receipt_storage_key"
down_revision = "0023_normalise_categories"
branch_labels = None
depends_on = None


def _info(insp):
    cols = {c["name"]: c for c in insp.get_columns("receipts")} if insp.has_table("receipts") else {}
    return cols


def upgrade():
    bind = op.get_bind()
    cols = _info(sa.inspect(bind))
    if not cols:
        return
    if "storage_key" not in cols:
        op.add_column("receipts", sa.Column("storage_key", sa.String(), nullable=True))
    if "data" in cols and not cols["data"]["nullable"]:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("receipts") as batch_op:
                batch_op.alter_column("data", existing_type=sa.LargeBinary(), nullable=True)
        else:
            op.alter_column("receipts", "data", existing_type=sa.LargeBinary(), nullable=True)


def downgrade():
    bind = op.get_bind()
    cols = _info(sa.inspect(bind))
    if not cols:
        return
    moved = bind.execute(sa.text("SELECT count(*) FROM receipts WHERE data IS NULL")).scalar()
    if moved:
        raise RuntimeError(
            f"{moved} receipt(s) live only in object storage; copy them back into the database "
            "before downgrading."
        )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("receipts") as batch_op:
            batch_op.alter_column("data", existing_type=sa.LargeBinary(), nullable=False)
            if "storage_key" in cols:
                batch_op.drop_column("storage_key")
    else:
        op.alter_column("receipts", "data", existing_type=sa.LargeBinary(), nullable=False)
        if "storage_key" in cols:
            op.drop_column("receipts", "storage_key")
