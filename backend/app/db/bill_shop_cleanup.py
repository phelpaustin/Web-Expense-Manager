"""One-time repair: give bills that were recorded as a single total their shop.

Recording a bill as a total used to store the shop name only in the expense's description
and leave `shop` empty, so shop-based features (the scorecard, the shop filter, shop-based
categorisation) saw these as having no shop. For each such expense this fills `shop` from
the bill it came from, or from its description when the bill has since been deleted (the
description was always the bill's shop). Rows that already have a shop are left alone, and
running it again changes nothing.
"""
import sqlalchemy as sa

from app.db import models


def fill_bill_total_shops(conn) -> int:
    """Fill the shop of recorded bill totals on `conn`; returns how many rows were updated."""
    expenses, bills = models.Expense.__table__, models.PendingBill.__table__
    bill_shop = (
        sa.select(sa.func.nullif(sa.func.trim(bills.c.shop), ""))
        .where(bills.c.id == expenses.c.source_bill_id)
        .scalar_subquery()
    )
    result = conn.execute(
        sa.update(expenses)
        .where(
            expenses.c.bill_total_only.is_(True),
            sa.func.trim(expenses.c.shop) == "",
            # nothing to fill in from: leave the row as it is rather than rewrite it every run
            sa.or_(bill_shop.is_not(None), sa.func.trim(expenses.c.description) != ""),
        )
        .values(shop=sa.func.coalesce(bill_shop, sa.func.trim(expenses.c.description)))
    )
    return result.rowcount
