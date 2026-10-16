"""One-time repair: make every user's categories agree on one spelling.

Before categories were case-insensitive, "Milk", "milk" and "MILK" could all exist, which
split budgets and category totals three ways. For each user this keeps one spelling per
category (see taxonomy.preferred_spelling) and rewrites expenses, recurring templates,
budgets and the user's category list to it. Safe to run again: with nothing left to
repair it changes nothing.
"""
from collections import Counter, defaultdict

import sqlalchemy as sa

from app.db import models
from app.logic.taxonomy import category_key, clean_category, preferred_spelling

_TOTAL_BUDGET = "__total_monthly__"


def normalise_categories(conn) -> dict:
    """Repair all users' categories on `conn`; returns how many records were rewritten."""
    expenses, budgets = models.Expense.__table__, models.Budget.__table__
    recurring, options = models.RecurringTemplate.__table__, models.UserOptions.__table__

    used: dict[int, Counter] = defaultdict(Counter)  # user -> spelling -> uses
    for user_id, category, n in conn.execute(
        sa.select(expenses.c.user_id, expenses.c.category, sa.func.count())
        .where(expenses.c.user_id.is_not(None))
        .group_by(expenses.c.user_id, expenses.c.category)
    ):
        if clean_category(category):
            used[user_id][category] += n
    budget_rows = conn.execute(sa.select(budgets.c.id, budgets.c.user_id, budgets.c.category)).all()
    recurring_rows = conn.execute(sa.select(recurring.c.id, recurring.c.user_id, recurring.c.category)).all()
    for _, user_id, category in recurring_rows:
        if clean_category(category):
            used[user_id][category] += 1
    for _, user_id, category in budget_rows:
        if category != _TOTAL_BUDGET and clean_category(category):
            used[user_id][category] += 1
    listed_by_user = {
        r.user_id: (list(r.categories or []), dict(r.subcategories or {}))
        for r in conn.execute(sa.select(options.c.user_id, options.c.categories, options.c.subcategories))
    }

    changed = {"expenses": 0, "recurring": 0, "budgets": 0, "options": 0}
    for user_id in set(used) | set(listed_by_user):
        listed, subs = listed_by_user.get(user_id, ([], {}))
        spellings = Counter(used.get(user_id, {}))
        for name in listed:
            spellings.setdefault(name, 0)
        by_key: dict[str, Counter] = defaultdict(Counter)
        for spelling, n in spellings.items():
            by_key[category_key(spelling)][spelling] = n

        canon: dict[str, str] = {}  # variant spelling -> the one to keep
        for variants in by_key.values():
            keep = preferred_spelling(variants, listed)
            for spelling in variants:
                if spelling != keep:
                    canon[spelling] = keep
        if not canon:
            continue  # this user's spellings already agree

        for variant, keep in canon.items():
            changed["expenses"] += conn.execute(
                sa.update(expenses).where(expenses.c.user_id == user_id, expenses.c.category == variant).values(category=keep)
            ).rowcount
            changed["recurring"] += conn.execute(
                sa.update(recurring).where(recurring.c.user_id == user_id, recurring.c.category == variant).values(category=keep)
            ).rowcount

        # One budget per category: keep the kept spelling's budget, otherwise promote one variant.
        user_budgets = [(bid, cat) for bid, uid, cat in budget_rows if uid == user_id]
        by_target: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for bid, cat in user_budgets:
            by_target[canon.get(cat, cat)].append((bid, cat))
        for target, rows in by_target.items():
            if len(rows) < 2 and rows[0][1] == target:
                continue
            exact = [r for r in rows if r[1] == target]
            keeper = exact[0] if exact else rows[0]
            for bid, _ in rows:
                if bid != keeper[0]:
                    conn.execute(sa.delete(budgets).where(budgets.c.id == bid))
                    changed["budgets"] += 1
            if keeper[1] != target:
                conn.execute(sa.update(budgets).where(budgets.c.id == keeper[0]).values(category=target))
                changed["budgets"] += 1

        if user_id in listed_by_user:
            new_listed = sorted({canon.get(c, c) for c in listed})
            new_subs: dict[str, list] = {}
            for category, entries in subs.items():
                merged = new_subs.setdefault(canon.get(category, category), [])
                merged.extend(e for e in entries if e not in merged)
            conn.execute(sa.update(options).where(options.c.user_id == user_id).values(categories=new_listed, subcategories=new_subs))
            changed["options"] += 1
    return changed
