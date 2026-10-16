"""One place that keeps category spelling consistent, however a record is saved.

Expenses, budgets and recurring templates all carry a free-text category. Rather than
trusting every route (create, edit, bulk, import, bills, recurring...) to remember to
normalise it, any such record saved with a category that differs only by case or spacing
from one in the user's category list is corrected to the listed spelling just before it
is written. Categories the list doesn't have yet are left as typed, apart from making
variants inside one save agree.
"""
from collections import Counter, defaultdict

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.db import models
from app.logic.taxonomy import CategoryResolver, category_key, clean_category, find_existing

# Budgets use this in place of a category for the overall budget; it is not a category.
_NOT_A_CATEGORY = {"__total_monthly__"}
_RECORDS = (models.Expense, models.Budget, models.RecurringTemplate)


def _needs_check(obj) -> bool:
    if not isinstance(obj, _RECORDS) or obj.user_id is None or not obj.category:
        return False
    if obj.category in _NOT_A_CATEGORY:
        return False
    state = inspect(obj)
    return state.transient or state.pending or state.attrs.category.history.has_changes()


@event.listens_for(Session, "before_flush")
def _canonicalise_categories(session, flush_context, instances):
    records = [obj for obj in (*session.new, *session.dirty) if _needs_check(obj)]
    if not records:
        return
    by_user: dict[int, list] = defaultdict(list)
    for obj in records:
        by_user[obj.user_id].append(obj)

    with session.no_autoflush:
        for user_id, objs in by_user.items():
            listed = session.query(models.UserOptions.categories).filter(models.UserOptions.user_id == user_id).scalar() or []
            # Spellings the list doesn't know yet are variants of each other within this save:
            # the most used wins, then alphabetical ("Milk" before "milk").
            fresh: dict[str, Counter] = defaultdict(Counter)
            for obj in objs:
                cleaned = clean_category(obj.category)
                if find_existing(listed, cleaned) is None:
                    fresh[category_key(cleaned)][cleaned] += 1
            chosen = [min(counts, key=lambda sp: (-counts[sp], sp)) for counts in fresh.values()]
            resolver = CategoryResolver([*listed, *chosen])
            for obj in objs:
                resolved = resolver.resolve(obj.category)
                if obj.category != resolved:
                    obj.category = resolved
