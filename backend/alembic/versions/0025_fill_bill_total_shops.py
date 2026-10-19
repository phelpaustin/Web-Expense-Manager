"""give bills recorded as a single total their shop (it was only in the description)

Revision ID: 0025_fill_bill_total_shops
Revises: 0024_receipt_storage_key
Create Date: 2026-10-19
"""
from alembic import op

revision = "0025_fill_bill_total_shops"
down_revision = "0024_receipt_storage_key"
branch_labels = None
depends_on = None


def upgrade():
    from app.db.bill_shop_cleanup import fill_bill_total_shops

    fill_bill_total_shops(op.get_bind())


def downgrade():
    # The shop is also in the description, so nothing is lost by leaving it filled in.
    pass
