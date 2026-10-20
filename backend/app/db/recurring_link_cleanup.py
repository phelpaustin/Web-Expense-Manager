"""Best-effort repair: link past expenses to the recurring template that (almost certainly) posted them.

Expenses posted by a recurring template now carry `recurring_template_id`, but those posted
before that existed have no link, so they would all read as everyday spending. A template
posts expenses with a very particular shape (its item as the description, its category,
amount and currency, and nothing else filled in), so this links an expense to a template only when:

  - it matches the template on item, category, amount and currency (case and spacing aside),
    has no shop, brand or subcategory, a quantity of 1, the default unit, belongs to no bill or
    shared space, and is dated no later than the template's last application;
  - at least MIN_MATCHES expenses match (a template repeats; one coincidence is not evidence);
  - no other template matches the same expense (two identical templates can't be told apart).

This is a heuristic, not a record: an identical expense you typed by hand several times is
indistinguishable and will be linked too. Anything uncertain is left unlinked (everyday).
Safe to run again: only expenses without a link are considered.
"""
import sqlalchemy as sa

from app.db import models

MIN_MATCHES = 2
_CHUNK = 500  # keep IN (...) lists well under SQLite's variable limit


def _clean(column):
    return sa.func.lower(sa.func.trim(column))


def link_recurring_expenses(conn) -> int:
    """Link matching past expenses to their templates on `conn`; returns how many were linked."""
    templates, expenses = models.RecurringTemplate.__table__, models.Expense.__table__
    matches: dict[int, list[int]] = {}  # template id -> expense ids
    claimed: dict[int, set[int]] = {}  # expense id -> template ids that match it

    for t in conn.execute(sa.select(templates).where(templates.c.last_applied.is_not(None))):
        ids = [
            row.id
            for row in conn.execute(
                sa.select(expenses.c.id).where(
                    expenses.c.user_id == t.user_id,
                    expenses.c.recurring_template_id.is_(None),
                    _clean(expenses.c.description) == t.item.strip().lower(),
                    _clean(expenses.c.category) == (t.category or "Recurring").strip().lower(),
                    expenses.c.amount == t.amount,
                    expenses.c.currency == t.currency,
                    expenses.c.date <= t.last_applied,
                    sa.func.trim(expenses.c.shop) == "",
                    sa.func.trim(expenses.c.brand) == "",
                    sa.func.trim(expenses.c.subcategory) == "",
                    expenses.c.quantity == 1,
                    expenses.c.unit == "Count",
                    expenses.c.source_bill_id.is_(None),
                    expenses.c.group_id.is_(None),
                    expenses.c.bill_total_only.is_(False),
                )
            )
        ]
        matches[t.id] = ids
        for expense_id in ids:
            claimed.setdefault(expense_id, set()).add(t.id)

    linked = 0
    for template_id, ids in matches.items():
        mine = [i for i in ids if claimed[i] == {template_id}]
        if len(mine) < MIN_MATCHES:
            continue
        for start in range(0, len(mine), _CHUNK):
            chunk = mine[start:start + _CHUNK]
            linked += conn.execute(
                sa.update(expenses).where(expenses.c.id.in_(chunk)).values(recurring_template_id=template_id)
            ).rowcount
    return linked
